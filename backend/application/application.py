"""Public in-process facade for a future local Masha Home UI."""

from __future__ import annotations

from .contracts import (
    ConversationTurnResult,
    ConversationView,
    MashaStatusView,
    ModelProfileView,
    ModelSwitchResult,
    ResolvedVisualAsset,
    SafetyView,
    VisualAssetView,
)
from .conversation import ConversationApplicationService
from .model_settings import ModelSettingsService
from .status import MashaStatusService
from .visual_assets import VisualIdentityResolver


class MashaApplication:
    """Thin facade: orchestration and presentation only, never domain ownership."""

    def __init__(
        self,
        *,
        conversation: ConversationApplicationService,
        status: MashaStatusService,
        visuals: VisualIdentityResolver,
        models: ModelSettingsService,
    ):
        self._conversation = conversation
        self._status = status
        self._visuals = visuals
        self._models = models

    def send_message(self, content: str, *, project_id: str, conversation_id: str | None = None) -> ConversationTurnResult:
        return self._conversation.send_message(content, project_id=project_id, conversation_id=conversation_id)

    def conversation(self, conversation_id: str, *, limit: int = 16) -> ConversationView:
        return self._conversation.conversation(conversation_id, limit=limit)

    def status(self) -> MashaStatusView:
        return self._status.snapshot()

    def emergency_stop(self, reason: str = "manual_emergency_stop") -> SafetyView:
        return self._status.engage_emergency_stop(reason)

    def resume_autonomy(self) -> SafetyView:
        return self._status.release_emergency_stop()

    def canonical_visual_assets(self) -> tuple[VisualAssetView, ...]:
        return self._visuals.canonical_assets()

    def resolve_visual_asset(self, asset_id: str) -> ResolvedVisualAsset:
        return self._visuals.resolve(asset_id)

    def model_profiles(self) -> tuple[ModelProfileView, ...]:
        return self._models.list_profiles()

    def current_model(self) -> ModelProfileView:
        return self._models.current()

    def use_model(self, profile_id: str) -> ModelSwitchResult:
        return self._models.use(profile_id)
