from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.presentation.models import (
    ActivityState,
    ModelOverlay,
    SafetyOverlay,
    SurfaceKind,
    SurfaceLifecycle,
)
from backend.presentation.tier0 import TierZeroPrototypeController


class AdvancingClock:
    def __init__(self):
        self.value = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)

    def __call__(self):
        current = self.value
        self.value += timedelta(seconds=1)
        return current


def test_tier_zero_scene_is_one_home_with_presence_and_contextual_surfaces():
    controller = TierZeroPrototypeController(clock=AdvancingClock())
    scene = controller.scene()

    assert scene.room_title == "Дом Маши"
    assert scene.presence_name == "МАША"
    assert scene.asset_id == "masha.canonical"
    assert any(surface.kind == SurfaceKind.CONVERSATION.value for surface in scene.surfaces)
    assert "уровень 2" in scene.proactive_label
    assert "primary" in scene.model_label
    assert not any("\\" in surface.surface_id or "/" in surface.surface_id for surface in scene.surfaces)


def test_local_prototype_cycles_conversation_activity_proactive_and_model_without_llm():
    controller = TierZeroPrototypeController(clock=AdvancingClock())

    thinking = controller.conversation_next()
    thinking = controller.conversation_next()
    assert thinking.activity_label == "processing"
    response = controller.conversation_next()
    assert response.activity_label == "speaking"

    controller.activity_next()
    controller.activity_next()
    controller.activity_next()
    activity = controller.model.activities[-1]
    assert activity.state is ActivityState.RUNNING
    assert activity.progress.completed_units == 4
    assert any(surface.kind == SurfaceKind.ACTIVITY.value for surface in controller.scene().surfaces)

    controller.proactive_next()
    delivered = controller.proactive_next()
    assert any(
        surface.kind == SurfaceKind.PROACTIVE.value
        and surface.lifecycle == SurfaceLifecycle.ACTIVE.value
        for surface in delivered.surfaces
    )

    visual_identity = controller.model.presence.visual_identity
    controller.cycle_model()
    assert controller.model.overlays.active_profile_id == "fast"
    assert controller.model.presence.visual_identity == visual_identity
    controller.cycle_model()
    assert controller.model.overlays.model is ModelOverlay.UNAVAILABLE


def test_tier_zero_emergency_stop_blocks_activity_and_proactive_visual_delivery():
    controller = TierZeroPrototypeController(clock=AdvancingClock())
    controller.toggle_safety()
    assert controller.model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED

    controller.activity_next()
    controller.activity_next()
    assert controller.model.activities[-1].state is ActivityState.WAITING
    assert controller.model.activities[-1].reason_code == "emergency_stop_engaged"

    controller.proactive_next()
    controller.proactive_next()
    proactive = next(
        surface for surface in controller.model.surfaces if surface.kind is SurfaceKind.PROACTIVE
    )
    assert proactive.lifecycle is SurfaceLifecycle.BACKGROUND
    assert "остановлена" in proactive.summary

    blocked_activity = controller.model.activities[-1]
    controller.toggle_safety()
    assert controller.model.overlays.safety is SafetyOverlay.AUTONOMY_ACTIVE
    assert controller.model.activities[-1] == blocked_activity
