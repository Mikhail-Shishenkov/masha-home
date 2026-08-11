"""Deterministic, local-only CHECK_IN event detection."""

from __future__ import annotations

from backend.conversation.conversation_store import ConversationStore

from .proactive import ProactivePolicy
from .proactive_events import (
    ProactiveEvent,
    ProactiveEventStore,
    ProactiveEventType,
    check_in_event_id,
)
from .temporal_engine import TemporalEngine


class CheckInDetector:
    """Detect one absence-period event; policy permission and delivery are elsewhere."""

    def __init__(self, history: ConversationStore, engine: TemporalEngine, events: ProactiveEventStore):
        self.history = history
        self.engine = engine
        self.events = events

    def detect(self, policy: ProactivePolicy) -> ProactiveEvent | None:
        anchor = self.history.latest_message()
        if anchor is None:
            return None
        context = self.engine.context(anchor.created_at)
        absence = context.absence_duration_seconds
        if absence is None or absence <= policy.absence_threshold_seconds:
            return None
        event = ProactiveEvent(
            event_id=check_in_event_id(anchor.id),
            event_type=ProactiveEventType.CHECK_IN,
            source_type="absence",
            source_id=anchor.id,
            created_at=context.current_utc_time,
            detected_at=context.current_utc_time,
            payload={
                "anchor_message_id": anchor.id,
                "anchor_created_at": anchor.created_at.isoformat(),
                "absence_seconds": absence,
            },
        )
        return self.events.create(event)
