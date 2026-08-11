"""Deterministic local recovery of overdue Commitment events.

This module deliberately has no scheduler, message delivery, LLM call, or
memory mutation.  It persists only the existing temporal event rows.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .temporal_models import CommitmentDueEvent, TemporalEventContext


EVENT_TYPE = "commitment_due"
SOURCE_TYPE = "commitment"


def commitment_due_event_id(commitment_id: str, due_at: datetime) -> str:
    """Return the stable ID for one commitment/deadline occurrence."""
    due_utc = due_at.astimezone(timezone.utc).isoformat()
    key = f"temporal-event:v1|{EVENT_TYPE}|{SOURCE_TYPE}|{commitment_id}|{due_utc}"
    return "tev1_" + hashlib.sha256(key.encode("utf-8")).hexdigest()


class TemporalRuntime:
    """Recover overdue Commitment events through the existing SQLite table."""

    def __init__(self, repository, engine, *, context_limit: int = 6):
        self.repository = repository
        self.engine = engine
        self.context_limit = context_limit

    def recover(self) -> TemporalEventContext:
        """Return deterministic overdue events, idempotently persisting detection."""
        document = self.repository.read_document()
        now = self.engine.clock.now_utc().astimezone(timezone.utc)
        if document is None:
            return TemporalEventContext(generated_at=now, events=())

        eligible = [
            commitment
            for commitment in document.commitments
            if self.engine.commitment_status(commitment) == "overdue"
        ]
        events = [self._recover_commitment(commitment, now, document.identity_version) for commitment in eligible]
        events.sort(key=lambda event: (event.due_at, event.event_id))
        return TemporalEventContext(generated_at=now, events=tuple(events[: self.context_limit]))

    def _recover_commitment(self, commitment, now: datetime, identity_version: str) -> CommitmentDueEvent:
        assert commitment.due_at is not None
        due_at = commitment.due_at.astimezone(timezone.utc)
        event_id = commitment_due_event_id(commitment.id, due_at)
        due_text = due_at.isoformat()
        with self.repository._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT id, due_at, created_at, status
                    FROM temporal_events
                    WHERE event_type = ? AND source_type = ? AND source_id = ? AND due_at = ?
                    """,
                    (EVENT_TYPE, SOURCE_TYPE, commitment.id, due_text),
                ).fetchone()
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO temporal_events(
                            id, event_type, source_type, source_id, due_at, created_at,
                            status, occurred_at, recovery_at, identity_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            EVENT_TYPE,
                            SOURCE_TYPE,
                            commitment.id,
                            due_text,
                            now.isoformat(),
                            "overdue",
                            due_text,
                            now.isoformat(),
                            identity_version,
                        ),
                    )
                    row = {"id": event_id, "due_at": due_text, "created_at": now.isoformat(), "status": "overdue"}
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return CommitmentDueEvent(
            event_id=str(row["id"]),
            source_commitment_id=commitment.id,
            due_at=datetime.fromisoformat(row["due_at"]),
            detected_at=datetime.fromisoformat(row["created_at"]),
            status=str(row["status"]),
        )
