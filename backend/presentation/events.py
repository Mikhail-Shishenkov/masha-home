"""Immutable input events for the deterministic Presentation Reducer."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .models import HomeMoment, HomeProximity, InteractionSurface, RuntimeMode


class PresentationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    occurred_at: AwareDatetime


class UserOpenedApplication(PresentationEvent):
    kind: Literal["user_opened_application"] = "user_opened_application"

class HomeMomentChanged(PresentationEvent):
    kind: Literal["home_moment_changed"] = "home_moment_changed"
    moment: HomeMoment

class HomeProximityChanged(PresentationEvent):
    kind: Literal["home_proximity_changed"] = "home_proximity_changed"
    proximity: HomeProximity


class UserSentMessage(PresentationEvent):
    kind: Literal["user_sent_message"] = "user_sent_message"


class AssistantStartedThinking(PresentationEvent):
    kind: Literal["assistant_started_thinking"] = "assistant_started_thinking"


class AssistantResponded(PresentationEvent):
    kind: Literal["assistant_responded"] = "assistant_responded"
    expression_cue: Literal[
        "warm",
        "amused",
        "thoughtful",
        "supportive",
        "firm",
        "playful",
    ] = "warm"

class AssistantSettled(PresentationEvent):
    kind: Literal["assistant_settled"] = "assistant_settled"


class SurfaceCreated(PresentationEvent):
    kind: Literal["surface_created"] = "surface_created"
    surface: InteractionSurface


class SurfaceFocused(PresentationEvent):
    kind: Literal["surface_focused"] = "surface_focused"
    surface_id: str


class SurfaceMinimized(PresentationEvent):
    kind: Literal["surface_minimized"] = "surface_minimized"
    surface_id: str


class SurfaceBackgrounded(PresentationEvent):
    kind: Literal["surface_backgrounded"] = "surface_backgrounded"
    surface_id: str


class SurfaceCompleted(PresentationEvent):
    kind: Literal["surface_completed"] = "surface_completed"
    surface_id: str


class SurfaceClosed(PresentationEvent):
    kind: Literal["surface_closed"] = "surface_closed"
    surface_id: str


class ActivityQueued(PresentationEvent):
    kind: Literal["activity_queued"] = "activity_queued"
    activity_id: str
    surface_id: str
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="Ожидает запуска", max_length=500)


class ActivityStarted(PresentationEvent):
    kind: Literal["activity_started"] = "activity_started"
    activity_id: str
    surface_id: str
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="Работаю над задачей", max_length=500)


class ActivityProgressed(PresentationEvent):
    kind: Literal["activity_progressed"] = "activity_progressed"
    activity_id: str
    completed_units: int = Field(ge=0)
    total_units: int = Field(gt=0)
    summary: str = Field(default="Продолжаю работу", max_length=500)


class ActivityWaiting(PresentationEvent):
    kind: Literal["activity_waiting"] = "activity_waiting"
    activity_id: str
    summary: str = Field(default="Жду продолжения", max_length=500)


class ActivityCompleted(PresentationEvent):
    kind: Literal["activity_completed"] = "activity_completed"
    activity_id: str
    summary: str = Field(default="Готово", max_length=500)


class ActivityFailed(PresentationEvent):
    kind: Literal["activity_failed"] = "activity_failed"
    activity_id: str
    summary: str = Field(default="Не удалось завершить", max_length=500)
    reason_code: str = Field(default="activity_failed", max_length=120)


class ActivityCancelled(PresentationEvent):
    kind: Literal["activity_cancelled"] = "activity_cancelled"
    activity_id: str
    summary: str = Field(default="Остановлено", max_length=500)


class ProactiveCandidateAppeared(PresentationEvent):
    kind: Literal["proactive_candidate_appeared"] = "proactive_candidate_appeared"
    event_id: str
    title: str = Field(default="Маша хочет обратить внимание", max_length=160)


class ProactiveDelivered(PresentationEvent):
    kind: Literal["proactive_delivery"] = "proactive_delivery"
    event_id: str
    text: str = Field(min_length=1, max_length=500)


class ProactiveDismissed(PresentationEvent):
    kind: Literal["proactive_dismissed"] = "proactive_dismissed"
    event_id: str


class ProactiveAcknowledged(PresentationEvent):
    kind: Literal["proactive_acknowledged"] = "proactive_acknowledged"
    event_id: str


class ModelSwitchStarted(PresentationEvent):
    kind: Literal["model_switch_started"] = "model_switch_started"


class ModelChanged(PresentationEvent):
    kind: Literal["model_changed"] = "model_changed"
    profile_id: str
    display_name: str = Field(min_length=1, max_length=160)


class ModelUnavailable(PresentationEvent):
    kind: Literal["model_unavailable"] = "model_unavailable"
    profile_id: str
    display_name: str = Field(min_length=1, max_length=160)


class EmergencyStopEngaged(PresentationEvent):
    kind: Literal["emergency_stop"] = "emergency_stop"
    reason: str = Field(default="manual_emergency_stop", min_length=1, max_length=200)


class AutonomyResumed(PresentationEvent):
    kind: Literal["autonomy_resumed"] = "autonomy_resumed"


class RuntimeModeChanged(PresentationEvent):
    kind: Literal["runtime_mode_changed"] = "runtime_mode_changed"
    runtime_mode: RuntimeMode
    daemon_running: bool = False


class WindowFocusChanged(PresentationEvent):
    kind: Literal["window_focus_changed"] = "window_focus_changed"
    focused: bool
