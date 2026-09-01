from datetime import datetime, timezone

import pytest

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery
from backend.conversation.pending_resolution import PendingResolutionStore
from backend.conversation.resolution_coordinator import DialogueCore
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


pytestmark = pytest.mark.contract
NOW = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)


def test_dialogue_snapshot_is_bounded_read_only_state(tmp_path):
    clock = FixedClock(NOW)
    catalog = default_home_capability_catalog()
    core = DialogueCore(
        discovery=CapabilityCandidateDiscovery(
            catalog=catalog,
            temporal_engine=TemporalEngine(clock=clock),
        ),
        builder=DeterministicClarificationBuilder(catalog=catalog, clock=clock.now_utc),
        engine=FollowUpResolutionEngine(),
        store=PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock.now_utc),
    )

    core.coordinate("Запиши занятие завтра в 12", conversation_id="c1")
    state = core.snapshot("c1")

    assert state.version == "2.0"
    assert len(state.flow_stack) == 1
    assert state.active_flow_id == state.flow_stack[0].flow_id
    assert state.flow_stack[0].candidate_operation_ids == (
        "google_calendar.event.create", "home.timed_commitments",
    )
    assert state.flow_stack[0].active_question.kind.value == "capability"
    assert not hasattr(state, "store")
    assert not hasattr(state, "resolve")
