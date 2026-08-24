"""Deterministic explicit-memory intent handling for a conversation."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

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
from backend.memory.text_normalization import meaningful_tokens, stem_russian_token
from .conversation_models import ConversationMessage
from .human_reference import (
    HumanEntityAction,
    HumanEntityClarification,
    HumanEntityKind,
    HumanEntityRef,
    PresentedEntityRef,
    PresentedEntitySet,
)
from .capability_router import (
    CapabilityIntent,
    NaturalLanguageCapabilityRouter,
    ParsedCapabilityIntent,
    normalize_utterance,
)


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
    r"^\s*(?:маша\s*,?\s*)?(?:закрой|закрыть|заверши|завершить|удали|удалить|убери|убрать)\s+"
    r"(?:открытую\s+)?(?:нить|тему)"
    r"(?:\s+(?:про|о))?\s*[:,]?\s*"
    r"(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_ACTIVE_CONTINUITY_KEEP_OPEN = re.compile(
    r"^(?:да\s*,?\s*)?(?:эту\s+)?(?:тему|нить|ее|её)\s+"
    r"(?:пока\s+)?(?:остав(?:им|ля(?:ем|ю))\s+открыт(?:ой|ую)|не\s+закрыва(?:ем|ю))$|"
    r"^вернемся\s+потом$",
    re.IGNORECASE,
)
_GENERIC_CONTINUITY_TEXT = {
    "это", "эта", "эту", "ее", "её", "тема", "тему", "нить", "нитку",
    "этот вопрос", "эту тему", "эту нить",
}
_EXPLICIT_INTENT = re.compile(
    r"^\s*(?:маша\s*,?\s*)?запомни(?:\s+как\s+(?P<kind>факт|решение(?:\s+проекта)?|обязательство|эпизод))?\s*,?\s*(?:что\s+)?(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_CONVERSATION_EPISODE = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:"
    r"(?:запомни|сохрани)\s+(?:наш|этот)\s+разговор(?:\s+(?:про|о)\s+(?P<topic>.+?))?|"
    r"хочу\s+сохранить\s+этот\s+разговор\s+как\s+эпизод(?:\s+(?:про|о)\s+(?P<topic_two>.+?))?"
    r")\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_CONFIRM = re.compile(
    r"^\s*(?:да|подтверждаю|сохраняй|сохрани|сохраняем)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$",
    re.IGNORECASE,
)
_REJECT = re.compile(r"^\s*(?:нет|не надо|не сейчас|не сохраняй|не запоминай|отмена)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$", re.IGNORECASE)
_MEMORY_PREFIX = re.compile(r"^\s*(?:маша\s*,?\s*)?запомни\b", re.IGNORECASE)
_COMPLETE = re.compile(r"^\s*(?:маша\s*,?\s*)?отметь\s+(?P<body>.+?)\s+выполненным\s*$", re.IGNORECASE)
_SHOW_MEMORY = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:что\s+ты\s+(?:обо\s+мне\s+)?помнишь(?:\s+про\s+(?P<remember_query>.+?))?|"
    r"что\s+ты\s+знаешь(?:\s+про\s+(?P<query>.+?))?|покажи\s+(?:мою\s+)?память)\s*\??\s*$",
    re.IGNORECASE,
)
_FORGOTTEN_REVIEW = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:"
    r"что\s+я\s+(?:тебя\s+)?просил\s+(?:тебя\s+)?забыть|"
    r"что\s+ты\s+забыла|покажи\s+(?:мне\s+)?забытые\s+записи|"
    r"покажи\s+(?:мне\s+)?забытую\s+память"
    r")(?:\s+про\s+(?P<body>.+?))?\s*\??\s*$",
    re.IGNORECASE,
)
_SEARCH_INFORMATION = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:найди|поищи)\s+"
    r"(?:(?:всю|все|всё)\s+)?(?:(?P<kind>информацию|записи|дело|историю|тему)\s+)?"
    r"(?:про|о)?\s*(?P<body>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_RESTORE_INFORMATION = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:верни|восстанови)\s+(?P<body>.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_INSPECT_PRESENTED = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:что\s+(?:было\s+)?в|расскажи\s+про)\s+"
    r"(?P<body>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_LIST_COMMITMENTS = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:какие\s+(?:у\s+(?:меня|нас)\s+)?(?:сейчас\s+)?(?:дела|задачи|обязательства)|"
    r"что\s+(?:у\s+(?:меня|нас)\s+)?(?:сейчас\s+)?(?:по\s+)?(?:делам|задачам|обязательствам)|"
    r"покажи\s+(?:мои\s+)?(?:дела|задачи|обязательства))\s*\??\s*$",
    re.IGNORECASE,
)
_CREATE_COMMITMENT = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:"
    r"добавь(?:\s+в\s+наши\s+дела)?\s+(?:(?:мне|нам)\s+)?(?:дело|задачу|обязательство)?|"
    r"создай\s+(?:(?:мне|нам)\s+)?(?:дело|задачу|обязательство)|"
    r"запиши\s+(?:нам\s+)?(?:дело|задачу|обязательство)|"
    r"(?:дело|задачу|обязательство)\s+(?:добавь|запиши)|"
    r"(?:и\s+)?ещ[её]\s+(?:одн[ау]\s+)?(?:задача|дело|обязательство)|"
    r"напомни\s+(?:мне\s+)?"
    r")\s*[:,—-]?\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_FORGET = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:забудь|удали\s+из\s+памяти|это\s+больше\s+не\s+актуально,?\s+забудь)\s*[,!:—-]?\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_HUMAN_REMOVE = re.compile(
    r"^\s*(?:маша\s*[,!:-]?\s*)?(?:"
    r"(?P<verb>забудь|удал(?:и|ить)|уб(?:ери|рать))\b(?:\s+из\s+памяти)?\s*[,!:—-]?\s*(?P<body>.*?)|"
    r"(?P<suffix_body>.+?)\s+(?P<suffix_verb>забудь|удали|убери)|"
    r"(?P<deictic>это\s+больше\s+не\s+нужно)"
    r")\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_ORDINAL_WORDS = {
    "первая": 1, "первую": 1, "первый": 1, "первой": 1,
    "вторая": 2, "вторую": 2, "второй": 2,
    "третья": 3, "третью": 3, "третий": 3, "третьей": 3,
    "четвертая": 4, "четвертую": 4, "четвертый": 4, "четвертой": 4,
    "пятая": 5, "пятую": 5, "пятый": 5, "пятой": 5,
    "шестая": 6, "шестую": 6, "шестой": 6,
    "седьмая": 7, "седьмую": 7, "седьмой": 7,
    "восьмая": 8, "восьмую": 8, "восьмой": 8,
    "девятая": 9, "девятую": 9, "девятый": 9, "девятой": 9,
    "десятая": 10, "десятую": 10, "десятый": 10, "десятой": 10,
    "одиннадцатая": 11, "одиннадцатую": 11, "одиннадцатый": 11,
    "двенадцатая": 12, "двенадцатую": 12, "двенадцатый": 12,
}
_DEICTIC_ONLY = {
    "ее", "её", "эту", "это", "вот эту", "она", "это больше не нужно",
}
_REMOVABLE_MEMORY_TYPES = {"fact", "decision", "episode", "relationship_memory", "commitment"}
_UPDATE = re.compile(
    r"^\s*(?:маша\s*,?\s*)?(?:обнови|измени)\s+(?:в\s+памяти\s+)?(?P<old>.+?)\s+на\s+(?P<new>.+?)\s*$",
    re.IGNORECASE,
)
_COMPLETE_IMPLICIT = re.compile(r"^\s*(?:маша\s*,?\s*)?(?:я\s+)?(?:это\s+)?(?:сделал|сделала|выполнил|выполнила)\s*\.?\s*$", re.IGNORECASE)
_COMMITMENT_REFERENCE_QUERY = re.compile(
    r"^\s*(?:маш(?:а|енька)?\s*[,!:-]?\s*)?что(?:\s+там)?\s+с\s+(?P<body>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_AMBIGUOUS_COMMITMENT_FOLLOW_UP = re.compile(
    r"^\s*(?:и\s+)?ещ[её]\s+(?:одно|одна)\b",
    re.IGNORECASE,
)


class ChatCapabilityAction(str, Enum):
    """Finite, local actions recognised before the LLM is ever called.

    This is deliberately a parser result, not a tool interface: the model never
    receives a service object, SQL handle, or arbitrary callable.
    """

    SHOW_MEMORY = "show_memory"
    LIST_COMMITMENTS = "list_commitments"
    CREATE_COMMITMENT = "create_commitment"
    FORGET = "forget"
    UPDATE = "update"
    COMPLETE = "complete"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PendingProposalConflict(ValueError):
    """A conversation already owns the one user-facing confirmation slot."""


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
        if self.pending_for_conversation(proposal.conversation_id):
            raise PendingProposalConflict("a confirmation is already pending")
        updated = {**self._proposals, proposal.id: proposal}
        self._save(updated)
        self._proposals = updated
        return proposal

    def get(self, proposal_id: str) -> MemoryProposal | None:
        return self._proposals.get(proposal_id)

    def pending_for_conversation(self, conversation_id: str) -> tuple[MemoryProposal, ...]:
        return tuple(
            proposal
            for proposal in self._proposals.values()
            if proposal.conversation_id == conversation_id and proposal.status == ProposalStatus.PENDING
        )

    def current_for_conversation(self, conversation_id: str) -> MemoryProposal | None:
        """Recover one deterministic UI slot from legacy competing proposals.

        Older proposals are cancelled, never applied. This migration touches
        transient proposal state only and makes a plain confirmation safe.
        """
        pending = sorted(
            self.pending_for_conversation(conversation_id),
            key=lambda item: (item.created_at, item.id),
        )
        if not pending:
            return None
        current = pending[-1]
        if len(pending) > 1:
            updated = dict(self._proposals)
            for stale in pending[:-1]:
                updated[stale.id] = stale.model_copy(
                    update={"status": ProposalStatus.CANCELLED}
                )
            self._save(updated)
            self._proposals = updated
        return current

    def set_status(self, proposal_id: str, status: ProposalStatus) -> MemoryProposal:
        proposal = self._proposals[proposal_id]
        updated = proposal.model_copy(update={"status": status})
        proposals = {**self._proposals, proposal_id: updated}
        self._save(proposals)
        self._proposals = proposals
        return updated

    def _load(self) -> dict[str, MemoryProposal]:
        if not self.file_path.exists():
            return {}
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        return {
            item["id"]: MemoryProposal.model_validate(item)
            for item in raw.get("proposals", [])
        }

    def _save(self, proposals: dict[str, MemoryProposal] | None = None) -> None:
        snapshot = self._proposals if proposals is None else proposals
        temporary = self.file_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"proposals": [item.model_dump(mode="json") for item in snapshot.values()]},
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


class ContinuityResolveClarification(BaseModel):
    """Application-session context for one ambiguous human reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str = Field(min_length=1)
    candidate_thread_ids: tuple[str, ...] = Field(min_length=2)
    original_query: str = Field(min_length=1)


class ConfirmationFailureDiagnostic(BaseModel):
    """Safe local metadata for a failed confirmed mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exception_type: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    record_id: str | None = None
    stage: Literal[
        "proposal_validation",
        "repository_write",
        "postcondition_check",
        "proposal_status",
    ]
    timestamp: AwareDatetime


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
        capability_router: NaturalLanguageCapabilityRouter | None = None,
        human_information=None,
        on_commitment_terminal=None,
    ):
        self.proposal_store = proposal_store
        self.confirmed_memory = confirmed_memory
        self.temporal_engine = temporal_engine or TemporalEngine()
        self.memory_management = memory_management
        self.shared_continuity = shared_continuity
        self.capability_router = capability_router or NaturalLanguageCapabilityRouter()
        self.human_information = human_information
        self._on_commitment_terminal = on_commitment_terminal
        self._continuity_clarifications: dict[str, ContinuityResolveClarification] = {}
        self._human_entity_clarifications: dict[str, HumanEntityClarification] = {}
        self._presented_entity_sets: dict[str, PresentedEntitySet] = {}
        self._diagnostic_path = proposal_store.file_path.with_name(
            "confirmation-failures.json"
        )

    def handle(
        self,
        message: str,
        *,
        conversation_id: str,
        project_id: str,
        active_continuity_thread_id: str | None = None,
        conversation_messages: tuple[ConversationMessage, ...] = (),
        conversation_first: bool = False,
    ) -> MemoryIntentResult:
        # A plain human confirmation always resolves the single user-facing
        # slot. IDs remain an internal bridge compatibility detail.
        if confirm := _CONFIRM.match(message):
            clarification = self._continuity_clarifications.get(conversation_id)
            if (
                clarification is not None
                and confirm.group("id") is None
                and self.proposal_store.current_for_conversation(conversation_id) is None
            ):
                return MemoryIntentResult(
                    handled=True,
                    response="Сначала уточни, какую именно нить закрыть — пока ничего не меняю.",
                )
            self._continuity_clarifications.pop(conversation_id, None)
            self._human_entity_clarifications.pop(conversation_id, None)
            return self._confirm(confirm.group("id"), conversation_id)
        if reject := _REJECT.match(message):
            human_clarification = self._human_entity_clarifications.get(conversation_id)
            if (
                human_clarification is not None
                and reject.group("id") is None
                and self.proposal_store.current_for_conversation(conversation_id) is None
            ):
                self._human_entity_clarifications.pop(conversation_id, None)
                return MemoryIntentResult(
                    handled=True,
                    response="Хорошо, ничего не убираю.",
                )
            clarification = self._continuity_clarifications.get(conversation_id)
            if (
                clarification is not None
                and reject.group("id") is None
                and self.proposal_store.current_for_conversation(conversation_id) is None
            ):
                self._continuity_clarifications.pop(conversation_id, None)
                return MemoryIntentResult(
                    handled=True,
                    response="Хорошо, ничего не закрываю.",
                )
            self._continuity_clarifications.pop(conversation_id, None)
            self._human_entity_clarifications.pop(conversation_id, None)
            return self._cancel(reject.group("id"), conversation_id)
        pending = self.proposal_store.current_for_conversation(conversation_id) is not None

        # Conversation-first sessions discard stale shelf clarifications.
        # An explicit new command below can still open a fresh shelf interaction.
        if conversation_first:
            self._continuity_clarifications.pop(conversation_id, None)
            self._human_entity_clarifications.pop(conversation_id, None)

        human_clarification = self._human_entity_clarifications.get(conversation_id)
        if human_clarification is not None:
            remove_query = self._human_remove_query(message)
            parsed_clarification = self.capability_router.route(
                message,
                allow_semantic=not conversation_first,
                explicit_only=conversation_first,
            )
            if remove_query is not None or parsed_clarification is None:
                if pending:
                    return self._pending_conflict()
                return self._refine_human_remove(
                    message if remove_query is None else remove_query,
                    human_clarification,
                )
            self._human_entity_clarifications.pop(conversation_id, None)

        clarification = self._continuity_clarifications.get(conversation_id)
        if clarification is not None:
            parsed_clarification = self.capability_router.route(
                message,
                allow_semantic=not conversation_first,
                explicit_only=conversation_first,
            )
            if parsed_clarification is None:
                return self._refine_continuity_resolution(message, clarification)
            # A new explicit action replaces the abandoned clarification.  A
            # repeated resolve command starts a fresh candidate set below.
            self._continuity_clarifications.pop(conversation_id, None)

        # A resumed thread is a real conversational context, not a one-turn
        # prompt trick.  Deictic follow-ups refer to that existing thread and
        # must never become a new generic continuity record.
        if (
            active_continuity_thread_id is not None
            and _ACTIVE_CONTINUITY_KEEP_OPEN.match(normalize_utterance(message))
        ):
            summary = self._active_thread_summary(active_continuity_thread_id)
            if summary is not None:
                return MemoryIntentResult(
                    handled=True,
                    response="Хорошо, оставляем эту тему открытой — вернёмся к ней позже.",
                )

        # These read/proposal commands are deliberately resolved locally.  They
        # cannot be hallucinated as a model capability and never expose storage.
        if show := _SHOW_MEMORY.match(message):
            query = show.group("remember_query") or show.group("query")
            return self._show_memory(
                query,
                project_id,
                conversation_id=conversation_id,
            )
        if forgotten := _FORGOTTEN_REVIEW.match(message):
            return self._search_human_information(
                forgotten.group("body") or "",
                project_id=project_id,
                conversation_id=conversation_id,
                mode="forgotten_review",
            )
        if restore := _RESTORE_INFORMATION.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_restore_reference(
                restore.group("body"),
                conversation_id=conversation_id,
                project_id=project_id,
            )
        if inspect := _INSPECT_PRESENTED.match(message):
            return self._inspect_presented_reference(
                inspect.group("body"),
                conversation_id=conversation_id,
            )
        if search := _SEARCH_INFORMATION.match(message):
            requested_kind = (search.group("kind") or "").casefold()
            scope = (
                "tasks"
                if requested_kind == "дело"
                else "history"
                if requested_kind in {"историю", "тему"}
                else "all"
            )
            return self._search_human_information(
                search.group("body"),
                project_id=project_id,
                conversation_id=conversation_id,
                mode="retrospective",
                scope=scope,
            )
        if _LIST_COMMITMENTS.match(message):
            return self._list_commitments(project_id)
        if (remove_query := self._human_remove_query(message)) is not None:
            if pending:
                return self._pending_conflict()
            return self._propose_human_remove(
                remove_query,
                conversation_id=conversation_id,
                project_id=project_id,
            )
        if create := _CREATE_COMMITMENT.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_commitment(create.group("body"), conversation_id, project_id)
        if forget := _FORGET.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_human_remove(
                forget.group("body"),
                conversation_id=conversation_id,
                project_id=project_id,
            )
        if update := _UPDATE.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_update(update.group("old"), update.group("new"), conversation_id)
        if shared := _SHARED_MEMORY.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_shared_memory(
                shared,
                conversation_id=conversation_id,
                project_id=project_id,
            )
        if thread := _OPEN_THREAD.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_open_thread(thread.group("body"), conversation_id)
        if thread := _RESOLVE_THREAD.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_resolve_thread(thread.group("body"), conversation_id)
        if complete := _COMPLETE.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_completion(complete.group("body"), conversation_id)
        if not conversation_first and _COMPLETE_IMPLICIT.match(message):
            return MemoryIntentResult(
                handled=True,
                response="Какое именно дело отметить выполненным? Назови его, чтобы я ничего не закрыла по догадке.",
            )
        if episode := _CONVERSATION_EPISODE.match(message):
            if pending:
                return self._pending_conflict()
            return self._propose_conversation_episode(
                episode,
                conversation_id=conversation_id,
                project_id=project_id,
                conversation_messages=conversation_messages,
            )
        match = _EXPLICIT_INTENT.match(message)
        if match:
            if pending:
                return self._pending_conflict()
            return self._propose(match, conversation_id=conversation_id, project_id=project_id)
        if _MEMORY_PREFIX.match(message):
            return MemoryIntentResult(
                handled=True,
                response="Что именно сохранить и как: факт, решение, обязательство или эпизод?",
            )
        if not conversation_first and _AMBIGUOUS_COMMITMENT_FOLLOW_UP.match(message):
            return MemoryIntentResult(
                handled=True,
                response=(
                    "Это похоже на продолжение мысли, но не на явную команду. "
                    "Если хочешь добавить дело, скажи прямо — пока ничего не добавляю."
                ),
            )
        if not conversation_first and (reference := _COMMITMENT_REFERENCE_QUERY.match(message)):
            records = self._matching_open_commitments(reference.group("body"), project_id)
            if records:
                return self._render_commitments(records)
        if parsed := self.capability_router.route(
                message,
                allow_semantic=not conversation_first,
                explicit_only=conversation_first,
            ):
            if pending and parsed.intent in {
                CapabilityIntent.FORGET_MEMORY,
                CapabilityIntent.CREATE_COMMITMENT,
                CapabilityIntent.COMPLETE_COMMITMENT,
                CapabilityIntent.OPEN_CONTINUITY,
                CapabilityIntent.RESOLVE_CONTINUITY,
            }:
                return self._pending_conflict()
            return self._handle_capability(
                parsed,
                conversation_id=conversation_id,
                project_id=project_id,
                active_continuity_thread_id=active_continuity_thread_id,
            )
        return MemoryIntentResult(handled=False)

    @staticmethod
    def _pending_conflict() -> MemoryIntentResult:
        return MemoryIntentResult(
            handled=True,
            response=(
                "Сначала решим текущее предложение: подтверди его или выбери «не сейчас». "
                "Новое пока не создаю."
            ),
        )

    def _handle_capability(
        self,
        parsed: ParsedCapabilityIntent,
        *,
        conversation_id: str,
        project_id: str,
        active_continuity_thread_id: str | None = None,
    ) -> MemoryIntentResult:
        if parsed.intent is CapabilityIntent.QUERY_MEMORY:
            return self._show_memory(
                parsed.entity,
                project_id,
                conversation_id=conversation_id,
            )
        if parsed.intent is CapabilityIntent.FORGET_MEMORY:
            return self._propose_human_remove(
                parsed.entity or "это",
                conversation_id=conversation_id,
                project_id=project_id,
            )
        if parsed.intent is CapabilityIntent.QUERY_COMMITMENTS:
            return self._list_commitments(project_id, query=parsed.entity, temporal_scope=parsed.temporal_scope)
        if parsed.intent is CapabilityIntent.CREATE_COMMITMENT:
            return self._propose_commitment(parsed.entity or "", conversation_id, project_id)
        if parsed.intent is CapabilityIntent.COMPLETE_COMMITMENT:
            return self._propose_completion(parsed.entity or "", conversation_id)
        if parsed.intent is CapabilityIntent.QUERY_CONTINUITY:
            return self._list_continuity(
                parsed.entity,
                conversation_id=conversation_id,
            )
        if parsed.intent is CapabilityIntent.OPEN_CONTINUITY:
            if not parsed.entity:
                return MemoryIntentResult(handled=True, response="Какую именно тему оставить открытой? Назови её — я не буду угадывать по истории чата.")
            return self._propose_open_thread(parsed.entity, conversation_id)
        if parsed.intent is CapabilityIntent.RESOLVE_CONTINUITY:
            if parsed.entity:
                return self._propose_resolve_thread(parsed.entity, conversation_id)
            if active_continuity_thread_id is None:
                return MemoryIntentResult(
                    handled=True,
                    response="Какую именно открытую нить закрыть? Назови её, чтобы я ничего не изменила по догадке.",
                )
            summary = self._active_thread_summary(active_continuity_thread_id)
            if summary is None:
                return MemoryIntentResult(handled=True, response="Не нашла эту открытую нить.")
            return self._propose_resolve_thread(
                active_continuity_thread_id,
                conversation_id,
                display_text=summary,
            )
        return MemoryIntentResult(handled=False)

    def _show_memory(
        self,
        query: str | None,
        project_id: str,
        *,
        conversation_id: str,
    ) -> MemoryIntentResult:
        if self.human_information is not None:
            return self._search_human_information(
                query or "",
                project_id=project_id,
                conversation_id=conversation_id,
                mode="retrospective",
                scope="history",
            )
        if self.memory_management is None:
            self._presented_entity_sets.pop(conversation_id, None)
            return MemoryIntentResult(handled=True, response="Сейчас не могу прочитать локальную память.")
        records = self.memory_management.list(project_id=project_id, include_hidden=False)
        visible = [item for item in records if item.record_type in {"fact", "decision", "episode"}]
        if query:
            visible = self._rank_records(visible, query, self._memory_line)
        if not visible:
            self._presented_entity_sets.pop(conversation_id, None)
            return MemoryIntentResult(
                handled=True,
                response=(
                    "Про это в подтверждённой памяти сейчас ничего подходящего не нашла."
                    if query
                    else "В подтверждённой памяти пока ничего не нашла."
                ),
            )
        lines = ["Вот что у меня подтверждённо есть в памяти:"]
        refs: list[PresentedEntityRef] = []
        for item in visible[:6]:
            label = self._memory_line(item)
            ordinal = len(refs) + 1
            lines.append(f"{ordinal}. {label}")
            refs.append(PresentedEntityRef(
                ordinal=ordinal,
                entity_kind=HumanEntityKind.MEMORY,
                entity_id=item.record_id,
                human_label=label,
                allowed_actions=(HumanEntityAction.FORGET,),
            ))
        if len(visible) > 6:
            lines.append(f"И ещё {len(visible) - 6}. Могу сузить вопрос.")
        self._presented_entity_sets[conversation_id] = PresentedEntitySet(
            conversation_id=conversation_id,
            source_kind="confirmed_memory",
            created_at=self._now(),
            items=tuple(refs),
        )
        return MemoryIntentResult(handled=True, response="\n".join(lines))

    def _search_human_information(
        self,
        query: str,
        *,
        project_id: str,
        conversation_id: str,
        mode: str,
        scope: str = "all",
    ) -> MemoryIntentResult:
        if self.human_information is None:
            self._presented_entity_sets.pop(conversation_id, None)
            return MemoryIntentResult(
                handled=True,
                response="Поиск по сохранённой информации сейчас недоступен.",
            )
        result = self.human_information.search_for_conversation(
            query=query,
            project_id=project_id,
            scope=scope,
            mode=mode,
            limit=8,
        )
        if not result.matches:
            self._presented_entity_sets.pop(conversation_id, None)
            response = (
                "Среди забытых записей ничего подходящего не нашла."
                if mode == "forgotten_review"
                else "В сохранённой информации ничего подходящего не нашла."
            )
            return MemoryIntentResult(handled=True, response=response)

        heading = (
            "Вот что ты просил не использовать:"
            if mode == "forgotten_review"
            else "Нашла в сохранённой информации:"
        )
        availability_labels = {
            "active": "актуально",
            "archived": "из прошлого",
            "forgotten": "забыто",
        }
        kind_labels = {
            HumanEntityKind.MEMORY: "Память",
            HumanEntityKind.HISTORY: "История",
            HumanEntityKind.TASK: "Дело",
            HumanEntityKind.THREAD: "Тема",
        }
        lines = [heading]
        for ordinal, match in enumerate(result.matches, 1):
            item = match.item
            lines.append(
                f"{ordinal}. {kind_labels[item.kind]} · "
                f"{availability_labels[item.availability.value]} — {item.label}"
            )
        if mode == "forgotten_review":
            lines.append("Если хочешь вернуть запись, назови её номер — сначала я попрошу подтверждение.")
        presented = self.human_information.presented_entity_set(
            result,
            conversation_id=conversation_id,
        )
        assert presented is not None
        self._presented_entity_sets[conversation_id] = presented
        return MemoryIntentResult(handled=True, response="\n".join(lines))

    def _propose_restore_reference(
        self,
        query: str,
        *,
        conversation_id: str,
        project_id: str,
    ) -> MemoryIntentResult:
        if self.human_information is None:
            return MemoryIntentResult(handled=True, response="Восстановление памяти сейчас недоступно.")
        presented = self._presented_entity_sets.get(conversation_id)
        selected = None
        ordinal = self._ordinal_from_text(query)
        if presented is not None:
            if ordinal is not None:
                selected = next((item for item in presented.items if item.ordinal == ordinal), None)
            elif normalize_utterance(query) in _DEICTIC_ONLY:
                restorable = [
                    item for item in presented.items
                    if HumanEntityAction.RESTORE in item.allowed_actions
                ]
                if len(restorable) == 1:
                    selected = restorable[0]
                elif len(restorable) > 1:
                    return MemoryIntentResult(
                        handled=True,
                        response="Уточни номер забытой записи, которую нужно вернуть.",
                    )
        if selected is None and ordinal is None and normalize_utterance(query) not in _DEICTIC_ONLY:
            result = self.human_information.search_for_conversation(
                query=query,
                project_id=project_id,
                mode="forgotten_review",
                limit=2,
            )
            if len(result.matches) == 1:
                item = result.matches[0].item
                selected = PresentedEntityRef(
                    ordinal=1,
                    entity_kind=item.kind,
                    entity_id=item.ref.entity_id,
                    human_label=item.label,
                    allowed_actions=item.ref.allowed_actions,
                )
        if selected is None:
            return MemoryIntentResult(
                handled=True,
                response="Сначала покажи забытые записи или уточни, что именно вернуть.",
            )
        if HumanEntityAction.RESTORE not in selected.allowed_actions:
            return MemoryIntentResult(
                handled=True,
                response="Эта запись не является забытой; ничего не меняю.",
            )
        try:
            self.human_information.restore_information(
                record_id=selected.entity_id,
                conversation_id=conversation_id,
                proposal_store=self.proposal_store,
            )
        except (KeyError, ValueError):
            return MemoryIntentResult(
                handled=True,
                response="Эта забытая запись уже недоступна или была восстановлена; ничего не меняю.",
            )
        return MemoryIntentResult(
            handled=True,
            response=(
                f"Вернуть в обычную память: «{selected.human_label}»? "
                "Её прежнее состояние и история сохранятся.\n"
                "Подтверди обычным «да» или выбери «не сейчас»."
            ),
        )

    def _inspect_presented_reference(
        self,
        query: str,
        *,
        conversation_id: str,
    ) -> MemoryIntentResult:
        presented = self._presented_entity_sets.get(conversation_id)
        ordinal = self._ordinal_from_text(query)
        if presented is None or ordinal is None:
            return MemoryIntentResult(
                handled=True,
                response="Сначала покажи нужный список, затем назови номер пункта.",
            )
        selected = next(
            (item for item in presented.items if item.ordinal == ordinal),
            None,
        )
        if selected is None:
            return MemoryIntentResult(
                handled=True,
                response=f"В последнем показанном списке нет пункта {ordinal}.",
            )
        return MemoryIntentResult(
            handled=True,
            response=f"В пункте {ordinal}: {selected.human_label}",
        )

    def _list_commitments(self, project_id: str, *, query: str | None = None, temporal_scope: str | None = None) -> MemoryIntentResult:
        if self.memory_management is None:
            return MemoryIntentResult(handled=True, response="Список дел сейчас недоступен.")
        records = [
            item for item in self.memory_management.list(record_type="commitment", project_id=project_id, include_hidden=False)
            if item.payload.get("status") == "open"
        ]
        if query:
            records = self._rank_records(records, query, lambda item: item.payload.get("text", ""))
        if temporal_scope == "today":
            local_now = self.temporal_engine.now_local()
            records = [
                item for item in records
                if item.payload.get("due_at") is not None
                and datetime.fromisoformat(
                    str(item.payload["due_at"]).replace("Z", "+00:00")
                ).astimezone(local_now.tzinfo).date() == local_now.date()
            ]
        if not records:
            return MemoryIntentResult(handled=True, response="Сейчас не вижу открытых дел.")
        return self._render_commitments(records)

    @staticmethod
    def _render_commitments(records) -> MemoryIntentResult:
        lines = ["Сейчас открыто:"]
        for item in records[:8]:
            due_at = item.payload.get("due_at")
            due = " без срока" if due_at is None else f" — срок {due_at}"
            lines.append(f"— {item.payload['text']}{due}")
        return MemoryIntentResult(handled=True, response="\n".join(lines))

    def presented_entity_set(self, conversation_id: str) -> PresentedEntitySet | None:
        """Inspect the latest application-owned selection truth for a conversation."""
        return self._presented_entity_sets.get(conversation_id)

    def remember_presented_entity_set(self, presented: PresentedEntitySet) -> None:
        """Reuse the v0.3 ordinal truth for typed application search results."""
        self._presented_entity_sets[presented.conversation_id] = presented

    def discard_presented_entity_set(self, conversation_id: str) -> None:
        """Invalidate ordinal truth before an unowned model presentation."""
        self._presented_entity_sets.pop(conversation_id, None)

    @staticmethod
    def _human_remove_query(message: str) -> str | None:
        match = _HUMAN_REMOVE.match(message)
        if match is None:
            return None
        body = (
            match.group("body")
            or match.group("suffix_body")
            or match.group("deictic")
            or ""
        ).strip()
        return body.strip(" ,:;—-«»\"'")

    @staticmethod
    def _ordinal_from_text(value: str) -> int | None:
        normalized = normalize_utterance(value)
        words = normalized.split()
        positional_fillers = {
            "по", "списку", "в", "списке", "пункт", "пункта", "пункту",
            "строка", "строку", "строчки", "строчку", "строке",
            "запись", "записи", "записью", "номер",
        }
        for index, word in enumerate(words):
            if word in _ORDINAL_WORDS:
                remaining = words[:index] + words[index + 1 :]
                return (
                    _ORDINAL_WORDS[word]
                    if all(item in positional_fillers for item in remaining)
                    else None
                )
        for index, word in enumerate(words):
            if word.isdigit() and len(word) <= 2:
                remaining = words[:index] + words[index + 1 :]
                return int(word) if all(item in positional_fillers for item in remaining) else None
        return None

    def _propose_human_remove(
        self,
        query: str,
        *,
        conversation_id: str,
        project_id: str,
    ) -> MemoryIntentResult:
        ordinal = self._ordinal_from_text(query)
        if ordinal is not None:
            presented = self._presented_entity_sets.get(conversation_id)
            if presented is None:
                return MemoryIntentResult(
                    handled=True,
                    response=(
                        "Сначала попроси показать нашу историю, а затем назови номер. "
                        "Без списка приложения я не буду угадывать, что значит этот номер."
                    ),
                )
            selected = next(
                (item for item in presented.items if item.ordinal == ordinal),
                None,
            )
            if selected is None:
                return MemoryIntentResult(
                    handled=True,
                    response=f"В последнем показанном списке нет пункта {ordinal}. Уточни, что именно убрать.",
                )
            ref = HumanEntityRef(
                entity_kind=selected.entity_kind,
                entity_id=selected.entity_id,
                human_label=selected.human_label,
                allowed_actions=selected.allowed_actions,
            )
            if not self._human_entity_is_current(ref):
                return MemoryIntentResult(
                    handled=True,
                    response="Этот список уже устарел. Покажи нашу историю ещё раз — пока ничего не меняю.",
                )
            return self._dispatch_human_remove(ref, conversation_id)

        normalized = normalize_utterance(query)
        if normalized in {"память", "все"}:
            return MemoryIntentResult(
                handled=True,
                response="Уточни, какое именно воспоминание или открытую тему убрать. Я не буду выбирать всё сразу.",
            )
        if not normalized or normalized in _DEICTIC_ONLY:
            presented = self._presented_entity_sets.get(conversation_id)
            if presented is not None and len(presented.items) == 1:
                selected = presented.items[0]
                ref = HumanEntityRef(
                    entity_kind=selected.entity_kind,
                    entity_id=selected.entity_id,
                    human_label=selected.human_label,
                    allowed_actions=selected.allowed_actions,
                )
                if self._human_entity_is_current(ref):
                    return self._dispatch_human_remove(ref, conversation_id)
            return MemoryIntentResult(
                handled=True,
                response="Уточни, какое именно воспоминание или открытую тему убрать. Я не буду выбирать по догадке.",
            )

        matches = self._rank_human_entities(
            self._human_removable_entities(project_id),
            query,
        )
        if not matches:
            return MemoryIntentResult(
                handled=True,
                response=(
                    "Не нашла такую открытую нить или подходящее воспоминание. "
                    "Пока ничего не меняю."
                ),
            )
        if len(matches) > 1:
            bounded = tuple(matches[:5])
            self._human_entity_clarifications[conversation_id] = HumanEntityClarification(
                conversation_id=conversation_id,
                candidates=bounded,
                original_query=query.strip(),
            )
            return self._human_entity_clarification_response(
                bounded,
                conversation_id=conversation_id,
            )
        return self._dispatch_human_remove(matches[0], conversation_id)

    def _human_removable_entities(self, project_id: str) -> list[HumanEntityRef]:
        refs: list[HumanEntityRef] = []
        if self.memory_management is not None:
            for view in self.memory_management.list(
                project_id=project_id,
                include_hidden=False,
            ):
                if view.record_type not in _REMOVABLE_MEMORY_TYPES:
                    continue
                if view.record_type == "fact" and view.payload.get("status") != "active":
                    continue
                if view.record_type == "decision" and view.payload.get("status") != "active":
                    continue
                if (
                    view.record_type == "relationship_memory"
                    and view.payload.get("status") != "current"
                ):
                    continue
                refs.append(HumanEntityRef(
                    # This is the v0.3 remove-only path. Unified search uses
                    # the richer MEMORY/HISTORY/TASK mapping separately.
                    entity_kind=HumanEntityKind.MEMORY,
                    entity_id=view.record_id,
                    human_label=self._memory_line(view),
                    allowed_actions=(HumanEntityAction.FORGET,),
                ))
        if self.shared_continuity is not None:
            refs.extend(
                HumanEntityRef(
                    entity_kind=HumanEntityKind.CONTINUITY,
                    entity_id=follow_up.id,
                    human_label=follow_up.summary,
                    allowed_actions=(HumanEntityAction.RESOLVE_CONTINUITY,),
                )
                for _, follow_up in self.shared_continuity.open_follow_ups()
            )
        return refs

    @classmethod
    def _rank_human_entities(
        cls,
        refs: list[HumanEntityRef] | tuple[HumanEntityRef, ...],
        query: str,
    ) -> list[HumanEntityRef]:
        return cls._rank_records(refs, query, lambda ref: ref.human_label)

    def _human_entity_is_current(self, ref: HumanEntityRef) -> bool:
        if ref.entity_kind in {
            HumanEntityKind.MEMORY,
            HumanEntityKind.HISTORY,
            HumanEntityKind.TASK,
        }:
            if self.memory_management is None:
                return False
            view = self.memory_management.get(ref.entity_id)
            return bool(
                view is not None
                and view.record_type in _REMOVABLE_MEMORY_TYPES
                and view.payload.get("visibility", "visible") == "visible"
            )
        return bool(
            self.shared_continuity is not None
            and any(
                follow_up.id == ref.entity_id
                for _, follow_up in self.shared_continuity.open_follow_ups()
            )
        )

    def _dispatch_human_remove(
        self,
        ref: HumanEntityRef,
        conversation_id: str,
    ) -> MemoryIntentResult:
        self._human_entity_clarifications.pop(conversation_id, None)
        if ref.entity_kind in {
            HumanEntityKind.MEMORY,
            HumanEntityKind.HISTORY,
            HumanEntityKind.TASK,
        }:
            if HumanEntityAction.FORGET not in ref.allowed_actions or self.memory_management is None:
                return MemoryIntentResult(handled=True, response="Это воспоминание сейчас нельзя убрать.")
            view = self.memory_management.get(ref.entity_id)
            if view is None or not self._human_entity_is_current(ref):
                return MemoryIntentResult(handled=True, response="Это воспоминание уже недоступно; ничего не меняю.")
            return self._propose_forget_view(view, conversation_id)
        if HumanEntityAction.RESOLVE_CONTINUITY not in ref.allowed_actions:
            return MemoryIntentResult(handled=True, response="Эту открытую тему сейчас нельзя убрать.")
        if not self._human_entity_is_current(ref):
            return MemoryIntentResult(handled=True, response="Эта открытая тема уже закрыта; ничего не меняю.")
        return self._propose_resolve_thread(
            ref.entity_id,
            conversation_id,
            display_text=ref.human_label,
            human_remove=True,
        )

    def _refine_human_remove(
        self,
        query: str,
        clarification: HumanEntityClarification,
    ) -> MemoryIntentResult:
        candidates = tuple(
            ref for ref in clarification.candidates if self._human_entity_is_current(ref)
        )
        if not candidates:
            self._human_entity_clarifications.pop(clarification.conversation_id, None)
            return MemoryIntentResult(
                handled=True,
                response="Эти варианты уже недоступны. Покажи нашу историю ещё раз — ничего не меняю.",
            )
        ordinal = self._ordinal_from_text(query)
        if ordinal is not None and ordinal <= len(candidates):
            return self._dispatch_human_remove(
                candidates[ordinal - 1],
                clarification.conversation_id,
            )
        normalized = normalize_utterance(query)
        if normalized in _DEICTIC_ONLY:
            return MemoryIntentResult(
                handled=True,
                response="Не поняла, какой именно вариант ты имеешь в виду. Назови номер или несколько слов из него.",
            )
        refined = self._rank_human_entities(candidates, query)
        if not refined:
            return MemoryIntentResult(
                handled=True,
                response="Среди этих вариантов не поняла, что убрать. Назови номер или несколько слов из нужного пункта.",
            )
        if len(refined) > 1:
            bounded = tuple(refined[:5])
            self._human_entity_clarifications[clarification.conversation_id] = clarification.model_copy(
                update={"candidates": bounded}
            )
            return self._human_entity_clarification_response(
                bounded,
                conversation_id=clarification.conversation_id,
            )
        return self._dispatch_human_remove(refined[0], clarification.conversation_id)

    def _human_entity_clarification_response(
        self,
        matches: tuple[HumanEntityRef, ...],
        *,
        conversation_id: str,
    ) -> MemoryIntentResult:
        kinds = {ref.entity_kind for ref in matches}
        lines = [
            "Нашла несколько похожих нитей и вещей:"
            if kinds == {HumanEntityKind.CONTINUITY}
            else "Нашла несколько похожих вещей:"
        ]
        presented: list[PresentedEntityRef] = []
        for ordinal, ref in enumerate(matches, 1):
            kind = "воспоминание" if ref.entity_kind is HumanEntityKind.MEMORY else "открытая тема"
            lines.append(f"{ordinal}. {kind}: {ref.human_label}")
            presented.append(PresentedEntityRef(
                ordinal=ordinal,
                entity_kind=ref.entity_kind,
                entity_id=ref.entity_id,
                human_label=ref.human_label,
                allowed_actions=ref.allowed_actions,
            ))
        lines.append("Что именно убрать?")
        self._presented_entity_sets[conversation_id] = PresentedEntitySet(
            conversation_id=conversation_id,
            source_kind="remove_clarification",
            created_at=self._now(),
            items=tuple(presented),
        )
        return MemoryIntentResult(handled=True, response="\n".join(lines))

    def _list_continuity(
        self,
        query: str | None = None,
        *,
        conversation_id: str,
    ) -> MemoryIntentResult:
        if self.shared_continuity is None:
            return MemoryIntentResult(handled=True, response="Общие нити сейчас недоступны.")
        moments = list(self.shared_continuity.relationship_memories(limit=8))
        rows = list(self.shared_continuity.open_follow_ups())
        if query:
            moments = self._rank_records(
                moments,
                query,
                lambda item: f"{item.title} {self.shared_continuity.relationship_text(item)}",
            )
            rows = self._rank_text_rows(rows, query, lambda row: f"{row[1].topic} {row[1].summary}")
        if not moments and not rows:
            self._presented_entity_sets.pop(conversation_id, None)
            return MemoryIntentResult(handled=True, response="В нашей сохранённой истории пока нет подходящих моментов или открытых нитей.")
        lines = ["Вот что есть в нашей сохранённой истории:"]
        refs: list[PresentedEntityRef] = []
        for item in moments[:6]:
            label = self.shared_continuity.relationship_text(item)
            ordinal = len(refs) + 1
            lines.append(f"{ordinal}. Воспоминание: {label}")
            refs.append(PresentedEntityRef(
                ordinal=ordinal,
                entity_kind=HumanEntityKind.MEMORY,
                entity_id=item.id,
                human_label=label,
                allowed_actions=(HumanEntityAction.FORGET,),
            ))
        for _, item in rows[:6]:
            ordinal = len(refs) + 1
            lines.append(f"{ordinal}. Открытая тема: {item.summary}")
            refs.append(PresentedEntityRef(
                ordinal=ordinal,
                entity_kind=HumanEntityKind.CONTINUITY,
                entity_id=item.id,
                human_label=item.summary,
                allowed_actions=(HumanEntityAction.RESOLVE_CONTINUITY,),
            ))
        self._presented_entity_sets[conversation_id] = PresentedEntitySet(
            conversation_id=conversation_id,
            source_kind="shared_history",
            created_at=self._now(),
            items=tuple(refs),
        )
        return MemoryIntentResult(handled=True, response="\n".join(lines))

    def _propose_commitment(self, body: str, conversation_id: str, project_id: str) -> MemoryIntentResult:
        body = body.strip().rstrip(".")
        body = re.sub(
            r"^(?:дело|задач[ау]|обязательство)\s*[:,—-]?\s+",
            "",
            body,
            flags=re.IGNORECASE,
        )
        if not body:
            return MemoryIntentResult(handled=True, response="Какое именно дело добавить?")
        body = re.sub(r"^через\s+(?:два|две)\s+", "через 2 ", body, flags=re.IGNORECASE)
        body, due = self.temporal_engine.extract_due(body)
        if due is not None and due.ambiguity is not None:
            return MemoryIntentResult(handled=True, response="Срок получился неоднозначным. Скажи дату и время точнее — я не буду угадывать.")
        record = self._make_record("commitment", body, project_id, due_at=None if due is None else due.resolved_utc)
        proposal = self.proposal_store.create(MemoryProposal(
            id=str(uuid4()), conversation_id=conversation_id, record_type="commitment",
            record_payload=record.model_dump(mode="json"), created_at=self._now(), status=ProposalStatus.PENDING,
        ))
        return MemoryIntentResult(handled=True, response=self._proposal_text(proposal, record))

    def _propose_forget_view(self, view, conversation_id: str) -> MemoryIntentResult:
        assert self.memory_management is not None
        self.memory_management.propose(
            self.proposal_store,
            operation=MemoryMutationOperation.FORGET,
            record_id=view.record_id,
            conversation_id=conversation_id,
        )
        return MemoryIntentResult(
            handled=True,
            response=(
                f"Скрыть из активной памяти это воспоминание: «{self._memory_line(view)}»? "
                "Это не удалит историю безвозвратно.\n"
                "Подтверди обычным «да» или выбери «не сейчас»."
            ),
        )

    def _propose_update(self, old: str, new: str, conversation_id: str) -> MemoryIntentResult:
        if self.memory_management is None:
            return MemoryIntentResult(handled=True, response="Изменение памяти сейчас недоступно.")
        matches = self._find_memories(old)
        if len(matches) != 1:
            return self._mutation_lookup_problem(matches, "обновить")
        view = matches[0]
        if view.record_type != "fact":
            return MemoryIntentResult(handled=True, response="Сейчас через разговор я умею уточнять только факты. Для решения или эпизода скажи, что именно нужно изменить.")
        payload = dict(view.payload)
        payload["value"] = new.strip().rstrip(".")
        proposal = self.memory_management.propose(self.proposal_store, operation=MemoryMutationOperation.EDIT,
            record_id=view.record_id, conversation_id=conversation_id, replacement_payload=payload)
        return MemoryIntentResult(handled=True, response=(
            f"Обновить факт «{self._memory_line(view)}» на «{payload['subject']}: {payload['key']} — {payload['value']}»?\n"
            "Подтверди обычным «да» или выбери «не сейчас»."
        ))

    def _propose_mutation(self, query: str, conversation_id: str, operation: MemoryMutationOperation) -> MemoryIntentResult:
        if self.memory_management is None:
            return MemoryIntentResult(handled=True, response="Изменение памяти сейчас недоступно.")
        matches = self._find_memories(query)
        if len(matches) != 1:
            return self._mutation_lookup_problem(matches, "забыть")
        view = matches[0]
        proposal = self.memory_management.propose(self.proposal_store, operation=operation,
            record_id=view.record_id, conversation_id=conversation_id)
        return MemoryIntentResult(handled=True, response=(
            f"Скрыть из активной памяти: «{self._memory_line(view)}»? Это не удалит историю безвозвратно.\n"
            "Подтверди обычным «да» или выбери «не сейчас»."
        ))

    def _find_memories(self, query: str):
        assert self.memory_management is not None
        return self._rank_records(self.memory_management.list(include_hidden=False), query, self._memory_line)

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(meaningful_tokens(normalize_utterance(value)))

    @staticmethod
    def _stem(token: str) -> str:
        return stem_russian_token(token)

    @classmethod
    def _rank_records(cls, records, query: str, text_getter):
        query_text = normalize_utterance(query.strip().strip("«»\"'").rstrip("."))
        query_tokens = cls._tokens(query_text)
        scored = []
        for record in records:
            candidate = normalize_utterance(str(text_getter(record)))
            candidate_tokens = cls._tokens(candidate)
            overlap = len(query_tokens & candidate_tokens) / max(1, len(query_tokens))
            fuzzy = (
                sum(
                    max((SequenceMatcher(None, left, right).ratio() for right in candidate_tokens), default=0.0)
                    for left in query_tokens
                ) / max(1, len(query_tokens))
            )
            score = 1.0 if query_text and query_text in candidate else max(overlap, fuzzy * 0.92)
            if score >= 0.5:
                scored.append((score, record))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if not scored:
            return []
        best = scored[0][0]
        return [record for score, record in scored if score >= max(0.5, best - 0.12)]

    def _matching_open_commitments(self, query: str, project_id: str):
        if self.memory_management is None:
            return []
        return self._rank_records(
            [
                item
                for item in self.memory_management.list(
                    record_type="commitment", project_id=project_id, include_hidden=False
                )
                if item.payload.get("status") == "open"
            ],
            query,
            lambda item: item.payload.get("text", ""),
        )

    @classmethod
    def _rank_text_rows(cls, rows, query: str, text_getter):
        query_tokens = cls._tokens(query)
        scored = []
        for row in rows:
            candidate_tokens = cls._tokens(text_getter(row))
            overlap = len(query_tokens & candidate_tokens) / max(1, len(query_tokens))
            fuzzy = (
                sum(
                    max(
                        (SequenceMatcher(None, left, right).ratio() for right in candidate_tokens),
                        default=0.0,
                    )
                    for left in query_tokens
                )
                / max(1, len(query_tokens))
            )
            score = max(overlap, fuzzy * 0.92)
            if score >= 0.5:
                scored.append((score, row))
        if not scored:
            return []
        scored.sort(key=lambda pair: pair[0], reverse=True)
        best = scored[0][0]
        return [row for score, row in scored if score >= max(0.5, best - 0.12)]

    @staticmethod
    def _mutation_lookup_problem(matches, verb: str) -> MemoryIntentResult:
        if not matches:
            return MemoryIntentResult(handled=True, response=f"Не нашла в подтверждённой памяти то, что нужно {verb}.")
        return MemoryIntentResult(handled=True, response=f"Нашла несколько похожих записей. Уточни, какую именно нужно {verb}.")

    @staticmethod
    def _memory_line(view) -> str:
        payload = view.payload
        if view.record_type == "fact":
            return f"{payload['subject']}: {payload['key']} — {payload['value']}"
        if view.record_type == "decision":
            return f"решение: {payload['decision']}"
        if view.record_type == "relationship_memory":
            content = payload.get("content")
            return str(content.get("text", payload.get("title", view.record_id))) if isinstance(content, dict) else str(content)
        return payload.get("summary") or payload.get("text") or view.record_id

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
        if normalize_utterance(body) in _GENERIC_CONTINUITY_TEXT:
            return MemoryIntentResult(
                handled=True,
                response="Какую именно тему оставить открытой? Назови её — я не буду создавать отдельную нить из указательного слова.",
            )
        proposal = self.shared_continuity.propose_open_thread(
            self.proposal_store,
            text=body,
            conversation_id=conversation_id,
        )
        return MemoryIntentResult(
            handled=True,
            response=(
                "Оставить это открытой нитью между разговорами?\n"
                f"«{body.strip().rstrip('.')}»\nПодтверди обычным «да» или выбери «не сейчас»."
            ),
        )

    def _propose_resolve_thread(
        self,
        body: str,
        conversation_id: str,
        *,
        display_text: str | None = None,
        human_remove: bool = False,
    ) -> MemoryIntentResult:
        if self.shared_continuity is None:
            return MemoryIntentResult(handled=True, response="Общие нити сейчас недоступны.")
        matches = self._continuity_matches(body)
        if not matches:
            self._continuity_clarifications.pop(conversation_id, None)
            return MemoryIntentResult(handled=True, response="Не нашла такую открытую нить.")
        if len(matches) > 1:
            self._continuity_clarifications[conversation_id] = ContinuityResolveClarification(
                conversation_id=conversation_id,
                candidate_thread_ids=tuple(item.id for item in matches),
                original_query=body.strip(),
            )
            return self._continuity_clarification_response(matches)
        selected = matches[0]
        try:
            proposal = self.shared_continuity.propose_resolve_thread(
                self.proposal_store,
                query=selected.id,
                conversation_id=conversation_id,
            )
        except (LookupError, ValueError):
            self._continuity_clarifications.pop(conversation_id, None)
            return MemoryIntentResult(handled=True, response="Не нашла такую открытую нить.")
        self._continuity_clarifications.pop(conversation_id, None)
        if human_remove:
            return MemoryIntentResult(
                handled=True,
                response=(
                    "Убрать открытую тему:\n"
                    f"«{(display_text or selected.summary).strip()}»?\n"
                    "Подтверди обычным «да» или выбери «не сейчас»."
                ),
            )
        return MemoryIntentResult(
            handled=True,
            response=(
                "Закрыть эту общую нить?\n"
                f"«{(display_text or selected.summary).strip()}»\n"
                "Подтверди обычным «да» или выбери «не сейчас»."
            ),
        )

    def _refine_continuity_resolution(
        self,
        query: str,
        clarification: ContinuityResolveClarification,
    ) -> MemoryIntentResult:
        matches = self._continuity_matches(
            query,
            candidate_ids=set(clarification.candidate_thread_ids),
        )
        if not matches:
            self._continuity_clarifications.pop(clarification.conversation_id, None)
            return MemoryIntentResult(handled=True, response="Не нашла среди этих нитей такую тему.")
        if len(matches) > 1:
            self._continuity_clarifications[clarification.conversation_id] = clarification.model_copy(
                update={"candidate_thread_ids": tuple(item.id for item in matches)}
            )
            return self._continuity_clarification_response(matches)
        return self._propose_resolve_thread(
            matches[0].id,
            clarification.conversation_id,
            display_text=matches[0].summary,
        )

    def _continuity_matches(self, query: str, *, candidate_ids: set[str] | None = None):
        if self.shared_continuity is None:
            return []
        rows = [
            row
            for row in self.shared_continuity.open_follow_ups()
            if candidate_ids is None or row[1].id in candidate_ids
        ]
        exact_id = [row[1] for row in rows if row[1].id == query.strip()]
        if exact_id:
            return exact_id
        return [
            row[1]
            for row in self._rank_text_rows(
                rows,
                query,
                lambda row: f"{row[1].topic} {row[1].summary}",
            )
        ]

    @staticmethod
    def _continuity_clarification_response(matches) -> MemoryIntentResult:
        descriptions = "\n".join(f"— {item.summary}" for item in matches[:5])
        return MemoryIntentResult(
            handled=True,
            response=(
                "Нашла несколько похожих нитей. Уточни, какую закрыть:\n"
                f"{descriptions}"
            ),
        )

    def _active_thread_summary(self, thread_id: str) -> str | None:
        if self.shared_continuity is None:
            return None
        for _, follow_up in self.shared_continuity.open_follow_ups():
            if follow_up.id == thread_id:
                return follow_up.summary
        return None

    def _propose_completion(self, text: str, conversation_id: str) -> MemoryIntentResult:
        if self.memory_management is None:
            return MemoryIntentResult(handled=True, response="Завершение обязательств сейчас недоступно.")
        matches = self._rank_records(
            [view for view in self.memory_management.list(record_type="commitment") if view.payload.get("status") == "open"],
            text,
            lambda item: item.payload["text"],
        )
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
        return MemoryIntentResult(handled=True, response=f"Отметить обязательство выполненным?\n«{view.payload['text']}»\nСтатус: открыто → выполнено.\nПодтверди обычным «да» или выбери «не сейчас».")

    def propose_cancellation_by_id(
            self,
            record_id: str,
            conversation_id: str,
    ) -> MemoryIntentResult:
        """Create a cancellation proposal for one explicitly selected Commitment."""

        if self.memory_management is None:
            return MemoryIntentResult(
                handled=True,
                response="Изменение обязательств сейчас недоступно.",
            )

        view = self.memory_management.get(record_id)

        if view is None or view.record_type != "commitment":
            return MemoryIntentResult(
                handled=True,
                response="Не нашла такое обязательство.",
            )

        if view.payload.get("status") != "open":
            return MemoryIntentResult(
                handled=True,
                response="Это обязательство уже не открыто.",
            )

        payload = dict(view.payload)
        now = self.temporal_engine.clock.now_utc()

        payload.update(
            status="cancelled",
            completed_at=None,
            updated_at=now.isoformat(),
        )

        self.memory_management.propose(
            self.proposal_store,
            operation=MemoryMutationOperation.EDIT,
            record_id=view.record_id,
            conversation_id=conversation_id,
            replacement_payload=payload,
        )

        return MemoryIntentResult(
            handled=True,
            response=(
                "Убрать это дело из активных?\n"
                f"«{view.payload['text']}»\n"
                "Оно останется в истории как больше не актуальное.\n"
                "Подтверди обычным «да» или выбери «не сейчас»."
            ),
        )

    def propose_due_change_by_id(
            self,
            record_id: str,
            conversation_id: str,
            due_at: datetime | None,
    ) -> MemoryIntentResult:
        """Create a proposal that changes only one Commitment due date."""

        if self.memory_management is None:
            raise RuntimeError("commitment mutation is unavailable")

        view = self.memory_management.get(record_id)

        if view is None or view.record_type != "commitment":
            raise KeyError("commitment not found")

        if view.payload.get("status") != "open":
            raise ValueError("commitment is not open")

        now = self.temporal_engine.clock.now_utc()

        resolved_due = None

        if due_at is not None:
            if due_at.tzinfo is None:
                raise ValueError(
                    "commitment due date must be timezone-aware"
                )

            resolved_due = due_at.astimezone(timezone.utc)

            if resolved_due <= now:
                raise ValueError(
                    "new commitment due date must be in the future"
                )

        if (
                resolved_due is None
                and view.payload.get("due_at") is None
        ):
            raise ValueError(
                "commitment already has no due date"
            )

        payload = dict(view.payload)

        payload.update(
            due_at=(
                None
                if resolved_due is None
                else resolved_due.isoformat()
            ),
            updated_at=now.isoformat(),
        )

        self.memory_management.propose(
            self.proposal_store,
            operation=MemoryMutationOperation.EDIT,
            record_id=view.record_id,
            conversation_id=conversation_id,
            replacement_payload=payload,
        )

        if resolved_due is None:
            response = (
                "Оставить это дело без срока?\n"
                f"«{view.payload['text']}»\n"
                "Само дело останется открытым и перейдёт "
                "в «Когда будет время».\n"
                "Подтверди обычным «да» или выбери «не сейчас»."
            )
        else:
            local_due = resolved_due.astimezone(
                self.temporal_engine.home_timezone.tzinfo
            )

            response = (
                "Перенести срок этого дела?\n"
                f"«{view.payload['text']}»\n"
                f"Новый срок: {local_due.strftime('%d.%m.%Y в %H:%M')}.\n"
                "Подтверди обычным «да» или выбери «не сейчас»."
            )

        return MemoryIntentResult(
            handled=True,
            response=response,
        )

    def _propose_conversation_episode(
        self,
        match: re.Match[str],
        *,
        conversation_id: str,
        project_id: str,
        conversation_messages: tuple[ConversationMessage, ...],
    ) -> MemoryIntentResult:
        explicit_topic = (match.group("topic") or match.group("topic_two") or "").strip()
        explicit_topic = explicit_topic.rstrip(".!?")
        evidence = tuple(conversation_messages[:-1][-6:])
        user_evidence = [
            " ".join(message.content.split()).strip()
            for message in evidence
            if message.role.value == "user" and message.content.strip()
        ][-2:]
        if explicit_topic:
            title = f"Разговор про {explicit_topic}"[:120]
            summary = f"В недавнем разговоре обсуждали {explicit_topic}."
            topics = [explicit_topic[:120]]
        elif user_evidence:
            seed = user_evidence[-1].rstrip(".!?")
            title = f"Разговор: {seed}"[:120]
            excerpt = "; затем ".join(item.rstrip(".!?") for item in user_evidence)
            summary = f"В недавнем разговоре обсуждали: {excerpt[:360]}."
            topics = [seed[:120]]
        else:
            title = "Недавний разговор"
            summary = "Сохранили недавний разговор как отдельный эпизод без дополнительных утверждений о фактах."
            topics = ["недавний разговор"]
        now = self._now()
        record = Episode(
            id=f"episode_{uuid4()}",
            title=title,
            summary=summary,
            occurred_at=now,
            source=SourceType.EXPLICIT_USER_INPUT,
            importance=0.7,
            visibility=Visibility.VISIBLE,
            project_ids=[project_id],
            participants=[IdentityCode.MISHA, IdentityCode.MASHA],
            topics=topics,
            produced=EpisodeProduced(
                facts=[], decisions=[], commitments=[], reflections=[], relationship_memories=[], affective_records=[], project_changes=[]
            ),
            updated=EpisodeUpdated(facts=[], decisions=[], commitments=[], continuity_states=[], projects=[]),
            superseded=EpisodeSuperseded(facts=[], decisions=[], commitments=[]),
            related_memory_ids=[],
            created_at=now,
        )
        self.proposal_store.create(MemoryProposal(
            id=str(uuid4()),
            conversation_id=conversation_id,
            record_type="episode",
            record_payload=record.model_dump(mode="json"),
            created_at=now,
            status=ProposalStatus.PENDING,
        ))
        return MemoryIntentResult(
            handled=True,
            response=(
                "Могу сохранить этот разговор как эпизод.\n"
                f"Название: «{record.title}»\n"
                f"Кратко: {record.summary}\n"
                "Сохраняем?"
            ),
        )

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
        try:
            if self._confirmation_postcondition(proposal):
                self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
                return self._confirmation_success(proposal)
        except Exception as error:
            stage = "proposal_validation" if isinstance(error, ValidationError) else "postcondition_check"
            return self._confirmation_failure(error, proposal, save=proposal.operation == "create", stage=stage)

        try:
            if proposal.operation in {"continuity_create", "continuity_update"}:
                if self.shared_continuity is None:
                    return MemoryIntentResult(handled=True, response="Общие нити сейчас недоступны.")
                self.shared_continuity.confirm_proposal(proposal, self.proposal_store)
            elif proposal.operation != "create":
                if self.memory_management is None:
                    return MemoryIntentResult(handled=True, response="Эта операция сейчас недоступна.")
                self.memory_management.confirm_proposal(proposal, self.proposal_store)
            else:
                self.confirmed_memory.confirm(
                    ExplicitMemoryConfirmation(
                        confirmed_by=IdentityCode.MISHA,
                        record=self._record_from_proposal(proposal),
                        proposal_id=proposal.id,
                    )
                )
                if not self._confirmation_postcondition(proposal):
                    raise RuntimeError("confirmed memory postcondition was not satisfied")
                self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
        except Exception as error:
            return self._recover_confirmation(error, proposal)
        return self._confirmation_success(proposal)

    def _confirmation_postcondition(self, proposal: MemoryProposal) -> bool:
        if proposal.operation in {"continuity_create", "continuity_update"}:
            return bool(
                self.shared_continuity is not None
                and self.shared_continuity.proposal_postcondition(proposal) is not None
            )
        if proposal.operation != "create":
            return bool(
                self.memory_management is not None
                and self.memory_management.proposal_postcondition(proposal) is not None
            )
        confirmation = ExplicitMemoryConfirmation(
            confirmed_by=IdentityCode.MISHA,
            record=self._record_from_proposal(proposal),
            proposal_id=proposal.id,
        )
        if not hasattr(self.confirmed_memory, "confirmation_postcondition"):
            return False
        return self.confirmed_memory.confirmation_postcondition(confirmation)

    def _recover_confirmation(
        self,
        error: Exception,
        proposal: MemoryProposal,
    ) -> MemoryIntentResult:
        save = proposal.operation == "create"
        try:
            applied = self._confirmation_postcondition(proposal)
        except Exception as check_error:
            stage = "proposal_validation" if isinstance(check_error, ValidationError) else "postcondition_check"
            return self._confirmation_failure(check_error, proposal, save=save, stage=stage)
        if not applied:
            return self._confirmation_failure(
                error,
                proposal,
                save=save,
                stage="repository_write",
            )
        try:
            self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
        except Exception as status_error:
            return self._confirmation_failure(
                status_error,
                proposal,
                save=save,
                stage="proposal_status",
                mutation_applied=True,
            )
        return self._confirmation_success(proposal)

    def _confirmation_success(self, proposal: MemoryProposal) -> MemoryIntentResult:
        if (
            proposal.record_type == "commitment"
            and proposal.record_payload.get("status") in {"completed", "cancelled"}
            and self._on_commitment_terminal is not None
        ):
            commitment_id = proposal.target_record_id or proposal.record_payload.get("id")
            if isinstance(commitment_id, str) and commitment_id:
                self._on_commitment_terminal(commitment_id)
        if proposal.operation in {"continuity_create", "continuity_update"}:
            response = "Готово. Наша история обновлена."
        elif proposal.operation == MemoryMutationOperation.FORGET.value:
            response = "Готово. Эта запись больше не используется как активная память."
        elif proposal.operation == MemoryMutationOperation.RESTORE.value:
            response = "Готово. Эта запись снова доступна в обычной памяти."
        elif proposal.operation == MemoryMutationOperation.EDIT.value:
            if proposal.record_type == "commitment" and proposal.record_payload.get("status") == "completed":
                response = "Готово, обязательство отмечено выполненным."
            else:
                response = "Готово. Подтверждённая память обновлена."
        elif proposal.operation != "create":
            response = "Готово. Изменение применено."
        else:
            response = "Готово, сохранила."
        return MemoryIntentResult(handled=True, response=response)

    def _confirmation_failure(
        self,
        error: Exception,
        proposal: MemoryProposal,
        *,
        save: bool,
        stage: Literal[
            "proposal_validation",
            "repository_write",
            "postcondition_check",
            "proposal_status",
        ],
        mutation_applied: bool = False,
    ) -> MemoryIntentResult:
        diagnostic = ConfirmationFailureDiagnostic(
            exception_type=type(error).__name__,
            operation=proposal.operation,
            record_type=proposal.record_type,
            proposal_id=proposal.id,
            record_id=proposal.target_record_id or str(proposal.record_payload.get("id") or "") or None,
            stage=stage,
            timestamp=self._now(),
        )
        existing: list[dict] = []
        if self._diagnostic_path.exists():
            try:
                raw = json.loads(self._diagnostic_path.read_text(encoding="utf-8"))
                existing = list(raw.get("failures", []))
            except (OSError, ValueError, TypeError):
                existing = []
        existing.append(diagnostic.model_dump(mode="json"))
        temporary = self._diagnostic_path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps({"failures": existing[-100:]}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self._diagnostic_path)
        except OSError:
            pass
        if mutation_applied:
            return MemoryIntentResult(
                handled=True,
                response=(
                    "Изменение уже применено один раз, но я пока не смогла завершить подтверждение. "
                    "Повтори «Подтверждаю» — я безопасно сверю состояние."
                ),
            )
        verb = "сохранить" if save else "применить"
        return MemoryIntentResult(
            handled=True,
            response=f"Не смогла {verb} изменение. Оно осталось ожидающим подтверждения — можно повторить.",
        )

    def _cancel(self, proposal_id: str | None, conversation_id: str) -> MemoryIntentResult:
        proposal, problem = self._resolve(proposal_id, conversation_id)
        if problem:
            return MemoryIntentResult(handled=True, response=problem)
        assert proposal is not None
        if proposal.status == ProposalStatus.PENDING:
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            if self._proposal_resolves_open_continuity(proposal):
                response = "Хорошо, открытую тему не убираю."
            else:
                response = "Хорошо, не сохраняю."
            return MemoryIntentResult(handled=True, response=response)
        return MemoryIntentResult(handled=True, response="Это предложение уже не ожидает подтверждения.")

    def _proposal_resolves_open_continuity(self, proposal: MemoryProposal) -> bool:
        if proposal.record_type != "continuity_state" or self.shared_continuity is None:
            return False
        open_ids = {
            follow_up.id for _, follow_up in self.shared_continuity.open_follow_ups()
        }
        return any(
            item.get("id") in open_ids and item.get("status") == "resolved"
            for item in proposal.record_payload.get("intended_follow_ups", ())
        )

    def _resolve(self, proposal_id: str | None, conversation_id: str) -> tuple[MemoryProposal | None, str | None]:
        if proposal_id:
            proposal = self.proposal_store.get(proposal_id)
            if proposal is None or proposal.conversation_id != conversation_id:
                return None, "Не вижу такого предложения в этом разговоре."
            return proposal, None
        pending = self.proposal_store.current_for_conversation(conversation_id)
        if pending is not None:
            return pending, None
        if pending is None:
            return None, "Сейчас нет предложения памяти, которое можно подтвердить."

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
        return f"{description} Источник — твоё явное утверждение. Сохраняем?"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
