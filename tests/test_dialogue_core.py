from __future__ import annotations

from datetime import datetime, timezone

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery
from backend.conversation.pending_resolution import PendingResolutionStore
from backend.conversation.resolution_coordinator import CoordinationStatus, DialogueCore
from backend.conversation.resolution_coordinator import V2LiveAdoptionPolicy
from backend.conversation.semantic_resolver import (
    SemanticFollowUpProposal,
    SemanticFollowUpRelation,
    SemanticFollowUpResult,
    SemanticProposalValidator,
)
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


NOW = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)


class _OrdinaryFollowUpResolver:
    def resolve_follow_up(self, utterance, vocabulary, context, *, profile_id=None):
        return SemanticFollowUpResult(
            proposal=SemanticFollowUpProposal(
                relation=SemanticFollowUpRelation.NOT_A_FOLLOW_UP,
            ),
            latency_ms=0,
        )


def _core(tmp_path):
    catalog = default_home_capability_catalog()
    clock = FixedClock(NOW)
    discovery = CapabilityCandidateDiscovery(catalog=catalog)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=discovery.specifications,
        allowed_operation_ids=adoption.supported_operation_ids,
    )
    return DialogueCore(
        discovery=discovery,
        builder=DeterministicClarificationBuilder(
            catalog=catalog,
            clock=clock.now_utc,
        ),
        engine=FollowUpResolutionEngine(
            semantic_resolver=_OrdinaryFollowUpResolver(),
            semantic_validator=validator,
            temporal_engine=TemporalEngine(clock=clock),
        ),
        store=PendingResolutionStore(
            tmp_path / "pending-resolutions.json",
            clock=clock.now_utc,
        ),
    )


def _slots(core: DialogueCore, conversation_id: str) -> dict[str, str]:
    state = core.snapshot(conversation_id)
    return {
        slot.name: slot.value
        for slot in state.flow_stack[0].validated_slots
        if slot.value is not None
    }


def test_active_duration_question_owns_short_number_and_cross_slot_correction(tmp_path):
    core = _core(tmp_path)
    first = core.coordinate(
        "Добавь в календарь запись на завтра на 12, что я буду учиться йоге",
        conversation_id="c1",
    )
    ambiguous = core.coordinate("12", conversation_id="c1")
    corrected = core.coordinate("12 часов дня", conversation_id="c1")

    assert first.response == "На сколько времени поставить?"
    assert ambiguous.status is CoordinationStatus.STILL_UNRESOLVED
    assert ambiguous.response == "12 минут или 12 часов?"
    assert corrected.status is CoordinationStatus.STILL_UNRESOLVED
    assert corrected.response == "На сколько времени поставить?"
    assert _slots(core, "c1") == {
        "date": "2026-08-29",
        "time": "12:00",
        "subject": "учиться йоге",
    }
    question = core.snapshot("c1").flow_stack[0].active_question
    assert question.requested_slot == "duration_minutes"
    assert question.value_hint is None


def test_duration_answer_resumes_same_flow_after_ordinary_interruption(tmp_path):
    core = _core(tmp_path)
    first = core.coordinate(
        "Добавь в календарь запись на завтра на 12, что я буду учиться йоге",
        conversation_id="c1",
    )
    flow_id = core.snapshot("c1").active_flow_id

    ordinary = core.coordinate("Сегодня отличный день", conversation_id="c1")
    resumed = core.coordinate("на час", conversation_id="c1")

    assert ordinary.status is CoordinationStatus.PASS_THROUGH
    assert core.store.get(flow_id).status.value == "resolved"
    assert resumed.status is CoordinationStatus.RESOLVED_HANDOFF
    assert resumed.handoff.resolution_id == first.clarification.resolution_id
    assert {slot.name: slot.value for slot in resumed.handoff.slots} == {
        "date": "2026-08-29",
        "time": "12:00",
        "subject": "учиться йоге",
        "duration_minutes": "60",
    }


def test_explicit_date_advances_instead_of_repeating_same_question(tmp_path):
    core = _core(tmp_path)
    first = core.coordinate("Поставь занятие в 12 на час", conversation_id="c1")
    resolved = core.coordinate("29 августа", conversation_id="c1")

    assert first.response == "На какой день?"
    assert resolved.status is CoordinationStatus.RESOLVED_HANDOFF
    assert {slot.name: slot.value for slot in resolved.handoff.slots}["date"] == "2026-08-29"


def test_plain_yes_answers_clarification_but_never_authorizes_action(tmp_path):
    core = _core(tmp_path)
    core.coordinate("Запиши занятие завтра в 12", conversation_id="c1")

    result = core.coordinate("да", conversation_id="c1")

    assert result.status in {
        CoordinationStatus.STILL_UNRESOLVED,
        CoordinationStatus.PASS_THROUGH,
    }
    assert result.handoff is None
    assert core.snapshot("c1").active_flow_id is not None


def test_diagnostic_snapshot_is_bounded_read_only_and_has_one_flow(tmp_path):
    core = _core(tmp_path)
    core.coordinate("Запиши занятие завтра в 12", conversation_id="c1")

    state = core.snapshot("c1")

    assert state.version == "2.0"
    assert len(state.flow_stack) == 1
    assert state.active_flow_id == state.flow_stack[0].flow_id
    assert state.flow_stack[0].candidate_operation_ids == (
        "google_calendar.event.create",
        "home.timed_commitments",
    )
    assert state.flow_stack[0].active_question.kind.value == "capability"
    assert not hasattr(state, "store")
    assert not hasattr(state, "resolve")
