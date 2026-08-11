"""Persistent proactive-event lifecycle, deliberately separate from Memory."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProactiveEventType(str, Enum):
    COMMITMENT_REMINDER = "commitment_reminder"
    CHECK_IN = "check_in"


class ProactiveEventState(str, Enum):
    DETECTED = "detected"
    CANDIDATE = "candidate"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"
    EXPIRED = "expired"


TERMINAL_STATES = {
    ProactiveEventState.ACKNOWLEDGED,
    ProactiveEventState.DISMISSED,
    ProactiveEventState.RESOLVED,
    ProactiveEventState.EXPIRED,
}


class ProactiveEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    event_type: ProactiveEventType
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    created_at: datetime
    detected_at: datetime
    valid_until: datetime | None = None
    state: ProactiveEventState = ProactiveEventState.DETECTED
    payload: dict[str, Any] = Field(default_factory=dict)
    delivered_at: datetime | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    dismissed_at: datetime | None = None


def commitment_reminder_event_id(commitment_id: str, due_at: datetime) -> str:
    return _event_id("pre1", "commitment_reminder", commitment_id, due_at)


def check_in_event_id(absence_anchor_id: str) -> str:
    return _event_id("chk1", "check_in", absence_anchor_id)


def _event_id(prefix: str, event_type: str, source_id: str, marker: datetime | None = None) -> str:
    value = f"proactive-event:v1|{event_type}|{source_id}"
    if marker is not None:
        value += f"|{marker.astimezone(timezone.utc).isoformat()}"
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


class ProactiveEventStore:
    """SQLite lifecycle store; it makes no policy, model, or memory decision."""

    def __init__(self, repository):
        self.repository = repository

    def create(self, event: ProactiveEvent) -> ProactiveEvent:
        with self.repository._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                inserted = connection.execute(
                    """INSERT OR IGNORE INTO proactive_events(
                        event_id,event_type,source_type,source_id,created_at,detected_at,
                        valid_until,state,payload_json,delivered_at,acknowledged_at,resolved_at,dismissed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    self._values(event),
                )
                row = connection.execute("SELECT * FROM proactive_events WHERE event_id=?", (event.event_id,)).fetchone()
                if inserted.rowcount:
                    self.repository._insert_audit_event(connection, action="proactive_event_detected", entity_type="proactive_event", entity_id=event.event_id, payload={"event_type": event.event_type.value, "source_type": event.source_type})
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self._row(row)

    def get(self, event_id: str) -> ProactiveEvent | None:
        with self.repository._connection() as connection:
            row = connection.execute("SELECT * FROM proactive_events WHERE event_id=?", (event_id,)).fetchone()
        return None if row is None else self._row(row)

    def find_by_source(self, source_type: str, source_id: str) -> tuple[ProactiveEvent, ...]:
        with self.repository._connection() as connection:
            rows = connection.execute("SELECT * FROM proactive_events WHERE source_type=? AND source_id=? ORDER BY created_at", (source_type, source_id)).fetchall()
        return tuple(self._row(row) for row in rows)

    def find_by_state(self, state: ProactiveEventState) -> tuple[ProactiveEvent, ...]:
        with self.repository._connection() as connection:
            rows = connection.execute("SELECT * FROM proactive_events WHERE state=? ORDER BY created_at", (state.value,)).fetchall()
        return tuple(self._row(row) for row in rows)

    def update_state(self, event_id: str, state: ProactiveEventState, at: datetime) -> ProactiveEvent:
        with self.repository._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT * FROM proactive_events WHERE event_id=?", (event_id,)).fetchone()
                if row is None:
                    raise KeyError(event_id)
                current = ProactiveEventState(row["state"])
                if current in TERMINAL_STATES:
                    result = row
                else:
                    allowed = {
                        ProactiveEventState.DETECTED: {ProactiveEventState.CANDIDATE, ProactiveEventState.EXPIRED},
                        ProactiveEventState.CANDIDATE: {ProactiveEventState.DELIVERED, ProactiveEventState.DISMISSED, ProactiveEventState.EXPIRED},
                        ProactiveEventState.DELIVERED: {ProactiveEventState.ACKNOWLEDGED, ProactiveEventState.DISMISSED, ProactiveEventState.RESOLVED, ProactiveEventState.EXPIRED},
                    }
                    if state not in allowed.get(current, set()):
                        raise ValueError(f"invalid proactive event transition: {current.value} -> {state.value}")
                    field = {ProactiveEventState.DELIVERED: "delivered_at", ProactiveEventState.ACKNOWLEDGED: "acknowledged_at", ProactiveEventState.RESOLVED: "resolved_at", ProactiveEventState.DISMISSED: "dismissed_at"}.get(state)
                    if field is None:
                        connection.execute("UPDATE proactive_events SET state=? WHERE event_id=?", (state.value, event_id))
                    else:
                        connection.execute(f"UPDATE proactive_events SET state=?, {field}=? WHERE event_id=?", (state.value, self._utc(at), event_id))
                    result = connection.execute("SELECT * FROM proactive_events WHERE event_id=?", (event_id,)).fetchone()
                    self.repository._insert_audit_event(connection, action="proactive_event_transition", entity_type="proactive_event", entity_id=event_id, payload={"from": current.value, "to": state.value})
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self._row(result)

    def resolve_check_ins_for_user_message(self, message_at: datetime) -> tuple[ProactiveEvent, ...]:
        """Resolve only check-ins delivered before this new user message."""
        with self.repository._connection() as connection:
            rows = connection.execute("SELECT event_id FROM proactive_events WHERE event_type=? AND state=? AND delivered_at < ?", (ProactiveEventType.CHECK_IN.value, ProactiveEventState.DELIVERED.value, self._utc(message_at))).fetchall()
        return tuple(self.update_state(row["event_id"], ProactiveEventState.RESOLVED, message_at) for row in rows)

    def expire_due(self, now: datetime) -> tuple[ProactiveEvent, ...]:
        with self.repository._connection() as connection:
            rows = connection.execute("SELECT event_id FROM proactive_events WHERE valid_until IS NOT NULL AND valid_until <= ? AND state IN ('detected','candidate','delivered')", (self._utc(now),)).fetchall()
        return tuple(self.update_state(row["event_id"], ProactiveEventState.EXPIRED, now) for row in rows)

    @classmethod
    def _values(cls, event: ProactiveEvent) -> tuple:
        return (event.event_id, event.event_type.value, event.source_type, event.source_id, cls._utc(event.created_at), cls._utc(event.detected_at), cls._utc(event.valid_until), event.state.value, json.dumps(event.payload, ensure_ascii=False, sort_keys=True), cls._utc(event.delivered_at), cls._utc(event.acknowledged_at), cls._utc(event.resolved_at), cls._utc(event.dismissed_at))

    @staticmethod
    def _utc(value: datetime | None) -> str | None:
        return None if value is None else value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _row(row) -> ProactiveEvent:
        raw = dict(row)
        raw["payload"] = json.loads(raw.pop("payload_json"))
        for field in ("created_at", "detected_at", "valid_until", "delivered_at", "acknowledged_at", "resolved_at", "dismissed_at"):
            if raw[field] is not None:
                raw[field] = datetime.fromisoformat(raw[field])
        return ProactiveEvent.model_validate(raw)
