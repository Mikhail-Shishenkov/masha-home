"""Tier 0 semantic renderer and no-LLM interactive prototype controller."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from .events import (
    ActivityCompleted,
    ActivityProgressed,
    ActivityQueued,
    ActivityStarted,
    AssistantResponded,
    AssistantStartedThinking,
    AutonomyResumed,
    EmergencyStopEngaged,
    ModelChanged,
    ModelUnavailable,
    ProactiveAcknowledged,
    ProactiveCandidateAppeared,
    ProactiveDelivered,
    RuntimeModeChanged,
    UserOpenedApplication,
    UserSentMessage,
    WindowFocusChanged,
)
from .models import (
    ActivityState,
    HomePresentationModel,
    ModelOverlay,
    ProactiveOverlay,
    RuntimeMode,
    SafetyOverlay,
    SurfaceKind,
    SurfaceLifecycle,
    default_home_model,
)
from .reducer import PresentationRuntime


class TierZeroModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TierZeroSurfaceView(TierZeroModel):
    surface_id: str
    kind: str
    title: str
    summary: str
    lifecycle: str
    primary: bool
    sensitive: bool


class TierZeroActivityView(TierZeroModel):
    title: str
    summary: str
    state: str
    progress_label: str | None


class TierZeroScene(TierZeroModel):
    room_title: str
    presence_name: str
    asset_id: str
    pose_label: str
    expression_label: str
    attention_label: str
    activity_label: str
    safety_label: str
    proactive_label: str
    model_label: str
    runtime_label: str
    privacy_masked: bool
    surfaces: tuple[TierZeroSurfaceView, ...]
    activities: tuple[TierZeroActivityView, ...]


class TierZeroRenderer:
    """Pure semantic renderer; the Tk window consumes this stable scene."""

    def render(self, model: HomePresentationModel) -> TierZeroScene:
        visible = tuple(
            TierZeroSurfaceView(
                surface_id=surface.surface_id,
                kind=surface.kind.value,
                title=surface.title,
                summary="Содержимое скрыто"
                if model.privacy_masked and surface.sensitive
                else surface.summary,
                lifecycle=surface.lifecycle.value,
                primary=surface.surface_id == model.active_surface_id,
                sensitive=surface.sensitive,
            )
            for surface in model.surfaces
            if surface.lifecycle is not SurfaceLifecycle.CLOSED
        )
        activities = tuple(
            TierZeroActivityView(
                title=activity.title,
                summary=activity.summary,
                state=activity.state.value,
                progress_label=activity.progress.label,
            )
            for activity in model.activities
        )
        asset_id = (
            model.presence.visual_identity.asset_ids[0]
            if model.presence.visual_identity.asset_ids
            else "masha.canonical"
        )
        return TierZeroScene(
            room_title="Дом Маши",
            presence_name="МАША",
            asset_id=asset_id,
            pose_label=model.presence.pose.value,
            expression_label=f"{model.presence.expression.code.value} · {model.presence.expression.intensity:.2f}",
            attention_label=model.presence.attention.value,
            activity_label=model.presence.activity.value,
            safety_label="Автономность остановлена"
            if model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED
            else "Автономность активна",
            proactive_label=f"Инициативность · уровень {model.overlays.proactive_level} · {model.overlays.proactive.value}",
            model_label=f"{model.overlays.active_profile_id} · {model.overlays.model_display_name} · {model.overlays.model.value}",
            runtime_label=f"{model.overlays.runtime_mode.value} · {model.overlays.daemon.value}",
            privacy_masked=model.privacy_masked,
            surfaces=visible,
            activities=activities,
        )


class TierZeroPrototypeController:
    """Deterministic scenario controls for the structural desktop prototype."""

    ACTIVITY_ID = "prototype.project_observer"
    ACTIVITY_SURFACE_ID = "surface.project_observer"
    PROACTIVE_EVENT_ID = "prototype.check_in"

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        model: HomePresentationModel | None = None,
    ):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        initial = model or default_home_model(observed_at=self._clock())
        initial = initial.model_copy(
            update={
                "overlays": initial.overlays.model_copy(
                    update={"proactive": ProactiveOverlay.ON, "proactive_level": 2}
                )
            }
        )
        self.runtime = PresentationRuntime(initial)
        self.renderer = TierZeroRenderer()
        self._conversation_step = 0
        self.runtime.dispatch(UserOpenedApplication(occurred_at=self._clock()))

    @property
    def model(self) -> HomePresentationModel:
        return self.runtime.model

    def scene(self) -> TierZeroScene:
        return self.renderer.render(self.model)

    def conversation_next(self) -> TierZeroScene:
        events = (
            UserSentMessage,
            AssistantStartedThinking,
            AssistantResponded,
        )
        event_type = events[self._conversation_step % len(events)]
        self._conversation_step += 1
        self.runtime.dispatch(event_type(occurred_at=self._clock()))
        return self.scene()

    def activity_next(self) -> TierZeroScene:
        activity = next(
            (item for item in self.model.activities if item.activity_id == self.ACTIVITY_ID),
            None,
        )
        if activity is None or activity.state in {
            ActivityState.COMPLETED,
            ActivityState.FAILED,
            ActivityState.CANCELLED,
        }:
            event = ActivityQueued(
                occurred_at=self._clock(),
                activity_id=self.ACTIVITY_ID,
                surface_id=self.ACTIVITY_SURFACE_ID,
                title="Project Observer",
                summary="Подготовила безопасное наблюдение проекта",
            )
        elif activity.state is ActivityState.QUEUED:
            event = ActivityStarted(
                occurred_at=self._clock(),
                activity_id=self.ACTIVITY_ID,
                surface_id=self.ACTIVITY_SURFACE_ID,
                title=activity.title,
                summary="Проверяю структуру проекта",
            )
        elif activity.state is ActivityState.WAITING:
            event = ActivityStarted(
                occurred_at=self._clock(),
                activity_id=self.ACTIVITY_ID,
                surface_id=self.ACTIVITY_SURFACE_ID,
                title=activity.title,
                summary="Проверяю структуру проекта",
            )
        elif activity.progress.completed_units is None:
            event = ActivityProgressed(
                occurred_at=self._clock(),
                activity_id=self.ACTIVITY_ID,
                completed_units=4,
                total_units=12,
                summary="Проверено 4 из 12 областей",
            )
        elif activity.progress.completed_units < 8:
            event = ActivityProgressed(
                occurred_at=self._clock(),
                activity_id=self.ACTIVITY_ID,
                completed_units=8,
                total_units=12,
                summary="Проверено 8 из 12 областей",
            )
        else:
            event = ActivityCompleted(
                occurred_at=self._clock(),
                activity_id=self.ACTIVITY_ID,
                summary="Структура проекта проверена",
            )
        self.runtime.dispatch(event)
        return self.scene()

    def proactive_next(self) -> TierZeroScene:
        surface = next(
            (
                item
                for item in self.model.surfaces
                if item.kind is SurfaceKind.PROACTIVE
                and item.lifecycle is not SurfaceLifecycle.CLOSED
            ),
            None,
        )
        if surface is None or surface.lifecycle is SurfaceLifecycle.COMPLETED:
            event = ProactiveCandidateAppeared(
                occurred_at=self._clock(), event_id=self.PROACTIVE_EVENT_ID
            )
        elif surface.lifecycle in {SurfaceLifecycle.CREATED, SurfaceLifecycle.BACKGROUND}:
            event = ProactiveDelivered(
                occurred_at=self._clock(),
                event_id=self.PROACTIVE_EVENT_ID,
                text="Миша, можно тебя на секунду?",
            )
        else:
            event = ProactiveAcknowledged(
                occurred_at=self._clock(), event_id=self.PROACTIVE_EVENT_ID
            )
        self.runtime.dispatch(event)
        return self.scene()

    def toggle_safety(self) -> TierZeroScene:
        if self.model.overlays.safety is SafetyOverlay.AUTONOMY_ACTIVE:
            event = EmergencyStopEngaged(
                occurred_at=self._clock(), reason="tier_zero_prototype"
            )
        else:
            event = AutonomyResumed(occurred_at=self._clock())
        self.runtime.dispatch(event)
        return self.scene()

    def cycle_model(self) -> TierZeroScene:
        overlays = self.model.overlays
        if overlays.model is ModelOverlay.UNAVAILABLE:
            event = ModelChanged(
                occurred_at=self._clock(),
                profile_id="primary",
                display_name="Qwen 3.5 9B",
            )
        elif overlays.active_profile_id == "primary":
            event = ModelChanged(
                occurred_at=self._clock(),
                profile_id="fast",
                display_name="Qwen 3.5 4B",
            )
        else:
            event = ModelUnavailable(
                occurred_at=self._clock(),
                profile_id=overlays.active_profile_id,
                display_name=overlays.model_display_name,
            )
        self.runtime.dispatch(event)
        return self.scene()

    def toggle_runtime_mode(self) -> TierZeroScene:
        current = self.model.overlays.runtime_mode
        target = RuntimeMode.BACKGROUND if current is RuntimeMode.MANUAL else RuntimeMode.MANUAL
        self.runtime.dispatch(
            RuntimeModeChanged(
                occurred_at=self._clock(),
                runtime_mode=target,
                daemon_running=target is RuntimeMode.BACKGROUND,
            )
        )
        return self.scene()

    def window_focus(self, focused: bool) -> TierZeroScene:
        self.runtime.dispatch(
            WindowFocusChanged(occurred_at=self._clock(), focused=focused)
        )
        return self.scene()
