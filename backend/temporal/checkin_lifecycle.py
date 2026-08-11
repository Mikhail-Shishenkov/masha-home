"""Pure deterministic lifecycle permission for detected CHECK_IN events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .proactive import ProactiveDecisionEngine, ProactivePolicy
from .proactive_events import ProactiveEvent, ProactiveEventState, ProactiveEventStore
from .temporal_models import ProactiveDecision


@dataclass(frozen=True)
class CheckInEvaluation:
    event: ProactiveEvent
    decision: ProactiveDecision
    reason: str


class CheckInLifecycleRuntime:
    """Applies policy to an existing event; it does not deliver or call a model."""

    def __init__(self, store: ProactiveEventStore, decisions: ProactiveDecisionEngine | None = None):
        self.store = store
        self.decisions = decisions or ProactiveDecisionEngine()

    def evaluate(self, event_id: str, policy: ProactivePolicy, *, now: datetime, reminders_sent: int = 0, last_delivery_at: datetime | None = None, reminder_pending: bool = False) -> CheckInEvaluation:
        event = self.store.get(event_id)
        if event is None:
            raise KeyError(event_id)
        if event.state in {ProactiveEventState.DISMISSED, ProactiveEventState.ACKNOWLEDGED, ProactiveEventState.RESOLVED, ProactiveEventState.EXPIRED, ProactiveEventState.DELIVERED}:
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, f"terminal_or_delivered:{event.state.value}")
        if reminder_pending:
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, "higher_priority_reminder")
        absence = event.payload.get("absence_seconds")
        if not policy.enabled:
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, "proactive_disabled")
        if policy.proactive_level < 2:
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, "level_below_checkin")
        if not policy.allow_checkins:
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, "checkins_disabled")
        if absence is None or absence < policy.absence_threshold_seconds:
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, "absence_threshold_not_reached")
        if self.decisions._in_quiet_hours(now, policy):
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, "quiet_hours")
        if reminders_sent >= policy.daily_message_limit:
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, "daily_limit")
        if last_delivery_at is not None and (now - last_delivery_at).total_seconds() < policy.cooldown_seconds:
            return CheckInEvaluation(event, ProactiveDecision.SUPPRESS, "cooldown")
        decision = self.decisions.decide_checkin(policy, absence_seconds=absence, now=now, reminders_sent=reminders_sent, last_reminder_at=last_delivery_at)
        if decision is ProactiveDecision.SUPPRESS:
            return CheckInEvaluation(event, decision, "policy_suppressed")
        if event.state is ProactiveEventState.DETECTED:
            event = self.store.update_state(event.event_id, ProactiveEventState.CANDIDATE, now)
        return CheckInEvaluation(event, ProactiveDecision.CHECK_IN, "authorised")
