import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.memory.sqlite_repository import MemorySqliteRepository


def _repository(tmp_path: Path) -> MemorySqliteRepository:
    return MemorySqliteRepository(tmp_path / "memory.sqlite3")


def test_import_read_and_export_preserve_validated_document(
    tmp_path: Path,
    canonical_memory: dict,
):
    source = tmp_path / "source.json"
    exported = tmp_path / "exported.json"
    source.write_text(json.dumps(canonical_memory), encoding="utf-8")
    repository = _repository(tmp_path)

    imported = repository.import_json(source)
    reopened = MemorySqliteRepository(repository.database_path)
    restored = reopened.read_document()
    repository.export_json(exported)

    assert restored is not None
    assert restored.model_dump(mode="json") == imported.model_dump(mode="json")
    assert json.loads(exported.read_text(encoding="utf-8")) == canonical_memory
    assert [event["action"] for event in repository.list_audit_events()] == [
        "import_json",
        "export_json",
    ]


def test_schema_uses_wal_and_enforces_project_foreign_key(tmp_path: Path):
    repository = _repository(tmp_path)

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO record_projects(record_id, project_id) VALUES (?, ?)",
                ("missing_record", "missing_project"),
            )


def test_invalid_replacement_keeps_previous_document(
    tmp_path: Path,
    canonical_memory: dict,
):
    repository = _repository(tmp_path)
    repository.replace_document(canonical_memory)
    invalid = json.loads(json.dumps(canonical_memory))
    invalid["facts"][0]["project_ids"] = ["unknown_project"]

    with pytest.raises(ValidationError):
        repository.replace_document(invalid)

    restored = repository.read_document()
    assert restored is not None
    assert restored.model_dump(mode="json") == canonical_memory


def test_backup_restores_to_a_separate_database(
    tmp_path: Path,
    canonical_memory: dict,
):
    repository = _repository(tmp_path)
    repository.replace_document(canonical_memory)
    backup = repository.backup_to(tmp_path / "backup.sqlite3")

    restored = MemorySqliteRepository.restore_to(
        backup,
        tmp_path / "restored.sqlite3",
    )

    document = restored.read_document()
    assert document is not None
    assert document.model_dump(mode="json") == canonical_memory
    assert any(
        event["action"] == "restored_from_backup"
        for event in restored.list_audit_events()
    )


def test_concurrent_audit_writes_do_not_lose_events(tmp_path: Path):
    repository = _repository(tmp_path)

    with ThreadPoolExecutor(max_workers=4) as executor:
        event_ids = list(
            executor.map(
                lambda index: repository.record_event(
                    action="concurrency_test",
                    entity_type="test",
                    entity_id=str(index),
                    payload={"index": index},
                ),
                range(12),
            )
        )

    events = repository.list_audit_events()
    assert len(event_ids) == len(set(event_ids)) == 12
    assert {event["entity_id"] for event in events} == {
        str(index) for index in range(12)
    }
