from datetime import datetime, timedelta, timezone

from backend.conversation.conversation_models import ConversationRole
from backend.conversation.conversation_store import ConversationStore
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_router import ModelRouter
from backend.temporal.checkin_detection import CheckInDetector
from backend.temporal.proactive import ProactivePolicy
from backend.temporal.proactive_events import ProactiveEventStore, check_in_event_id
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.proactive_runtime import ControlledProactiveRuntime


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


START = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def _append(store, monkeypatch, when, conversation_id, role=ConversationRole.USER):
    monkeypatch.setattr(ConversationStore, "_now", staticmethod(lambda: when))
    return store.append(conversation_id, role, "message")


def test_latest_message_is_global_and_restart_safe(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path / "history.json")
    first = store.create()
    first_message = _append(store, monkeypatch, START + timedelta(minutes=3), first.id)
    second = store.create()  # Newer conversation does not hide an actual message.
    assert store.latest_message() == first_message
    second_message = _append(store, monkeypatch, START + timedelta(minutes=5), second.id)
    assert store.latest_message() == second_message
    reopened = ConversationStore(store.file_path)
    assert reopened.latest_message() is not None
    assert reopened.latest_message().created_at == second_message.created_at


def test_latest_message_returns_none_for_empty_history(tmp_path):
    assert ConversationStore(tmp_path / "history.json").latest_message() is None


def test_checkin_detection_uses_global_anchor_and_is_idempotent(tmp_path, monkeypatch):
    history = ConversationStore(tmp_path / "history.json")
    first = history.create()
    old = _append(history, monkeypatch, START, first.id)
    second = history.create()
    anchor = _append(history, monkeypatch, START + timedelta(minutes=5), second.id)
    assert anchor.id != old.id
    repo = MemorySqliteRepository(tmp_path / "events.sqlite3")
    detector = CheckInDetector(history, TemporalEngine(FixedClock(START + timedelta(hours=2))), ProactiveEventStore(repo))
    policy = ProactivePolicy(absence_threshold_seconds=60)

    first_event = detector.detect(policy)
    second_event = detector.detect(policy)

    assert first_event is not None
    assert first_event.event_id == second_event.event_id == check_in_event_id(anchor.id)
    assert first_event.source_id == anchor.id
    assert len(ProactiveEventStore(MemorySqliteRepository(repo.database_path)).find_by_source("absence", anchor.id)) == 1


def test_checkin_detection_requires_strictly_greater_than_threshold(tmp_path, monkeypatch):
    history = ConversationStore(tmp_path / "history.json")
    conversation = history.create()
    _append(history, monkeypatch, START, conversation.id)
    detector = CheckInDetector(
        history,
        TemporalEngine(FixedClock(START + timedelta(seconds=60))),
        ProactiveEventStore(MemorySqliteRepository(tmp_path / "events.sqlite3")),
    )

    assert detector.detect(ProactivePolicy(absence_threshold_seconds=60)) is None


def test_controlled_cycle_persists_deterministic_decision_trace_without_duplicates(tmp_path, monkeypatch, canonical_memory):
    history = ConversationStore(tmp_path / "history.json")
    conversation = history.create()
    _append(history, monkeypatch, START, conversation.id)
    repo = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repo.replace_document(canonical_memory)
    provider = FakeProvider(provider_id="ollama-local", response_text="Миша, я рядом. Напиши, если захочется.")
    runtime = ControlledProactiveRuntime(
        history=history,
        temporal_engine=TemporalEngine(FixedClock(START + timedelta(hours=2))),
        repository=repo,
        identity_kernel=IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json")),
        router=ModelRouter([provider]),
        model_profiles=ModelProfileStore(tmp_path / "models.json"),
    )
    policy = ProactivePolicy(enabled=True, proactive_level=2, allow_checkins=True, absence_threshold_seconds=60, daily_message_limit=2)

    first = runtime.run_checkin_cycle(policy)
    provider.last_request = None
    second = runtime.run_checkin_cycle(policy)
    third = runtime.run_checkin_cycle(policy)
    traces = [item for item in repo.list_audit_events() if item["action"] == "proactive_decision"]

    assert first.decision == "delivered"
    assert second.decision == third.decision == "suppress"
    assert second.reason.startswith("terminal_or_delivered")
    assert provider.last_request is None
    assert [item["payload"]["reason"] for item in traces] == ["authorised", second.reason]
