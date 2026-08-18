"""UI-safe read and explicit proposal boundary for Commitments."""

from __future__ import annotations

from datetime import timezone

from backend.conversation.conversation_service import ConversationService
from backend.memory.memory_models import Visibility

from .contracts import (
    CommitmentListView,
    CommitmentProposalResult,
    CommitmentView,
    MessageView,
    PendingConfirmationView,
)
from .conversation import ConversationApplicationService


class CommitmentApplicationService:
    """Project deterministic Commitment state without owning domain semantics."""

    def __init__(self, *, conversation: ConversationService):
        self._conversation = conversation

    def list(
            self,
            *,
            limit: int | None = 10,
            offset: int = 0,
    ) -> CommitmentListView:
        if offset < 0 or (limit is not None and limit < 1):
            raise ValueError("invalid commitment page")

        document = (
            self._conversation
            .memory_retriever
            .memory_store
            .read_document()
        )

        if document is None:
            return CommitmentListView(
                observed_at=self._now(),
                items=(),
                offset=offset,
            )

        engine = self._conversation.temporal_engine
        observed_at = engine.clock.now_utc()

        rows = []

        for commitment in document.commitments:
            if commitment.visibility is not Visibility.VISIBLE:
                continue

            domain_status = engine.commitment_status(commitment)

            if domain_status in {"completed", "cancelled"}:
                continue

            status = (
                "upcoming"
                if domain_status == "open"
                   and commitment.due_at is not None
                   and commitment.due_at.astimezone(timezone.utc) > observed_at
                else domain_status
            )
            time_bucket = self._time_bucket_for(
                status=status,
                due_at=commitment.due_at,
                observed_at=observed_at,
            )

            rows.append(
                (
                    CommitmentView(
                        commitment_id=commitment.id,
                        text=commitment.text,
                        status=status,
                        time_bucket=time_bucket,
                        due_at=commitment.due_at,
                        completed_at=commitment.completed_at,
                        can_propose_completion=domain_status == "open",
                    ),
                    commitment,
                )
            )

        rows.sort(key=self._sort_key)

        items = [view for view, _ in rows]

        bucket_counts = {
            "fresh_overdue": 0,
            "upcoming": 0,
            "unscheduled": 0,
            "stale_overdue": 0,
        }

        for view in items:
            bucket_counts[view.time_bucket] += 1

        page = (
            items[offset:]
            if limit is None
            else items[offset: offset + limit]
        )

        next_offset = offset + len(page)
        has_more = next_offset < len(items)

        actionable_total = sum(bucket_counts.values())

        return CommitmentListView(
            observed_at=observed_at,
            items=tuple(page),
            offset=offset,
            page_size=(
                max(1, len(page))
                if limit is None
                else limit
            ),
            total=actionable_total,
            actionable_total=actionable_total,
            fresh_overdue_total=bucket_counts["fresh_overdue"],
            upcoming_total=bucket_counts["upcoming"],
            unscheduled_total=bucket_counts["unscheduled"],
            stale_overdue_total=bucket_counts["stale_overdue"],
            has_more=has_more,
            next_offset=next_offset if has_more else None,
        )

    def get(self, commitment_id: str) -> CommitmentView | None:
        return next(
            (
                item
                for item in self.list(limit=None).items
                if item.commitment_id == commitment_id
            ),
            None,
        )

    @staticmethod
    def _time_bucket_for(
            *,
            status,
            due_at,
            observed_at,
    ):
        if status == "overdue" and due_at is not None:
            overdue_seconds = (
                    observed_at
                    - due_at.astimezone(timezone.utc)
            ).total_seconds()

            return (
                "fresh_overdue"
                if overdue_seconds <= 24 * 60 * 60
                else "stale_overdue"
            )

        if status == "upcoming":
            return "upcoming"

        return "unscheduled"

    @staticmethod
    def _sort_key(row):
        view, commitment = row

        if view.time_bucket == "fresh_overdue":
            return (
                0,
                -view.due_at.timestamp(),
                commitment.id,
            )

        if view.time_bucket == "upcoming":
            return (
                1,
                view.due_at.timestamp(),
                commitment.id,
            )

        if view.time_bucket == "unscheduled":
            return (
                2,
                -commitment.created_at.timestamp(),
                commitment.id,
            )

        return (
            3,
            -view.due_at.timestamp(),
            commitment.id,
        )

    def propose_completion(
        self,
        *,
        commitment_id: str,
        conversation_id: str | None,
        project_id: str,
    ) -> CommitmentProposalResult:
        conversation, user, assistant = self._conversation.propose_commitment_completion(
            commitment_id=commitment_id,
            conversation_id=conversation_id,
            project_id=project_id,
        )
        pending = tuple(
            item
            for item in self._conversation.memory_intent_handler.proposal_store.pending_for_conversation(conversation)
            if item.record_type == "commitment"
        )
        if len(pending) != 1:
            raise RuntimeError("completion proposal projection is ambiguous")
        proposal = pending[0]
        payload = proposal.record_payload
        return CommitmentProposalResult(
            conversation_id=conversation,
            user_message=self._message(user),
            assistant_message=self._message(assistant),
            pending_confirmation=PendingConfirmationView(
                proposal_id=proposal.id,
                conversation_id=proposal.conversation_id,
                confirmation_type="commitment_complete",
                title="Отметить обязательство выполненным?",
                subject=str(payload.get("text") or "Обязательство"),
                due_at=payload.get("due_at"),
                created_at=proposal.created_at,
            ),
        )

    def propose_cancellation(
            self,
            *,
            commitment_id: str,
            conversation_id: str | None,
            project_id: str,
    ) -> CommitmentProposalResult:
        conversation, user, assistant = (
            self._conversation.propose_commitment_cancellation(
                commitment_id=commitment_id,
                conversation_id=conversation_id,
                project_id=project_id,
            )
        )

        pending = tuple(
            item
            for item in (
                self._conversation
                .memory_intent_handler
                .proposal_store
                .pending_for_conversation(conversation)
            )
            if item.record_type == "commitment"
        )

        if len(pending) != 1:
            raise RuntimeError("cancellation proposal projection is ambiguous")

        proposal = pending[0]
        payload = proposal.record_payload

        return CommitmentProposalResult(
            conversation_id=conversation,
            user_message=self._message(user),
            assistant_message=self._message(assistant),
            pending_confirmation=PendingConfirmationView(
                proposal_id=proposal.id,
                conversation_id=proposal.conversation_id,
                confirmation_type="commitment_cancel",
                title="Убрать дело как больше не актуальное?",
                subject=str(payload.get("text") or "Обязательство"),
                due_at=payload.get("due_at"),
                created_at=proposal.created_at,
            ),
        )

    @staticmethod
    def _message(message) -> MessageView:
        return MessageView(
            message_id=message.id,
            conversation_id=message.conversation_id,
            role=message.role.value,
            content=ConversationApplicationService._human_content(message.content),
            created_at=message.created_at,
            persisted=True,
        )

    def _now(self):
        return self._conversation.temporal_engine.clock.now_utc()
