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

    def list(self, *, limit: int = 12) -> CommitmentListView:
        document = self._conversation.memory_retriever.memory_store.read_document()
        if document is None:
            return CommitmentListView(observed_at=self._now(), items=())
        engine = self._conversation.temporal_engine
        observed_at = engine.clock.now_utc()
        items = []
        for commitment in document.commitments:
            if commitment.visibility is not Visibility.VISIBLE:
                continue
            domain_status = engine.commitment_status(commitment)
            status = (
                "upcoming"
                if domain_status == "open" and commitment.due_at is not None
                and commitment.due_at.astimezone(timezone.utc) > observed_at
                else domain_status
            )
            items.append(
                CommitmentView(
                    commitment_id=commitment.id,
                    text=commitment.text,
                    status=status,
                    due_at=commitment.due_at,
                    completed_at=commitment.completed_at,
                    can_propose_completion=domain_status == "open",
                )
            )
        rank = {"overdue": 0, "open": 1, "upcoming": 2, "completed": 3, "cancelled": 4}
        items.sort(
            key=lambda item: (
                rank[item.status],
                item.due_at or item.completed_at or self._far_future(),
                item.text.casefold(),
            )
        )
        return CommitmentListView(observed_at=observed_at, items=tuple(items[:limit]))

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

    @staticmethod
    def _far_future():
        from datetime import datetime

        return datetime.max.replace(tzinfo=timezone.utc)
