from datetime import datetime, timezone

import pytest

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery
from backend.conversation.pending_resolution import PendingResolutionStatus, PendingResolutionStore
from backend.conversation.resolution_coordinator import CoordinationStatus, DialogueCore
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


@pytest.mark.parametrize(
    ("clock_answer", "expected"),
    (("18:00", "18:00"), ("в 6 вечера", "18:00")),
)
def test_clock_answer_resolves_the_same_pending_flow(tmp_path, clock_answer, expected):
    clock = FixedClock(NOW)
    catalog = default_home_capability_catalog()
    core = DialogueCore(
        discovery=CapabilityCandidateDiscovery(catalog=catalog),
        builder=DeterministicClarificationBuilder(catalog=catalog, clock=clock.now_utc),
        engine=FollowUpResolutionEngine(),
        store=PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock.now_utc),
    )

    question = core.coordinate(
        "Поставь занятие в календарь завтра",
        conversation_id="clock-follow-up",
    )
    answer = core.coordinate(clock_answer, conversation_id="clock-follow-up")

    assert question.status is CoordinationStatus.CLARIFICATION
    assert question.response == "Во сколько?"
    assert answer.status is CoordinationStatus.RESOLVED_HANDOFF
    assert answer.handoff is not None
    assert answer.handoff.operation_id == "google_calendar.event.create"
    assert {slot.name: slot.value for slot in answer.handoff.slots}["time"] == expected
    assert core.snapshot("clock-follow-up").active_flow_id is None


def test_explicit_cancel_then_new_request_replaces_pending_owner(tmp_path):
    clock = FixedClock(NOW)
    catalog = default_home_capability_catalog()
    store = PendingResolutionStore(
        tmp_path / "pending-resolutions.json",
        clock=clock.now_utc,
    )
    core = DialogueCore(
        discovery=CapabilityCandidateDiscovery(catalog=catalog),
        builder=DeterministicClarificationBuilder(catalog=catalog, clock=clock.now_utc),
        engine=FollowUpResolutionEngine(),
        store=store,
    )

    core.coordinate("Запиши занятие завтра в 10", conversation_id="replace")
    before = store.active_for_conversation("replace")
    outcome = core.coordinate(
        "Ладно, забыли. Запиши тренировку завтра в 12",
        conversation_id="replace",
    )
    after = store.active_for_conversation("replace")

    assert before is not None and after is not None
    assert before.resolution_id != after.resolution_id
    assert store.get(before.resolution_id).status is PendingResolutionStatus.CANCELLED
    assert after.interpretation.original_utterance == "Запиши тренировку завтра в 12"
    assert outcome.status is CoordinationStatus.CLARIFICATION
    assert outcome.diagnostic.pending_outcome == "cancelled_then_clarification"
