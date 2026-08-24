"""Read-only external observation foundation."""

from .intent import (
    ExplicitExternalIntentGate,
    ExplicitWebFetchIntentGate,
    ExternalIntentDecision,
    FetchIntentDecision,
    InformationSpace,
    classify_information_space,
)
from .context import (
    ExternalContextHint,
    ExternalContextHintKind,
    ExternalContextHintProvider,
    ExternalContextResolution,
    requires_local_context_resolution,
)
from .models import (
    ExternalObservation,
    FetchedPageEvidence,
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
from .safe_fetcher import SafeFetchError, SafeFetchResponse, SafePublicHttpsFetcher
from .store import ExternalObservationStore
from .source_selector import FakeSourceSelector, LocalSourceSelector, SelectableSource, SourceSelector

__all__ = [
    "DDGSWebSearchProvider",
    "EXTERNAL_INFORMATION_CONTRACT",
    "ExplicitExternalIntentGate",
    "ExplicitWebFetchIntentGate",
    "ExternalContextHint",
    "ExternalContextHintKind",
    "ExternalContextHintProvider",
    "ExternalContextResolution",
    "ExternalIntentDecision",
    "FetchIntentDecision",
    "InformationSpace",
    "classify_information_space",
    "ExternalObservation",
    "FetchedPageEvidence",
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
    "requires_local_context_resolution",
    "LocalSourceSelector",
    "ObservationKind",
    "ObservationRequest",
    "ObservationStatus",
    "ProviderSearchRequest",
    "SearchEvidence",
    "SafeFetchError",
    "SafeFetchResponse",
    "SafePublicHttpsFetcher",
    "SourceSelector",
    "SelectableSource",
    "FakeSourceSelector",
    "SourceTime",
    "SourceTimeKind",
    "SourceTimePrecision",
    "WebSearchProvider",
    "WebSearchProviderFailedError",
    "WebSearchProviderTimeoutError",
    "WebSearchProviderUnavailableError",
    "canonicalize_https_url",
]
