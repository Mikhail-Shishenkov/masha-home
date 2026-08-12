"""Public in-process facade for a future local Masha Home UI."""

from __future__ import annotations

from datetime import datetime, timezone

from .contracts import (
    AgentRunListView,
    ConversationTurnResult,
    CommitmentListView,
    CommitmentProposalResult,
    HonestHelpResolutionView,
    ConfirmationResolutionResult,
    ConversationView,
    ConversationSummaryView,
    HomeAttentionView,
    MashaStatusView,
    ModelProfileView,
    ModelSwitchResult,
    PendingConfirmationView,
    ProactiveInteractionListView,
    ProactiveInteractionView,
    ReflectionResolutionView,
    ReflectionWorkspaceView,
    ResolvedVisualAsset,
    SafetyView,
    SharedContinuityView,
    VisualAssetView,
    WorkbenchView,
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
        commitments,
        activities,
        proactive,
        continuity,
        reflections,
        workbench,
    ):
        self._conversation = conversation
        self._status = status
        self._visuals = visuals
        self._models = models
        self._home_snapshot = home_snapshot
        self._commitments = commitments
        self._activities = activities
        self._proactive = proactive
        self._continuity = continuity
        self._reflections = reflections
        self._workbench = workbench

    def send_message(self, content: str, *, project_id: str, conversation_id: str | None = None) -> ConversationTurnResult:
        return self._conversation.send_message(content, project_id=project_id, conversation_id=conversation_id)

    def conversation(self, conversation_id: str, *, limit: int = 16) -> ConversationView:
        return self._conversation.conversation(conversation_id, limit=limit)

    def latest_conversation(self, *, limit: int = 16) -> ConversationView | None:
        """Read the transcript with the latest actual interaction, if one exists."""
        return self._conversation.latest_conversation(limit=limit)

    def recent_conversations(self, *, limit: int = 8) -> tuple[ConversationSummaryView, ...]:
        return self._conversation.recent_conversations(limit=limit)

    def commitments(self, *, limit: int = 12) -> CommitmentListView:
        return self._commitments.list(limit=limit)

    def agent_runs(self, *, limit: int = 8) -> AgentRunListView:
        return self._activities.list(limit=limit)

    def proactive_interactions(self, *, limit: int = 6) -> ProactiveInteractionListView:
        return self._proactive.list(limit=limit)

    def refresh_proactive_interactions(self, *, limit: int = 6) -> ProactiveInteractionListView:
        """Advance only the existing policy-controlled local runtime."""
        return self._proactive.refresh(limit=limit)

    def resolve_proactive(self, interaction_id: str, decision: str) -> ProactiveInteractionView:
        return self._proactive.resolve(interaction_id, decision)

    def shared_continuity(self) -> SharedContinuityView:
        return self._continuity.view()

    def continue_continuity_thread(
        self,
        thread_id: str,
        *,
        conversation_id: str | None,
        project_id: str,
    ) -> ConversationTurnResult:
        prompt = self._continuity.thread_prompt(thread_id)
        return self._conversation.send_message(
            prompt,
            project_id=project_id,
            conversation_id=conversation_id,
        )

    def reflection_workspace(self) -> ReflectionWorkspaceView:
        return self._reflections.workspace()

    def resolve_reflection(self, candidate_id: str, decision: str) -> ReflectionResolutionView:
        return self._reflections.resolve_reflection(candidate_id, decision)

    def resolve_honest_help(self, candidate_id: str, decision: str) -> HonestHelpResolutionView:
        return self._reflections.resolve_help(candidate_id, decision)

    def workbench(self) -> WorkbenchView:
        return self._workbench.view()

    def propose_skill_install(self, source_path: str):
        return self._workbench.propose_install(source_path)

    def resolve_skill_install(self, proposal_id: str, decision: str):
        return self._workbench.resolve_install(proposal_id, decision)

    def propose_commitment_completion(
        self,
        *,
        commitment_id: str,
        conversation_id: str | None,
        project_id: str,
    ) -> CommitmentProposalResult:
        return self._commitments.propose_completion(
            commitment_id=commitment_id,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    def pending_confirmation(self, conversation_id: str) -> PendingConfirmationView | None:
        return self._conversation.pending_confirmation(conversation_id)

    def resolve_confirmation(
        self,
        *,
        conversation_id: str,
        proposal_id: str,
        decision: str,
        project_id: str,
    ) -> ConfirmationResolutionResult:
        return self._conversation.resolve_confirmation(
            conversation_id=conversation_id,
            proposal_id=proposal_id,
            decision=decision,
            project_id=project_id,
        )

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
            commitments_count=sum(
                item.can_propose_completion for item in self._commitments.list().items
            ),
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
