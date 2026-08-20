"""Read-only Home projection owned by the public application boundary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from backend.presentation import (
    AssistantResponded,
    AssistantSettled,
    AssistantStartedThinking,
    ActivityCompleted,
    ActivityCancelled,
    ActivityFailed,
    ActivityStarted,
    ActivityWaiting,
    AutonomyResumed,
    CompositionPlan,
    CompositionResolver,
    CompositionVariant,
    HomePresentationModel,
    EmergencyStopEngaged,
    ModelUnavailable,
    ModelChanged,
    ModelSwitchStarted,
    ProactiveAcknowledged,
    ProactiveDelivered,
    ProactiveDismissed,
    InteractionSurface,
    SurfaceCapability,
    SurfaceCompleted,
    SurfaceCreated,
    SurfaceFocused,
    SurfaceKind,
    SurfaceLifecycle,
    SurfaceRole,
    PresentationRuntime,
    UserOpenedApplication,
    UserSentMessage,
    ViewportCharacteristics,
    presentation_model_from_application_state,
    HomeMoment,
    HomeMomentChanged,
    HomeProximity,
    HomeProximityChanged,
)

from .contracts import MashaStatusView, ModelProfileView, UiContract, VisualAssetView
from .model_settings import ModelSettingsService
from .status import MashaStatusService
from .visual_assets import VisualIdentityResolver

_RESPONSE_EXPRESSION_CUES = frozenset(
    {
        "warm",
        "amused",
        "thoughtful",
        "supportive",
        "firm",
        "playful",
    }
)

class HomeSnapshotView(UiContract):
    """Bounded renderer-safe data with no service, provider, or storage handles."""

    observed_at: datetime
    home_timezone: str
    status: MashaStatusView
    active_model: ModelProfileView
    visual_assets: tuple[VisualAssetView, ...]
    presentation: HomePresentationModel
    composition: CompositionPlan


class HomeSnapshotService:
    """Build one deterministic UI projection from existing read-only services."""

    def __init__(
            self,
            *,
            status: MashaStatusService,
            models: ModelSettingsService,
            visuals: VisualIdentityResolver,
            composition: CompositionResolver | None = None,
            clock: Callable[[], datetime] | None = None,
    ):
        self._status = status
        self._models = models
        self._visuals = visuals
        self._composition = composition or CompositionResolver()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def snapshot(
        self,
        *,
        viewport: ViewportCharacteristics | None = None,
    ) -> HomeSnapshotView:
        """Read local state without mutating persistence or invoking a model."""
        observed_at = self._clock()
        status = self._status.snapshot()
        active_model = self._models.current()
        visual_assets = self._visuals.canonical_assets()
        presentation = presentation_model_from_application_state(
            status=status,
            active_model=active_model,
            visual_assets=visual_assets,
            observed_at=observed_at,
        )
        return HomeSnapshotView(
            observed_at=presentation.observed_at,
            home_timezone=str(presentation.observed_at.tzinfo),
            status=status,
            active_model=active_model,
            visual_assets=visual_assets,
            presentation=presentation,
            composition=self._composition.resolve(
                presentation,
                viewport=viewport,
                variant=CompositionVariant.PRESENCE_FIRST,
            ),
        )

    def open_session(self) -> "HomePresentationSession":
        """Create a local UI-only presentation session from the current snapshot."""
        return HomePresentationSession(
            self.snapshot(),
            composition=self._composition,
            clock=self._clock,
        )


class HomePresentationSession:
    """Deterministic UI session; it owns no domain data and performs no mutation."""

    def __init__(
            self,
            snapshot: HomeSnapshotView,
            *,
            composition: CompositionResolver,
            clock: Callable[[], datetime] | None = None,
    ):
        self._status = snapshot.status
        self._active_model = snapshot.active_model
        self._visual_assets = snapshot.visual_assets
        self._home_timezone = snapshot.home_timezone
        self._composition = composition
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._runtime = PresentationRuntime(snapshot.presentation)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("presentation clock must return timezone-aware datetime")
        return now

    def opened(self) -> HomeSnapshotView:
        return self._dispatch(UserOpenedApplication(occurred_at=self._now()))

    def conversation_focused(self) -> HomeSnapshotView:
        """Return Presentation focus to conversation without a model turn."""
        return self._dispatch(
            SurfaceFocused(
                occurred_at=self._now(),
                surface_id="home.conversation",
            )
        )

    def enter_special_evening(self) -> HomeSnapshotView | None:
        """Enter the explicit shared evening moment only during evening hours."""
        now = self._now()

        if 7 <= now.hour < 18:
            return None

        return self._dispatch(
            HomeMomentChanged(
                occurred_at=now,
                moment=HomeMoment.SPECIAL_EVENING,
            )
        )

    def leave_special_evening(self) -> HomeSnapshotView:
        """Return Home to the ordinary day/evening presence family."""
        return self._dispatch(
            HomeMomentChanged(
                occurred_at=self._now(),
                moment=HomeMoment.ORDINARY,
            )
        )

    def set_special_proximity(
            self,
            proximity: HomeProximity,
    ) -> HomeSnapshotView | None:
        """Change closeness only inside the explicit Special Evening."""
        if (
            self._runtime.model.home_moment
            is not HomeMoment.SPECIAL_EVENING
        ):
            return None

        return self._dispatch(
            HomeProximityChanged(
                occurred_at=self._now(),
                proximity=proximity,
            )
        )

    def user_sent(self) -> HomeSnapshotView:
        return self._dispatch(UserSentMessage(occurred_at=self._now()))

    def assistant_thinking(self) -> HomeSnapshotView:
        return self._dispatch(AssistantStartedThinking(occurred_at=self._now()))

    def assistant_responded(
            self,
            *,
            expression_cue: str = "warm",
    ) -> HomeSnapshotView:
        safe_cue = (
            expression_cue
            if expression_cue
               in _RESPONSE_EXPRESSION_CUES
            else "warm"
        )

        return self._dispatch(
            AssistantResponded(
                occurred_at=self._now(),
                expression_cue=safe_cue,
            )
        )

    def assistant_settled(
            self,
            *,
            expected_revision: int,
    ) -> HomeSnapshotView | None:
        """Settle only if nothing newer has changed Presentation."""

        if self._runtime.model.revision != expected_revision:
            return None

        return self._dispatch(
            AssistantSettled(
                occurred_at=self._now()
            )
        )

    def confirmation_requested(self, *, title: str, summary: str) -> HomeSnapshotView:
        now = self._now()
        self._dispatch(
            SurfaceCreated(
                occurred_at=now,
                surface=InteractionSurface(
                    surface_id="confirmation.commitment",
                    kind=SurfaceKind.CONFIRMATION,
                    lifecycle=SurfaceLifecycle.ACTIVE,
                    role=SurfaceRole.DECISION,
                    title=title,
                    summary=summary,
                    sensitive=True,
                    capabilities=(SurfaceCapability.CONFIRM, SurfaceCapability.REJECT),
                ),
            )
        )
        return self._dispatch(
            SurfaceFocused(occurred_at=now, surface_id="confirmation.commitment")
        )

    def commitments_opened(self, *, summary: str) -> HomeSnapshotView:
        now = self._now()
        self._dispatch(
            SurfaceCreated(
                occurred_at=now,
                surface=InteractionSurface(
                    surface_id="home.commitments",
                    kind=SurfaceKind.COMMITMENT,
                    lifecycle=SurfaceLifecycle.ACTIVE,
                    role=SurfaceRole.SUPPORTING,
                    title="Наши дела",
                    summary=summary,
                    capabilities=(SurfaceCapability.INSPECT,),
                ),
            )
        )
        return self._dispatch(SurfaceFocused(occurred_at=now, surface_id="home.commitments"))

    def activity_opened(self, *, run_id: str, title: str, status: str) -> HomeSnapshotView:
        now = self._now()
        activity_id = f"agent.{run_id}"
        surface_id = f"agent.{run_id}"
        self._dispatch(
            ActivityStarted(
                occurred_at=now,
                activity_id=activity_id,
                surface_id=surface_id,
                title=title,
                summary="Проверенный локальный агентный запуск",
            )
        )
        if status == "running":
            return self._dispatch(SurfaceFocused(occurred_at=now, surface_id=surface_id))
        if status == "awaiting_confirmation":
            return self._dispatch(
                ActivityWaiting(
                    occurred_at=now,
                    activity_id=activity_id,
                    summary="Нужно твоё решение перед продолжением",
                )
            )
        if status == "completed":
            return self._dispatch(
                ActivityCompleted(
                    occurred_at=now,
                    activity_id=activity_id,
                    summary="Завершено и проверено",
                )
            )
        if status == "denied":
            return self._dispatch(
                ActivityCancelled(
                    occurred_at=now,
                    activity_id=activity_id,
                    summary="Остановлено правилами доступа",
                )
            )
        return self._dispatch(
            ActivityFailed(
                occurred_at=now,
                activity_id=activity_id,
                summary="Запуск завершился без подтверждённого результата",
                reason_code=status,
            )
        )

    def proactive_opened(self, *, event_id: str, text: str) -> HomeSnapshotView:
        now = self._now()
        self._dispatch(ProactiveDelivered(occurred_at=now, event_id=event_id, text=text))
        return self._dispatch(
            SurfaceFocused(occurred_at=now, surface_id=f"proactive:{event_id}")
        )

    def proactive_resolved(self, *, event_id: str, decision: str) -> HomeSnapshotView:
        event = (
            ProactiveAcknowledged(occurred_at=self._now(), event_id=event_id)
            if decision == "acknowledge"
            else ProactiveDismissed(occurred_at=self._now(), event_id=event_id)
        )
        return self._dispatch(event)

    def continuity_opened(self, *, summary: str) -> HomeSnapshotView:
        return self._open_memory_surface(
            surface_id="home.continuity",
            title="Наша история",
            summary=summary,
            decision=False,
        )

    def reflections_opened(self, *, summary: str, decision: bool) -> HomeSnapshotView:
        return self._open_memory_surface(
            surface_id="home.reflections",
            title="Мысли Маши",
            summary=summary,
            decision=decision,
        )

    def reflection_action_started(self, *, title: str) -> HomeSnapshotView:
        return self._dispatch(
            ActivityStarted(
                occurred_at=self._now(),
                activity_id="activity.reflection",
                surface_id="activity.reflection",
                title=title,
                summary="Только явно выбранное действие с рефлексией",
            )
        )

    def reflection_action_resolved(self, *, summary: str) -> HomeSnapshotView:
        return self._dispatch(
            ActivityCompleted(
                occurred_at=self._now(),
                activity_id="activity.reflection",
                summary=summary,
            )
        )

    def reflection_action_failed(self, *, summary: str) -> HomeSnapshotView:
        return self._dispatch(
            ActivityFailed(
                occurred_at=self._now(),
                activity_id="activity.reflection",
                summary=summary,
                reason_code="reflection_action_failed",
            )
        )

    def workbench_opened(self, *, summary: str, decision: bool) -> HomeSnapshotView:
        now = self._now()
        self._dispatch(
            SurfaceCreated(
                occurred_at=now,
                surface=InteractionSurface(
                    surface_id="home.workbench",
                    kind=SurfaceKind.MODEL_RUNTIME,
                    lifecycle=SurfaceLifecycle.ACTIVE,
                    role=SurfaceRole.DECISION if decision else SurfaceRole.SUPPORTING,
                    title="Рабочий уголок",
                    summary=summary,
                    sensitive=True,
                    capabilities=(
                        (SurfaceCapability.INSPECT, SurfaceCapability.CONFIRM)
                        if decision
                        else (SurfaceCapability.INSPECT,)
                    ),
                ),
            )
        )
        return self._dispatch(SurfaceFocused(occurred_at=now, surface_id="home.workbench"))

    def model_switch_started(self) -> HomeSnapshotView:
        return self._dispatch(ModelSwitchStarted(occurred_at=self._now()))

    def model_changed(
        self,
        *,
        active_model: ModelProfileView,
        status: MashaStatusView,
    ) -> HomeSnapshotView:
        self._active_model = active_model
        self._status = status
        return self._dispatch(
            ModelChanged(
                occurred_at=self._now(),
                profile_id=active_model.profile_id,
                display_name=active_model.display_name,
            )
        )

    def confirmation_resolving(self, *, title: str) -> HomeSnapshotView:
        now = self._now()
        self._dispatch(
            SurfaceCompleted(occurred_at=now, surface_id="confirmation.commitment")
        )
        return self._dispatch(
            ActivityStarted(
                occurred_at=now,
                activity_id="activity.confirmation",
                surface_id="activity.confirmation",
                title=title,
                summary="Применяю только подтверждённое изменение локально",
            )
        )

    def _open_memory_surface(
        self,
        *,
        surface_id: str,
        title: str,
        summary: str,
        decision: bool,
    ) -> HomeSnapshotView:
        now = self._now()
        self._dispatch(
            SurfaceCreated(
                occurred_at=now,
                surface=InteractionSurface(
                    surface_id=surface_id,
                    kind=SurfaceKind.MEMORY,
                    lifecycle=SurfaceLifecycle.ACTIVE,
                    role=SurfaceRole.DECISION if decision else SurfaceRole.SUPPORTING,
                    title=title,
                    summary=summary,
                    sensitive=True,
                    capabilities=(
                        (SurfaceCapability.INSPECT, SurfaceCapability.CONFIRM, SurfaceCapability.REJECT)
                        if decision
                        else (SurfaceCapability.INSPECT,)
                    ),
                ),
            )
        )
        return self._dispatch(SurfaceFocused(occurred_at=now, surface_id=surface_id))

    def confirmation_resolved(self, *, summary: str) -> HomeSnapshotView:
        return self._dispatch(
            ActivityCompleted(
                occurred_at=self._now(),
                activity_id="activity.confirmation",
                summary=summary,
            )
        )

    def confirmation_failed(self, *, summary: str) -> HomeSnapshotView:
        return self._dispatch(
            ActivityFailed(
                occurred_at=self._now(),
                activity_id="activity.confirmation",
                summary=summary,
                reason_code="confirmation_failed",
            )
        )

    def model_unavailable(self, *, profile_id: str, display_name: str) -> HomeSnapshotView:
        return self._dispatch(
            ModelUnavailable(
                occurred_at=self._now(),
                profile_id=profile_id,
                display_name=display_name,
            )
        )

    def emergency_stop(self, *, reason: str) -> HomeSnapshotView:
        self._status = self._status.model_copy(
            update={
                "emergency_stop_engaged": True,
                "safety_label": "Аварийная остановка включена",
            }
        )
        return self._dispatch(
            EmergencyStopEngaged(
                occurred_at=self._now(),
                reason=reason,
            )
        )

    def autonomy_resumed(self) -> HomeSnapshotView:
        self._status = self._status.model_copy(
            update={
                "emergency_stop_engaged": False,
                "safety_label": "Аварийная остановка выключена",
            }
        )
        return self._dispatch(AutonomyResumed(occurred_at=self._now()))

    def observe_time(self) -> HomeSnapshotView:
        """Refresh Home time and close an expired special evening."""
        observed_at = self._now()

        if (
                7 <= observed_at.hour < 18
                and self._runtime.model.home_moment
                is HomeMoment.SPECIAL_EVENING
        ):
            return self._dispatch(
                HomeMomentChanged(
                    occurred_at=observed_at,
                    moment=HomeMoment.ORDINARY,
                )
            )

        self._runtime.model = self._runtime.model.model_copy(
            update={"observed_at": observed_at}
        )

        presentation = self._runtime.model

        return HomeSnapshotView(
            observed_at=observed_at,
            home_timezone=self._home_timezone,
            status=self._status,
            active_model=self._active_model,
            visual_assets=self._visual_assets,
            presentation=presentation,
            composition=self._composition.resolve(
                presentation,
                variant=CompositionVariant.PRESENCE_FIRST,
            ),
        )
    @property
    def home_moment(self) -> HomeMoment:
        # UI-only authored moment; never persisted as domain memory.
        return self._runtime.model.home_moment

    @property
    def active_model_display_name(self) -> str:
        return self._active_model.display_name

    def _dispatch(self, event) -> HomeSnapshotView:
        presentation = self._runtime.dispatch(event)
        return HomeSnapshotView(
            observed_at=presentation.observed_at,
            home_timezone=self._home_timezone,
            status=self._status,
            active_model=self._active_model,
            visual_assets=self._visual_assets,
            presentation=presentation,
            composition=self._composition.resolve(
                presentation,
                variant=CompositionVariant.PRESENCE_FIRST,
            ),
        )
