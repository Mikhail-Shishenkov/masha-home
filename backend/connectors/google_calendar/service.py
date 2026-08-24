"""Conversation-safe Calendar read integration and human failure states."""

from __future__ import annotations

from datetime import datetime

from .intent import calendar_intent
from .reader import CalendarReadOutcome, GoogleCalendarReader


class GoogleCalendarConversationService:
    def __init__(self, *, reader: GoogleCalendarReader):
        self.reader = reader

    def observe(self, message: str, *, now_local: datetime) -> CalendarReadOutcome | None:
        intent = calendar_intent(message, now_local)
        if intent is None:
            return None
        return self.reader.read(start=intent.start, end=intent.end)

    @staticmethod
    def human_failure(outcome: CalendarReadOutcome) -> str:
        return {
            "disconnected": "Google Calendar не подключён.",
            "needs_reconnect": "Нужно переподключить Google Calendar.",
            "unavailable": "Сейчас не удалось прочитать календарь.",
        }.get(outcome.status, "Сейчас не удалось прочитать календарь.")
