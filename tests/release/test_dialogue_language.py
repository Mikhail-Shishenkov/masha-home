from datetime import datetime, timezone

import pytest

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import (
    CapabilityCandidateDiscovery,
    InterpretationAmbiguity,
    InterpretationResolutionState,
)
from backend.conversation.pending_resolution import PendingResolutionStore
from backend.conversation.resolution_coordinator import (
    CoordinationStatus,
    NaturalLanguageResolutionCoordinator,
)
from backend.conversation.semantic_resolver import (
    SemanticProposalValidator,
    parse_semantic_interpretation,
)
from backend.temporal.date_resolution import HomeCalendarDateResolver
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


pytestmark = pytest.mark.release
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


def _proposal(*, candidates, slots, action, selection=None):
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


def _coordinator(tmp_path):
    clock = FixedClock(NOW)
    catalog = default_home_capability_catalog()
    return NaturalLanguageResolutionCoordinator(
        discovery=CapabilityCandidateDiscovery(catalog=catalog),
        builder=DeterministicClarificationBuilder(catalog=catalog, clock=clock.now_utc),
        engine=FollowUpResolutionEngine(),
        store=PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock.now_utc),
    )


def test_rel_001_to_005_keep_language_meaning_grounded_and_non_authoritative(tmp_path):
    validator = _validator()

    generic = validator.validate(
        "Доброе утро, Маша! Запиши занятие завтра в 11",
        _proposal(
            candidates=["home.timed_commitments"],
            slots=(("subject", "занятие"), ("date", "завтра"), ("time", "в 11")),
            action="Запиши",
        ),
    )
    assert tuple(item.operation_id for item in generic.candidates) == (
        "google_calendar.event.create", "home.timed_commitments",
    )
    assert generic.ambiguity is InterpretationAmbiguity.CAPABILITY

    calendar = validator.validate(
        "Добавь встречу в календарь завтра в 14:30",
        _proposal(
            candidates=["google_calendar.event.create"],
            slots=(("subject", "встречу"), ("date", "завтра"), ("time", "14:30")),
            action="Добавь",
            selection={
                "operation_id": "google_calendar.event.create",
                "evidence_text": "в календарь",
            },
        ),
    )
    reminder = validator.validate(
        "Пожалуйста, напомни завтра в 9 позвонить маме",
        _proposal(
            candidates=["home.timed_commitments"],
            slots=(("subject", "позвонить маме"), ("date", "завтра"), ("time", "в 9")),
            action="напомни",
            selection={
                "operation_id": "home.timed_commitments",
                "evidence_text": "напомни",
            },
        ),
    )
    partial = validator.validate(
        "Добавь встречу в календарь завтра в 14:30",
        _proposal(
            candidates=["google_calendar.event.create"],
            slots=(
                ("subject", "встречу"), ("date", "завтра"),
                ("time", "14:30"), ("provider_id", "secret"),
            ),
            action="Добавь",
            selection={
                "operation_id": "google_calendar.event.create",
                "evidence_text": "в календарь",
            },
        ),
    )

    assert calendar.resolution_state is InterpretationResolutionState.RESOLVED
    assert reminder.resolution_state is InterpretationResolutionState.RESOLVED
    assert partial.resolution_state is InterpretationResolutionState.RESOLVED
    assert "provider_id" not in {slot.name for slot in partial.slots}
    assert any(
        item.name == "provider_id" and not item.accepted
        for item in validator.last_trace.slots
    )

    coordinator = _coordinator(tmp_path)
    ordinary = coordinator.coordinate(
        "Я завтра хочу позаниматься AI",
        conversation_id="ordinary",
    )
    assert ordinary.status is CoordinationStatus.PASS_THROUGH
    assert coordinator.store.active_for_conversation("ordinary") is None


def test_rel_007_008_and_010_keep_pending_meaning_without_authorization(tmp_path):
    coordinator = _coordinator(tmp_path)

    calendar_first = coordinator.coordinate(
        "Запиши занятие завтра в 10 на час", conversation_id="calendar",
    )
    calendar = coordinator.coordinate("В календарь", conversation_id="calendar")
    assert calendar_first.response == (
        "Занятие — поставить в календарь или просто напомнить в 10:00?"
    )
    assert calendar.status is CoordinationStatus.RESOLVED_HANDOFF
    assert calendar.handoff.operation_id == "google_calendar.event.create"
    assert {slot.name: slot.value for slot in calendar.handoff.slots} == {
        "date": "завтра", "time": "10:00", "duration_minutes": "60", "subject": "занятие",
    }

    coordinator.coordinate("Запиши завтра в 10", conversation_id="reminder")
    reminder_choice = coordinator.coordinate("Просто напомни", conversation_id="reminder")
    reminder = coordinator.coordinate("Проверить роутер", conversation_id="reminder")
    assert reminder_choice.status is CoordinationStatus.STILL_UNRESOLVED
    assert reminder.status is CoordinationStatus.RESOLVED_HANDOFF
    assert reminder.handoff.operation_id == "home.timed_commitments"
    assert all(
        field not in reminder.handoff.model_dump_json()
        for field in ("confirmed", "permission", "provider")
    )

    missing_subject = coordinator.coordinate(
        "Поставь в календарь завтра в 10 на час", conversation_id="subject",
    )
    subject = coordinator.coordinate("Занятие по AI", conversation_id="subject")
    assert missing_subject.response == "Что именно поставить в календарь?"
    assert {slot.name: slot.value for slot in subject.handoff.slots} == {
        "date": "завтра", "time": "10:00", "duration_minutes": "60", "subject": "Занятие по AI",
    }

    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="interrupt")
    interruption = coordinator.coordinate("Какая завтра погода?", conversation_id="interrupt")
    assert interruption.status is CoordinationStatus.PASS_THROUGH
    assert coordinator.store.active_for_conversation("interrupt") is not None

    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="supersede")
    superseding = coordinator.coordinate("Запиши тренировку завтра в 12", conversation_id="supersede")
    assert superseding.status is CoordinationStatus.CLARIFICATION
    assert superseding.diagnostic.pending_outcome == "superseded"

    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="yes")
    answer = coordinator.coordinate("да", conversation_id="yes")
    assert answer.status in {CoordinationStatus.STILL_UNRESOLVED, CoordinationStatus.PASS_THROUGH}
    assert answer.handoff is None
    assert coordinator.store.active_for_conversation("yes") is not None
