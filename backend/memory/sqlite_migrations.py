"""Versioned SQLite schema for the local Memory v0.4 store."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SqliteMigration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS = (
    SqliteMigration(
        version=1,
        name="initial_memory_store",
        statements=(
            """
            CREATE TABLE memory_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                position INTEGER NOT NULL UNIQUE
            )
            """,
            """
            CREATE TABLE memory_records (
                id TEXT PRIMARY KEY,
                record_type TEXT NOT NULL,
                status TEXT,
                visibility TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                payload_json TEXT NOT NULL,
                position INTEGER NOT NULL,
                CHECK (record_type IN (
                    'fact', 'decision', 'commitment', 'episode',
                    'candidate', 'reflection', 'relationship_memory',
                    'affective_record', 'continuity_state'
                ))
            )
            """,
            """
            CREATE TABLE record_projects (
                record_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                PRIMARY KEY (record_id, project_id),
                FOREIGN KEY (record_id) REFERENCES memory_records(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id)
                    ON DELETE RESTRICT
            )
            """,
            """
            CREATE TABLE audit_events (
                id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                payload_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_memory_records_type_position ON memory_records(record_type, position)",
            "CREATE INDEX idx_memory_records_visibility ON memory_records(visibility)",
            "CREATE INDEX idx_memory_records_status ON memory_records(status)",
            "CREATE INDEX idx_record_projects_project ON record_projects(project_id, record_id)",
            "CREATE INDEX idx_audit_events_occurred_at ON audit_events(occurred_at)",
        ),
    ),
)
