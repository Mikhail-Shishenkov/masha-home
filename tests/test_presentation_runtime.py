from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.application.contracts import (
    MashaStatusView,
    ModelAvailabilityCode,
    ModelProfileView,
    VisualAssetView,
)
from backend.presentation.adapter import presentation_model_from_application_state
from backend.presentation.events import (
    ActivityCancelled,
    ActivityCompleted,
    ActivityFailed,
    ActivityProgressed,
    ActivityQueued,
    ActivityStarted,
    ActivityWaiting,
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
    SurfaceClosed,
    SurfaceCompleted,
    SurfaceCreated,
    SurfaceFocused,
    SurfaceMinimized,
    UserOpenedApplication,
    UserSentMessage,
    WindowFocusChanged,
    HomeMomentChanged,
    HomeMoment,
)
from backend.presentation.models import (
    ActivityState,
    AmbientState,
    AttentionState,
    BasePose,
    DaemonOverlay,
    ExpressionCode,
    HomePresentationModel,
    InteractionSurface,
    ModelOverlay,
    PresenceActivity,
    ProactiveOverlay,
    RuntimeMode,
    SafetyOverlay,
    SurfaceKind,
    SurfaceLifecycle,
    SurfaceRole,
    VisualIdentity,
    WindowState,
    default_home_model,
)
from backend.presentation.reducer import CONVERSATION_SURFACE_ID, PresentationReducer
from backend.presentation.tier0 import TierZeroRenderer


NOW = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def _event(event_type, seconds: int = 1, **kwargs):
    return event_type(occurred_at=NOW + timedelta(seconds=seconds), **kwargs)


def _open_model() -> HomePresentationModel:
    reducer = PresentationReducer()
    return reducer.reduce(
        default_home_model(observed_at=NOW),
        UserOpenedApplication(occurred_at=NOW),
    )


def _surface(model: HomePresentationModel, surface_id: str):
    return next(item for item in model.surfaces if item.surface_id == surface_id)


def _activity(model: HomePresentationModel, activity_id: str):
    return next(item for item in model.activities if item.activity_id == activity_id)


def test_models_are_immutable_and_reducer_is_deterministic():
    model = _open_model()
    event = _event(AssistantStartedThinking)
    reducer = PresentationReducer()

    first = reducer.reduce(model, event)
    second = reducer.reduce(model, event)

    assert first == second
    assert model.presence.activity is PresenceActivity.IDLE
    assert first.presence.activity is PresenceActivity.PROCESSING
    assert first.revision == model.revision + 1
    with pytest.raises(ValidationError):
        first.opened = False


def test_conversation_state_composes_with_emergency_stop_and_resume():
    reducer = PresentationReducer()
    model = _open_model()
    model = reducer.reduce(model, _event(UserSentMessage))
    model = reducer.reduce(model, _event(AssistantStartedThinking, 2))
    model = reducer.reduce(model, _event(EmergencyStopEngaged, 3))

    assert model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED
    assert model.presence.activity is PresenceActivity.PROCESSING
    assert model.presence.expression.code is ExpressionCode.THOUGHTFUL
    visual_identity = model.presence.visual_identity

    model = reducer.reduce(model, _event(AssistantResponded, 4))
    assert model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED
    assert model.presence.activity is PresenceActivity.SPEAKING
    assert model.presence.visual_identity == visual_identity

    before_resume = model.surfaces, model.activities
    model = reducer.reduce(model, _event(AutonomyResumed, 5))
    assert model.overlays.safety is SafetyOverlay.AUTONOMY_ACTIVE
    assert (model.surfaces, model.activities) == before_resume


def test_surface_lifecycle_keeps_one_primary_and_has_no_frontend_payload():
    reducer = PresentationReducer()
    model = _open_model()
    media = InteractionSurface(
        surface_id="surface.media",
        kind=SurfaceKind.MEDIA,
        title="Фотографии",
    )
    with pytest.raises(ValidationError):
        InteractionSurface(
            surface_id="surface.bad",
            kind=SurfaceKind.GENERIC,
            title="Bad",
            javascript="alert(1)",
        )

    model = reducer.reduce(model, _event(SurfaceCreated, surface=media))
    assert _surface(model, media.surface_id).lifecycle is SurfaceLifecycle.CREATED
    model = reducer.reduce(model, _event(SurfaceFocused, 2, surface_id=media.surface_id))
    assert model.active_surface_id == media.surface_id
    assert _surface(model, media.surface_id).role is SurfaceRole.PRIMARY
    assert _surface(model, CONVERSATION_SURFACE_ID).role is SurfaceRole.SUPPORTING
    assert sum(surface.role is SurfaceRole.PRIMARY for surface in model.surfaces) == 1

    model = reducer.reduce(model, _event(SurfaceMinimized, 3, surface_id=media.surface_id))
    assert _surface(model, media.surface_id).lifecycle is SurfaceLifecycle.MINIMIZED
    assert model.active_surface_id is None
    model = reducer.reduce(model, _event(SurfaceFocused, 4, surface_id=CONVERSATION_SURFACE_ID))
    model = reducer.reduce(model, _event(SurfaceCompleted, 5, surface_id=media.surface_id))
    model = reducer.reduce(model, _event(SurfaceClosed, 6, surface_id=media.surface_id))
    assert _surface(model, media.surface_id).lifecycle is SurfaceLifecycle.CLOSED


def test_home_moment_changes_without_touching_presence_or_overlays():
    reducer = PresentationReducer()
    model = _open_model()

    original_presence = model.presence
    original_overlays = model.overlays

    model = reducer.reduce(
        model,
        _event(
            HomeMomentChanged,
            moment=HomeMoment.SPECIAL_EVENING,
        ),
    )

    assert model.home_moment is HomeMoment.SPECIAL_EVENING
    assert model.presence == original_presence
    assert model.overlays == original_overlays

    model = reducer.reduce(
        model,
        _event(
            HomeMomentChanged,
            2,
            moment=HomeMoment.ORDINARY,
        ),
    )

    assert model.home_moment is HomeMoment.ORDINARY

def test_activity_lifecycle_is_observable_and_progress_is_evidence_based():
    reducer = PresentationReducer()
    model = _open_model()
    common = {"activity_id": "activity.audit", "surface_id": "surface.audit"}
    model = reducer.reduce(
        model,
        _event(ActivityQueued, title="Project Observer", **common),
    )
    assert _activity(model, "activity.audit").state is ActivityState.QUEUED
    model = reducer.reduce(
        model,
        _event(ActivityStarted, 2, title="Project Observer", **common),
    )
    assert _activity(model, "activity.audit").state is ActivityState.RUNNING
    assert model.presence.activity is PresenceActivity.WORKING
    model = reducer.reduce(
        model,
        _event(
            ActivityProgressed,
            3,
            activity_id="activity.audit",
            completed_units=8,
            total_units=12,
            summary="Проверено 8 из 12",
        ),
    )
    progress = _activity(model, "activity.audit").progress
    assert (progress.completed_units, progress.total_units, progress.label) == (8, 12, "8 / 12")
    model = reducer.reduce(
        model,
        _event(ActivityWaiting, 4, activity_id="activity.audit", summary="Жду решения"),
    )
    assert _activity(model, "activity.audit").state is ActivityState.WAITING
    model = reducer.reduce(
        model,
        _event(ActivityCompleted, 5, activity_id="activity.audit"),
    )
    assert _activity(model, "activity.audit").state is ActivityState.COMPLETED
    assert _surface(model, "surface.audit").lifecycle is SurfaceLifecycle.COMPLETED
    assert model.presence.expression.code is ExpressionCode.PROUD


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [(ActivityFailed, ActivityState.FAILED), (ActivityCancelled, ActivityState.CANCELLED)],
)
def test_activity_terminal_states(event_type, expected):
    reducer = PresentationReducer()
    model = _open_model()
    model = reducer.reduce(
        model,
        _event(
            ActivityStarted,
            activity_id="activity.one",
            surface_id="surface.one",
            title="Локальная задача",
        ),
    )
    model = reducer.reduce(
        model,
        _event(event_type, 2, activity_id="activity.one"),
    )
    assert _activity(model, "activity.one").state is expected


def test_emergency_stop_prevents_autonomous_activity_presentation_and_resume_does_not_start_it():
    reducer = PresentationReducer()
    model = reducer.reduce(_open_model(), _event(EmergencyStopEngaged))
    model = reducer.reduce(
        model,
        _event(
            ActivityStarted,
            2,
            activity_id="activity.blocked",
            surface_id="surface.blocked",
            title="Не должна запуститься",
        ),
    )
    blocked = _activity(model, "activity.blocked")
    assert blocked.state is ActivityState.WAITING
    assert blocked.reason_code == "emergency_stop_engaged"
    assert model.presence.activity is PresenceActivity.IDLE

    model = reducer.reduce(model, _event(AutonomyResumed, 3))
    assert _activity(model, "activity.blocked") == blocked


def test_proactive_candidate_has_no_attention_until_delivery_and_stop_blocks_delivery():
    reducer = PresentationReducer()
    base = _open_model()
    base = base.model_copy(
        update={
            "overlays": base.overlays.model_copy(
                update={"proactive": ProactiveOverlay.ON, "proactive_level": 2}
            )
        }
    )
    model = reducer.reduce(
        base,
        _event(ProactiveCandidateAppeared, event_id="check.in"),
    )
    assert model.presence.attention is AttentionState.AMBIENT
    candidate = _surface(model, "proactive:check.in")
    assert candidate.lifecycle is SurfaceLifecycle.CREATED

    stopped = reducer.reduce(model, _event(EmergencyStopEngaged, 2))
    stopped = reducer.reduce(
        stopped,
        _event(ProactiveDelivered, 3, event_id="check.in", text="Миша, ты здесь?"),
    )
    assert stopped.overlays.proactive is ProactiveOverlay.ON
    assert _surface(stopped, "proactive:check.in").lifecycle is SurfaceLifecycle.BACKGROUND
    assert "остановлена" in _surface(stopped, "proactive:check.in").summary

    resumed = reducer.reduce(stopped, _event(AutonomyResumed, 4))
    assert _surface(resumed, "proactive:check.in").lifecycle is SurfaceLifecycle.BACKGROUND
    delivered = reducer.reduce(
        resumed,
        _event(ProactiveDelivered, 5, event_id="check.in", text="Миша, можно тебя на секунду?"),
    )
    assert delivered.overlays.proactive is ProactiveOverlay.ATTENTION
    assert delivered.presence.attention is AttentionState.PROACTIVE
    acknowledged = reducer.reduce(
        delivered,
        _event(ProactiveAcknowledged, 6, event_id="check.in"),
    )
    assert _surface(acknowledged, "proactive:check.in").lifecycle is SurfaceLifecycle.COMPLETED


def test_model_change_updates_only_execution_overlay_and_unavailable_keeps_presence():
    reducer = PresentationReducer()
    model = _open_model()
    invariant = (
        model.presence,
        model.surfaces,
        model.activities,
        model.home_state,
    )
    changed = reducer.reduce(
        model,
        _event(ModelChanged, profile_id="fast", display_name="Qwen 3.5 4B"),
    )
    assert changed.overlays.active_profile_id == "fast"
    assert changed.overlays.model is ModelOverlay.AVAILABLE
    assert (changed.presence, changed.surfaces, changed.activities, changed.home_state) == invariant

    unavailable = reducer.reduce(
        changed,
        _event(ModelUnavailable, 2, profile_id="fast", display_name="Qwen 3.5 4B"),
    )
    assert unavailable.overlays.model is ModelOverlay.UNAVAILABLE
    assert unavailable.presence.visual_identity == model.presence.visual_identity
    assert unavailable.presence.pose is BasePose.IDLE


def test_runtime_mode_overlay_is_independent():
    reducer = PresentationReducer()
    model = _open_model()
    presence = model.presence
    model = reducer.reduce(
        model,
        _event(
            RuntimeModeChanged,
            runtime_mode=RuntimeMode.BACKGROUND,
            daemon_running=False,
        ),
    )
    assert model.overlays.runtime_mode is RuntimeMode.BACKGROUND
    assert model.overlays.daemon is DaemonOverlay.STOPPED
    assert model.presence == presence


def test_unfocused_window_masks_sensitive_surfaces_without_closing_them():
    reducer = PresentationReducer()
    model = reducer.reduce(_open_model(), _event(WindowFocusChanged, focused=False))
    scene = TierZeroRenderer().render(model)

    assert model.window_state is WindowState.UNFOCUSED
    assert model.privacy_masked is True
    assert model.presence.ambient is AmbientState.PRIVACY
    conversation = next(item for item in scene.surfaces if item.kind == "conversation")
    assert conversation.summary == "Содержимое скрыто"
    assert _surface(model, CONVERSATION_SURFACE_ID).lifecycle is SurfaceLifecycle.ACTIVE


def test_ui01_projection_uses_opaque_visual_ids_and_independent_overlays():
    status = MashaStatusView(
        runtime_status="degraded",
        runtime_label="Маша работает с ограничениями",
        model_available=True,
        model_availability_code=ModelAvailabilityCode.AVAILABLE,
        model_label="Доступна",
        active_profile_id="primary",
        proactive_enabled=True,
        proactive_label="Инициативность включена",
        proactive_level=2,
        runtime_mode="background",
        runtime_mode_label="Фоновый режим",
        daemon_running=False,
        emergency_stop_engaged=True,
        safety_label="Аварийная остановка включена",
        pending_decisions_count=1,
        pending_interactions_count=1,
    )
    profile = ModelProfileView(
        profile_id="primary",
        display_name="Primary · Qwen 3.5 9B",
        model_id="qwen3.5:9b",
        capabilities=("text",),
        description="Основной разговор",
        enabled=True,
        active=True,
        available=True,
        availability_code=ModelAvailabilityCode.AVAILABLE,
        availability_label="Доступна",
    )
    assets = (
        VisualAssetView(
            asset_id="masha.canonical.one",
            purpose="canonical",
            media_type="image/png",
            byte_size=123,
        ),
    )

    model = presentation_model_from_application_state(
        status=status,
        active_model=profile,
        visual_assets=assets,
        observed_at=NOW,
    )

    assert model.home_state.value == "degraded"
    assert model.presence.visual_identity.asset_ids == ("masha.canonical.one",)
    assert model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED
    assert model.overlays.proactive is ProactiveOverlay.ON
    assert model.overlays.model is ModelOverlay.AVAILABLE
    assert model.overlays.runtime_mode is RuntimeMode.BACKGROUND
    assert model.overlays.daemon is DaemonOverlay.STOPPED
    assert not any(
        forbidden in model.model_dump_json().casefold()
        for forbidden in ("local-data", "sqlite", "\\identity\\", "/identity/")
    )


def test_visual_identity_rejects_filesystem_paths():
    with pytest.raises(ValidationError, match="opaque IDs"):
        VisualIdentity(
            visual_identity_id="masha",
            avatar_variant_id="canonical",
            asset_ids=(r"C:\\masha-home\\identity\\masha.png",),
        )


def test_presentation_events_do_not_touch_unrelated_persistent_files(tmp_path):
    files = {
        "identity": tmp_path / "identity.json",
        "memory": tmp_path / "memory.sqlite3",
        "commitment": tmp_path / "commitment.bin",
    }
    for name, path in files.items():
        path.write_bytes(f"unchanged:{name}".encode())
    before = {name: path.read_bytes() for name, path in files.items()}

    reducer = PresentationReducer()
    model = _open_model()
    for event in (
        _event(UserSentMessage),
        _event(AssistantStartedThinking, 2),
        _event(EmergencyStopEngaged, 3),
        _event(ModelChanged, 4, profile_id="fast", display_name="Fast"),
        _event(WindowFocusChanged, 5, focused=False),
    ):
        model = reducer.reduce(model, event)

    assert {name: path.read_bytes() for name, path in files.items()} == before
