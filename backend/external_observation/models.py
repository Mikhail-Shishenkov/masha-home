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
    target_url: str | None = Field(default=None, max_length=2_000)
    parent_observation_id: str | None = Field(default=None, min_length=8, max_length=100)
    parent_source_id: str | None = Field(default=None, pattern=r"^S[1-9][0-9]*$")

    @model_validator(mode="after")
    def web_fetch_target_and_parent_are_coherent(self):
        if self.kind is ObservationKind.WEB_SEARCH and self.target_url is not None:
            raise ValueError("WEB_SEARCH must not include target_url")
        if (self.parent_observation_id is None) != (self.parent_source_id is None):
            raise ValueError("parent observation and source must be provided together")
        return self


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


class FetchedPageEvidence(StrictObservationModel):
    requested_url: str = Field(min_length=8, max_length=2_000)
    final_url: str = Field(min_length=8, max_length=2_000)
    domain: str = Field(min_length=1, max_length=253)
    title: str | None = Field(default=None, max_length=300)
    content_type: str = Field(min_length=1, max_length=120)
    charset: str | None = Field(default=None, max_length=80)
    fetched_at: AwareDatetime
    raw_bytes_read: int = Field(ge=0, le=2 * 1024 * 1024)
    content_sha256: str = Field(
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 of the bounded decoded HTTP representation passed to extraction.",
    )
    truncated: bool = False
    extractor_id: str = Field(min_length=1, max_length=80)
    extracted_text: str = Field(min_length=1, max_length=8_000)

    @field_validator("requested_url", "final_url")
    @classmethod
    def fetched_urls_are_https(cls, value: str) -> str:
        if not value.casefold().startswith("https://"):
            raise ValueError("fetched page URL must use HTTPS")
        return value


class ExternalObservation(StrictObservationModel):
    request: ObservationRequest
    status: ObservationStatus
    evidence: tuple[SearchEvidence, ...] = Field(default=(), max_length=5)
    fetched_page: FetchedPageEvidence | None = None
    provider_calls: int = Field(default=0, ge=0, le=2)
    provider_id: str | None = Field(default=None, max_length=50)
    search_backend: str | None = Field(default=None, max_length=50)
    error_reason: str | None = Field(default=None, max_length=200)
    completed_at: AwareDatetime
    assistant_message_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def completed_observation_has_evidence(self):
        is_search = self.request.kind is ObservationKind.WEB_SEARCH
        if self.status is ObservationStatus.COMPLETED:
            if is_search and (not self.evidence or self.fetched_page is not None):
                raise ValueError("completed WEB_SEARCH requires search evidence only")
            if not is_search and (self.fetched_page is None or self.evidence):
                raise ValueError("completed WEB_FETCH requires one fetched page only")
        if self.status is not ObservationStatus.COMPLETED and (self.evidence or self.fetched_page is not None):
            raise ValueError("non-completed observation cannot expose evidence")
        return self


class ExternalObservationState(StrictObservationModel):
    schema_version: Literal["1.0"] = "1.0"
    observations: tuple[ExternalObservation, ...] = ()
