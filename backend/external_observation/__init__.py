"""Read-only external observation foundation."""

from .intent import ExplicitExternalIntentGate, ExternalIntentDecision
from .models import (
    ExternalObservation,
    FreshnessRequirement,
    FreshnessStatus,
    InvocationAuthority,
    ObservationKind,
    ObservationRequest,
    ObservationStatus,
    ProviderSearchRequest,
    SearchEvidence,
    SourceTime,
    SourceTimeKind,
    SourceTimePrecision,
)
from .planner import ExternalQueryPlan, FakeExternalQueryPlanner, LocalExternalQueryPlanner
from .policy import InternetAccessMode, InternetAccessPolicy, InternetAccessPolicyStore
from .provider import (
    DDGSWebSearchProvider,
    FakeWebSearchProvider,
    WebSearchProvider,
    WebSearchProviderFailedError,
    WebSearchProviderTimeoutError,
    WebSearchProviderUnavailableError,
    canonicalize_https_url,
)
from .service import EXTERNAL_INFORMATION_CONTRACT, ExternalObservationService
from .store import ExternalObservationStore

__all__ = [
    "DDGSWebSearchProvider",
    "EXTERNAL_INFORMATION_CONTRACT",
    "ExplicitExternalIntentGate",
    "ExternalIntentDecision",
    "ExternalObservation",
    "ExternalObservationService",
    "ExternalObservationStore",
    "ExternalQueryPlan",
    "FakeExternalQueryPlanner",
    "FakeWebSearchProvider",
    "FreshnessRequirement",
    "FreshnessStatus",
    "InternetAccessMode",
    "InternetAccessPolicy",
    "InternetAccessPolicyStore",
    "InvocationAuthority",
    "LocalExternalQueryPlanner",
    "ObservationKind",
    "ObservationRequest",
    "ObservationStatus",
    "ProviderSearchRequest",
    "SearchEvidence",
    "SourceTime",
    "SourceTimeKind",
    "SourceTimePrecision",
    "WebSearchProvider",
    "WebSearchProviderFailedError",
    "WebSearchProviderTimeoutError",
    "WebSearchProviderUnavailableError",
    "canonicalize_https_url",
]
