"""Public local application boundary for future Masha Home user interfaces."""

from .application import MashaApplication
from .composition import build_masha_application
from .home_snapshot import HomeSnapshotView
from .contracts import (
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ConversationTurnResult,
    ConversationTurnStatus,
    ConversationView,
    ConversationSummaryView,
    HomeAttentionView,
    MashaStatusView,
    MessageView,
    ModelAvailabilityCode,
    ModelProfileView,
    ModelSwitchResult,
    ModelSwitchStatus,
    ResolvedVisualAsset,
    SafetyView,
    VisualAssetView,
)
from .model_settings import ModelSettingsService

__all__ = (
    "ApplicationBoundaryError",
    "ApplicationErrorCode",
    "ConversationTurnResult",
    "ConversationTurnStatus",
    "ConversationView",
    "ConversationSummaryView",
    "HomeAttentionView",
    "MashaApplication",
    "HomeSnapshotView",
    "MashaStatusView",
    "MessageView",
    "ModelAvailabilityCode",
    "ModelProfileView",
    "ModelSettingsService",
    "ModelSwitchResult",
    "ModelSwitchStatus",
    "ResolvedVisualAsset",
    "SafetyView",
    "VisualAssetView",
    "build_masha_application",
)
