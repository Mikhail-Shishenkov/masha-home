"""Transactional local SQLite repository for validated Memory v0.4 documents."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .memory_models import MemoryDocument
from .sqlite_migrations import MIGRATIONS


RECORD_COLLECTIONS = {
    "fact": "facts",
    "decision": "decisions",
    "commitment": "commitments",
    "episode": "episodes",
    "candidate": "memory_candidates",
    "reflection": "reflections",
    "relationship_memory": "relationship_memories",
    "affective_record": "affective_records",
    "continuity_state": "continuity_states",
}


class MemorySqliteRepository:
    """Stores a whole validated document atomically; JSON remains portable."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in MIGRATIONS:
                if migration.version in applied:
                    continue
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in migration.statements:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                        (migration.version, migration.name, self._now()),
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise

    @property
    def data(self) -> dict[str, Any]:
        """Compatibility view for existing read-only retrievers and stores."""
        document = self.read_document()
        if document is None:
            raise ValueError("memory database has not been initialized with a document")
        return document.model_dump(mode="json")

    def replace_document(
        self,
        document: MemoryDocument | dict[str, Any],
        *,
        action: str = "replace_document",
        audit_payload: dict[str, Any] | None = None,
    ) -> None:
        validated = MemoryDocument.model_validate(document)
        payload = validated.model_dump(mode="json")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("DELETE FROM record_projects")
                connection.execute("DELETE FROM memory_records")
                connection.execute("DELETE FROM projects")
                connection.execute("DELETE FROM memory_metadata")

                connection.executemany(
                    "INSERT INTO memory_metadata(key, value) VALUES (?, ?)",
                    [
                        ("schema_version", payload["schema_version"]),
                        ("identity_version", payload["identity_version"]),
                    ],
                )
                for position, project in enumerate(payload["projects"]):
                    connection.execute(
                        """
                        INSERT INTO projects(id, name, status, payload_json, position)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            project["id"],
                            project["name"],
                            project["status"],
                            self._json(project),
                            position,
                        ),
                    )

                for record_type, collection_name in RECORD_COLLECTIONS.items():
                    for position, record in enumerate(payload[collection_name]):
                        connection.execute(
                            """
                            INSERT INTO memory_records(
                                id, record_type, status, visibility, created_at,
                                updated_at, payload_json, position
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                record["id"],
                                record_type,
                                record.get("status"),
                                record.get("visibility", "visible"),
                                self._created_at(record),
                                self._updated_at(record),
                                self._json(record),
                                position,
                            ),
                        )
                        for project_id in record.get("project_ids", []):
                            connection.execute(
                                "INSERT INTO record_projects(record_id, project_id) VALUES (?, ?)",
                                (record["id"], project_id),
                            )

                self._insert_audit_event(
                    connection,
                    action=action,
                    entity_type="memory_document",
                    payload={
                        "schema_version": payload["schema_version"],
                        "record_count": sum(
                            len(payload[collection])
                            for collection in RECORD_COLLECTIONS.values()
                        ),
                        **(audit_payload or {}),
                    },
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def read_document(self) -> MemoryDocument | None:
        with self._connection() as connection:
            metadata = dict(
                connection.execute("SELECT key, value FROM memory_metadata")
            )
            if not metadata:
                return None
            document: dict[str, Any] = {
                "schema_version": metadata["schema_version"],
                "identity_version": metadata["identity_version"],
                "projects": self._read_payloads(connection, "projects"),
            }
            for record_type, collection_name in RECORD_COLLECTIONS.items():
                document[collection_name] = self._read_payloads(
                    connection,
                    "memory_records",
                    "record_type = ?",
                    (record_type,),
                )
        return MemoryDocument.model_validate(document)

    def import_json(self, source_path: str | Path) -> MemoryDocument:
        source = Path(source_path)
        raw = json.loads(source.read_text(encoding="utf-8"))
        document = MemoryDocument.model_validate(raw)
        self.replace_document(document, action="import_json")
        return document

    def export_json(self, destination_path: str | Path) -> MemoryDocument:
        document = self.read_document()
        if document is None:
            raise ValueError("cannot export an empty memory database")
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        self.record_event(
            action="export_json",
            entity_type="memory_document",
            payload={"destination": str(destination)},
        )
        return document

    def backup_to(self, destination_path: str | Path) -> Path:
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == self.database_path.resolve():
            raise ValueError("backup destination must differ from the source database")
        with self._connection() as source, sqlite3.connect(destination) as target:
            source.backup(target)
        self.record_event(
            action="backup_created",
            entity_type="database",
            payload={"destination": str(destination)},
        )
        return destination

    @classmethod
    def restore_to(
        cls,
        backup_path: str | Path,
        destination_path: str | Path,
    ) -> "MemorySqliteRepository":
        """Restore only into a separate database; never overwrites a live store."""
        backup = Path(backup_path)
        destination = Path(destination_path)
        if destination.exists():
            raise FileExistsError("restore destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as source, sqlite3.connect(destination) as target:
            source.backup(target)
        repository = cls(destination)
        repository.record_event(
            action="restored_from_backup",
            entity_type="database",
            payload={"backup": str(backup)},
        )
        return repository

    def record_event(
        self,
        *,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                event_id = self._insert_audit_event(
                    connection,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    payload=payload or {},
                )
                connection.execute("COMMIT")
                return event_id
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def list_audit_events(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY rowid"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "occurred_at": row["occurred_at"],
                "action": row["action"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _read_payloads(
        connection: sqlite3.Connection,
        table: str,
        where: str | None = None,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        query = f"SELECT payload_json FROM {table}"
        if where:
            query += f" WHERE {where}"
        query += " ORDER BY position"
        return [json.loads(row["payload_json"]) for row in connection.execute(query, parameters)]

    def _insert_audit_event(
        self,
        connection: sqlite3.Connection,
        *,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any],
    ) -> str:
        event_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO audit_events(
                id, occurred_at, action, entity_type, entity_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                self._now(),
                action,
                entity_type,
                entity_id,
                self._json(payload),
            ),
        )
        return event_id

    @staticmethod
    def _created_at(record: dict[str, Any]) -> str | None:
        return record.get("created_at") or record.get("started_at") or record.get("occurred_at")

    @staticmethod
    def _updated_at(record: dict[str, Any]) -> str | None:
        return record.get("updated_at") or record.get("created_at") or record.get("started_at")

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
