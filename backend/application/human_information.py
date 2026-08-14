"""Application-owned human information, search and recall boundaries.

Storage records retain their rich domain types.  This module normalizes those
types into the four concepts a person can search or recall without changing
the stored lifecycle itself.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.conversation.human_reference import (
    HumanEntityAction,
    HumanEntityKind,
    HumanEntityRef,
    PresentedEntityRef,
    PresentedEntitySet,
)
from backend.memory.memory_management import MemoryManagementService, MemoryMutationOperation
from backend.memory.memory_models import MemoryDocument
from backend.memory.memory_retriever import ContextLens, MemoryRetrievalRequest
from backend.memory.shared_continuity import (
    is_legacy_developer_follow_up,
    is_readable_continuity_text,
)
from backend.memory.text_normalization import meaningful_tokens, normalize_search_text


class HumanAvailability(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"


class HumanSearchScope(str, Enum):
    ALL = "all"
    HISTORY = "history"
    TASKS = "tasks"


class RecallMode(str, Enum):
    CURRENT = "current"
    RETROSPECTIVE = "retrospective"
    FORGOTTEN_REVIEW = "forgotten_review"


class HumanTimePreset(str, Enum):
    TODAY = "today"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"


class HumanTimeFilter(BaseModel):
    """One optional Home-local time window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    preset: HumanTimePreset | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_window(self):
        explicit = self.start_date is not None or self.end_date is not None
        if self.preset is not None and explicit:
            raise ValueError("use either a preset or an explicit local date range")
        if self.preset is None and not explicit:
            raise ValueError("time filter is empty")
        if explicit and (self.start_date is None or self.end_date is None):
            raise ValueError("explicit local range requires both dates")
        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        return self


class HumanSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = ""
    project_id: str | None = None
    scope: HumanSearchScope = HumanSearchScope.ALL
    mode: RecallMode = RecallMode.RETROSPECTIVE
    time_filter: HumanTimeFilter | None = None
    limit: int = Field(default=20, ge=1, le=100)


class HumanRecallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    project_id: str | None = None
    mode: RecallMode | None = None
    scope: HumanSearchScope | None = None
    recent_user_messages: tuple[str, ...] = ()
    limit: int = Field(default=6, ge=0, le=6)
    memory_budget_chars: int = Field(default=3_600, ge=256, le=3_600)
    max_record_chars: int = Field(default=2_000, ge=128, le=2_000)


class HumanInformationItem(BaseModel):
    """One typed application ref plus human-facing searchable information."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: HumanEntityRef
    kind: HumanEntityKind
    record_type: str = Field(min_length=1)
    label: str = Field(min_length=1)
    searchable_text: str = Field(min_length=1)
    domain_state: str = Field(min_length=1)
    availability: HumanAvailability
    timestamp: AwareDatetime | None
    project_ids: tuple[str, ...]
    current_recall_eligible: bool


class HumanSearchMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item: HumanInformationItem
    relevance: float = Field(ge=0.0, le=1.0)


class HumanSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request: HumanSearchRequest
    matches: tuple[HumanSearchMatch, ...]

    @property
    def items(self) -> tuple[HumanInformationItem, ...]:
        return tuple(match.item for match in self.matches)


class HumanRecallTraceItem(BaseModel):
    """Inspectable internal trace; this object is never compiled for a model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str
    record_type: str
    availability: HumanAvailability
    score: float
    source: str


class HumanRecallResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: RecallMode
    working_context: tuple[dict[str, Any], ...]
    trace: tuple[HumanRecallTraceItem, ...]
    estimated_chars: int = Field(ge=0)

    def as_working_memory(self) -> list[dict[str, Any]]:
        """Wrap safe context for the existing bounded WorkingMemory object."""
        return [
            {"type": "human_information", "data": dict(item), "score": 0.0}
            for item in self.working_context
        ]


_HUMAN_TYPE_LABELS = {
    "fact": "факт",
    "decision": "решение",
    "episode": "эпизод",
    "relationship_memory": "общий момент",
    "commitment": "дело",
    "continuity_follow_up": "тема",
    "reflection": "мнение Маши",
    "continuity_state": "общая нить",
}
_STATE_LABELS = {
    "active": "актуально",
    "superseded": "заменено более новым",
    "cancelled": "отменено",
    "current": "актуально",
    "revised": "пересмотрено",
    "open": "открыто",
    "completed": "завершено",
    "expired": "срок истёк",
    "resolved": "закрыто",
    "snoozed": "отложено",
}
_QUERY_GLUE = {
    "найд", "покаж", "информац", "памят", "вспомн", "прос", "забыт",
    "верн", "сдел", "сделал", "над", "раньш", "прошл", "повод", "касал",
    "касалос", "обсужд", "выбирал", "выбир", "выбор", "расскаж",
}


def select_recall_mode(query: str) -> RecallMode:
    """Choose a deterministic recall mode without a model call."""
    normalized = normalize_search_text(query)
    if any(marker in normalized for marker in (
        "просил тебя забыть", "просил забыть", "забытая память",
        "забытые записи", "что ты забыла", "что я просил не использовать",
    )):
        return RecallMode.FORGOTTEN_REVIEW
    if any(marker in normalized for marker in (
        "помнишь", "раньше", "тогда", "уже сделал", "уже сделала",
        "мы обсуждали", "мы выбирали", "было раньше", "закрытая тема",
    )):
        return RecallMode.RETROSPECTIVE
    return RecallMode.CURRENT


def select_search_scope(query: str, mode: RecallMode) -> HumanSearchScope:
    normalized = normalize_search_text(query)
    if any(marker in normalized for marker in (
        "что я уже сделал", "что мне еще надо сделать", "какие дела",
        "задач", "обязательств", "дело про", "дела про",
    )):
        return HumanSearchScope.TASKS
    if mode is RecallMode.RETROSPECTIVE and any(marker in normalized for marker in (
        "помнишь", "раньше", "обсуждали", "истори",
    )):
        return HumanSearchScope.HISTORY
    return HumanSearchScope.ALL


class HumanInformationService:
    """Aggregate, search and recall human concepts without owning storage."""

    def __init__(
        self,
        repository,
        *,
        memory_management: MemoryManagementService | None = None,
        temporal_engine=None,
        clock: Callable[[], datetime] | None = None,
        proposal_store=None,
        memory_retriever=None,
    ):
        self.repository = repository
        self.memory_management = memory_management or MemoryManagementService(repository)
        self.temporal_engine = temporal_engine
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.proposal_store = proposal_store
        self.memory_retriever = memory_retriever

    def information_items(self) -> tuple[HumanInformationItem, ...]:
        document = self._document()
        items: list[HumanInformationItem] = []
        items.extend(self._fact(item) for item in document.facts)
        items.extend(self._decision(item) for item in document.decisions)
        items.extend(self._episode(item) for item in document.episodes)
        items.extend(self._relationship(item) for item in document.relationship_memories)
        items.extend(self._commitment(item) for item in document.commitments)
        for state in document.continuity_states:
            for follow_up in state.intended_follow_ups:
                if is_legacy_developer_follow_up(follow_up):
                    continue
                if not (
                    is_readable_continuity_text(follow_up.summary)
                    and is_readable_continuity_text(follow_up.reason_to_return)
                ):
                    continue
                items.append(self._follow_up(follow_up))
        return tuple(items)

    def search_for_conversation(
        self,
        *,
        query: str,
        project_id: str | None,
        mode: str,
        scope: str = "all",
        limit: int = 8,
    ) -> HumanSearchResult:
        """Thin injected adapter that avoids a reverse package dependency."""
        return self.search_information(HumanSearchRequest(
            query=query,
            project_id=project_id,
            mode=mode,
            scope=scope,
            limit=limit,
        ))

    def recall_for_conversation(
        self,
        *,
        query: str,
        project_id: str | None,
        recent_user_messages: tuple[str, ...],
        current_records: list[dict[str, Any]],
        context_lens: str,
        limit: int,
        force_current: bool,
    ) -> HumanRecallResult:
        return self.recall_information(
            HumanRecallRequest(
                query=query,
                project_id=project_id,
                mode="current" if force_current else None,
                recent_user_messages=recent_user_messages,
                limit=limit,
            ),
            current_records=current_records,
            context_lens=context_lens,
        )

    def search_information(self, request: HumanSearchRequest) -> HumanSearchResult:
        query_tokens = self._topic_tokens(request.query)
        query_text = normalize_search_text(request.query)
        now = self._now_local()
        scored: list[tuple[float, HumanInformationItem]] = []
        for item in self.information_items():
            if not self._matches_scope(item, request.scope):
                continue
            if request.project_id and item.project_ids and request.project_id not in item.project_ids:
                continue
            if not self._matches_mode(item, request.mode):
                continue
            if request.time_filter is not None and not self._matches_time(item, request.time_filter, now):
                continue
            relevance = self._relevance(query_text, query_tokens, item, now)
            if query_tokens and relevance < 0.24:
                continue
            scored.append((relevance, item))
        scored.sort(
            key=lambda row: (
                -row[0],
                -self._timestamp_number(row[1].timestamp),
                row[1].kind.value,
                row[1].ref.entity_id,
            )
        )
        return HumanSearchResult(
            request=request,
            matches=tuple(
                HumanSearchMatch(item=item, relevance=round(score, 6))
                for score, item in scored[: request.limit]
            ),
        )

    def recall_information(
        self,
        request: HumanRecallRequest,
        *,
        current_records: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
        context_lens: str = "general",
    ) -> HumanRecallResult:
        mode = request.mode or select_recall_mode(request.query)
        contextual_query = self._contextual_query(request.query, request.recent_user_messages)
        scope = request.scope or select_search_scope(request.query, mode)
        if (
            current_records is None
            and mode is RecallMode.CURRENT
            and self.memory_retriever is not None
        ):
            current_records = self.memory_retriever.retrieve(MemoryRetrievalRequest(
                query=contextual_query,
                project_id=request.project_id,
                limit=request.limit,
                lens=ContextLens.GENERAL,
                memory_budget_chars=request.memory_budget_chars,
                max_record_chars=request.max_record_chars,
            ))
        current_records = () if current_records is None else current_records
        candidates: list[tuple[dict[str, Any], HumanRecallTraceItem]] = []
        selected_ids: set[str] = set()

        # CURRENT keeps Query-aware Retrieval as the primary selector. Special
        # lenses remain exactly constrained to their established record types.
        if mode is RecallMode.CURRENT:
            for record in current_records:
                record_id = str(record.get("data", {}).get("id", ""))
                safe = self.humanize_retrieved(record)
                if safe is None:
                    continue
                candidates.append((safe, HumanRecallTraceItem(
                    entity_id=record_id or "internal-current-selection",
                    record_type=str(record.get("type", "information")),
                    availability=HumanAvailability.ACTIVE,
                    score=float(record.get("score", 0.0)),
                    source="query_aware_retrieval",
                )))
                if record_id:
                    selected_ids.add(record_id)

        if context_lens == "general" and (mode is not RecallMode.CURRENT or len(candidates) < request.limit):
            search = self.search_information(HumanSearchRequest(
                query=contextual_query,
                project_id=request.project_id,
                scope=scope,
                mode=mode,
                limit=max(1, request.limit * 3),
            ))
            selected_continuity_state = any(
                record.get("type") == "continuity_state" for record in current_records
            )
            completed_tasks_only = (
                scope is HumanSearchScope.TASKS
                and mode is RecallMode.RETROSPECTIVE
                and any(marker in normalize_search_text(request.query) for marker in (
                    "уже сделал", "уже сделала", "что завершил", "что завершила",
                ))
            )
            for match in search.matches:
                item = match.item
                if completed_tasks_only and item.domain_state != "completed":
                    continue
                if item.ref.entity_id in selected_ids:
                    continue
                if selected_continuity_state and item.kind is HumanEntityKind.THREAD:
                    continue
                candidates.append((self._item_context(item), HumanRecallTraceItem(
                    entity_id=item.ref.entity_id,
                    record_type=item.record_type,
                    availability=item.availability,
                    score=match.relevance,
                    source="human_information_search",
                )))
                selected_ids.add(item.ref.entity_id)

        working: list[dict[str, Any]] = []
        trace: list[HumanRecallTraceItem] = []
        used = 0
        for safe, trace_item in candidates:
            if len(working) >= request.limit:
                break
            estimated = len(json.dumps(safe, ensure_ascii=False, separators=(",", ":"), default=str))
            if estimated > request.max_record_chars:
                continue
            if used + estimated > request.memory_budget_chars:
                continue
            working.append(safe)
            trace.append(trace_item)
            used += estimated
        return HumanRecallResult(
            mode=mode,
            working_context=tuple(working),
            trace=tuple(trace),
            estimated_chars=used,
        )

    def restore_information(self, *, record_id: str, conversation_id: str, proposal_store=None):
        item = next(
            (candidate for candidate in self.information_items() if candidate.ref.entity_id == record_id),
            None,
        )
        if item is None:
            raise KeyError("human information item not found")
        if item.availability is not HumanAvailability.FORGOTTEN:
            raise ValueError("only forgotten information can be restored")
        selected_store = proposal_store or self.proposal_store
        if selected_store is None:
            raise RuntimeError("proposal store is unavailable")
        return self.memory_management.propose(
            selected_store,
            operation=MemoryMutationOperation.RESTORE,
            record_id=record_id,
            conversation_id=conversation_id,
        )

    def presented_entity_set(
        self,
        result: HumanSearchResult,
        *,
        conversation_id: str,
    ) -> PresentedEntitySet | None:
        if not result.matches:
            return None
        return PresentedEntitySet(
            conversation_id=conversation_id,
            source_kind="human_information_search",
            created_at=self._now_utc(),
            items=tuple(
                PresentedEntityRef(
                    ordinal=index,
                    entity_kind=match.item.kind,
                    entity_id=match.item.ref.entity_id,
                    human_label=match.item.label,
                    allowed_actions=match.item.ref.allowed_actions,
                )
                for index, match in enumerate(result.matches, 1)
            ),
        )

    @staticmethod
    def humanize_retrieved(record: dict[str, Any]) -> dict[str, Any] | None:
        data = record.get("data", {})
        record_type = str(record.get("type", ""))
        category = _HUMAN_TYPE_LABELS.get(record_type)
        if category is None:
            return None
        state = _STATE_LABELS.get(str(data.get("status", "")), "доступно")
        occurred = data.get("occurred_at") or data.get("created_at")
        if record_type == "fact":
            content = f"{data.get('subject')}: {data.get('key')} — {data.get('value')}"
        elif record_type == "decision":
            content = f"{data.get('title')}: {data.get('decision')}"
        elif record_type == "commitment":
            content = str(data.get("text", ""))
            occurred = data.get("completed_at") or data.get("created_at")
        elif record_type == "episode":
            content = f"{data.get('title')}: {data.get('summary')}"
        elif record_type == "relationship_memory":
            content_value = data.get("content")
            if isinstance(content_value, dict):
                content_value = content_value.get("text") or " ".join(
                    str(value) for value in content_value.values() if value
                )
            content = f"{data.get('title')}: {content_value}"
        elif record_type == "continuity_state":
            parts = [str(value) for value in data.get("current_focus", []) if is_readable_continuity_text(str(value))]
            parts.extend(
                f"{row.get('summary')}. Зачем вернуться: {row.get('reason_to_return')}"
                for row in data.get("intended_follow_ups", [])
                if row.get("status") == "open"
                and is_readable_continuity_text(str(row.get("summary", "")))
                and is_readable_continuity_text(str(row.get("reason_to_return", "")))
            )
            content = " ".join(parts)
            occurred = None
        else:  # reflection
            content = f"{data.get('text')} {data.get('meaning')}".strip()
        safe: dict[str, Any] = {"category": category, "content": content, "state": state}
        if occurred:
            safe["time"] = str(occurred)
        return safe

    def _document(self) -> MemoryDocument:
        if hasattr(self.repository, "read_document"):
            document = self.repository.read_document()
            if document is None:
                raise ValueError("memory store is empty")
            return document
        if hasattr(self.repository, "data"):
            return MemoryDocument.model_validate(self.repository.data)
        raise TypeError("unsupported memory repository")

    @staticmethod
    def _availability(*, visibility: str, status: str, active_states: set[str]) -> HumanAvailability:
        if visibility == "hidden":
            return HumanAvailability.FORGOTTEN
        return HumanAvailability.ACTIVE if status in active_states else HumanAvailability.ARCHIVED

    @staticmethod
    def _actions(kind: HumanEntityKind, availability: HumanAvailability, status: str) -> tuple[HumanEntityAction, ...]:
        if availability is HumanAvailability.FORGOTTEN:
            return (HumanEntityAction.RESTORE,)
        if kind is HumanEntityKind.THREAD:
            return (HumanEntityAction.RESOLVE_CONTINUITY,) if status == "open" else ()
        if kind is HumanEntityKind.TASK and status == "open":
            return (HumanEntityAction.COMPLETE_TASK, HumanEntityAction.FORGET)
        return (HumanEntityAction.FORGET,)

    def _item(
        self,
        *,
        entity_id: str,
        kind: HumanEntityKind,
        record_type: str,
        label: str,
        searchable_text: str,
        domain_state: str,
        availability: HumanAvailability,
        timestamp: datetime | None,
        project_ids: tuple[str, ...],
    ) -> HumanInformationItem:
        actions = self._actions(kind, availability, domain_state)
        return HumanInformationItem(
            ref=HumanEntityRef(
                entity_kind=kind,
                entity_id=entity_id,
                human_label=label,
                allowed_actions=actions,
            ),
            kind=kind,
            record_type=record_type,
            label=label,
            searchable_text=searchable_text,
            domain_state=domain_state,
            availability=availability,
            timestamp=timestamp,
            project_ids=project_ids,
            current_recall_eligible=availability is HumanAvailability.ACTIVE,
        )

    def _fact(self, item) -> HumanInformationItem:
        availability = self._availability(
            visibility=item.visibility.value,
            status=item.status.value,
            active_states={"active"},
        )
        text = f"{item.subject}: {item.key} — {item.value}"
        return self._item(
            entity_id=item.id, kind=HumanEntityKind.MEMORY, record_type="fact",
            label=text, searchable_text=text, domain_state=item.status.value,
            availability=availability, timestamp=item.created_at,
            project_ids=tuple(item.project_ids),
        )

    def _decision(self, item) -> HumanInformationItem:
        availability = self._availability(
            visibility=item.visibility.value,
            status=item.status.value,
            active_states={"active"},
        )
        text = f"{item.title}: {item.decision}. Причина: {item.reason}"
        return self._item(
            entity_id=item.id, kind=HumanEntityKind.MEMORY, record_type="decision",
            label=f"Решение: {item.decision}", searchable_text=text,
            domain_state=item.status.value, availability=availability,
            timestamp=item.created_at, project_ids=tuple(item.project_ids),
        )

    def _episode(self, item) -> HumanInformationItem:
        availability = self._availability(
            visibility=item.visibility.value,
            status="active",
            active_states={"active"},
        )
        text = f"{item.title}: {item.summary} {' '.join(item.topics)}"
        return self._item(
            entity_id=item.id, kind=HumanEntityKind.HISTORY, record_type="episode",
            label=f"История: {item.summary}", searchable_text=text,
            domain_state="active", availability=availability,
            timestamp=item.occurred_at, project_ids=tuple(item.project_ids),
        )

    def _relationship(self, item) -> HumanInformationItem:
        availability = self._availability(
            visibility=item.visibility.value,
            status=item.status.value,
            active_states={"current"},
        )
        if isinstance(item.content, dict):
            content = str(item.content.get("text") or " ".join(str(value) for value in item.content.values()))
        else:
            content = str(item.content)
        text = f"{item.title}: {content}"
        return self._item(
            entity_id=item.id, kind=HumanEntityKind.HISTORY,
            record_type="relationship_memory", label=f"Наша история: {content}",
            searchable_text=text, domain_state=item.status.value,
            availability=availability, timestamp=item.created_at,
            project_ids=tuple(item.project_ids),
        )

    def _commitment(self, item) -> HumanInformationItem:
        availability = self._availability(
            visibility=item.visibility.value,
            status=item.status.value,
            active_states={"open"},
        )
        state_label = _STATE_LABELS.get(item.status.value, item.status.value)
        timestamp = item.completed_at if item.status.value == "completed" else item.created_at
        return self._item(
            entity_id=item.id, kind=HumanEntityKind.TASK, record_type="commitment",
            label=f"Дело · {state_label}: {item.text}", searchable_text=item.text,
            domain_state=item.status.value, availability=availability,
            timestamp=timestamp, project_ids=tuple(item.project_ids),
        )

    def _follow_up(self, item) -> HumanInformationItem:
        availability = self._availability(
            visibility="visible",
            status=item.status.value,
            active_states={"open"},
        )
        state_label = _STATE_LABELS.get(item.status.value, item.status.value)
        text = f"{item.topic}: {item.summary}. {item.reason_to_return}"
        return self._item(
            entity_id=item.id, kind=HumanEntityKind.THREAD,
            record_type="continuity_follow_up",
            label=f"Тема · {state_label}: {item.summary}", searchable_text=text,
            domain_state=item.status.value, availability=availability,
            # ContinuityFollowUp has no own creation timestamp. Parent state
            # updated_at is deliberately not substituted.
            timestamp=None, project_ids=(),
        )

    @staticmethod
    def _matches_scope(item: HumanInformationItem, scope: HumanSearchScope) -> bool:
        if scope is HumanSearchScope.TASKS:
            return item.kind is HumanEntityKind.TASK
        if scope is HumanSearchScope.HISTORY:
            return item.kind in {HumanEntityKind.MEMORY, HumanEntityKind.HISTORY, HumanEntityKind.THREAD}
        return True

    @staticmethod
    def _matches_mode(item: HumanInformationItem, mode: RecallMode) -> bool:
        if mode is RecallMode.CURRENT:
            return item.availability is HumanAvailability.ACTIVE and item.current_recall_eligible
        if mode is RecallMode.FORGOTTEN_REVIEW:
            return item.availability is HumanAvailability.FORGOTTEN
        return item.availability in {HumanAvailability.ACTIVE, HumanAvailability.ARCHIVED}

    @staticmethod
    def _topic_tokens(query: str) -> tuple[str, ...]:
        return tuple(token for token in meaningful_tokens(query) if token not in _QUERY_GLUE)

    @staticmethod
    def _relevance(
        query_text: str,
        query_tokens: tuple[str, ...],
        item: HumanInformationItem,
        now: datetime,
    ) -> float:
        if not query_tokens:
            return 0.5
        candidate_text = normalize_search_text(item.searchable_text)
        candidate_tokens = set(meaningful_tokens(candidate_text))
        matched = {
            query_token
            for query_token in set(query_tokens)
            if any(
                query_token == candidate_token
                or (
                    min(len(query_token), len(candidate_token)) >= 3
                    and (
                        query_token.startswith(candidate_token)
                        or candidate_token.startswith(query_token)
                    )
                )
                for candidate_token in candidate_tokens
            )
        }
        if not matched:
            return 0.0
        coverage = len(matched) / len(set(query_tokens))
        record_coverage = len(matched) / max(1, min(len(candidate_tokens), 8))
        phrase = 1.0 if query_text and query_text in candidate_text else 0.0
        recency = 0.0
        if item.timestamp is not None:
            age_days = max(0.0, (now.astimezone(timezone.utc) - item.timestamp.astimezone(timezone.utc)).total_seconds() / 86_400)
            recency = 1.0 if age_days <= 7 else 0.5 if age_days <= 30 else 0.0
        return min(1.0, coverage * 0.68 + record_coverage * 0.17 + phrase * 0.10 + recency * 0.05)

    def _matches_time(self, item: HumanInformationItem, value: HumanTimeFilter, now: datetime) -> bool:
        if item.timestamp is None:
            return False
        if value.preset is HumanTimePreset.TODAY:
            start_date = end_date = now.date()
        elif value.preset is HumanTimePreset.LAST_7_DAYS:
            start_date, end_date = now.date() - timedelta(days=6), now.date()
        elif value.preset is HumanTimePreset.LAST_30_DAYS:
            start_date, end_date = now.date() - timedelta(days=29), now.date()
        else:
            assert value.start_date is not None and value.end_date is not None
            start_date, end_date = value.start_date, value.end_date
        local = item.timestamp.astimezone(now.tzinfo)
        return start_date <= local.date() <= end_date

    @staticmethod
    def _contextual_query(query: str, recent: tuple[str, ...]) -> str:
        normalized = normalize_search_text(query)
        if not any(marker in normalized for marker in (
            "по этому поводу", "насчет этого", "про это", "с этим",
        )):
            return query
        previous = next((value for value in reversed(recent[-3:]) if meaningful_tokens(value)), "")
        return f"{query} {previous}".strip()

    @staticmethod
    def _item_context(item: HumanInformationItem) -> dict[str, Any]:
        value: dict[str, Any] = {
            "category": _HUMAN_TYPE_LABELS[item.record_type],
            "content": item.label,
            "state": _STATE_LABELS.get(item.domain_state, "доступно"),
        }
        if item.timestamp is not None:
            value["time"] = item.timestamp.isoformat()
        return value

    def _now_local(self) -> datetime:
        if self.temporal_engine is not None:
            return self.temporal_engine.now_local()
        return self._clock().astimezone()

    def _now_utc(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _timestamp_number(value: datetime | None) -> float:
        return -math.inf if value is None else value.timestamp()
