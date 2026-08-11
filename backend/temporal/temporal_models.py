"""Small immutable temporal and proactive-domain objects for MEM-12.1."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .temporal_engine import TemporalContext


class TemporalEventStatus(str, Enum):
    OVERDUE = "overdue"


class ProactiveDecision(str, Enum):
    SUPPRESS = "suppress"
    REMIND = "remind"
    CHECK_IN = "check_in"
    URGENT_ALERT = "urgent_alert"
    REQUIRE_CONFIRMATION = "require_confirmation"


class CommitmentDueEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    event_type: str = "commitment_due"
    source_commitment_id: str = Field(min_length=1)
    due_at: datetime
    detected_at: datetime
    status: TemporalEventStatus = TemporalEventStatus.OVERDUE


class TemporalEventContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    events: tuple[CommitmentDueEvent, ...] = Field(max_length=6)


class ProactiveCandidate(BaseModel):
    """Bounded, non-delivered input for a future interaction layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    event: CommitmentDueEvent
    source_commitment_id: str = Field(min_length=1)
    source_commitment_text: str = Field(min_length=1)
    temporal_context: TemporalContext
    decision: ProactiveDecision
    generated_at: datetime


class CheckInCandidate(BaseModel):
    """Bounded authorised CHECK_IN formulation context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    absence_duration_seconds: int = Field(ge=0)
    last_message_at: datetime
    current_local_time: datetime
    timezone: str = "Europe/Moscow"
    proactive_level: int = Field(ge=2, le=5)
    decision: ProactiveDecision = ProactiveDecision.CHECK_IN
