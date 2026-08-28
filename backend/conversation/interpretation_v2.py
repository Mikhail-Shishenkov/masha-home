"""Pure Natural Language Router V2 interpretation foundation.

This module discovers descriptive candidates only.  It cannot execute a Home
operation, grant authority, ask a clarification question, or persist state.
The production V1 router remains the live routing boundary.
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

from .capability_router import normalize_utterance


_OPERATION_ID = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_SLOT_NAME = r"^[a-z][a-z0-9_]{0,63}$"


class StrictInterpretationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InterpretationResolutionState(str, Enum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"
    ORDINARY_CONVERSATION = "ordinary_conversation"


class InterpretationAmbiguity(str, Enum):
    NONE = "none"
    CAPABILITY = "capability"
    SLOT = "slot"
    REFERENT = "referent"
    PROVIDER_SCOPE = "provider_scope"


class InterpretationValueOrigin(str, Enum):
    EXPLICIT = "explicit"
    DETERMINISTIC = "deterministic"
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

    @model_validator(mode="after")
    def required_slots_are_valid_and_unique(self):
        if any(re.fullmatch(_SLOT_NAME, item) is None for item in self.required_slots):
            raise ValueError("required slot name is invalid")
        if len(self.required_slots) != len(set(self.required_slots)):
            raise ValueError("interpretation specification repeats a required slot")
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


def default_interpretation_specifications() -> tuple[InterpretationSpecification, ...]:
    return (
        InterpretationSpecification(
            operation_id="web.search",
            required_slots=("query",),
        ),
        InterpretationSpecification(
            operation_id="google_calendar.event.create",
            required_slots=("subject", "date", "time"),
        ),
        InterpretationSpecification(
            operation_id="google_drive.document.create",
            required_slots=("content",),
        ),
        InterpretationSpecification(operation_id="google_drive.read"),
        InterpretationSpecification(
            operation_id="home.timed_commitments",
            required_slots=("subject", "date", "time"),
        ),
        InterpretationSpecification(operation_id="yandex_mail.read"),
        InterpretationSpecification(operation_id="yandex_disk.read"),
    )


_CALENDAR_EXPLICIT = re.compile(r"^(?:поставь|запланируй|создай)\b")
_SCHEDULE_AMBIGUOUS = re.compile(r"^запиши\b")
_SAVE_REFERENTIAL = re.compile(r"^сохрани\s+(?P<referent>это|этот\s+текст|эту\s+заметку)$")
_MAIL_READ = re.compile(r"^(?:посмотри|проверь)\s+(?:мою\s+)?почту$")
_DATE = re.compile(r"\b(?P<date>сегодня|завтра)\b")
_TIME = re.compile(r"\bв\s*(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\b")


class CapabilityCandidateDiscovery:
    """Deterministic, side-effect-free V2 candidate discovery for Slice 2A."""

    def __init__(
        self,
        *,
        catalog: CapabilityCatalog,
        specifications: Iterable[InterpretationSpecification] | None = None,
    ):
        self.catalog = catalog
        self.specifications = InterpretationSpecificationRegistry(
            catalog=catalog,
            specifications=(
                default_interpretation_specifications()
                if specifications is None
                else specifications
            ),
        )

    def interpret(self, utterance: str) -> InterpretationFrame:
        original = utterance.strip()
        if not original:
            raise ValueError("utterance must not be empty")
        text = normalize_utterance(original)

        document = self._document_candidate(original)
        if document is not None:
            return self._frame(original, (document[0],), document[1], ())

        candidates: list[CapabilityCandidate] = []
        slots = self._temporal_slots(text)
        if _CALENDAR_EXPLICIT.search(text):
            subject = self._schedule_subject(text)
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
        elif _SCHEDULE_AMBIGUOUS.search(text):
            subject = self._schedule_subject(text)
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

    @staticmethod
    def _temporal_slots(text: str) -> tuple[InterpretationSlot, ...]:
        slots: list[InterpretationSlot] = []
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
        return tuple(slots)

    @staticmethod
    def _schedule_subject(text: str) -> str | None:
        subject = re.sub(r"^(?:поставь|запланируй|создай|запиши)\s+", "", text)
        subject = _DATE.sub("", subject)
        subject = _TIME.sub("", subject)
        subject = re.sub(r"\b(?:в|на)\s+календар(?:ь|е)\b", "", subject)
        subject = re.sub(r"\s+", " ", subject).strip(" ,.-")
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
