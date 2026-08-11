from datetime import datetime, time, timedelta, timezone

from backend.memory.sqlite_repository import MemorySqliteRepository
from backend.temporal.checkin_lifecycle import CheckInLifecycleRuntime
from backend.temporal.proactive import ProactivePolicy
from backend.temporal.proactive_events import ProactiveEvent, ProactiveEventState, ProactiveEventStore, ProactiveEventType, check_in_event_id
from backend.temporal.temporal_models import ProactiveDecision


NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def _event(store, suffix="one"):
    return store.create(ProactiveEvent(event_id=check_in_event_id(suffix), event_type=ProactiveEventType.CHECK_IN, source_type="absence", source_id=suffix, created_at=NOW, detected_at=NOW, payload={"absence_seconds": 120}))


def test_authorised_policy_moves_detected_to_candidate_and_is_idempotent(tmp_path):
    store = ProactiveEventStore(MemorySqliteRepository(tmp_path / "events.sqlite3"))
    event = _event(store)
    runtime = CheckInLifecycleRuntime(store)
    policy = ProactivePolicy(enabled=True, proactive_level=2, allow_checkins=True, absence_threshold_seconds=60, daily_message_limit=1)

    first = runtime.evaluate(event.event_id, policy, now=NOW)
    second = runtime.evaluate(event.event_id, policy, now=NOW)

    assert first.decision is ProactiveDecision.CHECK_IN and first.event.state is ProactiveEventState.CANDIDATE
    assert second.decision is ProactiveDecision.CHECK_IN and second.event.state is ProactiveEventState.CANDIDATE


def test_disabled_quiet_cooldown_daily_and_reminder_priority_suppress(tmp_path):
    store = ProactiveEventStore(MemorySqliteRepository(tmp_path / "events.sqlite3"))
    runtime = CheckInLifecycleRuntime(store)
    base = dict(enabled=True, proactive_level=2, allow_checkins=True, absence_threshold_seconds=60, daily_message_limit=1)
    assert runtime.evaluate(_event(store, "disabled").event_id, ProactivePolicy(), now=NOW).reason == "proactive_disabled"
    assert runtime.evaluate(_event(store, "quiet").event_id, ProactivePolicy(**base, quiet_hours_start=time(15), quiet_hours_end=time(16)), now=NOW).reason == "quiet_hours"
    assert runtime.evaluate(_event(store, "cooldown").event_id, ProactivePolicy(**base, cooldown_seconds=3600), now=NOW, last_delivery_at=NOW - timedelta(minutes=1)).reason == "cooldown"
    assert runtime.evaluate(_event(store, "daily").event_id, ProactivePolicy(**base), now=NOW, reminders_sent=1).reason == "daily_limit"
    priority = runtime.evaluate(_event(store, "priority").event_id, ProactivePolicy(**base), now=NOW, reminder_pending=True)
    assert priority.decision is ProactiveDecision.SUPPRESS and priority.reason == "higher_priority_reminder"


def test_dismissed_stays_suppressed_and_only_new_user_message_after_delivery_resolves(tmp_path):
    store = ProactiveEventStore(MemorySqliteRepository(tmp_path / "events.sqlite3"))
    event = _event(store, "dismiss")
    store.update_state(event.event_id, ProactiveEventState.CANDIDATE, NOW)
    store.update_state(event.event_id, ProactiveEventState.DISMISSED, NOW)
    assert CheckInLifecycleRuntime(store).evaluate(event.event_id, ProactivePolicy(enabled=True, proactive_level=2, allow_checkins=True), now=NOW).event.state is ProactiveEventState.DISMISSED

    delivered = _event(store, "delivered")
    store.update_state(delivered.event_id, ProactiveEventState.CANDIDATE, NOW)
    store.update_state(delivered.event_id, ProactiveEventState.DELIVERED, NOW)
    assert store.resolve_check_ins_for_user_message(NOW) == ()
    assert store.resolve_check_ins_for_user_message(NOW + timedelta(seconds=1))[0].state is ProactiveEventState.RESOLVED
