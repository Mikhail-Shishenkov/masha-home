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
    temporal = TemporalEngine(clock=clock)
    discovery = CapabilityCandidateDiscovery(catalog=catalog, temporal_engine=temporal)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=discovery.specifications,
        allowed_operation_ids=adoption.supported_operation_ids,
    )
    core = DialogueCore(
        discovery=discovery,
        builder=DeterministicClarificationBuilder(
            catalog=catalog,
            clock=clock.now_utc,
        ),
        engine=FollowUpResolutionEngine(
            semantic_resolver=_OrdinaryFollowUpResolver(),
            semantic_validator=validator,
            temporal_engine=temporal,
        ),
        store=PendingResolutionStore(
            tmp_path / "pending-resolutions.json",
            clock=clock.now_utc,
        ),
    )
    core.bind_temporal_engine(temporal)
    return core


def _slots(core: DialogueCore, conversation_id: str) -> dict[str, str]:
    state = core.snapshot(conversation_id)
    return {
        slot.name: slot.value
        for slot in state.flow_stack[0].validated_slots
        if slot.value is not None
    }


def test_calendar_uses_declared_duration_default_at_handoff(tmp_path):
    core = _core(tmp_path)
    result = core.coordinate(
        "Добавь в календарь запись на завтра на 12, что я буду учиться йоге",
        conversation_id="c1",
    )
    assert result.status is CoordinationStatus.RESOLVED_HANDOFF
    assert {slot.name: slot.value for slot in result.handoff.slots} == {
        "date": "2026-08-29",
        "time": "12:00",
        "subject": "учиться йоге",
        "duration_minutes": "60",
    }


def test_explicit_calendar_duration_overrides_declared_default(tmp_path):
    core = _core(tmp_path)
    result = core.coordinate(
        "Добавь в календарь запись на завтра на 12 на два часа, что я буду учиться йоге",
        conversation_id="c1",
    )

    assert result.status is CoordinationStatus.RESOLVED_HANDOFF
    assert {slot.name: slot.value for slot in result.handoff.slots}["duration_minutes"] == "120"


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
