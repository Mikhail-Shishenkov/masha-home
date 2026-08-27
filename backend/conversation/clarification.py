"""Deterministic clarification construction and pure follow-up resolution."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.application.capability_catalog import (
    CapabilityCatalog,
    CapabilityNotFoundError,
)

from .capability_router import normalize_utterance
from .interpretation_v2 import (
    CapabilityCandidate,
    InterpretationAmbiguity,
    InterpretationFrame,
    InterpretationReferent,
    InterpretationResolutionState,
    InterpretationSlot,
    InterpretationValueOrigin,
    explicit_file_provider_id,
)
from .pending_resolution import (
    ClarificationChoice,
    ClarificationKind,
    PendingResolution,
    PendingResolutionStatus,
    PendingResolutionTransitionError,
    StrictResolutionModel,
)


DEFAULT_CLARIFICATION_TTL = timedelta(minutes=30)

_CANCEL = re.compile(r"^(?:не надо|отмена|забудь|ладно не делай)$")
_CALENDAR_CHOICE = re.compile(r"^(?:в календарь|календарь|поставь в календарь)$")
_REMINDER_CHOICE = re.compile(r"^(?:просто напомни|напоминание|только напомни)$")
_INDEPENDENT_QUESTION = re.compile(
    r"^(?:(?:а )?(?:какая|какой|какие|какое|что|кто|где|когда|почему|как)\b)"
)
_INDEPENDENT_COMMAND = re.compile(
    r"^(?:создай|покажи|найди|поищи|проверь|посмотри|напомни)\b"
)
_EXPLICIT_MATERIAL = re.compile(
    r"^(?:вот\s+)?(?:этот\s+)?текст\s*:\s*(?P<material>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_DATE_VALUE = re.compile(r"^(?:сегодня|завтра)$")
_TIME_VALUE = re.compile(r"^(?:в\s*)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?$")
_UNRESOLVED_ANSWERS = frozenset(("это", "вот это", "туда", "там", "не знаю"))

_HUMAN_CHOICE_LABELS = {
    "google_calendar.event.create": "В календарь",
    "home.timed_commitments": "Просто напомнить",
    "google_drive.document.create": "Google Drive",
    "yandex_disk.document.create": "Яндекс Диск",
}


class ClarificationRequest(StrictResolutionModel):
    resolution_id: str = Field(min_length=36, max_length=36)
    conversation_id: str = Field(min_length=1, max_length=200)
    clarification_kind: ClarificationKind
    prompt: str = Field(min_length=1, max_length=500)
    choices: tuple[ClarificationChoice, ...] = Field(default=(), max_length=8)
    requested_slot: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    referent_expression: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def shape_matches_kind(self):
        if self.clarification_kind in {
            ClarificationKind.CAPABILITY,
            ClarificationKind.PROVIDER_SCOPE,
        }:
            if len(self.choices) < 2:
                raise ValueError("choice request requires at least two choices")
        elif self.choices:
            raise ValueError("slot/referent request cannot contain choices")
        if (self.clarification_kind is ClarificationKind.SLOT) != (self.requested_slot is not None):
            raise ValueError("requested_slot must occur only for slot clarification")
        if (self.clarification_kind is ClarificationKind.REFERENT) != (self.referent_expression is not None):
            raise ValueError("referent_expression must occur only for referent clarification")
        return self


class ClarificationBuildError(RuntimeError):
    pass


class DeterministicClarificationBuilder:
    """Build bounded human wording and durable state without a model call."""

    def __init__(
        self,
        *,
        catalog: CapabilityCatalog,
        clock: Callable[[], datetime] | None = None,
        ttl: timedelta = DEFAULT_CLARIFICATION_TTL,
        resolution_id_factory: Callable[[], str] | None = None,
    ):
        if ttl <= timedelta(0):
            raise ValueError("clarification TTL must be positive")
        self.catalog = catalog
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.ttl = ttl
        self._resolution_id_factory = resolution_id_factory or (lambda: str(uuid4()))

    def build(
        self,
        frame: InterpretationFrame,
        *,
        conversation_id: str,
    ) -> tuple[ClarificationRequest, PendingResolution]:
        now = self._now()
        resolution_id = self._resolution_id_factory()
        request = self.build_request(
            frame,
            conversation_id=conversation_id,
            resolution_id=resolution_id,
        )
        pending = PendingResolution(
            resolution_id=resolution_id,
            conversation_id=conversation_id,
            interpretation=frame,
            clarification_kind=request.clarification_kind,
            choices=request.choices,
            requested_slot=request.requested_slot,
            referent_expression=request.referent_expression,
            created_at=now,
            updated_at=now,
            expires_at=now + self.ttl,
        )
        return request, pending

    def build_request(
        self,
        frame: InterpretationFrame,
        *,
        conversation_id: str,
        resolution_id: str,
    ) -> ClarificationRequest:
        """Describe the next unresolved dimension for the same durable state."""

        if frame.resolution_state is not InterpretationResolutionState.CLARIFICATION_REQUIRED:
            raise ClarificationBuildError("interpretation does not require clarification")
        kind = self._kind(frame)
        choices: tuple[ClarificationChoice, ...] = ()
        requested_slot = None
        referent_expression = None
        if kind in {ClarificationKind.CAPABILITY, ClarificationKind.PROVIDER_SCOPE}:
            choices = self._choices(frame)
            prompt = self._choice_prompt(frame, kind)
        elif kind is ClarificationKind.SLOT:
            requested_slot = frame.missing_slots[0]
            prompt = self._slot_prompt(frame, requested_slot)
        else:
            unresolved = next(
                (
                    referent for referent in frame.referents
                    if referent.origin is InterpretationValueOrigin.UNRESOLVED
                ),
                None,
            )
            if unresolved is None:
                raise ClarificationBuildError("referent ambiguity has no unresolved referent")
            referent_expression = unresolved.expression
            prompt = "Что именно сохранить?"
        return ClarificationRequest(
            resolution_id=resolution_id,
            conversation_id=conversation_id,
            clarification_kind=kind,
            prompt=prompt,
            choices=choices,
            requested_slot=requested_slot,
            referent_expression=referent_expression,
        )

    @staticmethod
    def _kind(frame: InterpretationFrame) -> ClarificationKind:
        # Resolve a missing referent before asking where/how it should be saved.
        if any(
            referent.origin is InterpretationValueOrigin.UNRESOLVED
            for referent in frame.referents
        ):
            return ClarificationKind.REFERENT
        try:
            return ClarificationKind(frame.ambiguity.value)
        except ValueError as error:
            raise ClarificationBuildError(frame.ambiguity.value) from error

    def _choices(self, frame: InterpretationFrame) -> tuple[ClarificationChoice, ...]:
        choices = []
        for candidate in frame.candidates:
            try:
                descriptor = self.catalog.get(candidate.operation_id)
            except CapabilityNotFoundError as error:
                raise ClarificationBuildError(candidate.operation_id) from error
            choices.append(ClarificationChoice(
                operation_id=candidate.operation_id,
                label=_HUMAN_CHOICE_LABELS.get(
                    candidate.operation_id,
                    descriptor.display_name,
                ),
            ))
        if len(choices) < 2:
            raise ClarificationBuildError("choice ambiguity requires multiple candidates")
        return tuple(choices)

    @staticmethod
    def _choice_prompt(
        frame: InterpretationFrame,
        kind: ClarificationKind,
    ) -> str:
        if kind is ClarificationKind.PROVIDER_SCOPE:
            return "Где это сохранить?"
        operation_ids = {candidate.operation_id for candidate in frame.candidates}
        if operation_ids == {
            "google_calendar.event.create",
            "home.timed_commitments",
        }:
            slots = {slot.name: slot.value for slot in frame.slots}
            subject = (slots.get("subject") or "Это").strip().capitalize()
            time = slots.get("time")
            suffix = f" в {time}" if time else ""
            return f"{subject} — поставить в календарь или просто напомнить{suffix}?"
        return "Как именно это сделать?"

    @staticmethod
    def _slot_prompt(frame: InterpretationFrame, slot_name: str) -> str:
        operation_id = frame.candidates[0].operation_id
        if slot_name in {"subject", "title"} and operation_id == "google_calendar.event.create":
            return "Что именно поставить в календарь?"
        prompts = {
            "subject": "Что именно нужно запомнить как дело?",
            "title": "Как это назвать?",
            "date": "На какой день?",
            "time": "Во сколько?",
            "content": "Что именно сохранить?",
            "query": "Что именно найти?",
            "target": "Где это сделать?",
        }
        return prompts.get(slot_name, "Что именно уточнить?")

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("clarification clock must be timezone-aware")
        return value.astimezone(timezone.utc)


class FollowUpOutcome(str, Enum):
    RESOLVED = "resolved"
    STILL_UNRESOLVED = "still_unresolved"
    CANCELLED = "cancelled"
    NOT_A_FOLLOW_UP = "not_a_follow_up"


class FollowUpResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: FollowUpOutcome
    interpretation: InterpretationFrame
    selected_operation_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
    )
    supplied_slot: InterpretationSlot | None = None
    supplied_referent: InterpretationReferent | None = None

    @model_validator(mode="after")
    def outcome_matches_interpretation(self):
        if self.outcome is FollowUpOutcome.RESOLVED:
            if self.interpretation.resolution_state is not InterpretationResolutionState.RESOLVED:
                raise ValueError("resolved outcome requires resolved interpretation")
            if (
                len(self.interpretation.candidates) != 1
                or self.selected_operation_id
                != self.interpretation.candidates[0].operation_id
            ):
                raise ValueError("resolved outcome requires its final canonical operation")
        elif self.interpretation.resolution_state is InterpretationResolutionState.RESOLVED:
            raise ValueError("non-resolved outcome cannot carry a resolved interpretation")
        return self


class FollowUpResolutionEngine:
    """Patch one active interpretation; never route, execute, or authorize."""

    def resolve(
        self,
        pending: PendingResolution,
        follow_up: str,
    ) -> FollowUpResolutionResult:
        if pending.status is not PendingResolutionStatus.PENDING:
            raise PendingResolutionTransitionError("only active pending meaning can be resolved")
        original = follow_up.strip()
        if not original:
            return self._unchanged(pending, FollowUpOutcome.STILL_UNRESOLVED)
        text = normalize_utterance(original)
        if _CANCEL.fullmatch(text):
            return self._unchanged(pending, FollowUpOutcome.CANCELLED)
        if pending.clarification_kind in {
            ClarificationKind.CAPABILITY,
            ClarificationKind.PROVIDER_SCOPE,
        }:
            operation_id = self._selected_operation(pending, original, text)
            if operation_id is not None:
                return self._select_candidate(pending, operation_id)
            if self._is_independent(text):
                return self._unchanged(pending, FollowUpOutcome.NOT_A_FOLLOW_UP)
            return self._unchanged(pending, FollowUpOutcome.STILL_UNRESOLVED)
        if pending.clarification_kind is ClarificationKind.SLOT:
            if self._is_independent(text):
                return self._unchanged(pending, FollowUpOutcome.NOT_A_FOLLOW_UP)
            slot = self._slot_from_follow_up(pending.requested_slot, original, text)
            if slot is None:
                return self._unchanged(pending, FollowUpOutcome.STILL_UNRESOLVED)
            return self._fill_slot(pending, slot)
        if text in _UNRESOLVED_ANSWERS:
            return self._unchanged(pending, FollowUpOutcome.STILL_UNRESOLVED)
        if self._is_independent(text):
            return self._unchanged(pending, FollowUpOutcome.NOT_A_FOLLOW_UP)
        material = _EXPLICIT_MATERIAL.fullmatch(original.strip())
        if material is None:
            return self._unchanged(pending, FollowUpOutcome.STILL_UNRESOLVED)
        value = material.group("material").strip()[:500]
        if not value or normalize_utterance(value) in _UNRESOLVED_ANSWERS:
            return self._unchanged(pending, FollowUpOutcome.STILL_UNRESOLVED)
        referent = InterpretationReferent(
            expression=pending.referent_expression or "это",
            value=value,
            origin=InterpretationValueOrigin.EXPLICIT,
        )
        frame = self._reframe(
            pending.interpretation,
            referents=tuple(
                referent
                if item.origin is InterpretationValueOrigin.UNRESOLVED
                else item
                for item in pending.interpretation.referents
            ),
        )
        return FollowUpResolutionResult(
            outcome=self._outcome_for(frame),
            interpretation=frame,
            supplied_referent=referent,
        )

    @staticmethod
    def _selected_operation(
        pending: PendingResolution,
        original: str,
        text: str,
    ) -> str | None:
        available = {choice.operation_id for choice in pending.choices}
        if _CALENDAR_CHOICE.fullmatch(text):
            operation_id = "google_calendar.event.create"
            return operation_id if operation_id in available else None
        if _REMINDER_CHOICE.fullmatch(text):
            operation_id = "home.timed_commitments"
            return operation_id if operation_id in available else None
        provider_id = explicit_file_provider_id(original)
        if provider_id is not None:
            prefix = "google_drive." if provider_id == "google_drive" else "yandex_disk."
            matches = sorted(item for item in available if item.startswith(prefix))
            return matches[0] if len(matches) == 1 else None
        return None

    def _select_candidate(
        self,
        pending: PendingResolution,
        operation_id: str,
    ) -> FollowUpResolutionResult:
        candidate = next(
            item for item in pending.interpretation.candidates
            if item.operation_id == operation_id
        )
        frame = self._reframe(pending.interpretation, candidates=(candidate,))
        return FollowUpResolutionResult(
            outcome=self._outcome_for(frame),
            interpretation=frame,
            selected_operation_id=operation_id,
        )

    @staticmethod
    def _slot_from_follow_up(
        slot_name: str | None,
        original: str,
        text: str,
    ) -> InterpretationSlot | None:
        if slot_name is None or text in _UNRESOLVED_ANSWERS:
            return None
        value: str | None
        if slot_name == "time":
            match = _TIME_VALUE.fullmatch(text)
            if match is None:
                return None
            hour = int(match.group("hour"))
            minute = int(match.group("minute") or 0)
            if hour > 23 or minute > 59:
                return None
            value = f"{hour:02d}:{minute:02d}"
        elif slot_name == "date":
            value = text if _DATE_VALUE.fullmatch(text) else None
        else:
            value = original.strip()[:500]
        if not value:
            return None
        return InterpretationSlot(
            name=slot_name,
            value=value,
            origin=InterpretationValueOrigin.EXPLICIT,
        )

    def _fill_slot(
        self,
        pending: PendingResolution,
        slot: InterpretationSlot,
    ) -> FollowUpResolutionResult:
        slots = {
            item.name: item
            for item in pending.interpretation.slots
        }
        slots[slot.name] = slot
        candidates = tuple(
            CapabilityCandidate.model_validate({
                **candidate.model_dump(mode="python"),
                "slot_names": tuple(dict.fromkeys((*candidate.slot_names, slot.name))),
                "missing_slots": tuple(
                    name for name in candidate.missing_slots if name != slot.name
                ),
            })
            for candidate in pending.interpretation.candidates
        )
        frame = self._reframe(
            pending.interpretation,
            candidates=candidates,
            slots=tuple(slots.values()),
        )
        return FollowUpResolutionResult(
            outcome=self._outcome_for(frame),
            interpretation=frame,
            selected_operation_id=(
                frame.candidates[0].operation_id
                if frame.resolution_state is InterpretationResolutionState.RESOLVED
                else None
            ),
            supplied_slot=slot,
        )

    @staticmethod
    def _reframe(
        original: InterpretationFrame,
        *,
        candidates: tuple[CapabilityCandidate, ...] | None = None,
        slots: tuple[InterpretationSlot, ...] | None = None,
        referents: tuple[InterpretationReferent, ...] | None = None,
    ) -> InterpretationFrame:
        candidates = original.candidates if candidates is None else candidates
        slots = original.slots if slots is None else slots
        referents = original.referents if referents is None else referents
        missing = tuple(dict.fromkeys(
            name for candidate in candidates for name in candidate.missing_slots
        ))
        if len(candidates) > 1:
            ambiguity = InterpretationAmbiguity.CAPABILITY
        elif any(
            item.origin is InterpretationValueOrigin.UNRESOLVED
            for item in referents
        ):
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
            original_utterance=original.original_utterance,
            normalized_goal=(candidates[0].operation_id if len(candidates) == 1 else None),
            candidates=candidates,
            slots=slots,
            missing_slots=missing,
            referents=referents,
            ambiguity=ambiguity,
            resolution_state=state,
        )

    @staticmethod
    def _outcome_for(frame: InterpretationFrame) -> FollowUpOutcome:
        return (
            FollowUpOutcome.RESOLVED
            if frame.resolution_state is InterpretationResolutionState.RESOLVED
            else FollowUpOutcome.STILL_UNRESOLVED
        )

    @staticmethod
    def _is_independent(text: str) -> bool:
        return bool(
            _INDEPENDENT_QUESTION.search(text)
            or _INDEPENDENT_COMMAND.search(text)
        )

    @staticmethod
    def _unchanged(
        pending: PendingResolution,
        outcome: FollowUpOutcome,
    ) -> FollowUpResolutionResult:
        return FollowUpResolutionResult(
            outcome=outcome,
            interpretation=pending.interpretation,
        )
