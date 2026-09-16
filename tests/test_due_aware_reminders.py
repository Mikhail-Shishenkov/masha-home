from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest

from backend.application.proactive import ProactiveApplicationService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.runtime.daily_runtime import DailyCycleReceipt
from backend.temporal.proactive import ProactivePolicy
from backend.temporal.proactive_daemon import ProactiveDaemon, request_proactive_wakeup
from backend.temporal.proactive_interaction import ProactiveInteractionStore
from backend.temporal.temporal_engine import FixedClock
from backend.temporal.temporal_runtime import due_aware_cycle_delay
from backend.temporal.reminder_trace import ReminderDeliveryTrace


def test_confirmed_reminder_delivers_once_without_model_and_survives_restart(tmp_path, canonical_memory):
    from backend.conversation.conversation_store import ConversationStore
    from backend.conversation.memory_intent import MemoryIntentHandler, MemoryProposalStore
    from backend.memory.confirmed_memory_service import ConfirmedMemoryService
    from backend.llm.model_profiles import ModelProfileStore
    from backend.runtime.daily_runtime import DailyRuntime
    from backend.runtime.safety import AutonomySafetyStore, AutonomySafetyService
    from backend.temporal.temporal_engine import TemporalEngine

    repository = _repository(tmp_path, canonical_memory, NOW + timedelta(days=30))
    clock = FixedClock(NOW)
    engine = TemporalEngine(clock)
    handler = MemoryIntentHandler(
        proposal_store=MemoryProposalStore(tmp_path / "proposals.json"),
        confirmed_memory=ConfirmedMemoryService(repository), temporal_engine=engine,
    )
    preview = handler.propose_timed_commitment_from_resolved_intent(
        subject="Позвонить маме", date="2026-08-25", time="09:00",
        conversation_id="reminder", project_id="project_masha_home",
    )
    pending = handler.proposal_store.current_for_conversation("reminder")
    record_id = pending.record_payload["id"]
    assert "09:00" in preview.response
    assert all(item.id != record_id for item in repository.read_document().commitments)
    handler.handle("Подтверждаю", conversation_id="reminder", project_id="project_masha_home")
    record = next(item for item in repository.read_document().commitments if item.id == record_id)
    assert record.due_at == datetime(2026, 8, 25, 5, tzinfo=timezone.utc)
    assert record.reminder_delivery_mode.value == "explicit_user_reminder"
    router = Mock()
    router.generate.side_effect = AssertionError("explicit reminder must not call a model")
    policy = ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True)
    safety = AutonomySafetyStore(tmp_path / "safety.json")
    safety_control = AutonomySafetyService(store=safety, clock=clock.now_utc)
    def runtime():
        return DailyRuntime(
            history=ConversationStore(tmp_path / "history.json"), temporal_engine=engine,
            repository=repository, identity_kernel=Mock(), router=router,
            model_profiles=ModelProfileStore(tmp_path / "profiles.json"),
            safety_store=safety,
        )
    clock.set(record.due_at - timedelta(seconds=1))
    runtime().run_cycle(policy)
    assert not ProactiveInteractionStore(repository).list()
    clock.set(record.due_at + timedelta(seconds=1))
    safety_control.engage()
    assert runtime().run_cycle(policy).halted_reason == "emergency_stop_engaged"
    assert not ProactiveInteractionStore(repository).list()
    safety_control.release()
    runtime().run_cycle(policy)
    first = ProactiveInteractionStore(repository).list()
    assert len(first) == 1 and first[0]["state"] == "delivered"
    assert first[0]["message_text"] == "Напоминаю: Позвонить маме"
    runtime().run_cycle(policy)
    assert ProactiveInteractionStore(repository).list() == first
    store = ProactiveInteractionStore(repository)
    store.acknowledge(first[0]["event_id"], clock.now_utc())
    runtime().run_cycle(policy)
    assert store.list()[0]["state"] == "acknowledged"
    router.generate.assert_not_called()


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _repository(tmp_path, canonical_memory, due_at, *, explicit=False):
    data = deepcopy(canonical_memory)
    data["commitments"][0]["status"] = "open"
    data["commitments"][0]["due_at"] = due_at.isoformat()
    data["commitments"][0]["completed_at"] = None
    if explicit:
        data["commitments"][0]["reminder_delivery_mode"] = "explicit_user_reminder"
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(data)
    return repository


def test_nearest_due_wakeup_beats_generic_five_minute_cycle(tmp_path, canonical_memory):
    repository = _repository(tmp_path, canonical_memory, NOW + timedelta(minutes=2))

    delay = due_aware_cycle_delay(repository, now=NOW, cadence_seconds=300)

    assert delay == 121


@pytest.mark.parametrize("old_state", ["delivered", "acknowledged", "dismissed"])
def test_delivered_backlog_cannot_starve_later_reminders(tmp_path, canonical_memory, old_state):
    from backend.conversation.conversation_store import ConversationStore
    from backend.llm.model_profiles import ModelProfileStore
    from backend.runtime.daily_runtime import DailyRuntime
    from backend.runtime.safety import AutonomySafetyStore
    from backend.temporal.temporal_engine import TemporalEngine
    from backend.temporal.temporal_runtime import TemporalRuntime

    repository = _repository(tmp_path, canonical_memory, NOW - timedelta(minutes=10), explicit=True)
    data = repository.read_document().model_dump(mode="json")
    template = data["commitments"][0]
    data["commitments"] = [dict(template, id=template["id"] if i == 0 else f"reminder_{i}", due_at=(NOW - timedelta(minutes=10-i)).isoformat()) for i in range(7)]
    repository.replace_document(data)
    engine = TemporalEngine(FixedClock(NOW))
    def runtime():
        return DailyRuntime(
            history=ConversationStore(tmp_path / "history.json"), temporal_engine=engine,
            repository=repository, identity_kernel=Mock(), router=Mock(),
            model_profiles=ModelProfileStore(tmp_path / "profiles.json"),
            safety_store=AutonomySafetyStore(tmp_path / "safety.json"),
        )
    policy = ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True)
    runtime().run_cycle(policy)
    store = ProactiveInteractionStore(repository)
    assert len(store.list()) == 6
    if old_state != "delivered":
        transition = store.acknowledge if old_state == "acknowledged" else store.dismiss
        for row in store.list():
            transition(row["event_id"], NOW)
    runtime().run_cycle(policy)
    delivered = ProactiveInteractionStore(repository).list()
    assert len(delivered) == 7
    assert sum(row["state"] == old_state for row in delivered) == (7 if old_state == "delivered" else 6)
    assert any(row["state"] == "delivered" for row in delivered)
    runtime().run_cycle(policy)
    assert ProactiveInteractionStore(repository).list() == delivered
    assert len(TemporalRuntime(repository, engine).recover().events) == 6


def test_future_due_does_not_run_early_and_runs_just_after_due(tmp_path, canonical_memory):
    due_at = NOW + timedelta(minutes=2)
    repository = _repository(tmp_path, canonical_memory, due_at)
    clock = FixedClock(NOW)
    calls = []

    class Runtime:
        def __init__(self):
            self.repository = repository

        def run_cycle(self, _policy):
            calls.append(clock.now_utc())
            return DailyCycleReceipt(
                cycle_id=f"cycle-{len(calls)}",
                started_at=clock.now_utc(),
                finished_at=clock.now_utc(),
                model_profile="test",
            )

    policy = ProactivePolicy(runtime_mode="background", cycle_interval_seconds=300)
    service = ProactiveApplicationService(
        store=ProactiveInteractionStore(repository),
        clock=clock,
        runtime=Runtime(),
        policy_store=type("PolicyStore", (), {"load": lambda _self: policy})(),
    )

    service.refresh()
    clock.set(due_at)
    service.refresh()
    assert len(calls) == 1
    clock.set(due_at + timedelta(seconds=1))
    service.refresh()
    assert calls == [NOW, due_at + timedelta(seconds=1)]


def test_wakeup_signal_interrupts_existing_daemon_wait_without_database_poll(tmp_path):
    sleeps = []
    daemon = ProactiveDaemon(tmp_path)

    def sleep(seconds):
        sleeps.append(seconds)
        request_proactive_wakeup(tmp_path)

    daemon.sleep = sleep
    daemon._wait(300)

    assert sleeps == [1]
    assert daemon.wake_path.exists()


def test_wakeup_arriving_during_cycle_is_not_lost_before_wait(tmp_path):
    daemon = ProactiveDaemon(tmp_path, sleep=lambda _seconds: (_ for _ in ()).throw(
        AssertionError("already signalled wait must not sleep")
    ))
    revision_before_cycle = daemon._wake_revision()
    request_proactive_wakeup(tmp_path)

    daemon._wait(300, since_revision=revision_before_cycle)


def test_recovery_hold_suppresses_home_fallback_and_records_reason(tmp_path, canonical_memory):
    repository = _repository(
        tmp_path, canonical_memory, NOW - timedelta(minutes=1), explicit=True,
    )
    clock = FixedClock(NOW)
    calls = []
    trace = ReminderDeliveryTrace(tmp_path / "reminder-trace.json")

    class Runtime:
        def __init__(self):
            self.repository = repository

        def run_cycle(self, _policy):
            calls.append(True)
            raise AssertionError("recovery HOLD must suppress runtime")

    service = ProactiveApplicationService(
        store=ProactiveInteractionStore(repository),
        clock=clock,
        runtime=Runtime(),
        policy_store=type("PolicyStore", (), {"load": lambda _self: ProactivePolicy(
            enabled=True, proactive_level=1, allow_commitment_reminders=True,
            runtime_mode="background",
        )})(),
        hold_checker=lambda: True,
        trace=trace,
    )

    assert service.refresh().items == ()
    assert calls == []
    assert trace.list()[-1]["reason"] == "recovery_hold"


def test_recent_daemon_start_prevents_parallel_home_fallback(tmp_path, canonical_memory):
    repository = _repository(tmp_path, canonical_memory, NOW - timedelta(minutes=1))
    clock = FixedClock(NOW)
    calls = []
    daemon = ProactiveDaemon(tmp_path)
    daemon._status(
        "starting", result="starting", reason="safety_released",
        error=None, interval=None,
    )

    class Runtime:
        def __init__(self):
            self.repository = repository

        def run_cycle(self, _policy):
            calls.append(True)

    service = ProactiveApplicationService(
        store=ProactiveInteractionStore(repository),
        clock=clock,
        runtime=Runtime(),
        daemon=daemon,
        policy_store=type("PolicyStore", (), {"load": lambda _self: ProactivePolicy(
            enabled=True, proactive_level=1, allow_commitment_reminders=True,
            runtime_mode="background",
        )})(),
    )

    assert service.refresh().items == ()
    assert calls == []
