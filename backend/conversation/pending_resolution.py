"""Durable meaning-only clarification state for Natural Language Router V2.

Pending resolution is neither confirmation nor execution authority.  The
store persists only bounded interpretation structure and lifecycle evidence.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .interpretation_v2 import (
    InterpretationFrame,
    InterpretationResolutionState,
    InterpretationValueOrigin,
)


_OPERATION_ID = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_SLOT_NAME = r"^[a-z][a-z0-9_]{0,63}$"


class StrictResolutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PendingResolutionStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ClarificationKind(str, Enum):
    CAPABILITY = "capability"
    SLOT = "slot"
    REFERENT = "referent"
    PROVIDER_SCOPE = "provider_scope"


class ClarificationChoice(StrictResolutionModel):
    """A human label mapped internally to a canonical catalog operation."""

    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    label: str = Field(min_length=1, max_length=120)


class ActiveQuestion(StrictResolutionModel):
    """The one explicit question that owns interpretation of the next turn."""

    kind: ClarificationKind
    choices: tuple[ClarificationChoice, ...] = Field(default=(), max_length=8)
    requested_slot: str | None = Field(default=None, pattern=_SLOT_NAME)
    referent_expression: str | None = Field(default=None, min_length=1, max_length=300)
    value_hint: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def shape_matches_kind(self):
        if self.kind in {ClarificationKind.CAPABILITY, ClarificationKind.PROVIDER_SCOPE}:
            if len(self.choices) < 2:
                raise ValueError("choice question requires multiple choices")
        elif self.choices:
            raise ValueError("only a choice question may contain choices")
        if (self.kind is ClarificationKind.SLOT) != (self.requested_slot is not None):
            raise ValueError("slot question requires requested_slot")
        if (self.kind is ClarificationKind.REFERENT) != (self.referent_expression is not None):
            raise ValueError("referent question requires referent_expression")
        if self.value_hint is not None and self.kind is not ClarificationKind.SLOT:
            raise ValueError("only a slot question may retain a value hint")
        return self


class PendingResolution(StrictResolutionModel):
    resolution_id: str = Field(min_length=36, max_length=36)
    conversation_id: str = Field(min_length=1, max_length=200)
    interpretation: InterpretationFrame
    active_question: ActiveQuestion
    created_at: AwareDatetime
    updated_at: AwareDatetime
    expires_at: AwareDatetime
    status: PendingResolutionStatus = PendingResolutionStatus.PENDING
    terminal_reason: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_question_shape(cls, value):
        if not isinstance(value, dict) or "active_question" in value:
            return value
        migrated = dict(value)
        kind = migrated.pop("clarification_kind", None)
        choices = migrated.pop("choices", ())
        requested_slot = migrated.pop("requested_slot", None)
        referent_expression = migrated.pop("referent_expression", None)
        if kind is not None:
            migrated["active_question"] = {
                "kind": kind,
                "choices": choices,
                "requested_slot": requested_slot,
                "referent_expression": referent_expression,
            }
        return migrated

    @property
    def flow_id(self) -> str:
        return self.resolution_id

    @property
    def clarification_kind(self) -> ClarificationKind:
        return self.active_question.kind

    @property
    def choices(self) -> tuple[ClarificationChoice, ...]:
        return self.active_question.choices

    @property
    def requested_slot(self) -> str | None:
        return self.active_question.requested_slot

    @property
    def referent_expression(self) -> str | None:
        return self.active_question.referent_expression

    @field_validator("resolution_id")
    @classmethod
    def resolution_id_is_uuid(cls, value: str) -> str:
        UUID(value)
        return value

    @model_validator(mode="after")
    def lifecycle_and_clarification_are_consistent(self):
        if self.updated_at < self.created_at:
            raise ValueError("pending resolution update predates creation")
        if self.expires_at <= self.created_at:
            raise ValueError("pending resolution expiry must follow creation")
        operation_ids = [choice.operation_id for choice in self.choices]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("clarification choices must be unique")
        candidate_ids = {
            candidate.operation_id for candidate in self.interpretation.candidates
        }
        if (
            self.status is PendingResolutionStatus.PENDING
            and any(operation_id not in candidate_ids for operation_id in operation_ids)
        ):
            raise ValueError("clarification choice is not an interpretation candidate")
        if self.clarification_kind in {
            ClarificationKind.CAPABILITY,
            ClarificationKind.PROVIDER_SCOPE,
        }:
            if len(self.choices) < 2:
                raise ValueError("choice clarification requires at least two choices")
        elif self.choices:
            raise ValueError("slot/referent clarification cannot contain choices")
        if self.clarification_kind is ClarificationKind.SLOT:
            if self.requested_slot is None:
                raise ValueError("slot clarification requires requested_slot")
            if (
                self.status is PendingResolutionStatus.PENDING
                and self.requested_slot not in self.interpretation.missing_slots
            ):
                raise ValueError("requested slot is not missing from interpretation")
        elif self.requested_slot is not None:
            raise ValueError("only slot clarification may request a slot")
        if self.clarification_kind is ClarificationKind.REFERENT:
            if self.referent_expression is None:
                raise ValueError("referent clarification requires an expression")
            if self.status is PendingResolutionStatus.PENDING and not any(
                referent.expression == self.referent_expression
                and referent.value is None
                for referent in self.interpretation.referents
            ):
                raise ValueError("requested referent is not unresolved")
        elif self.referent_expression is not None:
            raise ValueError("only referent clarification may carry an expression")
        if self.status is PendingResolutionStatus.PENDING:
            if self.terminal_reason is not None:
                raise ValueError("pending resolution cannot have a terminal reason")
            if self.interpretation.resolution_state is not InterpretationResolutionState.CLARIFICATION_REQUIRED:
                raise ValueError("pending resolution requires unresolved interpretation")
        elif self.status is PendingResolutionStatus.RESOLVED:
            if self.terminal_reason is not None:
                raise ValueError("resolved meaning cannot have a terminal reason")
            if self.interpretation.resolution_state is not InterpretationResolutionState.RESOLVED:
                raise ValueError("resolved lifecycle requires resolved interpretation")
        else:
            if self.terminal_reason is None:
                raise ValueError("cancelled/expired/superseded resolution requires a reason")
        return self


class PendingResolutionDocument(StrictResolutionModel):
    schema_version: Literal["2.0"] = "2.0"
    resolutions: tuple[PendingResolution, ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def identifiers_and_active_conversations_are_unique(self):
        identifiers = [item.resolution_id for item in self.resolutions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("pending resolution document contains duplicate IDs")
        active_conversations = [
            item.conversation_id
            for item in self.resolutions
            if item.status is PendingResolutionStatus.PENDING
        ]
        if len(active_conversations) != len(set(active_conversations)):
            raise ValueError("conversation has multiple active pending resolutions")
        return self


class PendingResolutionStoreError(RuntimeError):
    pass


class PendingResolutionStoreCorruptError(PendingResolutionStoreError):
    pass


class PendingResolutionConflictError(PendingResolutionStoreError):
    pass


class PendingResolutionNotFoundError(PendingResolutionStoreError):
    pass


class PendingResolutionTransitionError(PendingResolutionStoreError):
    pass


class PendingResolutionStore:
    """Atomic bounded JSON store, separate from portable conversation history."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        max_records: int = 500,
        terminal_retention: int = 200,
    ):
        if not 1 <= max_records <= 1000:
            raise ValueError("max_records must be between 1 and 1000")
        if not 0 <= terminal_retention <= max_records:
            raise ValueError("terminal_retention must fit max_records")
        self.path = Path(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_records = max_records
        self.terminal_retention = terminal_retention

    def save(
        self,
        resolution: PendingResolution,
        *,
        supersede_active: bool = False,
    ) -> PendingResolution:
        if resolution.status is not PendingResolutionStatus.PENDING:
            raise PendingResolutionTransitionError("only a pending resolution can be saved")
        now = self._now()
        document, expiry_changed = self._load_with_expiry(now)
        if resolution.expires_at <= now:
            if expiry_changed:
                self._write(document)
            raise PendingResolutionTransitionError("cannot save an already expired resolution")
        if any(item.resolution_id == resolution.resolution_id for item in document.resolutions):
            if expiry_changed:
                self._write(document)
            raise PendingResolutionConflictError(resolution.resolution_id)
        rows = list(document.resolutions)
        active_index = next(
            (
                index
                for index, item in enumerate(rows)
                if item.conversation_id == resolution.conversation_id
                and item.status is PendingResolutionStatus.PENDING
            ),
            None,
        )
        if active_index is not None:
            if not supersede_active:
                if expiry_changed:
                    self._write(document)
                raise PendingResolutionConflictError(resolution.conversation_id)
            rows[active_index] = self._updated(rows[active_index], {
                "status": PendingResolutionStatus.SUPERSEDED,
                "updated_at": now,
                "terminal_reason": "superseded_by_new_resolution",
            })
        rows.append(resolution)
        self._write(self._compact(PendingResolutionDocument(resolutions=tuple(rows))))
        return resolution

    def get(self, resolution_id: str) -> PendingResolution | None:
        document, changed = self._load_with_expiry(self._now())
        if changed:
            self._write(document)
        return next(
            (item for item in document.resolutions if item.resolution_id == resolution_id),
            None,
        )

    def active_for_conversation(self, conversation_id: str) -> PendingResolution | None:
        document, changed = self._load_with_expiry(self._now())
        if changed:
            self._write(document)
        return next(
            (
                item
                for item in document.resolutions
                if item.conversation_id == conversation_id
                and item.status is PendingResolutionStatus.PENDING
            ),
            None,
        )

    def resolve(
        self,
        resolution_id: str,
        interpretation: InterpretationFrame,
    ) -> PendingResolution:
        if interpretation.resolution_state is not InterpretationResolutionState.RESOLVED:
            raise PendingResolutionTransitionError("resolution result is not resolved")
        return self._transition(
            resolution_id,
            status=PendingResolutionStatus.RESOLVED,
            interpretation=interpretation,
        )

    def update_pending(
        self,
        resolution_id: str,
        interpretation: InterpretationFrame,
        *,
        clarification_kind: ClarificationKind,
        choices: tuple[ClarificationChoice, ...] = (),
        requested_slot: str | None = None,
        referent_expression: str | None = None,
        active_question: ActiveQuestion | None = None,
    ) -> PendingResolution:
        if interpretation.resolution_state is not InterpretationResolutionState.CLARIFICATION_REQUIRED:
            raise PendingResolutionTransitionError("pending update must remain unresolved")
        return self._transition(
            resolution_id,
            status=PendingResolutionStatus.PENDING,
            interpretation=interpretation,
            clarification_update={
                "active_question": active_question or ActiveQuestion(
                    kind=clarification_kind,
                    choices=choices,
                    requested_slot=requested_slot,
                    referent_expression=referent_expression,
                ),
            },
        )

    def cancel(self, resolution_id: str, *, reason: str = "user_cancelled") -> PendingResolution:
        return self._transition(
            resolution_id,
            status=PendingResolutionStatus.CANCELLED,
            terminal_reason=reason,
        )

    def expire(self, resolution_id: str, *, reason: str = "ttl_expired") -> PendingResolution:
        return self._transition(
            resolution_id,
            status=PendingResolutionStatus.EXPIRED,
            terminal_reason=reason,
        )

    def supersede(
        self,
        resolution_id: str,
        *,
        reason: str = "superseded_by_new_request",
    ) -> PendingResolution:
        return self._transition(
            resolution_id,
            status=PendingResolutionStatus.SUPERSEDED,
            terminal_reason=reason,
        )

    def expire_due(self) -> int:
        document = self._load()
        expired = self._expire_rows(document, self._now())
        if expired != document:
            self._write(expired)
        return sum(
            1
            for before, after in zip(document.resolutions, expired.resolutions)
            if before.status is PendingResolutionStatus.PENDING
            and after.status is PendingResolutionStatus.EXPIRED
        )

    def _transition(
        self,
        resolution_id: str,
        *,
        status: PendingResolutionStatus,
        interpretation: InterpretationFrame | None = None,
        terminal_reason: str | None = None,
        clarification_update: dict[str, object] | None = None,
    ) -> PendingResolution:
        now = self._now()
        document, expiry_changed = self._load_with_expiry(now)
        rows = list(document.resolutions)
        index = next(
            (index for index, item in enumerate(rows) if item.resolution_id == resolution_id),
            None,
        )
        if index is None:
            if expiry_changed:
                self._write(document)
            raise PendingResolutionNotFoundError(resolution_id)
        current = rows[index]
        if current.status is not PendingResolutionStatus.PENDING:
            if expiry_changed:
                self._write(document)
            raise PendingResolutionTransitionError(
                f"terminal resolution cannot transition from {current.status.value}"
            )
        if interpretation is not None:
            self._validate_interpretation_patch(current.interpretation, interpretation)
        updated = self._updated(current, {
            "status": status,
            "interpretation": interpretation or current.interpretation,
            "updated_at": now,
            "terminal_reason": terminal_reason,
            **(clarification_update or {}),
        })
        rows[index] = updated
        self._write(self._compact(PendingResolutionDocument(resolutions=tuple(rows))))
        return updated

    @staticmethod
    def _validate_interpretation_patch(
        original: InterpretationFrame,
        updated: InterpretationFrame,
    ) -> None:
        if updated.original_utterance != original.original_utterance:
            raise PendingResolutionTransitionError("resolution lost original utterance provenance")
        old_slots = {slot.name: slot for slot in original.slots}
        new_slots = {slot.name: slot for slot in updated.slots}
        if not set(old_slots).issubset(new_slots):
            raise PendingResolutionTransitionError("resolution removed an already known slot")
        allowed_revision_origins = {
            InterpretationValueOrigin.FOLLOW_UP_SEMANTIC,
            InterpretationValueOrigin.TEMPORAL_NORMALIZED,
        }
        if any(
            new_slots[name] != slot
            and new_slots[name].origin not in allowed_revision_origins
            for name, slot in old_slots.items()
        ):
            raise PendingResolutionTransitionError(
                "resolution changed a known slot without follow-up provenance"
            )
        if any(
            name not in old_slots
            and slot.origin not in {
                InterpretationValueOrigin.EXPLICIT,
                InterpretationValueOrigin.FOLLOW_UP_SEMANTIC,
                InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            }
            for name, slot in new_slots.items()
        ):
            raise PendingResolutionTransitionError(
                "resolution added a slot without user or temporal provenance"
            )
        old_candidates = {item.operation_id: item for item in original.candidates}
        for item in updated.candidates:
            old = old_candidates.get(item.operation_id)
            if old is None or item.evidence != old.evidence:
                raise PendingResolutionTransitionError("resolution invented a capability candidate")
            if not set(old.slot_names).issubset(item.slot_names):
                raise PendingResolutionTransitionError("resolution lost candidate slot provenance")
            if not set(item.slot_names).issubset(new_slots):
                raise PendingResolutionTransitionError("candidate claims an absent slot")
            if not set(item.missing_slots).issubset(old.missing_slots):
                raise PendingResolutionTransitionError("resolution invented a missing slot")
            removed_missing = set(old.missing_slots) - set(item.missing_slots)
            if not removed_missing.issubset(new_slots):
                raise PendingResolutionTransitionError("resolution removed an unresolved slot")
        old_referents = {item.expression: item for item in original.referents}
        new_referents = {item.expression: item for item in updated.referents}
        if set(new_referents) != set(old_referents):
            raise PendingResolutionTransitionError("resolution changed referent provenance")
        for expression, old in old_referents.items():
            new = new_referents[expression]
            if old.value is not None and new != old:
                raise PendingResolutionTransitionError("resolution changed a known referent")
            if (
                old.value is None
                and new.value is not None
                and new.origin.value != "explicit"
            ):
                raise PendingResolutionTransitionError(
                    "resolved referent must come from explicit user evidence"
                )

    def _load_with_expiry(
        self,
        now: datetime,
    ) -> tuple[PendingResolutionDocument, bool]:
        document = self._load()
        expired = self._expire_rows(document, now)
        return expired, expired != document

    @staticmethod
    def _expire_rows(
        document: PendingResolutionDocument,
        now: datetime,
    ) -> PendingResolutionDocument:
        rows = tuple(
            PendingResolutionStore._updated(item, {
                "status": PendingResolutionStatus.EXPIRED,
                "updated_at": now,
                "terminal_reason": "ttl_expired",
            })
            if item.status is PendingResolutionStatus.PENDING
            and item.expires_at <= now
            else item
            for item in document.resolutions
        )
        return document if rows == document.resolutions else PendingResolutionDocument(resolutions=rows)

    @staticmethod
    def _updated(
        resolution: PendingResolution,
        changes: dict[str, object],
    ) -> PendingResolution:
        return PendingResolution.model_validate({
            **resolution.model_dump(mode="python"),
            **changes,
        })

    def _load(self) -> PendingResolutionDocument:
        if not self.path.exists():
            return PendingResolutionDocument()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("schema_version") == "1.0":
                payload = {**payload, "schema_version": "2.0"}
            return PendingResolutionDocument.model_validate(payload)
        except Exception as error:
            raise PendingResolutionStoreCorruptError(str(self.path)) from error

    def _compact(self, document: PendingResolutionDocument) -> PendingResolutionDocument:
        pending = [
            item for item in document.resolutions
            if item.status is PendingResolutionStatus.PENDING
        ]
        if len(pending) > self.max_records:
            raise PendingResolutionStoreError("too many active pending resolutions")
        terminal = sorted(
            (
                item for item in document.resolutions
                if item.status is not PendingResolutionStatus.PENDING
            ),
            key=lambda item: (item.updated_at, item.resolution_id),
        )
        keep_terminal = min(
            self.terminal_retention,
            self.max_records - len(pending),
        )
        return PendingResolutionDocument(
            resolutions=tuple(terminal[-keep_terminal:] if keep_terminal else ())
            + tuple(pending)
        )

    def _write(self, document: PendingResolutionDocument) -> None:
        document = self._compact(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as file:
                json.dump(
                    document.model_dump(mode="json"),
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("pending resolution clock must be timezone-aware")
        return value.astimezone(timezone.utc)
