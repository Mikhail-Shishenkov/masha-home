from datetime import datetime, timedelta, timezone

import pytest

from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.proactive_events import (
    ProactiveEvent, ProactiveEventState, ProactiveEventStore, ProactiveEventType,
    check_in_event_id, commitment_reminder_event_id,
)


NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def _check_in(*, valid_until=None):
    return ProactiveEvent(event_id=check_in_event_id("message-1"), event_type=ProactiveEventType.CHECK_IN, source_type="absence", source_id="message-1", created_at=NOW, detected_at=NOW, valid_until=valid_until, payload={"absence_seconds": 3601})


def test_deterministic_ids_and_create_are_restart_idempotent(tmp_path):
    repo = MemorySqliteRepository(tmp_path / "events.sqlite3")
    store = ProactiveEventStore(repo)
    event = _check_in()

    first = store.create(event)
    second = ProactiveEventStore(MemorySqliteRepository(repo.database_path)).create(event)

    assert first.event_id == second.event_id == check_in_event_id("message-1")
    assert len(store.find_by_source("absence", "message-1")) == 1
    assert [item["action"] for item in store.repository.list_audit_events()].count("proactive_event_detected") == 1
    assert commitment_reminder_event_id("commitment-1", NOW) == commitment_reminder_event_id("commitment-1", NOW)


def test_check_in_lifecycle_dismiss_expiry_and_return_resolution(tmp_path):
    store = ProactiveEventStore(MemorySqliteRepository(tmp_path / "events.sqlite3"))
    event = store.create(_check_in(valid_until=NOW + timedelta(hours=1)))
    assert store.update_state(event.event_id, ProactiveEventState.CANDIDATE, NOW).state is ProactiveEventState.CANDIDATE
    assert store.update_state(event.event_id, ProactiveEventState.DELIVERED, NOW).state is ProactiveEventState.DELIVERED
    assert store.resolve_check_ins_for_user_message(NOW + timedelta(seconds=1))[0].state is ProactiveEventState.RESOLVED
    assert store.get(event.event_id).state is ProactiveEventState.RESOLVED

    dismissed = store.create(ProactiveEvent(event_id=check_in_event_id("message-2"), event_type=ProactiveEventType.CHECK_IN, source_type="absence", source_id="message-2", created_at=NOW, detected_at=NOW))
    store.update_state(dismissed.event_id, ProactiveEventState.CANDIDATE, NOW)
    assert store.update_state(dismissed.event_id, ProactiveEventState.DISMISSED, NOW).state is ProactiveEventState.DISMISSED
    assert store.update_state(dismissed.event_id, ProactiveEventState.DELIVERED, NOW).state is ProactiveEventState.DISMISSED

    expiring = store.create(ProactiveEvent(event_id=check_in_event_id("message-3"), event_type=ProactiveEventType.CHECK_IN, source_type="absence", source_id="message-3", created_at=NOW, detected_at=NOW, valid_until=NOW))
    assert store.expire_due(NOW)[0].state is ProactiveEventState.EXPIRED


def test_invalid_transition_and_event_store_do_not_touch_memory_document(tmp_path, canonical_memory):
    repo = MemorySqliteRepository(tmp_path / "events.sqlite3")
    repo.replace_document(canonical_memory)
    before = repo.read_document().model_dump(mode="json")
    store = ProactiveEventStore(repo)
    event = store.create(_check_in())

    with pytest.raises(ValueError):
        store.update_state(event.event_id, ProactiveEventState.DELIVERED, NOW)

    assert repo.read_document().model_dump(mode="json") == before
