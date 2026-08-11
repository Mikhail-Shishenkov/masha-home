"""Public local application boundary for future Masha Home user interfaces."""

from .application import MashaApplication
from .composition import build_masha_application
from .contracts import (
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ConversationTurnResult,
    ConversationTurnStatus,
    ConversationView,
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
    "MashaApplication",
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
