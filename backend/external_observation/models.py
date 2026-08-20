"""Provider-neutral contracts for bounded read-only external observation."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictObservationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObservationKind(str, Enum):
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"


class FreshnessRequirement(str, Enum):
    TIMELESS = "timeless"
    RECENT = "recent"
    CURRENT = "current"
    BREAKING = "breaking"


class InvocationAuthority(str, Enum):
    USER_EXPLICIT = "user_explicit"
    ASSISTANT_AUTO = "assistant_auto"
    TASK_SCOPED = "task_scoped"
    BACKGROUND = "background"


class SourceTimeKind(str, Enum):
    PUBLISHED = "published"
    UPDATED = "updated"
    DISCOVERED = "discovered"
    PROVIDER_ESTIMATE = "provider_estimate"
    UNKNOWN = "unknown"


class SourceTimePrecision(str, Enum):
    EXACT = "exact"
    DATE = "date"
    RELATIVE = "relative"
    UNKNOWN = "unknown"


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    AGED = "aged"
    UNKNOWN = "unknown"


class ObservationStatus(str, Enum):
    COMPLETED = "completed"
    CLARIFICATION_REQUIRED = "clarification_required"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class SourceTime(StrictObservationModel):
    value: AwareDatetime | date | None = None
    kind: SourceTimeKind = SourceTimeKind.UNKNOWN
    precision: SourceTimePrecision = SourceTimePrecision.UNKNOWN

    @model_validator(mode="after")
    def value_and_kind_agree(self):
        if self.value is None and (
            self.kind is not SourceTimeKind.UNKNOWN
            or self.precision is not SourceTimePrecision.UNKNOWN
        ):
            raise ValueError("unknown source time must not claim a value or precision")
        if self.value is not None and self.kind is SourceTimeKind.UNKNOWN:
            raise ValueError("known source time requires a non-unknown kind")
        return self


class ObservationRequest(StrictObservationModel):
    observation_id: str = Field(min_length=8, max_length=100)
    kind: ObservationKind = ObservationKind.WEB_SEARCH
    query: str = Field(min_length=1, max_length=300)
    authority: InvocationAuthority
    freshness: FreshnessRequirement
    reason: str = Field(min_length=1, max_length=300)
    requested_at: AwareDatetime
    origin_message_id: str = Field(min_length=1, max_length=100)


class ProviderSearchRequest(StrictObservationModel):
    """The complete and intentionally small payload visible to a search provider."""

    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(ge=1, le=5)
    region: str = Field(pattern=r"^[a-z]{2}-[a-z]{2}$")
    freshness: FreshnessRequirement
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=20.0)


class SearchEvidence(StrictObservationModel):
    source_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    provider_id: str = Field(min_length=1, max_length=50)
    search_backend: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2_000)
    canonical_url: str = Field(min_length=8, max_length=2_000)
    domain: str = Field(min_length=1, max_length=253)
    snippet: str = Field(min_length=1, max_length=800)
    source_time: SourceTime = Field(default_factory=SourceTime)
    retrieved_at: AwareDatetime
    observation_started_at: AwareDatetime
    provider_rank: int = Field(ge=1, le=100)
    freshness_status: FreshnessStatus

    @field_validator("url", "canonical_url")
    @classmethod
    def https_only(cls, value: str) -> str:
        if not value.casefold().startswith("https://"):
            raise ValueError("external evidence URL must use HTTPS")
        return value


class ExternalObservation(StrictObservationModel):
    request: ObservationRequest
    status: ObservationStatus
    evidence: tuple[SearchEvidence, ...] = Field(default=(), max_length=5)
    provider_calls: int = Field(default=0, ge=0, le=2)
    provider_id: str | None = Field(default=None, max_length=50)
    search_backend: str | None = Field(default=None, max_length=50)
    error_reason: str | None = Field(default=None, max_length=200)
    completed_at: AwareDatetime
    assistant_message_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def completed_observation_has_evidence(self):
        if self.status is ObservationStatus.COMPLETED and not self.evidence:
            raise ValueError("completed observation requires evidence")
        if self.status is not ObservationStatus.COMPLETED and self.evidence:
            raise ValueError("non-completed observation cannot expose evidence")
        return self


class ExternalObservationState(StrictObservationModel):
    schema_version: Literal["1.0"] = "1.0"
    observations: tuple[ExternalObservation, ...] = ()
