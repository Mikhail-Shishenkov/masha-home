from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.presentation import (
    ActivityCompleted,
    ActivityProgressed,
    ActivityQueued,
    ActivityStarted,
    ActivityState,
    CompositionPlacement,
    CompositionPriority,
    CompositionRegionKind,
    CompositionResolver,
    CompositionSize,
    CompositionStability,
    CompositionVariant,
    EmergencyStopEngaged,
    ExpressionCode,
    ExpressionCue,
    FocusOwner,
    HomePresentationModel,
    InteractionSurface,
    ModelUnavailable,
    OverlayKind,
    ProactiveOverlay,
    RuntimeMode,
    RuntimeModeChanged,
    SurfaceCompositionIntent,
    SurfaceFocused,
    SurfaceKind,
    SurfaceLifecycle,
    SurfaceRole,
    UserOpenedApplication,
    ViewportCharacteristics,
    ViewportClass,
    WindowFocusChanged,
    default_home_model,
)
from backend.presentation.reducer import PresentationReducer


NOW = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def _event(event_type, seconds: int = 1, **kwargs):
    return event_type(occurred_at=NOW + timedelta(seconds=seconds), **kwargs)


def _open_model() -> HomePresentationModel:
    return PresentationReducer().reduce(
        default_home_model(observed_at=NOW),
        UserOpenedApplication(occurred_at=NOW),
    )


def _region(plan, surface_id: str):
    return next(region for region in plan.regions if region.surface_id == surface_id)


def _add_surface(
    model: HomePresentationModel,
    surface: InteractionSurface,
) -> HomePresentationModel:
    return HomePresentationModel.model_validate(
        model.model_copy(update={"surfaces": model.surfaces + (surface,)}).model_dump()
    )


def _proactive_model(*, title: str) -> HomePresentationModel:
    model = _open_model()
    model = model.model_copy(
        update={
            "overlays": model.overlays.model_copy(
                update={"proactive": ProactiveOverlay.ATTENTION, "proactive_level": 2}
            )
        }
    )
    return _add_surface(
        model,
        InteractionSurface(
            surface_id="proactive:example",
            kind=SurfaceKind.PROACTIVE,
            lifecycle=SurfaceLifecycle.ACTIVE,
            role=SurfaceRole.SUPPORTING,
            title=title,
            summary="Мягкое локальное обращение",
        ),
    )


def test_spatial_contract_is_immutable_and_rejects_renderer_coordinates():
    intent = SurfaceCompositionIntent()
    assert intent.preferred_position is CompositionPlacement.NEAR_RIGHT
    with pytest.raises(ValidationError):
        SurfaceCompositionIntent(x=742, y=183)
    with pytest.raises(ValidationError):
        intent.size_class = CompositionSize.EXPANDED


def test_idle_is_presence_first_with_only_the_room_ambient_region():
    model = default_home_model(observed_at=NOW)
    plan = CompositionResolver().resolve(model)

    assert len(plan.regions) == 1
    assert plan.regions[0].kind is CompositionRegionKind.AMBIENT
    assert plan.regions[0].surface_id is None
    assert plan.masha.placement is CompositionPlacement.CENTER_LEFT
    assert plan.masha.size_class is CompositionSize.EXPANDED
    assert plan.focus_owner is FocusOwner.PRESENCE
    assert plan.stability is CompositionStability.INITIAL


def test_normal_conversation_is_primary_to_the_right_of_masha():
    plan = CompositionResolver().resolve(_open_model())
    conversation = _region(plan, "home.conversation")

    assert conversation.kind is CompositionRegionKind.PRIMARY
    assert conversation.placement is CompositionPlacement.NEAR_RIGHT
    assert conversation.size_class is CompositionSize.STANDARD
    assert conversation.focus_owned is True
    assert conversation.occlusion.preserve_face is True


def test_long_conversation_can_expand_without_new_layout_engine():
    model = _open_model()
    conversation = model.surfaces[0].model_copy(
        update={
            "composition": SurfaceCompositionIntent(
                preferred_position=CompositionPlacement.NEAR_RIGHT,
                size_class=CompositionSize.EXPANDED,
            )
        }
    )
    model = model.model_copy(update={"surfaces": (conversation,)})

    region = _region(CompositionResolver().resolve(model), conversation.surface_id)
    assert region.size_class is CompositionSize.EXPANDED
    assert region.placement is CompositionPlacement.NEAR_RIGHT


def test_three_variants_are_plans_from_one_resolver_not_frontends():
    model = _open_model()
    resolver = CompositionResolver()
    plans = {
        variant: resolver.resolve(model, variant=variant)
        for variant in CompositionVariant
    }

    assert plans[CompositionVariant.PRESENCE_FIRST].masha.size_class is CompositionSize.EXPANDED
    assert (
        _region(plans[CompositionVariant.CONVERSATION_FIRST], "home.conversation").size_class
        is CompositionSize.EXPANDED
    )
    assert plans[CompositionVariant.ADAPTIVE_CINEMATIC].variant is CompositionVariant.ADAPTIVE_CINEMATIC
    assert {plan.primary_surface_id for plan in plans.values()} == {"home.conversation"}


def test_adaptive_cinematic_expands_a_focused_activity_and_keeps_conversation():
    reducer = PresentationReducer()
    model = reducer.reduce(
        _open_model(),
        _event(
            ActivityStarted,
            activity_id="activity.focused",
            surface_id="surface.focused",
            title="Совместная работа",
        ),
    )
    model = reducer.reduce(
        model,
        _event(SurfaceFocused, 2, surface_id="surface.focused"),
    )

    plan = CompositionResolver().resolve(
        model,
        variant=CompositionVariant.ADAPTIVE_CINEMATIC,
    )
    activity = _region(plan, "surface.focused")
    conversation = _region(plan, "home.conversation")
    assert activity.kind is CompositionRegionKind.PRIMARY
    assert activity.size_class is CompositionSize.EXPANDED
    assert activity.placement is CompositionPlacement.NEAR_RIGHT
    assert conversation.kind is CompositionRegionKind.SUPPORTING
    assert conversation.placement is CompositionPlacement.LOWER


def test_activity_queued_running_and_progress_keep_a_stable_supporting_region():
    reducer = PresentationReducer()
    resolver = CompositionResolver()
    model = _open_model()
    common = {
        "activity_id": "activity.audit",
        "surface_id": "surface.audit",
        "title": "Проверка проекта",
    }
    queued = reducer.reduce(model, _event(ActivityQueued, **common))
    queued_plan = resolver.resolve(queued)
    queued_region = _region(queued_plan, "surface.audit")
    assert queued_region.activity_state is ActivityState.QUEUED
    assert queued_region.placement is CompositionPlacement.LOWER

    running = reducer.reduce(queued, _event(ActivityStarted, 2, **common))
    running_plan = resolver.resolve(running, previous_plan=queued_plan)
    assert _region(running_plan, "surface.audit").activity_state is ActivityState.RUNNING
    assert _region(running_plan, "surface.audit").placement is CompositionPlacement.LOWER
    assert running_plan.stability is CompositionStability.STABLE

    progressed = reducer.reduce(
        running,
        _event(
            ActivityProgressed,
            3,
            activity_id="activity.audit",
            completed_units=4,
            total_units=10,
        ),
    )
    progress_plan = resolver.resolve(progressed, previous_plan=running_plan)
    assert _region(progress_plan, "surface.audit").activity_state is ActivityState.RUNNING
    assert progress_plan.stability is CompositionStability.STABLE


def test_completed_activity_becomes_compact_terminal_trace():
    reducer = PresentationReducer()
    model = reducer.reduce(
        _open_model(),
        _event(
            ActivityStarted,
            activity_id="activity.done",
            surface_id="surface.done",
            title="Локальная задача",
        ),
    )
    model = reducer.reduce(model, _event(ActivityCompleted, 2, activity_id="activity.done"))

    plan = CompositionResolver().resolve(model)
    region = _region(plan, "surface.done")
    assert region.activity_state is ActivityState.COMPLETED
    assert region.surface_lifecycle is SurfaceLifecycle.COMPLETED
    assert region.size_class is CompositionSize.COMPACT
    assert region.placement is CompositionPlacement.PERIPHERAL
    assert plan.primary_surface_id == "home.conversation"


def test_pending_confirmation_owns_decision_region_without_windows_modal_semantics():
    model = _add_surface(
        _open_model(),
        InteractionSurface(
            surface_id="confirmation.memory",
            kind=SurfaceKind.CONFIRMATION,
            lifecycle=SurfaceLifecycle.CREATED,
            role=SurfaceRole.DECISION,
            title="Запомнить это?",
            sensitive=True,
        ),
    )

    plan = CompositionResolver().resolve(model)
    confirmation = _region(plan, "confirmation.memory")
    assert plan.primary_surface_id == "confirmation.memory"
    assert confirmation.kind is CompositionRegionKind.DECISION
    assert confirmation.priority is CompositionPriority.DECISION
    assert confirmation.placement is CompositionPlacement.FOREGROUND


@pytest.mark.parametrize("title", ["Напоминание", "Миша, ты здесь?"])
def test_reminder_and_checkin_are_compact_presence_related_surfaces(title):
    plan = CompositionResolver().resolve(_proactive_model(title=title))
    proactive = _region(plan, "proactive:example")

    assert proactive.size_class is CompositionSize.WHISPER
    assert proactive.placement is CompositionPlacement.NEAR_RIGHT
    assert proactive.priority is CompositionPriority.SUPPORTING
    assert plan.primary_surface_id == "home.conversation"


def test_proactive_off_suppresses_proactive_surface_without_hiding_conversation():
    model = _proactive_model(title="Напоминание")
    model = model.model_copy(
        update={"overlays": model.overlays.model_copy(update={"proactive": ProactiveOverlay.OFF})}
    )

    plan = CompositionResolver().resolve(model)
    assert "proactive:example" in plan.suppressed_surface_ids
    assert plan.primary_surface_id == "home.conversation"
    assert any(overlay.kind is OverlayKind.PROACTIVE for overlay in plan.overlays)


def test_emergency_stop_keeps_activity_visible_and_suppresses_proactive():
    reducer = PresentationReducer()
    model = _proactive_model(title="Миша, ты здесь?")
    model = reducer.reduce(
        model,
        _event(
            ActivityStarted,
            activity_id="activity.active",
            surface_id="surface.active",
            title="Работа",
        ),
    )
    model = reducer.reduce(model, _event(EmergencyStopEngaged, 2))

    plan = CompositionResolver().resolve(model)
    assert _region(plan, "surface.active").surface_kind is SurfaceKind.ACTIVITY
    assert "proactive:example" in plan.suppressed_surface_ids
    assert plan.focus_owner is FocusOwner.SAFETY
    assert any(overlay.kind is OverlayKind.SAFETY for overlay in plan.overlays)
    assert plan.masha.silhouette_visible is True


def test_unfocused_privacy_masks_sensitive_content_before_normal_composition():
    model = PresentationReducer().reduce(
        _open_model(),
        _event(WindowFocusChanged, focused=False),
    )

    plan = CompositionResolver().resolve(model)
    conversation = _region(plan, "home.conversation")
    assert plan.privacy_masked is True
    assert plan.focus_owner is FocusOwner.PRIVACY
    assert conversation.content_masked is True
    assert plan.masha.face_visible is False
    assert plan.masha.silhouette_visible is True
    assert plan.overlays[0].kind is OverlayKind.PRIVACY


def test_viewport_privacy_requirement_masks_even_a_focused_window():
    plan = CompositionResolver().resolve(
        _open_model(),
        viewport=ViewportCharacteristics(privacy_required=True),
    )
    assert plan.privacy_masked is True
    assert _region(plan, "home.conversation").content_masked is True


@pytest.mark.parametrize(
    ("viewport_class", "masha_placement", "surface_placement", "surface_size"),
    [
        (
            ViewportClass.NARROW,
            CompositionPlacement.UPPER,
            CompositionPlacement.STACKED_PRIMARY,
            CompositionSize.STANDARD,
        ),
        (
            ViewportClass.VERY_NARROW,
            CompositionPlacement.UPPER,
            CompositionPlacement.STACKED_PRIMARY,
            CompositionSize.STANDARD,
        ),
    ],
)
def test_narrow_and_very_narrow_use_semantic_stacking(
    viewport_class,
    masha_placement,
    surface_placement,
    surface_size,
):
    plan = CompositionResolver().resolve(
        _open_model(),
        viewport=ViewportCharacteristics(size_class=viewport_class),
    )
    conversation = _region(plan, "home.conversation")
    assert plan.masha.placement is masha_placement
    assert conversation.placement is surface_placement
    assert conversation.size_class is surface_size


def test_activity_and_conversation_are_composed_without_two_primary_surfaces():
    model = PresentationReducer().reduce(
        _open_model(),
        _event(
            ActivityStarted,
            activity_id="activity.one",
            surface_id="surface.one",
            title="Анализ",
        ),
    )
    plan = CompositionResolver().resolve(model)

    assert plan.primary_surface_id == "home.conversation"
    assert _region(plan, "home.conversation").kind is CompositionRegionKind.PRIMARY
    assert _region(plan, "surface.one").kind is CompositionRegionKind.SUPPORTING
    assert _region(plan, "surface.one").placement is CompositionPlacement.LOWER


def test_confirmation_has_priority_over_active_activity_and_conversation():
    reducer = PresentationReducer()
    model = reducer.reduce(
        _open_model(),
        _event(
            ActivityStarted,
            activity_id="activity.one",
            surface_id="surface.one",
            title="Анализ",
        ),
    )
    model = _add_surface(
        model,
        InteractionSurface(
            surface_id="confirmation.one",
            kind=SurfaceKind.CONFIRMATION,
            lifecycle=SurfaceLifecycle.ACTIVE,
            role=SurfaceRole.DECISION,
            title="Продолжить?",
        ),
    )

    plan = CompositionResolver().resolve(model)
    assert plan.primary_surface_id == "confirmation.one"
    assert _region(plan, "surface.one").kind is CompositionRegionKind.SUPPORTING
    assert _region(plan, "home.conversation").kind is CompositionRegionKind.SUPPORTING


def test_model_unavailable_is_an_overlay_and_does_not_replace_masha_or_conversation():
    reducer = PresentationReducer()
    model = _open_model()
    visual_identity = model.presence.visual_identity
    model = reducer.reduce(
        model,
        _event(ModelUnavailable, profile_id="primary", display_name="Qwen 3.5 9B"),
    )

    plan = CompositionResolver().resolve(model)
    assert plan.primary_surface_id == "home.conversation"
    assert plan.masha.pose == model.presence.pose
    assert model.presence.visual_identity == visual_identity
    assert any(overlay.kind is OverlayKind.MODEL for overlay in plan.overlays)


@pytest.mark.parametrize("runtime_mode", [RuntimeMode.MANUAL, RuntimeMode.BACKGROUND])
def test_manual_and_background_runtime_are_ambient_not_layout_authority(runtime_mode):
    model = PresentationReducer().reduce(
        _open_model(),
        _event(
            RuntimeModeChanged,
            runtime_mode=runtime_mode,
            daemon_running=runtime_mode is RuntimeMode.BACKGROUND,
        ),
    )
    plan = CompositionResolver().resolve(model)
    runtime_overlay = next(overlay for overlay in plan.overlays if overlay.kind is OverlayKind.RUNTIME)
    assert runtime_mode.value in runtime_overlay.state_code
    assert runtime_overlay.priority is CompositionPriority.AMBIENT
    assert plan.primary_surface_id == "home.conversation"


def test_resolver_is_deterministic_and_does_not_mutate_presentation_model():
    model = _proactive_model(title="Напоминание")
    before = model.model_dump_json()
    resolver = CompositionResolver()

    first = resolver.resolve(model, variant=CompositionVariant.ADAPTIVE_CINEMATIC)
    second = resolver.resolve(model, variant=CompositionVariant.ADAPTIVE_CINEMATIC)

    assert first == second
    assert model.model_dump_json() == before
    assert not any(name in first.model_dump() for name in ("x", "y", "width", "height"))


def test_layout_hysteresis_retains_allowed_position_across_small_state_change():
    model = _open_model()
    first_intent = SurfaceCompositionIntent(
        preferred_position=CompositionPlacement.NEAR_LEFT,
        allowed_positions=(
            CompositionPlacement.NEAR_LEFT,
            CompositionPlacement.NEAR_RIGHT,
        ),
    )
    conversation = model.surfaces[0].model_copy(update={"composition": first_intent})
    first_model = model.model_copy(update={"surfaces": (conversation,)})
    resolver = CompositionResolver()
    first_plan = resolver.resolve(first_model)
    assert _region(first_plan, conversation.surface_id).placement is CompositionPlacement.NEAR_LEFT

    changed_intent = first_intent.model_copy(
        update={"preferred_position": CompositionPlacement.NEAR_RIGHT}
    )
    changed_conversation = conversation.model_copy(update={"composition": changed_intent})
    changed_presence = first_model.presence.model_copy(
        update={"expression": ExpressionCue(code=ExpressionCode.WARM_SMILE, intensity=0.4)}
    )
    changed_model = first_model.model_copy(
        update={"surfaces": (changed_conversation,), "presence": changed_presence}
    )
    second_plan = resolver.resolve(changed_model, previous_plan=first_plan)

    assert _region(second_plan, conversation.surface_id).placement is CompositionPlacement.NEAR_LEFT
    assert second_plan.stability is CompositionStability.STABLE


def test_viewport_change_overrides_hysteresis_deterministically():
    resolver = CompositionResolver()
    model = _open_model()
    wide = resolver.resolve(model)
    narrow_viewport = ViewportCharacteristics(size_class=ViewportClass.NARROW)
    narrow = resolver.resolve(model, viewport=narrow_viewport, previous_plan=wide)

    assert _region(narrow, "home.conversation").placement is CompositionPlacement.STACKED_PRIMARY
    assert narrow.stability is CompositionStability.VIEWPORT_OVERRIDE


def test_focus_change_recomposes_instead_of_preserving_conflicting_placements():
    reducer = PresentationReducer()
    resolver = CompositionResolver()
    model = reducer.reduce(
        _open_model(),
        _event(
            ActivityStarted,
            activity_id="activity.focus",
            surface_id="surface.focus",
            title="Работа",
        ),
    )
    conversation_plan = resolver.resolve(model)
    model = reducer.reduce(model, _event(SurfaceFocused, 2, surface_id="surface.focus"))
    activity_plan = resolver.resolve(
        model,
        variant=CompositionVariant.ADAPTIVE_CINEMATIC,
        previous_plan=conversation_plan.model_copy(
            update={"variant": CompositionVariant.ADAPTIVE_CINEMATIC}
        ),
    )

    assert _region(activity_plan, "surface.focus").placement is CompositionPlacement.NEAR_RIGHT
    assert _region(activity_plan, "home.conversation").placement is CompositionPlacement.LOWER
    assert activity_plan.stability is CompositionStability.RECOMPOSED


def test_very_narrow_capacity_is_bounded_and_reports_suppressed_surfaces():
    model = _open_model()
    for index, kind in enumerate((SurfaceKind.ACTIVITY, SurfaceKind.MEMORY, SurfaceKind.SKILLS)):
        model = _add_surface(
            model,
            InteractionSurface(
                surface_id=f"surface.extra.{index}",
                kind=kind,
                lifecycle=SurfaceLifecycle.ACTIVE,
                role=SurfaceRole.SUPPORTING,
                title=f"Дополнение {index}",
            ),
        )

    plan = CompositionResolver().resolve(
        model,
        viewport=ViewportCharacteristics(size_class=ViewportClass.VERY_NARROW),
    )
    assert len([region for region in plan.regions if region.surface_id]) == 2
    assert len(plan.suppressed_surface_ids) == 2
    assert plan.primary_surface_id == "home.conversation"
