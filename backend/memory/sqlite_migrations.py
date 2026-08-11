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
    SqliteMigration(
        version=2,
        name="temporal_events",
        statements=(
            """CREATE TABLE temporal_events (
                id TEXT PRIMARY KEY, event_type TEXT NOT NULL, source_type TEXT NOT NULL,
                source_id TEXT NOT NULL, due_at TEXT NOT NULL, created_at TEXT NOT NULL,
                status TEXT NOT NULL, occurred_at TEXT, recovery_at TEXT,
                identity_version TEXT NOT NULL, UNIQUE(event_type, source_type, source_id, due_at),
                FOREIGN KEY(source_id) REFERENCES memory_records(id)
            )""",
            "CREATE INDEX idx_temporal_events_status_due ON temporal_events(status, due_at)",
        ),
    ),
    SqliteMigration(
        version=3,
        name="proactive_interactions",
        statements=(
            """CREATE TABLE proactive_interactions (
                event_id TEXT PRIMARY KEY,
                decision TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('candidate','delivered','acknowledged','dismissed')),
                created_at TEXT NOT NULL,
                delivered_at TEXT,
                acknowledged_at TEXT,
                dismissed_at TEXT,
                message_text TEXT,
                FOREIGN KEY(event_id) REFERENCES temporal_events(id)
            )""",
            "CREATE INDEX idx_proactive_interactions_state ON proactive_interactions(state)",
        ),
    ),
    SqliteMigration(
        version=4,
        name="proactive_events",
        statements=(
            """CREATE TABLE proactive_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL CHECK (event_type IN ('commitment_reminder', 'check_in')),
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                valid_until TEXT,
                state TEXT NOT NULL CHECK (state IN (
                    'detected', 'candidate', 'delivered', 'acknowledged',
                    'dismissed', 'resolved', 'expired'
                )),
                payload_json TEXT NOT NULL,
                delivered_at TEXT,
                acknowledged_at TEXT,
                resolved_at TEXT,
                dismissed_at TEXT
            )""",
            "CREATE INDEX idx_proactive_events_state ON proactive_events(state)",
            "CREATE INDEX idx_proactive_events_source ON proactive_events(source_type, source_id)",
            "CREATE INDEX idx_proactive_events_valid_until ON proactive_events(valid_until)",
        ),
    ),
    SqliteMigration(
        version=5,
        name="dual_source_proactive_interactions",
        statements=(
            "ALTER TABLE proactive_interactions RENAME TO proactive_interactions_v3",
            """CREATE TABLE proactive_interactions (
                event_id TEXT PRIMARY KEY,
                temporal_event_id TEXT UNIQUE,
                proactive_event_id TEXT UNIQUE,
                decision TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('candidate','delivered','acknowledged','dismissed','resolved','expired')),
                created_at TEXT NOT NULL,
                delivered_at TEXT,
                acknowledged_at TEXT,
                dismissed_at TEXT,
                resolved_at TEXT,
                message_text TEXT,
                CHECK ((temporal_event_id IS NOT NULL) != (proactive_event_id IS NOT NULL)),
                FOREIGN KEY(temporal_event_id) REFERENCES temporal_events(id),
                FOREIGN KEY(proactive_event_id) REFERENCES proactive_events(event_id)
            )""",
            """INSERT INTO proactive_interactions(
                event_id, temporal_event_id, proactive_event_id, decision, state,
                created_at, delivered_at, acknowledged_at, dismissed_at, message_text
            ) SELECT event_id, event_id, NULL, decision, state, created_at,
                delivered_at, acknowledged_at, dismissed_at, message_text
              FROM proactive_interactions_v3""",
            "DROP TABLE proactive_interactions_v3",
            "CREATE INDEX idx_proactive_interactions_state ON proactive_interactions(state)",
        ),
    ),
)
