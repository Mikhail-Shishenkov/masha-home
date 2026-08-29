from datetime import datetime, timezone

import pytest

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery
from backend.conversation.pending_resolution import PendingResolutionStore
from backend.conversation.resolution_coordinator import (
    CoordinationStatus,
    NaturalLanguageResolutionCoordinator,
    V2LiveAdoptionPolicy,
)
from backend.conversation.semantic_resolver import (
    SemanticFollowUpProposal,
    SemanticFollowUpRelation,
    SemanticFollowUpResult,
    SemanticProposalValidator,
    SemanticResolverFailure,
    SemanticSlotMergeMode,
    SemanticSlotUpdateProposal,
)
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.date_resolution import HomeCalendarDateResolver


NOW = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)


class FollowUpResolver:
    def __init__(self, *proposals):
        self.proposals = list(proposals)
        self.calls = []

    def resolve_follow_up(self, utterance, vocabulary, context, *, profile_id=None):
        self.calls.append((utterance, vocabulary, context))
        if not self.proposals:
            return SemanticFollowUpResult(
                failure=SemanticResolverFailure.MALFORMED_OUTPUT,
                latency_ms=0,
            )
        return SemanticFollowUpResult(proposal=self.proposals.pop(0), latency_ms=0)


def _proposal(
    *, selected=None, selection_evidence=None, updates=(), relation="follow_up"
):
    return SemanticFollowUpProposal(
        relation=SemanticFollowUpRelation(relation),
        selected_operation_id=selected,
        operation_selection_evidence=selection_evidence,
        slot_updates=tuple(
            SemanticSlotUpdateProposal(
                name=name,
                evidence_text=value,
                mode=SemanticSlotMergeMode(mode),
            )
            for name, value, mode in updates
        ),
    )


def _coordinator(tmp_path, resolver=None):
    catalog = default_home_capability_catalog()
    discovery = CapabilityCandidateDiscovery(catalog=catalog)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=discovery.specifications,
        allowed_operation_ids=adoption.supported_operation_ids,
        date_resolver=HomeCalendarDateResolver(TemporalEngine(clock=FixedClock(NOW))),
    )
    clock = FixedClock(NOW)
    temporal = TemporalEngine(clock=clock)
    now = clock.now_utc
    store = PendingResolutionStore(tmp_path / "pending.json", clock=now)
    coordinator = NaturalLanguageResolutionCoordinator(
        discovery=discovery,
        builder=DeterministicClarificationBuilder(catalog=catalog, clock=now),
        engine=FollowUpResolutionEngine(
            semantic_resolver=resolver or FollowUpResolver(),
            semantic_validator=validator,
            temporal_engine=temporal,
        ),
        store=store,
        adoption=adoption,
    )
    return coordinator, store


def _slots(outcome):
    source = outcome.handoff.slots if outcome.handoff else outcome.clarification
    if outcome.handoff:
        return {item.name: item.value for item in source}
    return {
        item.name: item.value
        for item in outcome.diagnostic.merged_slots
    }


def test_capability_answer_preserves_accumulated_slots_and_normalizes_home_date(tmp_path):
    coordinator, store = _coordinator(tmp_path)
    first = coordinator.coordinate(
        "Запиши занятие завтра в 12 на час", conversation_id="c1",
    )
    resolution_id = first.clarification.resolution_id

    second = coordinator.coordinate("Поставь в календарь", conversation_id="c1")

    assert second.status is CoordinationStatus.RESOLVED_HANDOFF
    assert second.handoff.operation_id == "google_calendar.event.create"
    assert _slots(second) == {
        "date": "2026-08-29",
        "time": "12:00",
        "duration_minutes": "60",
        "subject": "занятие",
    }
    assert second.handoff.resolution_id == resolution_id
    assert second.diagnostic.prior_known_slots
    assert second.diagnostic.remaining_missing_slots == ()
    assert store.active_for_conversation("c1") is None


@pytest.mark.parametrize(
    ("answer", "expected"),
    (("на завтра", "2026-08-29"), ("29 августа", "2026-08-29")),
)
def test_explicit_date_fills_only_missing_date_without_semantic_guessing(
    tmp_path, answer, expected,
):
    resolver = FollowUpResolver()
    coordinator, _ = _coordinator(tmp_path, resolver)
    coordinator.coordinate("Поставь занятие в 12 на час", conversation_id="c1")

    result = coordinator.coordinate(answer, conversation_id="c1")

    assert result.status is CoordinationStatus.RESOLVED_HANDOFF
    assert _slots(result) == {
        "date": expected,
        "time": "12:00",
        "duration_minutes": "60",
        "subject": "занятие",
    }
    assert resolver.calls == []


def test_semantic_enrichment_and_correction_accumulate_before_choice(tmp_path):
    resolver = FollowUpResolver(
        _proposal(updates=(("subject", "занятие по вождению", "enrich"),)),
        _proposal(updates=(("time", "11", "correct"),)),
    )
    coordinator, store = _coordinator(tmp_path, resolver)
    first = coordinator.coordinate(
        "Запиши занятие завтра в 12 на час", conversation_id="c1",
    )
    resolution_id = first.clarification.resolution_id

    enriched = coordinator.coordinate(
        "Это будет занятие по вождению", conversation_id="c1",
    )
    corrected = coordinator.coordinate("Нет, лучше в 11", conversation_id="c1")
    resolved = coordinator.coordinate("В календарь", conversation_id="c1")

    assert enriched.status is CoordinationStatus.STILL_UNRESOLVED
    assert corrected.status is CoordinationStatus.STILL_UNRESOLVED
    assert resolved.status is CoordinationStatus.RESOLVED_HANDOFF
    assert resolved.handoff.resolution_id == resolution_id
    assert _slots(resolved) == {
        "date": "2026-08-29",
        "time": "11:00",
        "duration_minutes": "60",
        "subject": "занятие по вождению",
    }
    stored = store.get(resolution_id)
    assert stored.status.value == "resolved"


def test_semantic_capability_choice_cannot_drop_original_slots(tmp_path):
    resolver = FollowUpResolver(
        _proposal(
            selected="home.timed_commitments",
            selection_evidence="для Дома",
        ),
    )
    coordinator, _ = _coordinator(tmp_path, resolver)
    coordinator.coordinate("Запиши занятие завтра в 12", conversation_id="c1")

    result = coordinator.coordinate("Давай просто для Дома", conversation_id="c1")

    assert result.status is CoordinationStatus.RESOLVED_HANDOFF
    assert result.handoff.operation_id == "home.timed_commitments"
    assert _slots(result) == {
        "date": "2026-08-29",
        "time": "12:00",
        "subject": "занятие",
    }


def test_ordinary_turn_does_not_corrupt_or_cancel_pending_meaning(tmp_path):
    resolver = FollowUpResolver(
        _proposal(relation="not_a_follow_up"),
    )
    coordinator, store = _coordinator(tmp_path, resolver)
    first = coordinator.coordinate("Поставь завтра в 12", conversation_id="c1")

    ordinary = coordinator.coordinate("Сегодня был хороший день", conversation_id="c1")

    assert ordinary.status is CoordinationStatus.PASS_THROUGH
    active = store.active_for_conversation("c1")
    assert active.resolution_id == first.clarification.resolution_id
    assert {item.name: item.value for item in active.interpretation.slots} == {
        "date": "завтра",
        "time": "12:00",
    }


def test_invalid_semantic_update_fails_closed_and_keeps_pending(tmp_path):
    resolver = FollowUpResolver(
        _proposal(updates=(("subject", "придуманная встреча", "add"),)),
    )
    coordinator, store = _coordinator(tmp_path, resolver)
    first = coordinator.coordinate("Поставь завтра в 12", conversation_id="c1")

    result = coordinator.coordinate("Просто продолжим разговор", conversation_id="c1")

    assert result.status is CoordinationStatus.STILL_UNRESOLVED
    assert result.diagnostic.semantic_command_status == "rejected"
    assert result.diagnostic.proposed_semantic_command is not None
    assert result.diagnostic.semantic_rejection == "field_validation_rejected"
    assert any(
        item.reason == "follow_up_subject_not_grounded"
        for item in result.diagnostic.semantic_validation.slots
    )
    assert store.active_for_conversation("c1").resolution_id == first.clarification.resolution_id


def test_restart_preserves_refined_slots_and_same_resolution(tmp_path):
    resolver = FollowUpResolver(
        _proposal(updates=(("subject", "занятие по вождению", "enrich"),)),
    )
    coordinator, store = _coordinator(tmp_path, resolver)
    first = coordinator.coordinate("Запиши занятие завтра в 12 на час", conversation_id="c1")
    coordinator.coordinate("Занятие по вождению", conversation_id="c1")

    restarted, _ = _coordinator(tmp_path)
    result = restarted.coordinate("В календарь", conversation_id="c1")

    assert result.handoff.resolution_id == first.clarification.resolution_id
    assert _slots(result)["subject"] == "занятие по вождению"
    assert store.get(first.clarification.resolution_id).interpretation.slots


@pytest.mark.parametrize(
    ("expression", "expected"),
    (
        ("завтрашнее", "2026-08-29"),
        ("в субботу", "2026-08-29"),
        ("через два дня", "2026-08-30"),
    ),
)
def test_home_owned_relative_date_normalization_uses_injected_clock(
    expression, expected,
):
    resolver = HomeCalendarDateResolver(
        TemporalEngine(clock=FixedClock(NOW)),
    )

    assert resolver.resolve(expression).canonical == expected
