"""Deterministic explicit-memory intent handling for a conversation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.memory.confirmed_memory_service import (
    ConfirmedMemoryService,
    ConfirmedRecord,
    ExplicitMemoryConfirmation,
)
from backend.memory.memory_models import (
    Commitment,
    CommitmentStatus,
    Decision,
    DecisionStatus,
    Episode,
    EpisodeProduced,
    EpisodeSuperseded,
    EpisodeUpdated,
    Fact,
    FactStatus,
    IdentityCode,
    RelationshipKind,
    RelationshipMemory,
    RelationshipStatus,
    SourceType,
    Visibility,
)
from backend.temporal.temporal_engine import TemporalEngine
from backend.memory.memory_management import MemoryMutationOperation


MemoryRecordType = Literal[
    "fact",
    "decision",
    "commitment",
    "episode",
    "relationship_memory",
    "continuity_state",
]
_SHARED_MEMORY = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:запомни|сохрани)\s+как\s+"
    r"(?P<kind>наш\s+момент|часть\s+нашей\s+истории|наш\s+символ)\s*[:,]?\s*"
    r"(?:что\s+)?(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_OPEN_THREAD = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:оставь|сохрани)\s+(?:это\s+)?(?:как\s+)?"
    r"открыт(?:ой|ую)\s+нит(?:ью|ь)\s*[:,]?\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_RESOLVE_THREAD = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:закрой|заверши)\s+(?:открытую\s+)?нить\s*[:,]?\s*"
    r"(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_EXPLICIT_INTENT = re.compile(
    r"^\s*(?:маша\s*,?\s*)?запомни(?:\s+как\s+(?P<kind>факт|решение(?:\s+проекта)?|обязательство|эпизод))?\s*,?\s*(?:что\s+)?(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_CONFIRM = re.compile(r"^\s*(?:да|подтверждаю|сохраняй|сохрани)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*$", re.IGNORECASE)
_REJECT = re.compile(r"^\s*(?:нет|не надо|не запоминай|отмена)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*$", re.IGNORECASE)
_MEMORY_PREFIX = re.compile(r"^\s*(?:маша\s*,?\s*)?запомни\b", re.IGNORECASE)
_COMPLETE = re.compile(r"^\s*(?:маша\s*,?\s*)?отметь\s+(?P<body>.+?)\s+выполненным\s*$", re.IGNORECASE)


class ProposalStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class MemoryProposal(BaseModel):
    """Local pending state only; this is deliberately not a MemoryDocument record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    record_type: MemoryRecordType
    record_payload: dict
    created_at: AwareDatetime
    status: ProposalStatus
    operation: str = "create"
    target_record_id: str | None = None


class MemoryProposalStore:
    """Portable local pending proposals, separate from production memory."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._proposals = self._load()

    def create(self, proposal: MemoryProposal) -> MemoryProposal:
        if proposal.id in self._proposals:
            raise ValueError(f"proposal already exists: {proposal.id}")
        self._proposals[proposal.id] = proposal
        self._save()
        return proposal

    def get(self, proposal_id: str) -> MemoryProposal | None:
        return self._proposals.get(proposal_id)

    def pending_for_conversation(self, conversation_id: str) -> tuple[MemoryProposal, ...]:
        return tuple(
            proposal
            for proposal in self._proposals.values()
            if proposal.conversation_id == conversation_id and proposal.status == ProposalStatus.PENDING
        )

    def set_status(self, proposal_id: str, status: ProposalStatus) -> MemoryProposal:
        proposal = self._proposals[proposal_id]
        updated = proposal.model_copy(update={"status": status})
        self._proposals[proposal_id] = updated
        self._save()
        return updated

    def _load(self) -> dict[str, MemoryProposal]:
        if not self.file_path.exists():
            return {}
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        return {
            item["id"]: MemoryProposal.model_validate(item)
            for item in raw.get("proposals", [])
        }

    def _save(self) -> None:
        temporary = self.file_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"proposals": [item.model_dump(mode="json") for item in self._proposals.values()]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.file_path)


class MemoryIntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    handled: bool
    response: str | None = None


class MemoryIntentHandler:
    """Creates/cancels/confirms proposals; only ConfirmedMemoryService writes memory."""

    def __init__(
        self,
        *,
        proposal_store: MemoryProposalStore,
        confirmed_memory: ConfirmedMemoryService,
        temporal_engine: TemporalEngine | None = None,
        memory_management=None,
        shared_continuity=None,
    ):
        self.proposal_store = proposal_store
        self.confirmed_memory = confirmed_memory
        self.temporal_engine = temporal_engine or TemporalEngine()
        self.memory_management = memory_management
        self.shared_continuity = shared_continuity

    def handle(
        self,
        message: str,
        *,
        conversation_id: str,
        project_id: str,
    ) -> MemoryIntentResult:
        if shared := _SHARED_MEMORY.match(message):
            return self._propose_shared_memory(
                shared,
                conversation_id=conversation_id,
                project_id=project_id,
            )
        if thread := _OPEN_THREAD.match(message):
            return self._propose_open_thread(thread.group("body"), conversation_id)
        if thread := _RESOLVE_THREAD.match(message):
            return self._propose_resolve_thread(thread.group("body"), conversation_id)
        if complete := _COMPLETE.match(message):
            return self._propose_completion(complete.group("body"), conversation_id)
        match = _EXPLICIT_INTENT.match(message)
        if match:
            return self._propose(match, conversation_id=conversation_id, project_id=project_id)
        if confirm := _CONFIRM.match(message):
            return self._confirm(confirm.group("id"), conversation_id)
        if reject := _REJECT.match(message):
            return self._cancel(reject.group("id"), conversation_id)
        if _MEMORY_PREFIX.match(message):
            return MemoryIntentResult(
                handled=True,
                response="Что именно сохранить и как: факт, решение, обязательство или эпизод?",
            )
        return MemoryIntentResult(handled=False)

    def _propose_shared_memory(
        self,
        match: re.Match[str],
        *,
        conversation_id: str,
        project_id: str,
    ) -> MemoryIntentResult:
        body = match.group("body").strip().rstrip(".")
        kind = {
            "наш момент": RelationshipKind.SHARED_MILESTONE,
            "часть нашей истории": RelationshipKind.RELATIONSHIP_NOTE,
            "наш символ": RelationshipKind.SHARED_SYMBOL,
        }[" ".join(match.group("kind").casefold().split())]
        now = self._now()
        record = RelationshipMemory(
            id=f"relationship_{uuid4()}",
            kind=kind,
            title=body[:80],
            content={
                "text": body,
                "declared_by": "misha",
                "confirmation": "explicit_user_confirmation",
            },
            status=RelationshipStatus.CURRENT,
            visibility=Visibility.VISIBLE,
            importance=0.8,
            confidence=1.0,
            source=SourceType.EXPLICIT_USER_INPUT,
            project_ids=[project_id],
            source_episode_ids=[],
            revises_id=None,
            created_at=now,
        )
        proposal = self.proposal_store.create(
            MemoryProposal(
                id=str(uuid4()),
                conversation_id=conversation_id,
                record_type="relationship_memory",
                record_payload=record.model_dump(mode="json"),
                created_at=now,
                status=ProposalStatus.PENDING,
            )
        )
        return MemoryIntentResult(
            handled=True,
            response=(
                "Предлагаю сохранить это не как факт о тебе, а как часть нашей "
                f"подтверждённой истории:\n«{body}»\nСохраняем? Напиши: да"
            ),
        )

    def _propose_open_thread(self, body: str, conversation_id: str) -> MemoryIntentResult:
        if self.shared_continuity is None:
            return MemoryIntentResult(handled=True, response="Общие нити сейчас недоступны.")
        proposal = self.shared_continuity.propose_open_thread(
            self.proposal_store,
            text=body,
            conversation_id=conversation_id,
        )
        return MemoryIntentResult(
            handled=True,
            response=(
                "Оставить это открытой нитью между разговорами?\n"
                f"«{body.strip().rstrip('.')}»\nПодтверди: да {proposal.id}"
            ),
        )

    def _propose_resolve_thread(self, body: str, conversation_id: str) -> MemoryIntentResult:
        if self.shared_continuity is None:
            return MemoryIntentResult(handled=True, response="Общие нити сейчас недоступны.")
        try:
            proposal = self.shared_continuity.propose_resolve_thread(
                self.proposal_store,
                query=body,
                conversation_id=conversation_id,
            )
        except LookupError:
            return MemoryIntentResult(handled=True, response="Не нашла такую открытую нить.")
        except ValueError:
            return MemoryIntentResult(
                handled=True,
                response="Нашла несколько похожих нитей. Уточни формулировку.",
            )
        return MemoryIntentResult(
            handled=True,
            response=f"Закрыть эту общую нить?\n«{body.strip()}»\nПодтверди: да {proposal.id}",
        )

    def _propose_completion(self, text: str, conversation_id: str) -> MemoryIntentResult:
        if self.memory_management is None:
            return MemoryIntentResult(handled=True, response="Завершение обязательств сейчас недоступно.")
        matches = [view for view in self.memory_management.list(record_type="commitment") if view.payload.get("status") == "open" and text.casefold() in view.payload["text"].casefold()]
        if not matches:
            return MemoryIntentResult(handled=True, response="Не нашла открытое обязательство с таким текстом.")
        if len(matches) != 1:
            return MemoryIntentResult(handled=True, response="Нашла несколько обязательств; уточни текст точнее.")
        return self.propose_completion_by_id(matches[0].record_id, conversation_id)

    def propose_completion_by_id(self, record_id: str, conversation_id: str) -> MemoryIntentResult:
        """Create the existing completion proposal for one explicitly selected Commitment."""
        if self.memory_management is None:
            return MemoryIntentResult(handled=True, response="Завершение обязательств сейчас недоступно.")
        view = self.memory_management.get(record_id)
        if view is None or view.record_type != "commitment":
            return MemoryIntentResult(handled=True, response="Не нашла такое обязательство.")
        if view.payload.get("status") != "open":
            return MemoryIntentResult(handled=True, response="Это обязательство уже не открыто.")
        payload = dict(view.payload)
        now = self.temporal_engine.clock.now_utc()
        payload.update(status="completed", completed_at=now.isoformat(), updated_at=now.isoformat())
        proposal = self.memory_management.propose(self.proposal_store, operation=MemoryMutationOperation.EDIT, record_id=view.record_id, conversation_id=conversation_id, replacement_payload=payload)
        return MemoryIntentResult(handled=True, response=f"Отметить обязательство выполненным?\n«{view.payload['text']}»\nСтатус: открыто → выполнено.\nПодтверди: да {proposal.id}")

    def _propose(self, match: re.Match[str], *, conversation_id: str, project_id: str) -> MemoryIntentResult:
        body = match.group("body").strip().rstrip(".")
        if not body:
            return MemoryIntentResult(
                handled=True,
                response="Что именно сохранить: факт, решение, обязательство или эпизод?",
            )
        record_type = self._record_type(match.group("kind"))
        due = None
        if match.group("kind") is None:
            body, due = self.temporal_engine.extract_due(body)
            if due is not None:
                record_type = "commitment"
        record = self._make_record(record_type, body, project_id, due_at=None if due is None else due.resolved_utc)
        proposal = self.proposal_store.create(
            MemoryProposal(
                id=str(uuid4()),
                conversation_id=conversation_id,
                record_type=record_type,
                record_payload=record.model_dump(mode="json"),
                created_at=self._now(),
                status=ProposalStatus.PENDING,
            )
        )
        return MemoryIntentResult(
            handled=True,
            response=self._proposal_text(proposal, record),
        )

    def _confirm(self, proposal_id: str | None, conversation_id: str) -> MemoryIntentResult:
        proposal, problem = self._resolve(proposal_id, conversation_id)
        if problem:
            return MemoryIntentResult(handled=True, response=problem)
        assert proposal is not None
        if proposal.status == ProposalStatus.CONFIRMED:
            return MemoryIntentResult(handled=True, response="Эта запись уже сохранена.")
        if proposal.status == ProposalStatus.CANCELLED:
            return MemoryIntentResult(handled=True, response="Это предложение уже отменено; ничего не сохраняла.")
        if proposal.operation in {"continuity_create", "continuity_update"}:
            if self.shared_continuity is None:
                return MemoryIntentResult(handled=True, response="Общие нити сейчас недоступны.")
            try:
                self.shared_continuity.confirm_proposal(proposal, self.proposal_store)
            except Exception:
                return MemoryIntentResult(
                    handled=True,
                    response=f"Не смогла применить предложение {proposal.id}. Оно осталось ожидающим подтверждения.",
                )
            return MemoryIntentResult(
                handled=True,
                response="Готово. Наша общая нить обновлена.",
            )
        if proposal.operation != "create":
            if self.memory_management is None:
                return MemoryIntentResult(handled=True, response="Эта операция сейчас недоступна.")
            try:
                self.memory_management.confirm_proposal(proposal, self.proposal_store)
            except Exception:
                return MemoryIntentResult(handled=True, response=f"Не смогла применить предложение {proposal.id}. Оно осталось ожидающим подтверждения.")
            return MemoryIntentResult(handled=True, response="Готово, обязательство отмечено выполненным.")
        try:
            self.confirmed_memory.confirm(
                ExplicitMemoryConfirmation(
                    confirmed_by=IdentityCode.MISHA,
                    record=self._record_from_proposal(proposal),
                )
            )
        except Exception:
            return MemoryIntentResult(
                handled=True,
                response=f"Не смогла сохранить предложение {proposal.id}. Оно осталось ожидающим подтверждения.",
            )
        self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
        return MemoryIntentResult(handled=True, response="Готово, сохранила.")

    def _cancel(self, proposal_id: str | None, conversation_id: str) -> MemoryIntentResult:
        proposal, problem = self._resolve(proposal_id, conversation_id)
        if problem:
            return MemoryIntentResult(handled=True, response=problem)
        assert proposal is not None
        if proposal.status == ProposalStatus.PENDING:
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            return MemoryIntentResult(handled=True, response="Хорошо, не сохраняю.")
        return MemoryIntentResult(handled=True, response="Это предложение уже не ожидает подтверждения.")

    def _resolve(self, proposal_id: str | None, conversation_id: str) -> tuple[MemoryProposal | None, str | None]:
        if proposal_id:
            proposal = self.proposal_store.get(proposal_id)
            if proposal is None or proposal.conversation_id != conversation_id:
                return None, "Не вижу такого предложения в этом разговоре."
            return proposal, None
        pending = self.proposal_store.pending_for_conversation(conversation_id)
        if len(pending) == 1:
            return pending[0], None
        if not pending:
            return None, "Сейчас нет предложения памяти, которое можно подтвердить."
        ids = ", ".join(item.id for item in pending)
        return None, f"Есть несколько предложений. Подтверди или отмени конкретное: да <id>. IDs: {ids}"

    @staticmethod
    def _record_type(kind: str | None) -> MemoryRecordType:
        normalized = (kind or "факт").lower()
        if normalized.startswith("решение"):
            return "decision"
        if normalized == "обязательство":
            return "commitment"
        if normalized == "эпизод":
            return "episode"
        return "fact"

    @classmethod
    def _make_record(cls, record_type: MemoryRecordType, body: str, project_id: str, due_at=None) -> ConfirmedRecord:
        now = cls._now()
        record_id = f"{record_type}_{uuid4()}"
        if record_type == "fact":
            preference = re.match(r"я\s+предпочитаю\s+(.+)", body, re.IGNORECASE)
            value = preference.group(1) if preference else body
            return Fact(
                id=record_id,
                subject="misha",
                key="preference" if preference else "explicit_statement",
                value=value,
                status=FactStatus.ACTIVE,
                visibility=Visibility.VISIBLE,
                importance=0.7,
                confidence=1.0,
                source=SourceType.EXPLICIT_USER_INPUT,
                owner=IdentityCode.MISHA,
                known_by=[IdentityCode.MISHA, IdentityCode.MASHA],
                project_ids=[project_id],
                source_episode_ids=[],
                superseded_by=None,
                created_at=now,
                updated_at=now,
            )
        if record_type == "decision":
            return Decision(
                id=record_id,
                title="Project decision",
                decision=body,
                reason="Explicit user statement.",
                status=DecisionStatus.ACTIVE,
                visibility=Visibility.VISIBLE,
                project_ids=[project_id],
                source=SourceType.EXPLICIT_USER_INPUT,
                source_episode_ids=[],
                superseded_by=None,
                created_at=now,
                updated_at=now,
            )
        if record_type == "commitment":
            return Commitment(
                id=record_id,
                text=body,
                owner=IdentityCode.MISHA,
                status=CommitmentStatus.OPEN,
                visibility=Visibility.VISIBLE,
                project_ids=[project_id],
                due_at=due_at,
                completed_at=None,
                importance=0.7,
                source=SourceType.EXPLICIT_USER_INPUT,
                source_episode_ids=[],
                replaces_id=None,
                created_at=now,
                updated_at=now,
            )
        return Episode(
            id=record_id,
            title="Explicitly remembered episode",
            summary=body,
            occurred_at=now,
            source=SourceType.EXPLICIT_USER_INPUT,
            importance=0.7,
            visibility=Visibility.VISIBLE,
            project_ids=[project_id],
            participants=[IdentityCode.MISHA],
            topics=["explicit memory"],
            produced=EpisodeProduced(
                facts=[], decisions=[], commitments=[], reflections=[], relationship_memories=[], affective_records=[], project_changes=[]
            ),
            updated=EpisodeUpdated(facts=[], decisions=[], commitments=[], continuity_states=[], projects=[]),
            superseded=EpisodeSuperseded(facts=[], decisions=[], commitments=[]),
            related_memory_ids=[],
            created_at=now,
        )

    @staticmethod
    def _record_from_proposal(proposal: MemoryProposal) -> ConfirmedRecord:
        models = {
            "fact": Fact,
            "decision": Decision,
            "commitment": Commitment,
            "episode": Episode,
            "relationship_memory": RelationshipMemory,
        }
        return models[proposal.record_type].model_validate(proposal.record_payload)

    @staticmethod
    def _proposal_text(proposal: MemoryProposal, record: ConfirmedRecord) -> str:
        if isinstance(record, Fact):
            description = f"Могу сохранить это как факт: {record.subject}.{record.key} = {record.value!r}."
        elif isinstance(record, Decision):
            description = f"Могу сохранить это как решение: {record.decision}."
        elif isinstance(record, Commitment):
            deadline = " без срока" if record.due_at is None else f" со сроком {record.due_at.astimezone().strftime('%d.%m.%Y %H:%M')}"
            description = f"Могу сохранить это как обязательство: {record.text}{deadline}."
        elif isinstance(record, Episode):
            description = f"Могу сохранить это как эпизод: {record.summary}."
        else:
            description = f"Могу сохранить это как часть нашей истории: {record.content}."
        return f"{description} Источник — твоё явное утверждение. Сохраняем? ID предложения: {proposal.id}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
