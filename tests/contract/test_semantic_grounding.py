from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.contract

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.interpretation_v2 import (
    CapabilityCandidateDiscovery,
    InterpretationAmbiguity,
    InterpretationResolutionState,
)
from backend.conversation.semantic_resolver import (
    SemanticProposalValidator,
    SemanticValidationError,
    parse_semantic_interpretation,
)
from backend.temporal.date_resolution import HomeCalendarDateResolver
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


NOW = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)


def _validator() -> SemanticProposalValidator:
    catalog = default_home_capability_catalog()
    discovery = CapabilityCandidateDiscovery(catalog=catalog)
    return SemanticProposalValidator(
        catalog=catalog,
        specifications=discovery.specifications,
        known_operation_ids=frozenset(discovery.specifications.operation_ids),
        date_resolver=HomeCalendarDateResolver(
            TemporalEngine(clock=FixedClock(NOW)),
        ),
    )


def _supported(*, candidates, slots, action, selection=None):
    return parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": candidates,
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": name, "evidence_text": evidence}
            for name, evidence in slots
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": action},
        "operation_selection_evidence": selection or {
            "operation_id": None,
            "evidence_text": None,
        },
    })


def test_generic_schedule_keeps_application_owned_calendar_reminder_ambiguity():
    utterance = "Доброе утро, Маша! Запиши занятие завтра в 11"
    proposal = _supported(
        candidates=["home.timed_commitments"],
        slots=(("subject", "занятие"), ("date", "завтра"), ("time", "в 11")),
        action="Запиши",
    )

    frame = _validator().validate(utterance, proposal)

    assert tuple(item.operation_id for item in frame.candidates) == (
        "google_calendar.event.create",
        "home.timed_commitments",
    )
    assert frame.ambiguity is InterpretationAmbiguity.CAPABILITY
    assert {item.name: item.value for item in frame.slots} == {
        "subject": "занятие",
        "date": "2026-08-29",
        "time": "11:00",
    }


def test_grounded_reminder_selection_narrows_group_without_calendar_guess():
    utterance = "Пожалуйста, напомни завтра в 9 позвонить маме"
    proposal = _supported(
        candidates=["home.timed_commitments"],
        slots=(
            ("subject", "позвонить маме"),
            ("date", "завтра"),
            ("time", "в 9"),
        ),
        action="напомни",
        selection={
            "operation_id": "home.timed_commitments",
            "evidence_text": "напомни",
        },
    )

    frame = _validator().validate(utterance, proposal)

    assert tuple(item.operation_id for item in frame.candidates) == (
        "home.timed_commitments",
    )
    assert frame.resolution_state is InterpretationResolutionState.RESOLVED


def test_grounded_calendar_selection_uses_declared_duration_default():
    utterance = "Машенька, добавь встречу в календарь завтра в 14:30"
    proposal = _supported(
        candidates=["google_calendar.event.create"],
        slots=(("subject", "встречу"), ("date", "завтра"), ("time", "14:30")),
        action="добавь",
        selection={
            "operation_id": "google_calendar.event.create",
            "evidence_text": "в календарь",
        },
    )

    frame = _validator().validate(utterance, proposal)

    assert tuple(item.operation_id for item in frame.candidates) == (
        "google_calendar.event.create",
    )
    assert frame.missing_slots == ()
    assert frame.ambiguity is InterpretationAmbiguity.NONE
    assert {item.name: item.value for item in frame.slots}["duration_minutes"] == "60"


def test_operation_selection_evidence_must_exist_in_current_utterance():
    proposal = _supported(
        candidates=["google_calendar.event.create"],
        slots=(("subject", "встречу"), ("date", "завтра"), ("time", "14:30")),
        action="Добавь",
        selection={
            "operation_id": "google_calendar.event.create",
            "evidence_text": "в календарь",
        },
    )

    validator = _validator()
    frame = validator.validate("Добавь встречу завтра в 14:30", proposal)

    assert frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED
    assert tuple(item.operation_id for item in frame.candidates) == (
        "google_calendar.event.create", "home.timed_commitments",
    )
    assert validator.last_trace.operation_selection.accepted is False
    assert validator.last_trace.operation_selection.reason == "invented_operation_selection_evidence"


def test_grounded_generic_scheduling_word_cannot_select_calendar():
    proposal = _supported(
        candidates=["google_calendar.event.create"],
        slots=(("subject", "занятие"), ("date", "завтра"), ("time", "11")),
        action="запланируем",
        selection={
            "operation_id": "google_calendar.event.create",
            "evidence_text": "запланируем",
        },
    )
    validator = _validator()

    frame = validator.validate("Давай завтра запланируем занятие в 11", proposal)

    assert tuple(item.operation_id for item in frame.candidates) == (
        "google_calendar.event.create", "home.timed_commitments",
    )
    assert validator.last_trace.operation_selection.reason == (
        "operation_selection_semantics_mismatch"
    )


def test_duration_and_date_evidence_are_canonicalized_only_by_home():
    utterance = "Добавь встречу в календарь 29 августа в 14:30 на час"
    proposal = _supported(
        candidates=["google_calendar.event.create"],
        slots=(
            ("subject", "встречу"),
            ("date", "29 августа"),
            ("time", "14:30"),
            ("duration_minutes", "на час"),
        ),
        action="Добавь",
        selection={
            "operation_id": "google_calendar.event.create",
            "evidence_text": "в календарь",
        },
    )

    frame = _validator().validate(utterance, proposal)

    assert {item.name: item.value for item in frame.slots} == {
        "subject": "встречу",
        "date": "2026-08-29",
        "time": "14:30",
        "duration_minutes": "60",
    }
    assert frame.resolution_state is InterpretationResolutionState.RESOLVED


def test_model_generated_year_absent_from_utterance_fails_grounding():
    proposal = _supported(
        candidates=["google_calendar.event.create"],
        slots=(
            ("subject", "встречу"),
            ("date", "2024-08-29"),
            ("time", "14:30"),
            ("duration_minutes", "на час"),
        ),
        action="Добавь",
    )

    validator = _validator()
    frame = validator.validate(
        "Добавь встречу 29 августа в 14:30 на час",
        proposal,
    )

    assert "date" in frame.missing_slots
    assert any(
        item.name == "date" and not item.accepted
        for item in validator.last_trace.slots
    )
