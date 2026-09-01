"""Public local application boundary for future Masha Home user interfaces."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .application import MashaApplication

from .home_snapshot import HomeSnapshotView
from .contracts import (
    AgentRunListView,
    AgentRunView,
    AgentStepView,
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ConversationTurnResult,
    ConversationTurnStatus,
    ConversationPageView,
    CommitmentListView,
    CommitmentProposalResult,
    CommitmentView,
    ConfirmationResolutionResult,
    ConfirmationResolutionStatus,
    ConversationView,
    ConversationSummaryView,
    ExternalObservationView,
    DocumentReadView,
    ExternalSourceView,
    FetchedPageView,
    HomeAttentionView,
    HonestHelpOfferView,
    HonestHelpResolutionView,
    MashaStatusView,
    MessageView,
    ModelAvailabilityCode,
    ModelProfileView,
    ModelSwitchResult,
    ModelSwitchStatus,
    PendingConfirmationView,
    PassiveMemoryCandidateView,
    PassiveMemoryCandidateResolutionView,
    MemoryProvenanceView,
    ProactiveInteractionListView,
    ProactiveInteractionView,
    ProactiveDiagnosticView,
    AdoptedReflectionView,
    ContinuityFollowUpView,
    ConfirmedMemoryItemView,
    PendingReflectionView,
    ReflectionResolutionView,
    ReflectionWorkspaceView,
    RelationshipMomentView,
    ResolvedVisualAsset,
    SafetyView,
    SharedContinuityView,
    VisualAssetView,
    WorkbenchView,
    SkillWorkbenchView,
    SkillInstallPreviewView,
    SkillInstallResultView,
    PermissionGrantView,
    PermissionPendingView,
)
from .model_settings import ModelSettingsService
from .human_information import (
    HumanAvailability,
    HumanInformationItem,
    HumanInformationService,
    HumanRecallRequest,
    HumanRecallResult,
    HumanSearchRequest,
    HumanSearchResult,
    HumanSearchScope,
    HumanTimeFilter,
    HumanTimePreset,
    RecallMode,
)


def __getattr__(name: str):
    """Load composition-heavy public exports only when they are requested.

    Conversation/domain modules import lightweight application contracts. An
    eager package-level composition import would pull those conversation
    modules back in while they are still initializing and make their public
    APIs depend on import order.
    """

    if name == "MashaApplication":
        from .application import MashaApplication

        globals()[name] = MashaApplication
        return MashaApplication
    if name == "build_masha_application":
        from .composition import build_masha_application

        globals()[name] = build_masha_application
        return build_masha_application
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = (
    "AgentRunListView",
    "AgentRunView",
    "AgentStepView",
    "ApplicationBoundaryError",
    "ApplicationErrorCode",
    "ConversationTurnResult",
    "ConversationTurnStatus",
    "ConversationPageView",
    "CommitmentListView",
    "CommitmentProposalResult",
    "CommitmentView",
    "ConfirmationResolutionResult",
    "ConfirmationResolutionStatus",
    "ConversationView",
    "ConversationSummaryView",
    "ExternalObservationView",
    "DocumentReadView",
    "ExternalSourceView",
    "FetchedPageView",
    "HomeAttentionView",
    "HonestHelpOfferView",
    "HonestHelpResolutionView",
    "MashaApplication",
    "HomeSnapshotView",
    "HumanAvailability",
    "HumanInformationItem",
    "HumanInformationService",
    "HumanRecallRequest",
    "HumanRecallResult",
    "HumanSearchRequest",
    "HumanSearchResult",
    "HumanSearchScope",
    "HumanTimeFilter",
    "HumanTimePreset",
    "MashaStatusView",
    "MessageView",
    "ModelAvailabilityCode",
    "ModelProfileView",
    "ModelSettingsService",
    "ModelSwitchResult",
    "ModelSwitchStatus",
    "PendingConfirmationView",
    "PassiveMemoryCandidateView",
    "PassiveMemoryCandidateResolutionView",
    "MemoryProvenanceView",
    "ProactiveInteractionListView",
    "ProactiveInteractionView",
    "ProactiveDiagnosticView",
    "AdoptedReflectionView",
    "ContinuityFollowUpView",
    "ConfirmedMemoryItemView",
    "PendingReflectionView",
    "ReflectionResolutionView",
    "ReflectionWorkspaceView",
    "RelationshipMomentView",
    "RecallMode",
    "ResolvedVisualAsset",
    "SafetyView",
    "SharedContinuityView",
    "VisualAssetView",
    "WorkbenchView",
    "SkillWorkbenchView",
    "SkillInstallPreviewView",
    "SkillInstallResultView",
    "PermissionGrantView",
    "PermissionPendingView",
    "build_masha_application",
)
