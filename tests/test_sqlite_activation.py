import json

import pytest

from backend.memory.confirmed_memory_service import (
    ConfirmedMemoryService,
    ExplicitMemoryConfirmation,
)
from backend.memory.memory_models import IdentityCode, SourceType
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore
from backend.memory.sqlite_activation import activate_sqlite_memory
from backend.memory.sqlite_repository import MemorySqliteRepository


def test_activation_migrates_once_creates_backup_and_is_idempotent(tmp_path, canonical_memory):
    source = tmp_path / "memory.json"
    source.write_text(json.dumps(canonical_memory), encoding="utf-8")
    database = tmp_path / "memory.sqlite3"

    first = activate_sqlite_memory(
        json_source=source,
        database_path=database,
        backup_directory=tmp_path / "backups",
    )
    second = activate_sqlite_memory(
        json_source=source,
        database_path=database,
        backup_directory=tmp_path / "backups",
    )

    assert first.migrated is True
    assert first.backup_path is not None and first.backup_path.read_bytes() == source.read_bytes()
    assert second.migrated is False
    assert MemorySqliteRepository(database).read_document().model_dump(mode="json") == canonical_memory


def test_activation_refuses_to_overwrite_divergent_database(tmp_path, canonical_memory):
    source = tmp_path / "memory.json"
    source.write_text(json.dumps(canonical_memory), encoding="utf-8")
    database = tmp_path / "memory.sqlite3"
    activate_sqlite_memory(json_source=source, database_path=database, backup_directory=tmp_path / "backups")
    changed = json.loads(json.dumps(canonical_memory))
    changed["facts"][0]["value"] = "different"
    source.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to overwrite"):
        activate_sqlite_memory(json_source=source, database_path=database, backup_directory=tmp_path / "backups")


def test_invalid_json_source_does_not_change_existing_sqlite_memory(tmp_path, canonical_memory):
    source = tmp_path / "memory.json"
    source.write_text(json.dumps(canonical_memory), encoding="utf-8")
    database = tmp_path / "memory.sqlite3"
    activate_sqlite_memory(json_source=source, database_path=database, backup_directory=tmp_path / "backups")
    original = MemorySqliteRepository(database).read_document().model_dump(mode="json")
    source.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        activate_sqlite_memory(json_source=source, database_path=database, backup_directory=tmp_path / "backups")

    assert MemorySqliteRepository(database).read_document().model_dump(mode="json") == original


def test_sqlite_remains_source_of_truth_after_json_source_changes(tmp_path, canonical_memory):
    source = tmp_path / "memory.json"
    source.write_text(json.dumps(canonical_memory), encoding="utf-8")
    database = tmp_path / "memory.sqlite3"
    activate_sqlite_memory(json_source=source, database_path=database, backup_directory=tmp_path / "backups")
    changed = json.loads(source.read_text(encoding="utf-8"))
    changed["facts"][0]["value"] = "manual JSON change"
    source.write_text(json.dumps(changed), encoding="utf-8")

    document = MemorySqliteRepository(database).read_document()

    assert document is not None
    assert document.facts[0].value == canonical_memory["facts"][0]["value"]


def test_confirmed_memory_audits_and_retrieves_through_sqlite(tmp_path, memory_path):
    json_store = MemoryStore(memory_path)
    source = json_store.read_document()
    repository = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    repository.replace_document(source)
    fact = json_store.get_fact("fact_002").model_copy(
        update={
            "id": "fact_sqlite_confirmed",
            "source": SourceType.EXPLICIT_USER_INPUT,
            "key": "sqlite_preference",
            "value": "local models",
            "source_episode_ids": [],
        }
    )

    ConfirmedMemoryService(repository).confirm(
        ExplicitMemoryConfirmation(confirmed_by=IdentityCode.MISHA, record=fact)
    )

    assert any(item["data"]["id"] == fact.id for item in MemoryRetriever(repository).retrieve("project_masha_home", 20))
    event = repository.list_audit_events()[-1]
    assert event["action"] == "confirmed_memory"
    assert event["payload"]["who"] == "misha"
    assert event["payload"]["record_id"] == fact.id
