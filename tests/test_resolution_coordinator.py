from datetime import datetime, timedelta, timezone

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import (
    CandidateEvidence, CapabilityCandidate, CapabilityCandidateDiscovery,
    InterpretationFrame, InterpretationResolutionState,
)
from backend.conversation.pending_resolution import (
    PendingResolutionStatus,
    PendingResolutionStore,
)
from backend.conversation.resolution_coordinator import (
    CoordinationStatus,
    DomainProposalContext,
    DomainProposalResult,
    NaturalLanguageResolutionCoordinator,
    ResolvedCapabilityAdapterRegistry,
    ResolvedCapabilityHandoff,
)


NOW = datetime(2026, 8, 28, 9, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value


def _coordinator(tmp_path, clock=None):
    clock = clock or MutableClock()
    catalog = default_home_capability_catalog()
    store = PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock)
    coordinator = NaturalLanguageResolutionCoordinator(
        discovery=CapabilityCandidateDiscovery(catalog=catalog),
        builder=DeterministicClarificationBuilder(catalog=catalog, clock=clock),
        engine=FollowUpResolutionEngine(),
        store=store,
    )
    return coordinator, store, clock


def test_capability_choice_persists_then_returns_strict_calendar_handoff(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)

    first = coordinator.coordinate(
        "Запиши занятие завтра в 10 на час", conversation_id="conversation-1"
    )
    active = store.active_for_conversation("conversation-1")
    second = coordinator.coordinate("В календарь", conversation_id="conversation-1")

    assert first.status is CoordinationStatus.CLARIFICATION
    assert first.response == (
        "Занятие — поставить в календарь или просто напомнить в 10:00?"
    )
    assert active is not None
    assert second.status is CoordinationStatus.RESOLVED_HANDOFF
    assert second.handoff == ResolvedCapabilityHandoff(
        conversation_id="conversation-1",
        operation_id="google_calendar.event.create",
        original_utterance="Запиши занятие завтра в 10 на час",
        slots=second.handoff.slots,
        resolution_id=active.resolution_id,
    )
    assert {item.name: item.value for item in second.handoff.slots} == {
        "date": "завтра",
        "time": "10:00",
        "duration_minutes": "60",
        "subject": "занятие",
    }
    assert store.get(active.resolution_id).status is PendingResolutionStatus.RESOLVED


def test_reminder_choice_returns_same_original_meaning_without_authority(tmp_path):
    coordinator, _, _ = _coordinator(tmp_path)
    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="c1")

    outcome = coordinator.coordinate("Просто напомни", conversation_id="c1")

    assert outcome.status is CoordinationStatus.RESOLVED_HANDOFF
    assert outcome.handoff.operation_id == "home.timed_commitments"
    serialized = outcome.handoff.model_dump()
    assert "confirmed" not in serialized
    assert "permission" not in serialized
    assert "provider" not in serialized


def test_missing_subject_follow_up_preserves_date_and_time(tmp_path):
    coordinator, _, _ = _coordinator(tmp_path)

    first = coordinator.coordinate(
        "Поставь в календарь завтра в 10 на час",
        conversation_id="c1",
    )
    second = coordinator.coordinate("Занятие по AI", conversation_id="c1")

    assert first.response == "Что именно поставить в календарь?"
    assert second.status is CoordinationStatus.RESOLVED_HANDOFF
    assert {item.name: item.value for item in second.handoff.slots} == {
        "date": "завтра",
        "time": "10:00",
        "duration_minutes": "60",
        "subject": "Занятие по AI",
    }


def test_timed_commitment_can_advance_from_choice_to_missing_subject(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)
    first = coordinator.coordinate("Запиши завтра в 10", conversation_id="c1")
    resolution_id = store.active_for_conversation("c1").resolution_id

    choice = coordinator.coordinate("Просто напомни", conversation_id="c1")
    final = coordinator.coordinate("Проверить роутер", conversation_id="c1")

    assert first.status is CoordinationStatus.CLARIFICATION
    assert choice.status is CoordinationStatus.STILL_UNRESOLVED
    assert choice.response == "Что именно нужно запомнить как дело?"
    assert store.get(resolution_id).resolution_id == resolution_id
    assert final.status is CoordinationStatus.RESOLVED_HANDOFF
    assert final.handoff.operation_id == "home.timed_commitments"
    assert {item.name: item.value for item in final.handoff.slots} == {
        "date": "завтра",
        "time": "10:00",
        "subject": "Проверить роутер",
    }


def test_unrelated_turns_pass_through_and_keep_pending(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)
    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="c1")
    resolution_id = store.active_for_conversation("c1").resolution_id

    weather = coordinator.coordinate("Какая завтра погода?", conversation_id="c1")
    coffee = coordinator.coordinate("Маш, я кофе сделал", conversation_id="c1")

    assert weather.status is CoordinationStatus.PASS_THROUGH
    assert coffee.status is CoordinationStatus.PASS_THROUGH
    assert store.active_for_conversation("c1").resolution_id == resolution_id


def test_new_supported_schedule_explicitly_supersedes_old_pending(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)
    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="c1")
    old = store.active_for_conversation("c1")

    outcome = coordinator.coordinate(
        "Запиши тренировку завтра в 12", conversation_id="c1"
    )
    current = store.active_for_conversation("c1")

    assert outcome.status is CoordinationStatus.CLARIFICATION
    assert outcome.diagnostic.pending_outcome == "superseded"
    assert current.resolution_id != old.resolution_id
    assert "Тренировку" in outcome.response
    assert store.get(old.resolution_id).status is PendingResolutionStatus.SUPERSEDED


def test_cancel_and_expiry_are_terminal_and_never_create_a_handoff(tmp_path):
    coordinator, store, clock = _coordinator(tmp_path)
    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="cancel")
    cancelled = store.active_for_conversation("cancel")
    outcome = coordinator.coordinate("Не надо", conversation_id="cancel")
    assert outcome.status is CoordinationStatus.CANCELLED
    assert store.get(cancelled.resolution_id).status is PendingResolutionStatus.CANCELLED

    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="expired")
    expired = store.active_for_conversation("expired")
    clock.value += timedelta(minutes=31)
    after_expiry = coordinator.coordinate("В календарь", conversation_id="expired")
    assert after_expiry.status is CoordinationStatus.PASS_THROUGH
    assert store.get(expired.resolution_id).status is PendingResolutionStatus.EXPIRED


def test_restart_recovers_same_resolution_and_resolves_it(tmp_path):
    first, store, clock = _coordinator(tmp_path)
    first.coordinate("Запиши занятие завтра в 10 на час", conversation_id="c1")
    resolution_id = store.active_for_conversation("c1").resolution_id

    restarted, restarted_store, _ = _coordinator(tmp_path, clock)
    outcome = restarted.coordinate("В календарь", conversation_id="c1")

    assert outcome.status is CoordinationStatus.RESOLVED_HANDOFF
    assert outcome.handoff.resolution_id == resolution_id
    assert restarted_store.get(resolution_id).status is PendingResolutionStatus.RESOLVED


def test_unsupported_docs_and_ordinary_conversation_remain_pass_through(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)
    for message in (
        "Короткий итог сегодняшнего занятия",
        "Маш, иди сюда, хочу немного побыть с тобой",
        "Сегодня мы продолжили делать наш Дом...",
        "Маша, создай документ на Гугл Диске: Сегодня мы продолжили делать наш Дом",
    ):
        outcome = coordinator.coordinate(message, conversation_id=message)
        assert outcome.status is CoordinationStatus.PASS_THROUGH
        assert store.active_for_conversation(message) is None


def test_known_unadopted_operation_is_application_owned_not_model_pass_through(tmp_path):
    class KnownDiscovery:
        def interpret(self, utterance, *, turn_context=None):
            return InterpretationFrame(
                original_utterance=utterance,
                    normalized_goal="home.proactive_reminders",
                    candidates=(CapabilityCandidate(
                        operation_id="home.proactive_reminders",
                    evidence=(CandidateEvidence(signal="local_semantic_proposal_validated"),),
                ),),
                resolution_state=InterpretationResolutionState.RESOLVED,
            )

    _, store, clock = _coordinator(tmp_path)
    coordinator = NaturalLanguageResolutionCoordinator(
        discovery=KnownDiscovery(),
        builder=DeterministicClarificationBuilder(
            catalog=default_home_capability_catalog(), clock=clock,
        ),
        engine=FollowUpResolutionEngine(),
        store=store,
    )

    outcome = coordinator.coordinate("Прочитай файл", conversation_id="known")

    assert outcome.status is CoordinationStatus.UNSUPPORTED_ACTION
    assert outcome.diagnostic.pending_outcome == "known_operation_not_adopted"
    assert "Ничего не запускаю" in outcome.response


def test_adapter_registry_accepts_future_operation_without_coordinator_change():
    class SyntheticAdapter:
        operation_id = "future.notes.create"

        def resolve(self, handoff, context):
            return DomainProposalResult(
                response=f"{handoff.slot('subject').value}:{context.project_id}",
                projection_state="waiting_confirmation",
                pending_application_operation="future_note_create",
            )

    from backend.conversation.interpretation_v2 import (
        InterpretationSlot,
        InterpretationValueOrigin,
    )

    handoff = ResolvedCapabilityHandoff(
        conversation_id="c1",
        operation_id="future.notes.create",
        original_utterance="Сохрани заметку",
        slots=(InterpretationSlot(
            name="subject", value="заметка",
            origin=InterpretationValueOrigin.EXPLICIT,
        ),),
    )
    registry = ResolvedCapabilityAdapterRegistry((SyntheticAdapter(),))

    result = registry.resolve(
        handoff,
        DomainProposalContext(project_id="project", now_local=NOW),
    )

    assert result.response == "заметка:project"


def test_corrupt_store_fails_safely_without_handoff(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("not-json", encoding="utf-8")

    outcome = coordinator.coordinate(
        "Запиши занятие завтра в 10", conversation_id="c1"
    )

    assert outcome.status is CoordinationStatus.FAILED
    assert outcome.handoff is None
    assert outcome.response == coordinator.FAILURE_RESPONSE
    assert outcome.diagnostic.pending_outcome == "infrastructure_failure"


def test_proven_domain_proposal_retires_stale_semantic_pending(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)
    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="c1")
    pending = store.active_for_conversation("c1")

    assert coordinator.supersede_for_domain_proposal("c1") is True
    assert store.active_for_conversation("c1") is None
    assert store.get(pending.resolution_id).status is PendingResolutionStatus.SUPERSEDED
