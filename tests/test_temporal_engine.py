from datetime import datetime, timezone

from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.memory.memory_models import Commitment, CommitmentStatus, IdentityCode, SourceType, Visibility


NOW = datetime(2026, 8, 11, 7, 42, tzinfo=timezone.utc)


def test_fixed_clock_builds_moscow_context_and_absence():
    engine = TemporalEngine(FixedClock(NOW))
    context = engine.context(datetime(2026, 8, 11, 6, 42, tzinfo=timezone.utc))
    assert context.current_local_time.hour == 10
    assert context.timezone == "Europe/Moscow"
    assert context.absence_duration_seconds == 3600
    assert engine.context(None).absence_duration_seconds is None


def test_due_parser_supports_deliberately_limited_russian_forms():
    engine = TemporalEngine(FixedClock(NOW))
    assert engine.parse_due("завтра в 10:00").resolved_local.hour == 10
    assert engine.parse_due("послезавтра").resolved_local.day == 13
    assert engine.parse_due("через 3 дня").resolved_local.day == 14
    assert engine.parse_due("через 2 часа").resolved_local.hour == 12
    assert engine.parse_due("до 12.08.2026").resolved_local.day == 12
    assert engine.parse_due("в пятницу").ambiguity is not None


def test_commitment_status_exact_due_is_open_then_overdue_unless_completed():
    due = datetime(2026, 8, 11, 7, 42, tzinfo=timezone.utc)
    item = Commitment(id="commitment_due", text="report", owner=IdentityCode.MISHA, status=CommitmentStatus.OPEN, visibility=Visibility.VISIBLE, project_ids=["p"], due_at=due, completed_at=None, importance=0.5, source=SourceType.EXPLICIT_USER_INPUT, source_episode_ids=[], replaces_id=None, created_at=due, updated_at=due)
    assert TemporalEngine(FixedClock(due)).commitment_status(item) == "open"
    assert TemporalEngine(FixedClock(due.replace(minute=43))).commitment_status(item) == "overdue"
    assert TemporalEngine(FixedClock(due.replace(minute=43))).commitment_status(item.model_copy(update={"status": CommitmentStatus.COMPLETED, "completed_at": due})) == "completed"
