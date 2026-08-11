import sqlite3
from datetime import datetime, timedelta, timezone

from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_router import ModelRouter
from backend.memory.sqlite_migrations import MIGRATIONS
from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.proactive_events import ProactiveEvent, ProactiveEventState, ProactiveEventStore, ProactiveEventType, check_in_event_id
from backend.temporal.proactive import ProactivePolicy, ProactivePolicyStore
from backend.temporal.proactive_interaction import ProactiveInteractionService, ProactiveInteractionStore
from backend.temporal.temporal_models import CheckInCandidate


ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def _candidate(repo, key="anchor"):
    store = ProactiveEventStore(repo)
    event = store.create(ProactiveEvent(event_id=check_in_event_id(key), event_type=ProactiveEventType.CHECK_IN, source_type="absence", source_id=key, created_at=NOW, detected_at=NOW, payload={"absence_seconds": 3600, "anchor_created_at": (NOW-timedelta(hours=1)).isoformat()}))
    store.update_state(event.event_id, ProactiveEventState.CANDIDATE, NOW)
    return CheckInCandidate(event_id=event.event_id, absence_duration_seconds=3600, last_message_at=NOW-timedelta(hours=1), current_local_time=NOW, proactive_level=2)


def test_checkin_formulates_once_uses_active_profile_and_persists_restart(tmp_path, canonical_memory):
    repo = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repo.replace_document(canonical_memory)
    before = repo.read_document().model_dump(mode="json")
    candidate = _candidate(repo)
    provider = FakeProvider(provider_id="ollama-local", response_text="Миша, давно тебя не было. Как ты там?")
    profiles = ModelProfileStore(tmp_path / "models.json")
    profiles.set_active_profile("fast")
    service = ProactiveInteractionService(store=ProactiveInteractionStore(repo), identity_kernel=IdentityKernel(IdentityStore(ROOT/'identity'/'masha.identity.json')), router=ModelRouter([provider]), model_profiles=profiles)

    first = service.formulate(candidate)
    request = provider.last_request
    provider.last_request = None
    second = service.formulate(candidate)

    assert first["state"] == second["state"] == "delivered"
    assert provider.last_request is None
    assert request.execution_model_id == "qwen3.5:4b"
    assert request.identity_context == service.identity_kernel.build_context()
    assert "memory_context" not in request.private_context
    assert "не диагноз" in request.messages[0].content
    assert "не придумывай причины отсутствия" in request.messages[0].content
    assert ProactiveEventStore(MemorySqliteRepository(repo.database_path)).get(candidate.event_id).state is ProactiveEventState.DELIVERED
    assert repo.read_document().model_dump(mode="json") == before

    resolved = service.store.resolve_check_ins_for_user_message(NOW + timedelta(seconds=1))
    assert resolved[0]["state"] == "resolved"
    assert ProactiveEventStore(repo).get(candidate.event_id).state is ProactiveEventState.RESOLVED


def test_model_switch_changes_only_proactive_execution_model(tmp_path, canonical_memory):
    repo = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repo.replace_document(canonical_memory)
    memory_before = repo.read_document().model_dump(mode="json")
    profiles = ModelProfileStore(tmp_path / "models.json")
    policy_store = ProactivePolicyStore(tmp_path / "proactive-policy.json")
    policy = policy_store.save(ProactivePolicy(enabled=True, proactive_level=2, allow_checkins=True, daily_message_limit=2))
    identity = IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json"))
    identity_before = identity.build_context()
    provider = FakeProvider(provider_id="ollama-local", response_text="Короткий тёплый check-in")
    service = ProactiveInteractionService(store=ProactiveInteractionStore(repo), identity_kernel=identity, router=ModelRouter([provider]), model_profiles=profiles)

    first = _candidate(repo, "primary-anchor")
    service.formulate(first)
    assert provider.last_request.execution_model_id == "qwen3.5:9b"
    first_event = ProactiveEventStore(repo).get(first.event_id)

    profiles.set_active_profile("fast")
    second = _candidate(repo, "fast-anchor")
    service.formulate(second)

    assert provider.last_request.execution_model_id == "qwen3.5:4b"
    assert ProactiveEventStore(repo).get(first.event_id) == first_event
    assert policy_store.load() == policy
    assert identity.build_context() == identity_before
    assert repo.read_document().model_dump(mode="json") == memory_before


def test_v5_migrates_existing_reminder_interaction(tmp_path):
    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT NOT NULL)")
    for migration in MIGRATIONS[:3]:
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute("INSERT INTO schema_migrations VALUES (?,?,?)", (migration.version, migration.name, NOW.isoformat()))
    connection.execute("INSERT INTO memory_records(id,record_type,visibility,payload_json,position) VALUES ('c','commitment','visible','{}',0)")
    connection.execute("INSERT INTO temporal_events(id,event_type,source_type,source_id,due_at,created_at,status,identity_version) VALUES ('t','commitment_due','commitment','c',?,?,?,?)", (NOW.isoformat(),NOW.isoformat(),'overdue','masha-0.1'))
    connection.execute("INSERT INTO proactive_interactions(event_id,decision,state,created_at) VALUES ('t','remind','delivered',?)", (NOW.isoformat(),))
    connection.commit(); connection.close()

    repo = MemorySqliteRepository(path)
    row = ProactiveInteractionStore(repo).get("t")
    assert row["temporal_event_id"] == "t" and row["proactive_event_id"] is None

    with repo._connection() as c:
        columns = {row[1] for row in c.execute("PRAGMA table_info(proactive_interactions)")}
    assert {"temporal_event_id", "proactive_event_id"} <= columns
