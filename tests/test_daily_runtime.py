from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.conversation.conversation_models import ConversationRole
from backend.conversation.conversation_store import ConversationStore
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_router import ModelRouter
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.memory.memory_models import MemoryDocument, ReminderDeliveryMode
from backend.runtime.daily_runtime import DailyRuntime, DailyRuntimeJournal
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.temporal.proactive import ProactivePolicy, ProactivePolicyStore
from backend.temporal.proactive_daemon import ProactiveDaemon
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.reminder_trace import ReminderDeliveryTrace


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 11, 15, tzinfo=timezone.utc)


class CountingProvider(FakeProvider):
    calls: int = 0

    def generate(self, request):
        self.calls += 1
        return super().generate(request)


def _runtime(tmp_path, canonical_memory, monkeypatch, *, overdue: bool, explicit: bool = False, trace=None):
    repo = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    document = MemoryDocument.model_validate(canonical_memory)
    if overdue:
        commitment = document.commitments[0].model_copy(update={
            "text": "Отправить отчёт", "due_at": NOW - timedelta(hours=1),
            "reminder_delivery_mode": (
                ReminderDeliveryMode.EXPLICIT_USER_REMINDER
                if explicit else ReminderDeliveryMode.POLICY_CONTROLLED
            ),
        })
        document = document.model_copy(update={"commitments": [commitment]})
    repo.replace_document(document)
    history = ConversationStore(tmp_path / "history.json")
    monkeypatch.setattr(ConversationStore, "_now", staticmethod(lambda: NOW - timedelta(hours=3)))
    conversation = history.create()
    history.append(conversation.id, ConversationRole.USER, "Я здесь")
    provider = CountingProvider(provider_id="ollama-local", response_text="Миша, я рядом.")
    profiles = ModelProfileStore(tmp_path / "models.json")
    runtime = DailyRuntime(
        history=history,
        temporal_engine=TemporalEngine(FixedClock(NOW)),
        repository=repo,
        identity_kernel=IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json")),
        router=ModelRouter([provider]),
        model_profiles=profiles,
        safety_store=AutonomySafetyStore(tmp_path / "safety.json"),
        trace=trace,
    )
    return runtime, repo, provider, profiles


def test_explicit_user_reminder_delivers_inside_quiet_hours_with_trace(tmp_path, canonical_memory, monkeypatch):
    trace = ReminderDeliveryTrace(tmp_path / "reminder-trace.json")
    runtime, _, provider, _ = _runtime(
        tmp_path, canonical_memory, monkeypatch, overdue=True, explicit=True, trace=trace,
    )
    policy = ProactivePolicy(
        enabled=True, proactive_level=2, allow_commitment_reminders=True,
        allow_checkins=True, quiet_hours_start=datetime.min.time().replace(hour=19),
        quiet_hours_end=datetime.min.time().replace(hour=20),
        daily_message_limit=0, maximum_reminders=0, cooldown_seconds=86_400,
        absence_threshold_seconds=60,
    )

    receipt = runtime.run_cycle(policy)

    reminder = next(item for item in receipt.items if item.kind == "reminder")
    assert (reminder.state, reminder.reason) == ("delivered", "explicit_user_reminder")
    assert provider.calls == 1
    decision = next(row for row in trace.list() if row["stage"] == "reminder_evaluated")
    assert decision["decision"] == "deliver"
    assert decision["reason"] == "explicit_user_reminder"
    assert decision["due_at"] is not None


def test_unsolicited_checkin_and_policy_reminder_stay_suppressed_in_quiet_hours(tmp_path, canonical_memory, monkeypatch):
    trace = ReminderDeliveryTrace(tmp_path / "reminder-trace.json")
    policy = ProactivePolicy(
        enabled=True, proactive_level=2, allow_commitment_reminders=True,
        allow_checkins=True, quiet_hours_start=datetime.min.time().replace(hour=19),
        quiet_hours_end=datetime.min.time().replace(hour=20),
        daily_message_limit=3, maximum_reminders=3, cooldown_seconds=0,
        absence_threshold_seconds=60,
    )
    reminder_runtime, _, reminder_provider, _ = _runtime(
        tmp_path / "reminder", canonical_memory, monkeypatch, overdue=True, trace=trace,
    )
    checkin_runtime, _, checkin_provider, _ = _runtime(
        tmp_path / "checkin", canonical_memory, monkeypatch, overdue=False,
    )

    reminder_receipt = reminder_runtime.run_cycle(policy)
    checkin_receipt = checkin_runtime.run_cycle(policy)

    assert reminder_receipt.items[0].reason == "quiet_hours"
    assert checkin_receipt.items[0].reason == "quiet_hours"
    assert reminder_provider.calls == checkin_provider.calls == 0
    decision = next(row for row in trace.list() if row["stage"] == "reminder_evaluated")
    assert (decision["decision"], decision["reason"]) == ("suppress", "quiet_hours")


def test_explicit_user_reminder_ignores_existing_daily_count_and_cooldown(tmp_path, canonical_memory, monkeypatch):
    runtime, _, provider, _ = _runtime(
        tmp_path, canonical_memory, monkeypatch, overdue=True, explicit=True,
    )
    runtime.controlled.interaction_store.delivery_stats = lambda _now: (99, NOW - timedelta(seconds=1))
    policy = ProactivePolicy(
        enabled=True, proactive_level=1, allow_commitment_reminders=True,
        daily_message_limit=1, maximum_reminders=1, cooldown_seconds=86_400,
    )

    receipt = runtime.run_cycle(policy)

    assert receipt.items[0].state == "delivered"
    assert receipt.items[0].reason == "explicit_user_reminder"
    assert provider.calls == 1


def test_explicit_user_reminder_still_respects_emergency_stop(tmp_path, canonical_memory, monkeypatch):
    trace = ReminderDeliveryTrace(tmp_path / "reminder-trace.json")
    runtime, _, provider, _ = _runtime(
        tmp_path, canonical_memory, monkeypatch, overdue=True, explicit=True, trace=trace,
    )
    AutonomySafetyService(store=runtime.safety_store, clock=lambda: NOW).engage()

    receipt = runtime.run_cycle(ProactivePolicy(
        enabled=True, proactive_level=1, allow_commitment_reminders=True,
    ))

    assert receipt.halted_reason == "emergency_stop_engaged"
    assert provider.calls == 0
    assert trace.list()[-1]["reason"] == "emergency_stop_engaged"


def test_daily_cycle_prioritises_reminder_and_suppresses_checkin(tmp_path, canonical_memory, monkeypatch):
    runtime, repo, provider, _ = _runtime(tmp_path, canonical_memory, monkeypatch, overdue=True)
    before = repo.read_document().model_dump(mode="json")
    policy = ProactivePolicy(enabled=True, proactive_level=2, allow_commitment_reminders=True, allow_checkins=True, maximum_reminders=3, daily_message_limit=3, cooldown_seconds=0, absence_threshold_seconds=60)

    receipt = runtime.run_cycle(policy)

    assert [(item.kind, item.state, item.reason) for item in receipt.items] == [
        ("reminder", "delivered", "authorised"),
        ("check_in", "suppress", "higher_priority_reminder"),
    ]
    assert receipt.delivered_count == 1
    assert provider.calls == 1
    assert repo.read_document().model_dump(mode="json") == before


def test_one_heartbeat_delivers_at_most_one_message(tmp_path, canonical_memory, monkeypatch):
    runtime, repo, provider, _ = _runtime(tmp_path, canonical_memory, monkeypatch, overdue=True)
    document = repo.read_document()
    second = document.commitments[0].model_copy(update={"id": "commitment_002", "text": "Купить билеты", "due_at": NOW - timedelta(hours=2)})
    repo.replace_document(document.model_copy(update={"commitments": [document.commitments[0], second]}))
    policy = ProactivePolicy(enabled=True, proactive_level=2, allow_commitment_reminders=True, allow_checkins=True, maximum_reminders=3, daily_message_limit=3, cooldown_seconds=0, absence_threshold_seconds=60)

    receipt = runtime.run_cycle(policy)

    reminder_items = [item for item in receipt.items if item.kind == "reminder"]
    assert [item.state for item in reminder_items] == ["delivered", "suppressed"]
    assert reminder_items[1].reason == "cycle_delivery_limit"
    assert provider.calls == 1
    assert receipt.delivered_count == 1


def test_daily_cycle_delivers_checkin_when_no_reminder_exists(tmp_path, canonical_memory, monkeypatch):
    runtime, _, provider, _ = _runtime(tmp_path, canonical_memory, monkeypatch, overdue=False)
    policy = ProactivePolicy(enabled=True, proactive_level=2, allow_checkins=True, daily_message_limit=2, cooldown_seconds=0, absence_threshold_seconds=60)

    receipt = runtime.run_cycle(policy)

    assert len(receipt.items) == 1
    assert receipt.items[0].kind == "check_in"
    assert receipt.items[0].state == "delivered"
    assert provider.calls == 1


def test_daily_cycle_restart_is_idempotent_and_does_not_call_model_twice(tmp_path, canonical_memory, monkeypatch):
    runtime, repo, provider, profiles = _runtime(
        tmp_path, canonical_memory, monkeypatch, overdue=True, explicit=True,
    )
    policy = ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True, maximum_reminders=3, daily_message_limit=3, cooldown_seconds=0)
    first = runtime.run_cycle(policy)
    restarted = DailyRuntime(
        history=runtime.controlled.history,
        temporal_engine=runtime.temporal_engine,
        repository=MemorySqliteRepository(repo.database_path),
        identity_kernel=runtime.controlled.interactions.identity_kernel,
        router=runtime.controlled.interactions.router,
        model_profiles=profiles,
        safety_store=runtime.safety_store,
    )
    second = restarted.run_cycle(policy)

    assert first.delivered_count == 1
    assert second.delivered_count == 0
    assert second.items[0].reason == "terminal_or_delivered:delivered"
    assert provider.calls == 1


def test_disabled_policy_never_calls_model(tmp_path, canonical_memory, monkeypatch):
    runtime, _, provider, _ = _runtime(tmp_path, canonical_memory, monkeypatch, overdue=True)
    receipt = runtime.run_cycle(ProactivePolicy())
    assert receipt.delivered_count == 0
    assert all(item.decision == "suppress" for item in receipt.items)
    assert provider.calls == 0


def test_emergency_stop_suppresses_whole_cycle_without_domain_mutation(tmp_path, canonical_memory, monkeypatch):
    runtime, repo, provider, _ = _runtime(tmp_path, canonical_memory, monkeypatch, overdue=True)
    before = repo.read_document().model_dump(mode="json")
    AutonomySafetyService(store=runtime.safety_store, clock=lambda: NOW).engage()

    receipt = runtime.run_cycle(
        ProactivePolicy(
            enabled=True,
            proactive_level=2,
            allow_commitment_reminders=True,
            allow_checkins=True,
        )
    )

    assert receipt.result == "suppress"
    assert receipt.reason == "emergency_stop_engaged"
    assert receipt.items == ()
    assert provider.calls == 0
    assert repo.read_document().model_dump(mode="json") == before


def test_local_model_failure_keeps_explainable_checkin_candidate(tmp_path, canonical_memory, monkeypatch):
    runtime, _, _, _ = _runtime(tmp_path, canonical_memory, monkeypatch, overdue=False)
    runtime.controlled.interactions.router = ModelRouter([FakeProvider(provider_id="ollama-local", available=False)])
    policy = ProactivePolicy(enabled=True, proactive_level=2, allow_checkins=True, daily_message_limit=2, cooldown_seconds=0, absence_threshold_seconds=60)

    receipt = runtime.run_cycle(policy)

    assert receipt.result == "suppress"
    assert receipt.reason == "local_model_unavailable"
    assert receipt.items[0].state == "candidate"


def test_daily_runtime_journal_is_bounded_and_excludes_message_text(tmp_path):
    journal = DailyRuntimeJournal(tmp_path / "receipts.json", limit=2)
    from backend.runtime.daily_runtime import DailyCycleReceipt

    for index in range(3):
        journal.append(DailyCycleReceipt(cycle_id=str(index), started_at=NOW, finished_at=NOW, model_profile="primary"))

    assert [item.cycle_id for item in journal.list()] == ["1", "2"]
    assert "message_text" not in journal.path.read_text(encoding="utf-8")


def test_background_daemon_uses_unified_cycle_for_reminder(tmp_path, canonical_memory, monkeypatch):
    runtime, repo, provider, profiles = _runtime(tmp_path, canonical_memory, monkeypatch, overdue=True)
    policy = ProactivePolicy(enabled=True, proactive_level=1, allow_commitment_reminders=True, maximum_reminders=1, daily_message_limit=1, cooldown_seconds=0, runtime_mode="background", cycle_interval_seconds=10)
    ProactivePolicyStore(profiles.path.parent / "proactive-policy.json").save(policy)
    service = SimpleNamespace(
        model_profiles=profiles,
        history=runtime.controlled.history,
        temporal_engine=runtime.temporal_engine,
        memory_retriever=SimpleNamespace(memory_store=repo),
        identity_kernel=runtime.controlled.interactions.identity_kernel,
        router=runtime.controlled.interactions.router,
    )
    monkeypatch.setattr("backend.conversation.cli.build_service", lambda project_root: service)

    daemon = ProactiveDaemon(tmp_path, sleep=lambda _: None)
    daemon.run(max_cycles=1)

    assert provider.calls == 1
    assert daemon.status()["last_result"] == "delivered"
    assert daemon.journal.latest().delivered_count == 1
