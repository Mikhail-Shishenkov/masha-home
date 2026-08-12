"""Public in-process facade for a future local Masha Home UI."""

from __future__ import annotations

from datetime import datetime, timezone

from .contracts import (
    ConversationTurnResult,
    ConversationView,
    ConversationSummaryView,
    HomeAttentionView,
    MashaStatusView,
    ModelProfileView,
    ModelSwitchResult,
    ResolvedVisualAsset,
    SafetyView,
    VisualAssetView,
)
from .conversation import ConversationApplicationService
from .home_snapshot import HomeSnapshotService, HomeSnapshotView
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
        home_snapshot: HomeSnapshotService,
    ):
        self._conversation = conversation
        self._status = status
        self._visuals = visuals
        self._models = models
        self._home_snapshot = home_snapshot

    def send_message(self, content: str, *, project_id: str, conversation_id: str | None = None) -> ConversationTurnResult:
        return self._conversation.send_message(content, project_id=project_id, conversation_id=conversation_id)

    def conversation(self, conversation_id: str, *, limit: int = 16) -> ConversationView:
        return self._conversation.conversation(conversation_id, limit=limit)

    def latest_conversation(self, *, limit: int = 16) -> ConversationView | None:
        """Read the transcript with the latest actual interaction, if one exists."""
        return self._conversation.latest_conversation(limit=limit)

    def recent_conversations(self, *, limit: int = 8) -> tuple[ConversationSummaryView, ...]:
        return self._conversation.recent_conversations(limit=limit)

    def status(self) -> MashaStatusView:
        return self._status.snapshot()

    def home_attention(self, *, conversation_id: str | None = None) -> HomeAttentionView:
        """Return only facts that are safe and meaningful in the current Home slice."""
        status = self._status.snapshot()
        active_conversation = None
        if conversation_id is not None:
            active_conversation = next(
                (
                    item
                    for item in self._conversation.recent_conversations(limit=8)
                    if item.conversation_id == conversation_id
                ),
                None,
            )
        return HomeAttentionView(
            observed_at=datetime.now(timezone.utc),
            active_conversation=active_conversation,
            model_available=status.model_available,
            model_label=status.model_label,
            emergency_stop_engaged=status.emergency_stop_engaged,
            safety_label=status.safety_label,
        )

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

    def home_snapshot(self) -> HomeSnapshotView:
        """Return the one-way, renderer-safe current Home projection."""
        return self._home_snapshot.snapshot()

    def open_home_session(self):
        """Create a deterministic presentation session for one local Home window."""
        return self._home_snapshot.open_session()
