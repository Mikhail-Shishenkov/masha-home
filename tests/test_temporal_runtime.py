from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time, timedelta, timezone

from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.memory_models import CommitmentStatus, ReminderDeliveryMode
from backend.temporal.proactive import ProactiveDecisionEngine, ProactivePolicy
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.temporal_models import ProactiveDecision
from backend.temporal.temporal_runtime import TemporalRuntime, commitment_due_event_id


NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _repository(tmp_path, canonical_memory, *, due_at, status="open", explicit=False):
    document = deepcopy(canonical_memory)
    commitment = document["commitments"][0]
    commitment["due_at"] = due_at.isoformat()
    commitment["status"] = status
    commitment["completed_at"] = due_at.isoformat() if status == "completed" else None
    if explicit:
        commitment["reminder_delivery_mode"] = "explicit_user_reminder"
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(document)
    return repository


def _runtime(repository, now=NOW):
    return TemporalRuntime(repository, TemporalEngine(FixedClock(now)))


def test_recovery_creates_stable_overdue_commitment_event_without_memory_mutation(tmp_path, canonical_memory):
    due_at = NOW - timedelta(minutes=1)
    repository = _repository(tmp_path, canonical_memory, due_at=due_at)
    before_document = repository.read_document().model_dump(mode="json")
    before_audit = repository.list_audit_events()

    context = _runtime(repository).recover()

    assert len(context.events) == 1
    event = context.events[0]
    assert event.event_id == commitment_due_event_id("commitment_001", due_at)
    assert event.source_commitment_id == "commitment_001"
    assert event.due_at == due_at
    assert event.detected_at == NOW
    assert event.status.value == "overdue"
    assert repository.read_document().model_dump(mode="json") == before_document
    assert repository.list_audit_events() == before_audit


def test_exact_due_boundary_creates_no_event_and_preserves_mem11_open_semantics(tmp_path, canonical_memory):
    repository = _repository(tmp_path, canonical_memory, due_at=NOW)

    context = _runtime(repository).recover()

    assert context.events == ()
    assert repository.read_document().commitments[0].status.value == "open"


def test_completed_and_cancelled_commitments_create_no_active_due_event(tmp_path, canonical_memory):
    due_at = NOW - timedelta(minutes=1)
    for status in ("completed", "cancelled"):
        repository = _repository(
            tmp_path / status, canonical_memory, due_at=due_at,
            status=status, explicit=True,
        )
        assert _runtime(repository).recover().events == ()


def test_commitment_status_and_reminder_origin_enums_remain_distinct():
    assert CommitmentStatus.EXPIRED.value == "expired"
    assert {item.value for item in ReminderDeliveryMode} == {
        "policy_controlled",
        "explicit_user_reminder",
    }


def test_repeated_recovery_and_restart_are_idempotent(tmp_path, canonical_memory):
    due_at = NOW - timedelta(minutes=1)
    repository = _repository(tmp_path, canonical_memory, due_at=due_at)
    first = _runtime(repository).recover()
    second = _runtime(repository).recover()
    restarted = _runtime(MemorySqliteRepository(repository.database_path)).recover()

    assert [event.event_id for event in first.events] == [event.event_id for event in second.events] == [event.event_id for event in restarted.events]
    with repository._connection() as connection:
        count = connection.execute("SELECT COUNT(*) FROM temporal_events").fetchone()[0]
    assert count == 1


def test_proactive_decision_policy_is_deterministic_and_does_not_mutate_event(tmp_path, canonical_memory):
    repository = _repository(tmp_path, canonical_memory, due_at=NOW - timedelta(minutes=1))
    event = _runtime(repository).recover().events[0]
    engine = ProactiveDecisionEngine()

    assert engine.decide(event, ProactivePolicy(), now=NOW) is ProactiveDecision.SUPPRESS
    assert engine.decide(event, ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True, maximum_reminders=1), now=NOW) is ProactiveDecision.REMIND
    assert engine.decide(event, ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True, maximum_reminders=1, quiet_hours_start=time(15, 0), quiet_hours_end=time(16, 0)), now=NOW) is ProactiveDecision.SUPPRESS
    assert engine.decide(event, ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True, maximum_reminders=1, cooldown_seconds=3600), now=NOW, last_reminder_at=NOW - timedelta(minutes=1)) is ProactiveDecision.SUPPRESS
    assert engine.decide(event, ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True, maximum_reminders=1), now=NOW, mutation_requested=True) is ProactiveDecision.REQUIRE_CONFIRMATION
    assert event.status.value == "overdue"


def test_bounded_candidate_contains_only_event_source_and_decision(tmp_path, canonical_memory):
    repository = _repository(tmp_path, canonical_memory, due_at=NOW - timedelta(minutes=1))
    event = _runtime(repository).recover().events[0]

    candidate = ProactiveDecisionEngine.candidate(
        event,
        commitment_text="Продолжить разработку Masha Home",
        temporal_context=TemporalEngine(FixedClock(NOW)).context(None),
        decision=ProactiveDecision.REMIND,
        generated_at=NOW,
    )

    assert candidate.candidate_id == f"{event.event_id}:remind"
    assert set(candidate.model_dump()) == {"candidate_id", "event", "source_commitment_id", "source_commitment_text", "temporal_context", "decision", "generated_at"}
    assert candidate.source_commitment_id == "commitment_001"


def test_extract_due_supports_clear_leading_and_terminal_expressions():
    engine = TemporalEngine(FixedClock(NOW))

    leading_text, leading_due = engine.extract_due("через 2 минуты проверить чайник")
    trailing_text, trailing_due = engine.extract_due("поставить чайник через 2 минуты")
    tomorrow_text, tomorrow_due = engine.extract_due("проверить окно завтра в 10:30")

    assert leading_text == "проверить чайник"
    assert trailing_text == "поставить чайник"
    assert leading_due.resolved_utc == trailing_due.resolved_utc == NOW + timedelta(minutes=2)
    assert tomorrow_text == "проверить окно"
    assert tomorrow_due.resolved_local.hour == 10
    assert tomorrow_due.resolved_local.minute == 30


def test_extract_due_leaves_unsupported_terminal_language_untouched():
    engine = TemporalEngine(FixedClock(NOW))
    text = "проверить окно завтра утром"

    body, due = engine.extract_due(text)

    assert body == text
    assert due is None
