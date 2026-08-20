"""Public in-process facade for a future local Masha Home UI."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.conversation.human_reference import PresentedEntitySet

from .contracts import (
    AgentRunListView,
    ConversationTurnResult,
    ContinuityFollowUpView,
    ConversationPageView,
    CommitmentView,
    CommitmentListView,
    CommitmentProposalResult,
    HonestHelpResolutionView,
    ConfirmationResolutionResult,
    ConversationView,
    ConversationSummaryView,
    MashaStatusView,
    ModelProfileView,
    ModelSwitchResult,
    PendingConfirmationView,
    PassiveMemoryCandidateResolutionView,
    PassiveMemoryCandidateView,
    MemoryProvenanceView,
    ProactiveInteractionListView,
    ProactiveInteractionView,
    ReflectionResolutionView,
    ReflectionWorkspaceView,
    ResolvedVisualAsset,
    SafetyView,
    SharedContinuityView,
    VisualAssetView,
    WorkbenchView,
    HomeAttentionItemView,
    HomeAttentionView,
)
from .conversation import ConversationApplicationService
from .home_snapshot import HomeSnapshotService, HomeSnapshotView
from .human_information import (
    HumanRecallRequest,
    HumanRecallResult,
    HumanSearchRequest,
    HumanSearchResult,
)
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
        memory_candidates,
        human_information,
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
        self._memory_candidates = memory_candidates
        self._human_information = human_information

    def send_message(
        self,
        content: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
        home_moment: str = "ordinary",
    ) -> ConversationTurnResult:
        return self._conversation.send_message(
            content,
            project_id=project_id,
            conversation_id=conversation_id,
            home_moment=home_moment,
        )

    def conversation(self, conversation_id: str, *, limit: int | None = None) -> ConversationView:
        return self._conversation.conversation(conversation_id, limit=limit)

    def latest_conversation(self, *, limit: int | None = None) -> ConversationView | None:
        """Read the transcript with the latest actual interaction, if one exists."""
        return self._conversation.latest_conversation(limit=limit)

    def recent_conversations(self, *, limit: int | None = None) -> tuple[ConversationSummaryView, ...]:
        return self._conversation.recent_conversations(limit=limit)

    def conversation_page(self, *, offset: int = 0, limit: int = 10, query: str | None = None) -> ConversationPageView:
        return self._conversation.conversation_page(offset=offset, limit=limit, query=query)

    def commitments(self, *, limit: int | None = 10, offset: int = 0) -> CommitmentListView:
        return self._commitments.list(limit=limit, offset=offset)

    def commitment(self, commitment_id: str) -> CommitmentView | None:
        return self._commitments.get(commitment_id)

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

    def continuity_thread(self, thread_id: str) -> ContinuityFollowUpView:
        return self._continuity.thread(thread_id)

    def activate_continuity_thread(
        self,
        thread_id: str,
        *,
        conversation_id: str | None,
    ) -> ContinuityFollowUpView:
        if conversation_id is None:
            raise ValueError("continuity thread needs an active conversation")
        thread = self._continuity.thread(thread_id)
        self._conversation.activate_continuity_thread(
            thread_id,
            conversation_id=conversation_id,
        )
        return thread

    def clear_continuity_thread(
        self,
        *,
        conversation_id: str | None,
    ) -> None:
        if conversation_id is None:
            return
        self._conversation.clear_continuity_thread(conversation_id=conversation_id)

    def active_continuity_thread(
        self,
        *,
        conversation_id: str | None,
    ) -> ContinuityFollowUpView | None:
        if conversation_id is None:
            return None
        thread_id = self._conversation.active_continuity_thread_id(
            conversation_id=conversation_id,
        )
        if thread_id is None:
            return None
        try:
            return self._continuity.thread(thread_id)
        except KeyError:
            self._conversation.clear_continuity_thread(conversation_id=conversation_id)
            return None

    def continue_continuity_thread(
        self,
        thread_id: str,
        *,
        conversation_id: str | None,
        project_id: str,
        home_moment: str = "ordinary",
    ) -> ConversationTurnResult:
        prompt = self._continuity.thread_prompt(thread_id)
        return self._conversation.send_message(
            prompt,
            project_id=project_id,
            conversation_id=conversation_id,
            allow_capability_routing=False,
            active_continuity_thread_id=thread_id,
            home_moment=home_moment,
        )

    def reflection_workspace(self) -> ReflectionWorkspaceView:
        return self._reflections.workspace()

    def resolve_reflection(self, candidate_id: str, decision: str) -> ReflectionResolutionView:
        return self._reflections.resolve_reflection(candidate_id, decision)

    def resolve_honest_help(self, candidate_id: str, decision: str) -> HonestHelpResolutionView:
        return self._reflections.resolve_help(candidate_id, decision)

    def list_pending_memory_candidates(
        self,
    ) -> tuple[PassiveMemoryCandidateView, ...]:
        return self._memory_candidates.list_pending_memory_candidates()

    def approve_memory_candidate(
        self,
        candidate_id: str,
        *,
        supersede_existing: bool = False,
    ) -> PassiveMemoryCandidateResolutionView:
        return self._memory_candidates.approve_memory_candidate(
            candidate_id,
            supersede_existing=supersede_existing,
        )

    def reject_memory_candidate(
        self,
        candidate_id: str,
    ) -> PassiveMemoryCandidateResolutionView:
        return self._memory_candidates.reject_memory_candidate(candidate_id)

    def memory_provenance(self, record_id: str) -> MemoryProvenanceView:
        return self._memory_candidates.memory_provenance(record_id)

    def search_information(self, request: HumanSearchRequest) -> HumanSearchResult:
        """Typed future-UI boundary; no synthetic conversation command required."""
        return self._human_information.search_information(request)

    def register_presented_information(
        self,
        result: HumanSearchResult,
        *,
        conversation_id: str,
    ) -> PresentedEntitySet | None:
        """Make the exact application-rendered order the one ordinal truth."""
        presented = self._human_information.presented_entity_set(
            result,
            conversation_id=conversation_id,
        )
        if presented is None:
            self._conversation.discard_presented_entity_set(conversation_id)
        else:
            self._conversation.remember_presented_entity_set(presented)
        return presented

    def presented_information(self, conversation_id: str) -> PresentedEntitySet | None:
        return self._conversation.presented_entity_set(conversation_id)

    def discard_presented_information(self, conversation_id: str) -> None:
        self._conversation.discard_presented_entity_set(conversation_id)

    def recall_information(self, request: HumanRecallRequest) -> HumanRecallResult:
        """Reusable deterministic recall for future application-owned callers."""
        return self._human_information.recall_information(request)

    def restore_information(self, *, record_id: str, conversation_id: str) -> PendingConfirmationView:
        """Create a restore proposal; visibility changes only after confirmation."""
        self._human_information.restore_information(
            record_id=record_id,
            conversation_id=conversation_id,
        )
        pending = self._conversation.pending_confirmation(conversation_id)
        if pending is None:  # pragma: no cover - proposal store contract
            raise RuntimeError("restore proposal was not created")
        return pending

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

    def propose_commitment_cancellation(
            self,
            *,
            commitment_id: str,
            conversation_id: str | None,
            project_id: str,
    ) -> CommitmentProposalResult:
        return self._commitments.propose_cancellation(
            commitment_id=commitment_id,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    def propose_commitment_due_change(
            self,
            *,
            commitment_id: str,
            conversation_id: str | None,
            project_id: str,
            due_at: datetime | None,
    ) -> CommitmentProposalResult:
        return self._commitments.propose_due_change(
            commitment_id=commitment_id,
            conversation_id=conversation_id,
            project_id=project_id,
            due_at=due_at,
        )

    def propose_commitment_reschedule(
            self,
            *,
            commitment_id: str,
            conversation_id: str | None,
            project_id: str,
            due_text: str,
    ) -> CommitmentProposalResult:
        return self._commitments.propose_reschedule_text(
            commitment_id=commitment_id,
            conversation_id=conversation_id,
            project_id=project_id,
            due_text=due_text,
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

    def home_attention(
            self,
            *,
            conversation_id: str | None = None,
    ) -> HomeAttentionView:
        """Return a bounded, human-facing projection of what deserves attention."""

        status = self._status.snapshot()

        # Commitments owns the temporal classification.
        # Attention consumes that projection instead of recalculating it.
        commitments = self._commitments.list(limit=None)
        observed_at = commitments.observed_at

        fresh_overdue = [
            item
            for item in commitments.items
            if item.time_bucket == "fresh_overdue"
        ]

        upcoming = [
            item
            for item in commitments.items
            if item.time_bucket == "upcoming"
        ]

        active_conversation = None

        if conversation_id is not None:
            active_conversation = next(
                (
                    item
                    for item in self._conversation.recent_conversations()
                    if item.conversation_id == conversation_id
                ),
                None,
            )

        proactive = self._proactive.list(limit=6)

        pending = (
            None
            if conversation_id is None
            else self._conversation.pending_confirmation(
                conversation_id
            )
        )

        attention_items: list[HomeAttentionItemView] = []

        # System state may speak first.
        if status.emergency_stop_engaged:
            attention_items.append(
                HomeAttentionItemView(
                    kind="safety_stop",
                    title="Автономные действия остановлены",
                    detail=(
                        "Разговор остаётся рядом, "
                        "но сама я ничего не запущу."
                    ),
                    urgency="notice",
                )
            )

        if not status.model_available:
            attention_items.append(
                HomeAttentionItemView(
                    kind="model_unavailable",
                    title="Локальная модель сейчас недоступна",
                    detail=status.model_label,
                    urgency="important",
                )
            )

        # An explicit human decision outranks ordinary planning.
        if pending is not None:
            attention_items.append(
                HomeAttentionItemView(
                    kind="pending_confirmation",
                    title=pending.title,
                    detail=pending.subject,
                    urgency="important",
                )
            )

        # At most one fresh overdue commitment.
        if fresh_overdue and len(attention_items) < 4:
            commitment = fresh_overdue[0]

            overdue_seconds = (
                    observed_at
                    - commitment.due_at.astimezone(timezone.utc)
            ).total_seconds()

            attention_items.append(
                HomeAttentionItemView(
                    kind="overdue_commitment",
                    title=commitment.text,
                    detail=(
                        "Срок только что прошёл"
                        if overdue_seconds < 60 * 60
                        else "Срок уже прошёл"
                    ),
                    urgency="important",
                )
            )

        # Then look forward.
        for commitment in upcoming:
            if len(attention_items) >= 4:
                break

            attention_items.append(
                HomeAttentionItemView(
                    kind="upcoming_commitment",
                    title=commitment.text,
                    detail=(
                        f"До "
                        f"{commitment.due_at.astimezone().strftime('%d.%m в %H:%M')}"
                        if commitment.due_at is not None
                        else None
                    ),
                    urgency="notice",
                )
            )

        # Proactivity uses only the remaining attention space.
        remaining_slots = max(
            0,
            4 - len(attention_items),
        )

        for interaction in proactive.items[:remaining_slots]:
            attention_items.append(
                HomeAttentionItemView(
                    kind="proactive_interaction",
                    title=interaction.title,
                    detail=interaction.message,
                    urgency="notice",
                )
            )

        return HomeAttentionView(
            observed_at=observed_at,
            active_conversation=active_conversation,
            model_available=status.model_available,
            model_label=status.model_label,
            emergency_stop_engaged=status.emergency_stop_engaged,
            safety_label=status.safety_label,
            commitments_count=commitments.actionable_total,
            overdue_commitments_count=(
                    commitments.fresh_overdue_total
                    + commitments.stale_overdue_total
            ),
            stale_overdue_commitments_count=(
                commitments.stale_overdue_total
            ),
            upcoming_commitments_count=(
                commitments.upcoming_total
            ),
            unscheduled_commitments_count=(
                commitments.unscheduled_total
            ),
            pending_interactions_count=len(proactive.items),
            attention_items=tuple(attention_items[:4]),
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
