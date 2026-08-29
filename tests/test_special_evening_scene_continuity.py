from backend.application.home_snapshot import (
    SpecialEveningSceneContinuityState,
)
from backend.conversation.context_compiler import (
    SPECIAL_EVENING_SCENE_CONTINUITY_CONTRACT,
    resolve_special_evening_scene_continuity,
)
from backend.presentation import HomeProximity


def test_scene_continuity_tracks_only_home_owned_distance_transitions():
    state = SpecialEveningSceneContinuityState()

    assert state.model_context() == {
        "last_transition": "none",
        "contact_state": "unspecified",
    }

    state.entered()
    assert state.model_context()["last_transition"] == "entered"

    state.proximity_changed(
        HomeProximity.WIDE,
        HomeProximity.CLOSE,
        source="manual",
    )
    assert state.model_context()["last_transition"] == "manual_closer"

    state.proximity_changed(
        HomeProximity.CLOSE,
        HomeProximity.NEAR,
        source="model",
    )
    assert state.model_context()["last_transition"] == "model_closer"

    state.proximity_changed(
        HomeProximity.NEAR,
        HomeProximity.CLOSE,
        source="model",
    )
    assert state.model_context()["last_transition"] == "model_farther"

    state.paused()
    assert state.model_context() == {
        "last_transition": "paused",
        "contact_state": "unspecified",
    }

    state.reset()
    assert state.model_context()["last_transition"] == "none"


def test_scene_continuity_never_promotes_arbitrary_renderer_or_model_text():
    assert resolve_special_evening_scene_continuity(
        "special_evening",
        {
            "last_transition": "I was sitting on Misha's lap",
            "contact_state": "embrace",
            "extra": "invented",
        },
    ) == {
        "last_transition": "none",
        "contact_state": "unspecified",
    }

    assert resolve_special_evening_scene_continuity(
        "ordinary",
        {"last_transition": "model_closer"},
    ) is None


def test_scene_continuity_contract_forbids_backfilling_pose_from_proximity():
    contract = SPECIAL_EVENING_SCENE_CONTINUITY_CONTRACT.casefold()

    assert "не устанавливает точную позу" in contract
    assert "с твоих колен" in contract
    assert "contact_state=unspecified" in contract
    assert "не запрещает новый естественный жест" in contract
