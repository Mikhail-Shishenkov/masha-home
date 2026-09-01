"""Pure Natural Language Router V2 interpretation foundation.

This module discovers descriptive candidates only.  It cannot execute a Home
operation, grant authority, ask a clarification question, or persist state.
Dialogue Core is the production owner for adopted conversational operations;
legacy capability services remain implementation adapters or non-overlapping
compatibility routes while their migrations are incomplete.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.application.capability_catalog import (
    CapabilityCatalog,
    CapabilityNotFoundError,
)
from backend.connectors.google_drive.document_create import (
    drive_document_create_intent,
)
from backend.connectors.provider_language import normalize_explicit_provider
from backend.connectors.yandex_mail.intent import mail_intent
from backend.temporal.duration_resolution import HomeDurationResolver
from backend.temporal.temporal_engine import TemporalEngine

from .capability_router import normalize_utterance


_OPERATION_ID = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_SLOT_NAME = r"^[a-z][a-z0-9_]{0,63}$"


class StrictInterpretationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InterpretationResolutionState(str, Enum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"
    ORDINARY_CONVERSATION = "ordinary_conversation"
    UNSUPPORTED_ACTION = "unsupported_action"


class InterpretationAmbiguity(str, Enum):
    NONE = "none"
    CAPABILITY = "capability"
    SLOT = "slot"
    REFERENT = "referent"
    PROVIDER_SCOPE = "provider_scope"


class InterpretationValueOrigin(str, Enum):
    EXPLICIT = "explicit"
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"
    FOLLOW_UP_SEMANTIC = "follow_up_semantic"
    TEMPORAL_NORMALIZED = "temporal_normalized"
    UNRESOLVED = "unresolved"


class CandidateEvidenceSource(str, Enum):
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"


class InterpretationSlot(StrictInterpretationModel):
    name: str = Field(pattern=_SLOT_NAME)
    value: str | None = Field(default=None, max_length=20_000)
    origin: InterpretationValueOrigin

    @model_validator(mode="after")
    def unresolved_value_is_empty(self):
        if self.origin is InterpretationValueOrigin.UNRESOLVED and self.value is not None:
            raise ValueError("unresolved slot cannot contain a value")
        if self.origin is not InterpretationValueOrigin.UNRESOLVED and not self.value:
            raise ValueError("resolved slot requires a value")
        return self


class InterpretationReferent(StrictInterpretationModel):
    expression: str = Field(min_length=1, max_length=300)
    value: str | None = Field(default=None, max_length=500)
    origin: InterpretationValueOrigin = InterpretationValueOrigin.UNRESOLVED

    @model_validator(mode="after")
    def unresolved_referent_has_no_invented_value(self):
        if self.origin is InterpretationValueOrigin.UNRESOLVED and self.value is not None:
            raise ValueError("unresolved referent cannot contain a value")
        if self.origin is not InterpretationValueOrigin.UNRESOLVED and not self.value:
            raise ValueError("resolved referent requires a value")
        return self


class CandidateEvidence(StrictInterpretationModel):
    signal: str = Field(min_length=1, max_length=200)
    source: CandidateEvidenceSource = CandidateEvidenceSource.DETERMINISTIC


class CapabilityCandidate(StrictInterpretationModel):
    """A plausible canonical operation, never permission or execution authority."""

    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    evidence: tuple[CandidateEvidence, ...] = Field(min_length=1, max_length=8)
    slot_names: tuple[str, ...] = Field(default=(), max_length=16)
    missing_slots: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def slot_names_are_bounded_and_unique(self):
        values = (*self.slot_names, *self.missing_slots)
        if any(re.fullmatch(_SLOT_NAME, item) is None for item in values):
            raise ValueError("candidate slot name is invalid")
        if len(self.slot_names) != len(set(self.slot_names)):
            raise ValueError("candidate contains duplicate slot names")
        if len(self.missing_slots) != len(set(self.missing_slots)):
            raise ValueError("candidate contains duplicate missing slots")
        return self


class InterpretationFrame(StrictInterpretationModel):
    original_utterance: str = Field(min_length=1, max_length=20_000)
    normalized_goal: str | None = Field(default=None, max_length=500)
    candidates: tuple[CapabilityCandidate, ...] = Field(default=(), max_length=8)
    slots: tuple[InterpretationSlot, ...] = Field(default=(), max_length=24)
    missing_slots: tuple[str, ...] = Field(default=(), max_length=24)
    referents: tuple[InterpretationReferent, ...] = Field(default=(), max_length=8)
    ambiguity: InterpretationAmbiguity = InterpretationAmbiguity.NONE
    resolution_state: InterpretationResolutionState

    @model_validator(mode="after")
    def state_matches_structure(self):
        operation_ids = [item.operation_id for item in self.candidates]
        slot_names = [item.name for item in self.slots]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("interpretation contains duplicate candidates")
        if len(slot_names) != len(set(slot_names)):
            raise ValueError("interpretation contains duplicate slots")
        if len(self.missing_slots) != len(set(self.missing_slots)):
            raise ValueError("interpretation contains duplicate missing slots")
        if self.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION:
            if self.candidates or self.slots or self.missing_slots or self.referents:
                raise ValueError("ordinary conversation cannot contain capability structure")
            if self.ambiguity is not InterpretationAmbiguity.NONE:
                raise ValueError("ordinary conversation cannot be ambiguous")
        if self.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION:
            if self.candidates or self.slots or self.missing_slots or self.referents:
                raise ValueError("unsupported action cannot carry supported capability structure")
            if self.ambiguity is not InterpretationAmbiguity.NONE:
                raise ValueError("unsupported action cannot be ambiguous")
        if self.resolution_state is InterpretationResolutionState.RESOLVED:
            if len(self.candidates) != 1 or self.missing_slots or self.ambiguity is not InterpretationAmbiguity.NONE:
                raise ValueError("resolved interpretation requires one complete unambiguous candidate")
            if any(item.origin is InterpretationValueOrigin.UNRESOLVED for item in self.referents):
                raise ValueError("resolved interpretation cannot contain unresolved referents")
        if self.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED:
            if not self.candidates:
                raise ValueError("clarification requires at least one candidate")
            if self.ambiguity is InterpretationAmbiguity.NONE:
                raise ValueError("clarification must identify its ambiguity")
        return self


class InterpretationSpecification(StrictInterpretationModel):
    """User-meaning requirements, deliberately separate from provider schemas."""

    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    required_slots: tuple[str, ...] = Field(default=(), max_length=16)
    purpose: str = Field(
        default="",
        max_length=500,
        description="Human semantic purpose only; never authority or credentials.",
    )
    operation_kind: str | None = Field(default=None, max_length=80)
    selection_evidence_meaning: str | None = Field(default=None, max_length=300)
    selection_evidence_examples: tuple[str, ...] = Field(default=(), max_length=6)
    selection_evidence_terms: tuple[str, ...] = Field(default=(), max_length=6)
    slots: tuple["InterpretationSlotSpecification", ...] = Field(
        default=(), max_length=16,
    )
    operation_selection_group: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )

    @model_validator(mode="after")
    def required_slots_are_valid_and_unique(self):
        if any(re.fullmatch(_SLOT_NAME, item) is None for item in self.required_slots):
            raise ValueError("required slot name is invalid")
        if len(self.required_slots) != len(set(self.required_slots)):
            raise ValueError("interpretation specification repeats a required slot")
        slot_names = [item.name for item in self.slots]
        if len(slot_names) != len(set(slot_names)):
            raise ValueError("interpretation specification repeats a slot")
        declared_required = {item.name for item in self.slots if item.required}
        if declared_required and declared_required != set(self.required_slots):
            raise ValueError("slot metadata must match required slots")
        return self

    def slot_specification(self, name: str) -> "InterpretationSlotSpecification | None":
        return next((item for item in self.slots if item.name == name), None)


class InterpretationSlotSpecification(StrictInterpretationModel):
    """Descriptive slot contract supplied to local language understanding."""

    name: str = Field(pattern=_SLOT_NAME, max_length=64)
    meaning: str = Field(min_length=1, max_length=300)
    required: bool = True
    normalizer: str | None = Field(default=None, max_length=80)
    default_value: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def defaults_are_only_for_optional_slots(self):
        if self.required and self.default_value is not None:
            raise ValueError("required slot cannot declare a default")
        return self


class InterpretationSpecificationError(RuntimeError):
    pass


class InterpretationSpecificationRegistry:
    def __init__(
        self,
        *,
        catalog: CapabilityCatalog,
        specifications: Iterable[InterpretationSpecification] = (),
    ):
        self._catalog = catalog
        self._items: dict[str, InterpretationSpecification] = {}
        for specification in specifications:
            self.register(specification)

    def register(self, specification: InterpretationSpecification) -> InterpretationSpecification:
        try:
            self._catalog.get(specification.operation_id)
        except CapabilityNotFoundError as error:
            raise InterpretationSpecificationError(specification.operation_id) from error
        if specification.operation_id in self._items:
            raise InterpretationSpecificationError(specification.operation_id)
        self._items[specification.operation_id] = specification
        return specification

    def get(self, operation_id: str) -> InterpretationSpecification:
        try:
            return self._items[operation_id]
        except KeyError as error:
            raise InterpretationSpecificationError(operation_id) from error

    @property
    def operation_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))


def default_interpretation_specifications() -> tuple[InterpretationSpecification, ...]:
    return (
        InterpretationSpecification(
            operation_id="web.search",
            required_slots=("query",),
            purpose="find publicly available information on the web",
            operation_kind="read",
            slots=(InterpretationSlotSpecification(name="query", meaning="what to search for", normalizer="text"),),
        ),
        InterpretationSpecification(
            operation_id="web.fetch",
            required_slots=("target",),
            purpose="read one already selected public web source",
            operation_kind="read",
            slots=(InterpretationSlotSpecification(name="target", meaning="selected source reference", normalizer="source_reference"),),
        ),
        InterpretationSpecification(
            operation_id="google_calendar.read",
            required_slots=("period",),
            purpose=(
                "показать события или расписание Google Calendar за явно "
                "запрошенный период; это не входящие письма и не файлы"
            ),
            operation_kind="read",
            slots=(InterpretationSlotSpecification(
                name="period",
                meaning="explicit requested calendar window such as today, tomorrow, a weekday, or one week",
                normalizer="calendar_period",
            ),),
        ),
        InterpretationSpecification(
            operation_id="google_calendar.event.create",
            required_slots=("subject", "date", "time"),
            purpose="create one calendar event",
            operation_kind="create",
            selection_evidence_meaning="человек прямо просит добавить или поставить это именно в календарь",
            selection_evidence_examples=("в календарь", "в моём календаре"),
            selection_evidence_terms=("календар",),
            slots=(
                InterpretationSlotSpecification(name="subject", meaning="event title or what happens", normalizer="text"),
                InterpretationSlotSpecification(name="date", meaning="local calendar day", normalizer="date"),
                InterpretationSlotSpecification(name="time", meaning="local event start time", normalizer="time"),
                InterpretationSlotSpecification(name="duration_minutes", meaning="event length in minutes", required=False, normalizer="duration", default_value="60"),
            ),
            operation_selection_group="personal_scheduling",
        ),
        InterpretationSpecification(
            operation_id="google_drive.document.create",
            required_slots=("content",),
            purpose="create a Google document from explicitly supplied material",
            operation_kind="create",
            slots=(InterpretationSlotSpecification(name="content", meaning="document source material", normalizer="protected_content"),),
        ),
        InterpretationSpecification(
            operation_id="google_calendar.event.update",
            required_slots=("subject", "date", "time"),
            purpose="change one identified calendar event",
            operation_kind="update",
            selection_evidence_meaning="человек прямо просит изменить, перенести или сдвинуть уже существующее событие",
            selection_evidence_examples=("перенеси", "измени", "сдвинь"),
            selection_evidence_terms=("перенес", "измен", "сдвин"),
            slots=(
                InterpretationSlotSpecification(name="subject", meaning="human description of the existing event to change, expressed as a noun or infinitive phrase", normalizer="text"),
                InterpretationSlotSpecification(name="date", meaning="local day on which to look up the existing event", normalizer="date"),
                InterpretationSlotSpecification(name="time", meaning="new local start time", normalizer="time"),
                InterpretationSlotSpecification(name="old_time", meaning="current start time when explicitly supplied", required=False, normalizer="time"),
                InterpretationSlotSpecification(name="duration_minutes", meaning="new event length when explicitly supplied", required=False, normalizer="duration"),
            ),
        ),
        InterpretationSpecification(
            operation_id="google_calendar.event.delete",
            required_slots=("subject", "date"),
            purpose="удалить одно уже существующее событие из Google Calendar",
            operation_kind="update",
            slots=(
                InterpretationSlotSpecification(
                    name="subject",
                    meaning="human description of the existing calendar event to delete",
                    normalizer="text",
                ),
                InterpretationSlotSpecification(
                    name="date",
                    meaning="local day on which to find the event",
                    normalizer="date",
                ),
                InterpretationSlotSpecification(
                    name="time",
                    meaning="current event start time when explicitly supplied",
                    required=False,
                    normalizer="time",
                ),
            ),
        ),
        InterpretationSpecification(
            operation_id="google_drive.read",
            required_slots=("mode",),
            purpose=(
                "прочитать, найти, показать или вывести ограниченный список файлов "
                "в Google Drive; сюда относится просьба о недавних файлах"
            ),
            operation_kind="read",
            slots=(
                InterpretationSlotSpecification(
                    name="mode",
                    meaning="requested file action: list, recent, search, or read",
                    normalizer="file_read_mode",
                ),
                InterpretationSlotSpecification(
                    name="query",
                    meaning="explicit filename or search topic, without provider/action words",
                    required=False,
                    normalizer="text",
                ),
                InterpretationSlotSpecification(
                    name="target",
                    meaning="one explicitly referenced already presented file",
                    required=False,
                    normalizer="presented_reference",
                ),
            ),
        ),
        InterpretationSpecification(
            operation_id="home.timed_commitments",
            required_slots=("subject", "date", "time"),
            purpose="create one Home reminder for a timed task",
            operation_kind="create",
            selection_evidence_meaning="человек прямо просит напомнить или не дать ему забыть",
            selection_evidence_examples=("напомни", "не дай забыть", "не дай мне забыть", "для Дома"),
            selection_evidence_terms=("напомн", "заб", "дом"),
            slots=(
                InterpretationSlotSpecification(name="subject", meaning="what to remember", normalizer="text"),
                InterpretationSlotSpecification(name="date", meaning="local due day", normalizer="date"),
                InterpretationSlotSpecification(name="time", meaning="local due time", normalizer="time"),
            ),
            operation_selection_group="personal_scheduling",
        ),
        InterpretationSpecification(
            operation_id="yandex_mail.read",
            purpose=(
                "проверить или показать почту, новые/непрочитанные письма, либо "
                "прочитать конкретное уже показанное письмо; «что пришло» означает "
                "входящие сообщения, а не календарные события"
            ),
            operation_kind="read",
            slots=(
                InterpretationSlotSpecification(
                    name="view",
                    meaning=(
                        "which mailbox view was requested: unread/new, recent, "
                        "today, or important"
                    ),
                    required=False,
                    normalizer="mail_view",
                    default_value="unread",
                ),
                InterpretationSlotSpecification(
                    name="sender",
                    meaning="explicit human sender to search for",
                    required=False,
                    normalizer="text",
                ),
                InterpretationSlotSpecification(
                    name="topic",
                    meaning="explicit mail subject or topic to search for",
                    required=False,
                    normalizer="text",
                ),
                InterpretationSlotSpecification(
                    name="target",
                    meaning="one explicitly referenced already presented message",
                    required=False,
                    normalizer="presented_reference",
                ),
            ),
        ),
        InterpretationSpecification(
            operation_id="yandex_mail.message.delete",
            required_slots=("target",),
            purpose=(
                "переместить в корзину одно реально показанное письмо; "
                "это изменение существующего письма, не чтение"
            ),
            operation_kind="update",
            slots=(InterpretationSlotSpecification(
                name="target",
                meaning="one explicit reference to an already presented email",
                normalizer="presented_reference",
            ),),
        ),
        InterpretationSpecification(
            operation_id="yandex_mail.message.move",
            required_slots=("target",),
            purpose=(
                "переместить в архив одно реально показанное письмо; "
                "произвольные папки пока не поддерживаются"
            ),
            operation_kind="update",
            slots=(InterpretationSlotSpecification(
                name="target",
                meaning="one explicit reference to an already presented email",
                normalizer="presented_reference",
            ),),
        ),
        InterpretationSpecification(
            operation_id="yandex_disk.read",
            required_slots=("mode",),
            purpose=(
                "прочитать, найти, показать или вывести ограниченный список файлов "
                "на Яндекс Диске; сюда относится просьба о недавних файлах"
            ),
            operation_kind="read",
            slots=(
                InterpretationSlotSpecification(
                    name="mode",
                    meaning="requested file action: list, recent, search, or read",
                    normalizer="file_read_mode",
                ),
                InterpretationSlotSpecification(
                    name="query",
                    meaning="explicit filename or search topic, without provider/action words",
                    required=False,
                    normalizer="text",
                ),
                InterpretationSlotSpecification(
                    name="target",
                    meaning="one explicitly referenced already presented file",
                    required=False,
                    normalizer="presented_reference",
                ),
            ),
        ),
        InterpretationSpecification(
            operation_id="home.commitments",
            purpose="показать или найти уже существующие домашние дела и задачи",
            operation_kind="read",
            slots=(InterpretationSlotSpecification(
                name="query", meaning="optional task filter", required=False, normalizer="text",
            ),),
        ),
        InterpretationSpecification(
            operation_id="home.commitments.create",
            required_slots=("subject",),
            purpose="добавить новое домашнее дело без конкретных даты и времени",
            operation_kind="create",
            slots=(InterpretationSlotSpecification(
                name="subject", meaning="the task to add", normalizer="text",
            ),),
        ),
        InterpretationSpecification(
            operation_id="home.commitments.complete",
            required_slots=("target",),
            purpose="отметить одно существующее домашнее дело выполненным",
            operation_kind="update",
            slots=(InterpretationSlotSpecification(
                name="target", meaning="the existing task to complete", normalizer="text",
            ),),
        ),
        InterpretationSpecification(operation_id="home.proactive_reminders", purpose="inspect Home reminders", operation_kind="read"),
        InterpretationSpecification(
            operation_id="home.memory.recall",
            purpose=(
                "ответить, что Маша подтверждённо помнит о человеке или теме; "
                "это человеческий recall, не административный список памяти"
            ),
            operation_kind="read",
            slots=(InterpretationSlotSpecification(
                name="query",
                meaning="explicit topic to recall, if one was named",
                required=False,
                normalizer="text",
            ),),
        ),
        InterpretationSpecification(
            operation_id="home.memory.inspect",
            purpose="показать или найти сохранённые записи как административный список",
            operation_kind="read",
            slots=(InterpretationSlotSpecification(
                name="query",
                meaning="explicit filter for saved information",
                required=False,
                normalizer="text",
            ),),
        ),
        InterpretationSpecification(
            operation_id="home.memory.remember",
            required_slots=("memory_content",),
            purpose="сохранить явно названный факт, решение или эпизод в подтверждённой памяти",
            operation_kind="create",
            slots=(
                InterpretationSlotSpecification(
                    name="memory_content",
                    meaning="the exact information to remember, without a leading speech complementizer",
                    normalizer="memory_content",
                ),
                InterpretationSlotSpecification(
                    name="record_kind", meaning="fact, decision, or episode when explicitly stated", required=False, normalizer="text",
                ),
            ),
        ),
        InterpretationSpecification(
            operation_id="home.memory.forget",
            required_slots=("target",),
            purpose=(
                "забыть по просьбе пользователя, то есть скрыть одно существующее "
                "подтверждённое воспоминание без удаления других записей"
            ),
            operation_kind="update",
            slots=(InterpretationSlotSpecification(
                name="target",
                meaning="the explicitly named existing memory or fact to forget",
                normalizer="text",
            ),),
        ),
        InterpretationSpecification(
            operation_id="home.continuity.read",
            purpose=(
                "показать общую историю, сохранённые моменты или открытые темы, "
                "к которым Миша и Маша хотели вернуться"
            ),
            operation_kind="read",
            slots=(InterpretationSlotSpecification(
                name="query",
                meaning="explicit history or open-thread topic filter",
                required=False,
                normalizer="text",
            ),),
        ),
        InterpretationSpecification(
            operation_id="home.continuity.open",
            required_slots=("topic",),
            purpose="оставить явно названную тему открытой между разговорами",
            operation_kind="create",
            slots=(InterpretationSlotSpecification(
                name="topic", meaning="the discussion topic to keep open", normalizer="text",
            ),),
        ),
        InterpretationSpecification(
            operation_id="home.continuity.resolve",
            required_slots=("target",),
            purpose="закрыть одну существующую открытую тему",
            operation_kind="update",
            slots=(InterpretationSlotSpecification(
                name="target", meaning="the existing open topic to close", normalizer="text",
            ),),
        ),
    )


_CALENDAR_EXPLICIT = re.compile(r"^(?:поставь|запланируй|создай)\b")
_CALENDAR_STRUCTURAL = re.compile(
    r"^(?:добавь|внеси)\b.*\b(?:в\s+)?календар(?:ь|е)\b"
)
_CALENDAR_DESTINATION = re.compile(r"\b(?:в\s+)?календар(?:ь|е)\b")
_SCHEDULE_AMBIGUOUS = re.compile(r"^запиши\b")
_REMINDER_EXPLICIT = re.compile(r"^(?:напомни|создай\s+напоминание|поставь\s+напоминание)\b")
_SAVE_REFERENTIAL = re.compile(r"^сохрани\s+(?P<referent>это|этот\s+текст|эту\s+заметку)$")
_MAIL_READ = re.compile(r"^(?:посмотри|проверь)\s+(?:мою\s+)?почту$")
_DATE = re.compile(r"\b(?P<date>сегодня|завтра)\b", re.IGNORECASE)
_TIME = re.compile(
    r"\b(?:в|на)\s*(?P<hour>\d{1,2})(?:(?::|\s)(?P<minute>\d{2}))?\b",
    re.IGNORECASE,
)
_DURATION_TEXT = re.compile(
    r"\bна\s+(?:(?:\d{1,3}|один|одна|одну|два|две|три|четыре|пять|шесть|"
    r"семь|восемь|девять|десять|одиннадцать|двенадцать)\s+)?"
    r"(?:час(?:а|ов)?|минут(?:у|ы)?)\b",
    re.IGNORECASE,
)
_RELATIVE_DUE = re.compile(
    r"\bчерез\s+\d+\s+(?:дн(?:я|ей)?|час(?:а|ов)?|минут(?:у|ы)?)\b|"
    r"\bчерез\s+неделю\b",
    re.IGNORECASE,
)


class CapabilityCandidateDiscovery:
    """Deterministic, side-effect-free V2 candidate discovery for Slice 2A."""

    def __init__(
        self,
        *,
        catalog: CapabilityCatalog,
        specifications: Iterable[InterpretationSpecification] | None = None,
        temporal_engine: TemporalEngine | None = None,
    ):
        self.catalog = catalog
        self.temporal_engine = temporal_engine
        self.specifications = InterpretationSpecificationRegistry(
            catalog=catalog,
            specifications=(
                default_interpretation_specifications()
                if specifications is None
                else specifications
            ),
        )

    def bind_temporal_engine(self, temporal_engine: TemporalEngine) -> None:
        """Refresh the injected Home clock without changing interpretation state."""

        self.temporal_engine = temporal_engine

    def interpret(
        self,
        utterance: str,
        *,
        turn_context=None,
    ) -> InterpretationFrame:
        original = utterance.strip()
        if not original:
            raise ValueError("utterance must not be empty")
        text = normalize_utterance(original)

        document = self._document_candidate(original)
        if document is not None:
            return self._frame(original, (document[0],), document[1], ())

        candidates: list[CapabilityCandidate] = []
        slots = self._temporal_slots(text)
        if _REMINDER_EXPLICIT.search(text):
            subject = self._schedule_subject(original)
            if subject is not None:
                slots = (*slots, InterpretationSlot(
                    name="subject", value=subject,
                    origin=InterpretationValueOrigin.DETERMINISTIC,
                ))
            candidate = self._candidate(
                "home.timed_commitments", slots,
                "explicit_home_reminder_language",
            )
            if candidate is not None:
                candidates.append(candidate)
        elif (
            (_CALENDAR_EXPLICIT.search(text) or _SCHEDULE_AMBIGUOUS.search(text))
            and _CALENDAR_DESTINATION.search(text)
        ) or _CALENDAR_STRUCTURAL.search(text):
            subject = self._schedule_subject(original)
            if subject is not None:
                slots = (*slots, InterpretationSlot(
                    name="subject", value=subject,
                    origin=InterpretationValueOrigin.DETERMINISTIC,
                ))
            candidate = self._candidate(
                "google_calendar.event.create", slots,
                "explicit_calendar_create_language",
            )
            if candidate is not None:
                candidates.append(candidate)
        elif _CALENDAR_EXPLICIT.search(text) or _SCHEDULE_AMBIGUOUS.search(text):
            subject = self._schedule_subject(original)
            if subject is not None:
                slots = (*slots, InterpretationSlot(
                    name="subject", value=subject,
                    origin=InterpretationValueOrigin.DETERMINISTIC,
                ))
            for operation_id in (
                "google_calendar.event.create",
                "home.timed_commitments",
            ):
                candidate = self._candidate(
                    operation_id, slots, "ambiguous_schedule_language",
                )
                if candidate is not None:
                    candidates.append(candidate)

        if not candidates and (
            _MAIL_READ.fullmatch(text) is not None or mail_intent(original) is not None
        ):
            candidate = self._candidate(
                "yandex_mail.read", (), "explicit_mail_read_language",
            )
            if candidate is not None:
                candidates.append(candidate)

        referents: tuple[InterpretationReferent, ...] = ()
        save = _SAVE_REFERENTIAL.fullmatch(text)
        if not candidates and save is not None:
            referents = (InterpretationReferent(expression=save.group("referent")),)
            for operation_id in (
                "google_drive.document.create",
                "home.timed_commitments",
            ):
                candidate = self._candidate(
                    operation_id, (), "unscoped_save_with_unresolved_referent",
                )
                if candidate is not None:
                    candidates.append(candidate)

        return self._frame(original, tuple(candidates), slots if candidates else (), referents)

    def _document_candidate(
        self,
        utterance: str,
    ) -> tuple[CapabilityCandidate, tuple[InterpretationSlot, ...]] | None:
        if not drive_document_create_intent(utterance):
            return None
        _, delimiter, material = utterance.partition(":")
        slots = [InterpretationSlot(
            name="target", value="google_drive",
            origin=InterpretationValueOrigin.EXPLICIT,
        )]
        if delimiter and material.strip():
            slots.append(InterpretationSlot(
                name="content", value=material.strip(),
                origin=InterpretationValueOrigin.EXPLICIT,
            ))
        candidate = self._candidate(
            "google_drive.document.create", tuple(slots),
            "explicit_google_drive_document_create",
        )
        return None if candidate is None else (candidate, tuple(slots))

    def _temporal_slots(self, text: str) -> tuple[InterpretationSlot, ...]:
        slots: list[InterpretationSlot] = []
        if self.temporal_engine is not None:
            _, due = self.temporal_engine.extract_due(text)
            if due is None and (relative := _RELATIVE_DUE.search(text)) is not None:
                due = self.temporal_engine.parse_due(relative.group(0))
            if due is not None and due.resolved_local is not None and due.ambiguity is None:
                local = due.resolved_local
                return (
                    InterpretationSlot(
                        name="date",
                        value=local.date().isoformat(),
                        origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
                    ),
                    InterpretationSlot(
                        name="time",
                        value=local.strftime("%H:%M"),
                        origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
                    ),
                )
        date = _DATE.search(text)
        if date is not None:
            slots.append(InterpretationSlot(
                name="date", value=date.group("date"),
                origin=InterpretationValueOrigin.EXPLICIT,
            ))
        time = _TIME.search(text)
        if time is not None:
            hour = int(time.group("hour"))
            minute = int(time.group("minute") or 0)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                slots.append(InterpretationSlot(
                    name="time", value=f"{hour:02d}:{minute:02d}",
                    origin=InterpretationValueOrigin.DETERMINISTIC,
                ))
        duration = HomeDurationResolver().resolve(text)
        if duration is not None and duration.minutes is not None:
            slots.append(InterpretationSlot(
                name="duration_minutes",
                value=duration.canonical,
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            ))
        return tuple(slots)

    @staticmethod
    def _schedule_subject(text: str) -> str | None:
        # In constructions such as "добавь запись ..., что я буду учиться"
        # the subordinate clause is the human meaning of the calendar entry.
        # This is structural payload segmentation, not intent classification.
        clauses = re.split(r"\bчто\b", text, flags=re.IGNORECASE)
        if len(clauses) > 1:
            text = clauses[-1]
            text = re.sub(r"^\s*я\s+(?:буду\s+)?", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"^\s*маш(?:а|енька)?\s*[,!:-]?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        subject = re.sub(
            r"^(?:поставь|запланируй|создай|запиши|напомни|"
            r"создай\s+напоминание|поставь\s+напоминание|добавь|внеси)"
            r"\s*[:,—-]?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        subject = _DATE.sub("", subject)
        subject = _TIME.sub("", subject)
        subject = _DURATION_TEXT.sub("", subject)
        subject = _RELATIVE_DUE.sub("", subject)
        subject = re.sub(
            r"\b(?:в|на)\s+календар(?:ь|е)\b", "", subject, flags=re.IGNORECASE
        )
        subject = re.sub(r"\bнапоминание\b", "", subject, flags=re.IGNORECASE)
        subject = re.sub(r"^\s*запись\s+", "", subject, flags=re.IGNORECASE)
        subject = re.sub(r"\s+", " ", subject).strip(" ,.-")
        subject_tokens = re.findall(r"[a-zа-яё0-9]+", subject.casefold())
        if subject_tokens and all(
            token in {
                "это", "этот", "эта", "эту", "его", "ее", "её", "их",
                "событие", "дело", "задача", "напоминание",
            }
            for token in subject_tokens
        ):
            return None
        return subject[:500] or None

    def _candidate(
        self,
        operation_id: str,
        slots: tuple[InterpretationSlot, ...],
        signal: str,
    ) -> CapabilityCandidate | None:
        try:
            self.catalog.get(operation_id)
            specification = self.specifications.get(operation_id)
        except (CapabilityNotFoundError, InterpretationSpecificationError):
            return None
        names = tuple(item.name for item in slots if item.value is not None)
        missing = tuple(
            name for name in specification.required_slots if name not in names
        )
        return CapabilityCandidate(
            operation_id=operation_id,
            evidence=(CandidateEvidence(signal=signal),),
            slot_names=tuple(dict.fromkeys(names)),
            missing_slots=missing,
        )

    @staticmethod
    def _frame(
        utterance: str,
        candidates: tuple[CapabilityCandidate, ...],
        slots: tuple[InterpretationSlot, ...],
        referents: tuple[InterpretationReferent, ...],
    ) -> InterpretationFrame:
        if not candidates:
            return InterpretationFrame(
                original_utterance=utterance,
                resolution_state=InterpretationResolutionState.ORDINARY_CONVERSATION,
            )
        missing = tuple(dict.fromkeys(
            slot for candidate in candidates for slot in candidate.missing_slots
        ))
        if len(candidates) > 1:
            ambiguity = InterpretationAmbiguity.CAPABILITY
        elif any(item.origin is InterpretationValueOrigin.UNRESOLVED for item in referents):
            ambiguity = InterpretationAmbiguity.REFERENT
        elif missing:
            ambiguity = InterpretationAmbiguity.SLOT
        else:
            ambiguity = InterpretationAmbiguity.NONE
        state = (
            InterpretationResolutionState.RESOLVED
            if ambiguity is InterpretationAmbiguity.NONE
            else InterpretationResolutionState.CLARIFICATION_REQUIRED
        )
        return InterpretationFrame(
            original_utterance=utterance,
            normalized_goal=(candidates[0].operation_id if len(candidates) == 1 else None),
            candidates=candidates,
            slots=slots,
            missing_slots=missing,
            referents=referents,
            ambiguity=ambiguity,
            resolution_state=state,
        )


def explicit_file_provider_id(utterance: str) -> str | None:
    """Expose existing provider normalization to V2 fixtures without an enum."""

    return normalize_explicit_provider(utterance).provider_id
