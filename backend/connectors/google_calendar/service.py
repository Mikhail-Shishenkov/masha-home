"""Conversation-safe Calendar read integration and human failure states."""

from __future__ import annotations

from datetime import datetime

from .intent import calendar_intent, calendar_period_intent
from .reader import CalendarEventEvidence, CalendarReadOutcome, GoogleCalendarReader


def present_verified_event(registry, conversation_id, *, receipt, event_id, state):
    """Project a receipt-proven result into the existing conversation entity set.

    This is reference context, not authority for another mutation. Do not derive
    it from the confirmation flag or human response text.
    """
    if registry is None or receipt is None:
        return
    if receipt.status != "verified" or receipt.verified_at is None or receipt.confirmed_at is None:
        return
    event = CalendarEventEvidence(
        calendar_id="primary", calendar_name="Основной календарь",
        event_id=event_id, title=state.title, start=state.start, end=state.end,
        all_day=False, location=None, status="confirmed",
    )
    registry.present(
        conversation_id, "google_calendar", (event,),
        entity_kind="calendar_event", presentation_kind="verified_result",
    )
    registry.focus_read_item(conversation_id, "google_calendar", event)


class GoogleCalendarConversationService:
    def __init__(self, *, reader: GoogleCalendarReader, presented_read_sets=None):
        self.reader = reader
        self.presented_read_sets = presented_read_sets

    def observe(self, message: str, *, now_local: datetime, conversation_id: str | None = None) -> CalendarReadOutcome | None:
        intent = calendar_intent(message, now_local)
        if intent is None:
            return None
        return self._read(intent, conversation_id)

    def observe_period(
        self, period: str, *, now_local: datetime, conversation_id: str | None = None,
    ) -> CalendarReadOutcome | None:
        intent = calendar_period_intent(period, now_local)
        if intent is None:
            return None
        return self._read(intent, conversation_id)

    def _read(self, intent, conversation_id):
        outcome = self.reader.read(start=intent.start, end=intent.end)
        if self.presented_read_sets is not None and conversation_id is not None:
            if outcome.status == "completed":
                self.presented_read_sets.present(
                    conversation_id, "google_calendar", outcome.events,
                    entity_kind="calendar_event", presentation_kind="read",
                )
            else:
                self.presented_read_sets.discard(conversation_id, owner="google_calendar")
        return outcome

    @staticmethod
    def human_failure(outcome: CalendarReadOutcome) -> str:
        return {
            "disconnected": "Google Calendar не подключён.",
            "needs_reconnect": "Нужно переподключить Google Calendar.",
            "unavailable": "Сейчас не удалось прочитать календарь.",
        }.get(outcome.status, "Сейчас не удалось прочитать календарь.")
