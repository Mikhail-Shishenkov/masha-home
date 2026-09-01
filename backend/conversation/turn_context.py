"""Bounded application-owned context for one language-understanding turn.

The envelope is descriptive evidence only.  It deliberately contains no
provider IDs, storage record IDs, credentials, permission grants or mutation
handles.  Supplying an item here can help resolve human references, but can
never authorize or prove an action.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.temporal.temporal_engine import TemporalContext

from .conversation_models import ConversationMessage


_OPERATION_ID = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_OPAQUE_REFERENCE = r"^(?:T|M|P)[1-9][0-9]?$"


class StrictTurnContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TurnContextSource(str, Enum):
    HOME_CLOCK = "home_clock"
    RECENT_CONVERSATION = "recent_conversation"
    ACTIVE_CONTINUITY = "active_continuity"
    ACTIVE_MEMORY = "active_memory"
    PRESENTED_ENTITY = "presented_entity"
    CAPABILITY_CATALOG = "capability_catalog"
    APPLICATION_RESULT = "application_result"


class TurnTemporalContext(StrictTurnContextModel):
    """One immutable Home-clock snapshot used throughout a turn."""

    source: Literal[TurnContextSource.HOME_CLOCK] = TurnContextSource.HOME_CLOCK
    current_utc_time: AwareDatetime
    current_local_time: AwareDatetime
    timezone: str = Field(min_length=1, max_length=100)
    local_date: date
    local_weekday: str = Field(min_length=1, max_length=20)
    daypart: str = Field(min_length=1, max_length=20)
    previous_turn_relation: str | None = Field(default=None, max_length=40)
    absence_duration_seconds: int | None = Field(default=None, ge=0)

    @classmethod
    def from_temporal_context(cls, value: TemporalContext) -> "TurnTemporalContext":
        return cls(
            current_utc_time=value.current_utc_time,
            current_local_time=value.current_local_time,
            timezone=value.timezone,
            local_date=value.local_date,
            local_weekday=value.local_weekday.value,
            daypart=value.daypart.value,
            previous_turn_relation=(
                None
                if value.previous_turn_relation is None
                else value.previous_turn_relation.value
            ),
            absence_duration_seconds=value.absence_duration_seconds,
        )


class TurnConversationHint(StrictTurnContextModel):
    """A small human transcript fragment with a turn-local opaque reference."""

    reference: str = Field(pattern=_OPAQUE_REFERENCE)
    source: Literal[TurnContextSource.RECENT_CONVERSATION] = (
        TurnContextSource.RECENT_CONVERSATION
    )
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)
    occurred_at: AwareDatetime | None = None


class TurnMemoryHint(StrictTurnContextModel):
    """Humanized active memory evidence; never a raw repository record."""

    reference: str = Field(pattern=_OPAQUE_REFERENCE)
    source: Literal[TurnContextSource.ACTIVE_MEMORY] = TurnContextSource.ACTIVE_MEMORY
    kind: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1_000)
    state: Literal["active", "current"] = "active"
    time_text: str | None = Field(default=None, max_length=120)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TurnContinuityHint(StrictTurnContextModel):
    """The one thread explicitly selected by the user for this conversation."""

    source: Literal[TurnContextSource.ACTIVE_CONTINUITY] = (
        TurnContextSource.ACTIVE_CONTINUITY
    )
    topic: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1_000)
    reason_to_return: str = Field(min_length=1, max_length=500)


class TurnPresentedEntityHint(StrictTurnContextModel):
    """A visible application result addressable by ordinal, without provider ID."""

    reference: str = Field(pattern=_OPAQUE_REFERENCE)
    source: Literal[TurnContextSource.PRESENTED_ENTITY] = (
        TurnContextSource.PRESENTED_ENTITY
    )
    position: int = Field(ge=1, le=10)
    owner_operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    kind: str = Field(min_length=1, max_length=80)
    human_label: str = Field(min_length=1, max_length=500)
    time_text: str | None = Field(default=None, max_length=120)


class TurnCapabilityHint(StrictTurnContextModel):
    """Descriptive availability only; this is never a grant."""

    source: Literal[TurnContextSource.CAPABILITY_CATALOG] = (
        TurnContextSource.CAPABILITY_CATALOG
    )
    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    availability: Literal[
        "available", "blocked", "needs_reconnect", "unavailable"
    ]


class TurnApplicationResultHint(StrictTurnContextModel):
    """Previous application projection, without receipt or provider identity."""

    source: Literal[TurnContextSource.APPLICATION_RESULT] = (
        TurnContextSource.APPLICATION_RESULT
    )
    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    projection_state: Literal[
        "clarification", "waiting_confirmation", "completed_read",
        "failed", "unsupported",
    ]


class TurnContextEnvelope(StrictTurnContextModel):
    """All bounded context Home may offer to semantic understanding for one turn."""

    schema_version: Literal["1.0"] = "1.0"
    temporal: TurnTemporalContext
    recent_turns: tuple[TurnConversationHint, ...] = Field(default=(), max_length=8)
    active_continuity: TurnContinuityHint | None = None
    memory_hints: tuple[TurnMemoryHint, ...] = Field(default=(), max_length=6)
    presented_entities: tuple[TurnPresentedEntityHint, ...] = Field(
        default=(), max_length=10,
    )
    capabilities: tuple[TurnCapabilityHint, ...] = Field(default=(), max_length=32)
    last_application_result: TurnApplicationResultHint | None = None

    @model_validator(mode="after")
    def references_and_capabilities_are_unique(self):
        references = [
            *(item.reference for item in self.recent_turns),
            *(item.reference for item in self.memory_hints),
            *(item.reference for item in self.presented_entities),
        ]
        if len(references) != len(set(references)):
            raise ValueError("turn context contains duplicate opaque references")
        operations = [item.operation_id for item in self.capabilities]
        if len(operations) != len(set(operations)):
            raise ValueError("turn context contains duplicate capabilities")
        presented_positions = [item.position for item in self.presented_entities]
        if len(presented_positions) != len(set(presented_positions)):
            raise ValueError("turn context contains duplicate presented positions")
        return self

    def model_safe_value(self) -> dict:
        """Return a JSON-ready value with only explicitly allow-listed fields."""

        return self.model_dump(mode="json")


class TurnContextEnvelopeBuilder:
    """Project existing application evidence into the bounded turn contract."""

    def build(
        self,
        *,
        temporal_context: TemporalContext,
        recent_messages: tuple[ConversationMessage, ...] = (),
        active_continuity: dict[str, str] | None = None,
        memory_context: tuple[dict, ...] = (),
        capability_snapshot: Any | None = None,
        presented_context: tuple[dict, ...] = (),
        last_application_result: tuple[str | None, str] | None = None,
    ) -> TurnContextEnvelope:
        turns = tuple(
            TurnConversationHint(
                reference=f"T{index}",
                role=message.role.value,
                content=self._bounded(message.content, 2_000),
                occurred_at=message.created_at,
            )
            for index, message in enumerate(recent_messages[-8:], start=1)
            if message.content.strip()
        )
        memories = []
        for item in memory_context[:6]:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            confidence = item.get("confidence")
            memories.append(TurnMemoryHint(
                reference=f"M{len(memories) + 1}",
                kind=self._bounded(str(item.get("category") or "information"), 80),
                content=self._bounded(content, 1_000),
                time_text=(
                    None
                    if item.get("time") is None
                    else self._bounded(str(item["time"]), 120)
                ),
                confidence=(
                    float(confidence) if isinstance(confidence, (int, float)) else None
                ),
            ))
        continuity = self._continuity(active_continuity)
        capability_rows = (
            ()
            if capability_snapshot is None
            else tuple(getattr(capability_snapshot, "operations", ()))
        )
        capabilities = tuple(
            TurnCapabilityHint(
                operation_id=item.operation.operation_id,
                availability=item.availability.value,
            )
            for item in capability_rows[:32]
        )
        presented_entities = tuple(
            TurnPresentedEntityHint(
                reference=f"P{index}",
                position=int(item["position"]),
                owner_operation_id=str(item["owner_operation_id"]),
                kind=self._bounded(str(item["kind"]), 80),
                human_label=self._bounded(str(item["human_label"]), 500),
                time_text=(
                    None
                    if item.get("time_text") is None
                    else self._bounded(str(item["time_text"]), 120)
                ),
            )
            for index, item in enumerate(presented_context[:10], start=1)
        )
        application_result = None
        if last_application_result is not None:
            operation_id, projection_state = last_application_result
            if operation_id is not None and projection_state in {
                "clarification", "waiting_confirmation", "completed_read",
                "failed", "unsupported",
            }:
                application_result = TurnApplicationResultHint(
                    operation_id=operation_id,
                    projection_state=projection_state,
                )
        return TurnContextEnvelope(
            temporal=TurnTemporalContext.from_temporal_context(temporal_context),
            recent_turns=turns,
            active_continuity=continuity,
            memory_hints=tuple(memories),
            presented_entities=presented_entities,
            capabilities=capabilities,
            last_application_result=application_result,
        )

    @staticmethod
    def _continuity(value: dict[str, str] | None) -> TurnContinuityHint | None:
        if not value:
            return None
        topic = str(value.get("topic") or "").strip()
        summary = str(value.get("summary") or "").strip()
        reason = str(value.get("reason_to_return") or "").strip()
        if not topic or not summary or not reason:
            return None
        return TurnContinuityHint(
            topic=TurnContextEnvelopeBuilder._bounded(topic, 200),
            summary=TurnContextEnvelopeBuilder._bounded(summary, 1_000),
            reason_to_return=TurnContextEnvelopeBuilder._bounded(reason, 500),
        )

    @staticmethod
    def _bounded(value: str, limit: int) -> str:
        normalized = " ".join(value.split())
        return normalized[:limit]
