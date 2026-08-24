from copy import deepcopy
from datetime import datetime, timedelta, timezone

from backend.application.proactive import ProactiveApplicationService
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.runtime.daily_runtime import DailyCycleReceipt
from backend.temporal.proactive import ProactivePolicy
from backend.temporal.proactive_daemon import ProactiveDaemon, request_proactive_wakeup
from backend.temporal.proactive_interaction import ProactiveInteractionStore
from backend.temporal.temporal_engine import FixedClock
from backend.temporal.temporal_runtime import due_aware_cycle_delay
from backend.temporal.reminder_trace import ReminderDeliveryTrace


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
