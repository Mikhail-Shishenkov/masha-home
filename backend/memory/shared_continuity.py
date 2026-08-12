"""Explicitly confirmed shared history and unfinished conversational threads."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from .memory_models import (
    ContinuityFollowUp,
    ContinuityState,
    FollowUpStatus,
    MemoryDocument,
    RelationshipMemory,
    RelationshipStatus,
    Visibility,
)


def is_readable_continuity_text(value: str) -> bool:
    """Quarantine obvious legacy mojibake without rewriting the stored source."""
    if not value.strip():
        return False
    suspicious = sum(
        "\u00c0" <= character <= "\u00ff" or character in {"Ð", "Ñ"}
        for character in value
    )
    letters = sum(character.isalpha() for character in value)
    return not letters or suspicious / letters < 0.2


def is_legacy_developer_follow_up(follow_up: ContinuityFollowUp) -> bool:
    """Hide migrated implementation backlog from the human shared-history view."""
    return (
        follow_up.id.startswith("followup_migrated_")
        or follow_up.topic in {"next_action", "open_question"}
        or any(marker in follow_up.summary.casefold() for marker in (
            "memory_schema.json", "python-модел", "хранение и поиск памяти",
        ))
    )


class SharedContinuityService:
    """Manage the existing continuity records without inferring or auto-writing them."""

    def __init__(self, repository, *, clock: Callable[[], datetime] | None = None):
        self.repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def relationship_memories(self, *, limit: int = 5) -> tuple[RelationshipMemory, ...]:
        document = self._document()
        visible = (
            item
            for item in document.relationship_memories
            if item.visibility == Visibility.VISIBLE
            and item.status == RelationshipStatus.CURRENT
        )
        return tuple(sorted(visible, key=lambda item: item.created_at, reverse=True)[:limit])

    def open_follow_ups(self) -> tuple[tuple[str, ContinuityFollowUp], ...]:
        document = self._document()
        rows = [
            (state.id, follow_up)
            for state in document.continuity_states
            for follow_up in state.intended_follow_ups
            if follow_up.status == FollowUpStatus.OPEN
            and not is_legacy_developer_follow_up(follow_up)
            and is_readable_continuity_text(follow_up.summary)
            and is_readable_continuity_text(follow_up.reason_to_return)
        ]
        return tuple(sorted(rows, key=lambda row: row[1].priority, reverse=True))

    def quarantined_count(self) -> int:
        document = self._document()
        return sum(
            follow_up.status == FollowUpStatus.OPEN
            and not (
                is_readable_continuity_text(follow_up.summary)
                and is_readable_continuity_text(follow_up.reason_to_return)
            )
            for state in document.continuity_states
            for follow_up in state.intended_follow_ups
        )

    def propose_open_thread(
        self,
        proposal_store,
        *,
        text: str,
        conversation_id: str,
        reason_to_return: str | None = None,
        priority: float = 0.7,
    ):
        """Prepare a continuity change; the repository is untouched until confirmation."""
        from backend.conversation.memory_intent import MemoryProposal, ProposalStatus

        summary = text.strip().rstrip(".")
        if not summary:
            raise ValueError("continuity thread cannot be empty")
        document = self._document()
        now = self._now()
        state = self._relationship_state(document)
        operation = "continuity_create" if state is None else "continuity_update"
        if state is None:
            state = ContinuityState(
                id="continuity_masha_misha",
                relationship_key="masha:misha",
                last_interaction_at=None,
                affective_record_ids=[],
                current_focus=[],
                intended_follow_ups=[],
                based_on_episode_ids=[],
                updated_at=now,
            )
        follow_up = ContinuityFollowUp(
            id=f"followup_{uuid4()}",
            topic=self._topic(summary),
            summary=summary,
            reason_to_return=(reason_to_return or "Вернуться к незавершённому общему разговору").strip(),
            priority=priority,
            status=FollowUpStatus.OPEN,
            source_memory_ids=[],
            revisit_after=None,
        )
        replacement = state.model_copy(
            update={
                "intended_follow_ups": [*state.intended_follow_ups, follow_up],
                "updated_at": now,
            }
        )
        proposal = MemoryProposal(
            id=str(uuid4()),
            conversation_id=conversation_id,
            record_type="continuity_state",
            record_payload=replacement.model_dump(mode="json"),
            created_at=now,
            status=ProposalStatus.PENDING,
            operation=operation,
            target_record_id=None if operation == "continuity_create" else state.id,
        )
        return proposal_store.create(proposal)

    def propose_resolve_thread(
        self,
        proposal_store,
        *,
        query: str,
        conversation_id: str,
    ):
        """Prepare resolution of one unambiguous thread; no Commitment is changed."""
        from backend.conversation.memory_intent import MemoryProposal, ProposalStatus

        needle = query.strip().casefold()
        if not needle:
            raise ValueError("continuity thread query cannot be empty")
        document = self._document()
        matches = [
            (state, follow_up)
            for state in document.continuity_states
            for follow_up in state.intended_follow_ups
            if follow_up.status == FollowUpStatus.OPEN
            and (
                needle == follow_up.id.casefold()
                or needle in follow_up.summary.casefold()
                or needle in follow_up.topic.casefold()
            )
        ]
        if not matches:
            raise LookupError("open continuity thread not found")
        if len(matches) != 1:
            raise ValueError("continuity thread query is ambiguous")
        state, selected = matches[0]
        now = self._now()
        follow_ups = [
            item.model_copy(update={"status": FollowUpStatus.RESOLVED})
            if item.id == selected.id
            else item
            for item in state.intended_follow_ups
        ]
        replacement = state.model_copy(
            update={"intended_follow_ups": follow_ups, "updated_at": now}
        )
        return proposal_store.create(
            MemoryProposal(
                id=str(uuid4()),
                conversation_id=conversation_id,
                record_type="continuity_state",
                record_payload=replacement.model_dump(mode="json"),
                created_at=now,
                status=ProposalStatus.PENDING,
                operation="continuity_update",
                target_record_id=state.id,
            )
        )

    def confirm_proposal(self, proposal, proposal_store) -> ContinuityState:
        """Apply one pending continuity proposal and leave all other memory untouched."""
        from backend.conversation.memory_intent import ProposalStatus

        if proposal.status != ProposalStatus.PENDING:
            raise ValueError("continuity proposal is not pending")
        if proposal.operation not in {"continuity_create", "continuity_update"}:
            raise ValueError("not a continuity proposal")
        replacement = ContinuityState.model_validate(proposal.record_payload)
        document = self._document()
        payload = document.model_dump(mode="json")
        positions = {
            item["id"]: index for index, item in enumerate(payload["continuity_states"])
        }
        if proposal.operation == "continuity_create":
            if replacement.id in positions:
                raise ValueError("continuity state already exists")
            payload["continuity_states"].append(replacement.model_dump(mode="json"))
        else:
            if proposal.target_record_id != replacement.id:
                raise ValueError("continuity update must retain the state id")
            if replacement.id not in positions:
                raise KeyError("continuity state not found")
            payload["continuity_states"][positions[replacement.id]] = replacement.model_dump(mode="json")
        self.repository.replace_document(
            MemoryDocument.model_validate(payload),
            action=proposal.operation,
            audit_payload={
                "who": "misha",
                "operation": proposal.operation,
                "proposal_id": proposal.id,
                "record_id": replacement.id,
            },
        )
        proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
        return replacement

    def render(self) -> str:
        moments = self.relationship_memories()
        threads = self.open_follow_ups()
        lines = ["Что между нами продолжается"]
        if moments:
            lines += ["", "Наша подтверждённая история:"]
            for index, memory in enumerate(moments, 1):
                lines.append(f"{index}. {self.relationship_text(memory)}")
        else:
            lines += ["", "Подтверждённых общих моментов пока нет."]
        if threads:
            lines += ["", "Открытые нити:"]
            for index, (_, follow_up) in enumerate(threads, 1):
                lines.append(f"{index}. {follow_up.summary}")
                lines.append(f"   Зачем вернуться: {follow_up.reason_to_return}")
        else:
            lines += ["", "Открытых нитей сейчас нет."]
        quarantined = self.quarantined_count()
        if quarantined:
            lines += [
                "",
                f"Скрыты повреждённые legacy-фрагменты: {quarantined}. "
                "Они не удалены и доступны через --raw.",
            ]
        return "\n".join(lines)

    def raw(self) -> str:
        document = self._document()
        return json.dumps(
            {
                "relationship_memories": [
                    item.model_dump(mode="json") for item in document.relationship_memories
                ],
                "continuity_states": [
                    item.model_dump(mode="json") for item in document.continuity_states
                ],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def relationship_text(memory: RelationshipMemory) -> str:
        if isinstance(memory.content, dict):
            return str(memory.content.get("text", memory.title))
        return str(memory.content)

    @staticmethod
    def _relationship_state(document: MemoryDocument) -> ContinuityState | None:
        matches = [
            item for item in document.continuity_states
            if item.relationship_key == "masha:misha"
        ]
        if len(matches) > 1:
            raise ValueError("multiple masha:misha continuity states")
        return matches[0] if matches else None

    @staticmethod
    def _topic(text: str) -> str:
        return " ".join(text.split()[:8])

    def _document(self) -> MemoryDocument:
        document = self.repository.read_document()
        if document is None:
            raise ValueError("memory store is empty")
        return document

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("shared continuity clock must return aware datetime")
        return value.astimezone(timezone.utc)
