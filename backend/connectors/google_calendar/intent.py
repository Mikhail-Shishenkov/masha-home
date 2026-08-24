"""Deterministic, narrow Russian Calendar read intent and Home-time windows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta


_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s'-]+", re.UNICODE)
_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среду": 2, "среда": 2, "четверг": 3,
    "пятницу": 4, "пятница": 4, "субботу": 5, "суббота": 5, "воскресенье": 6,
}


@dataclass(frozen=True)
class CalendarIntent:
    kind: str
    start: datetime
    end: datetime


def calendar_intent(message: str, now_local: datetime) -> CalendarIntent | None:
    text = _SPACE.sub(" ", _PUNCT.sub(" ", message.casefold().replace("ё", "е"))).strip()
    if not text:
        return None
    today = now_local.date()
    if re.search(r"\b(?:когда\s+)?следующ(?:ая|ее|ий)\s+(?:встреч|событи)|\bследующая\s+встреч", text):
        return CalendarIntent("next", now_local, now_local + timedelta(days=31))
    if re.search(r"\bсвобод(?:ен|на|но)\b.*\bсегодня\b.*\bвечер|\bсегодня\s+вечером\b.*\bсвобод", text):
        start = datetime.combine(today, time(18), tzinfo=now_local.tzinfo)
        return CalendarIntent("free", start, start + timedelta(hours=5))
    if "завтра" in text and _schedule_question(text):
        start = datetime.combine(today + timedelta(days=1), time.min, tzinfo=now_local.tzinfo)
        return CalendarIntent("schedule", start, start + timedelta(days=1))
    if re.search(r"\b(?:эт(?:а|ой|у)\s+недел\w*|на\s+недел\w*)\b", text) and _schedule_question(text):
        start = datetime.combine(today - timedelta(days=today.weekday()), time.min, tzinfo=now_local.tzinfo)
        return CalendarIntent("schedule", start, start + timedelta(days=7))
    for word, weekday in _WEEKDAYS.items():
        if word in text and _schedule_question(text):
            delta = (weekday - today.weekday()) % 7
            start = datetime.combine(today + timedelta(days=delta), time.min, tzinfo=now_local.tzinfo)
            return CalendarIntent("schedule", start, start + timedelta(days=1))
    if "сегодня" in text and _schedule_question(text):
        start = datetime.combine(today, time.min, tzinfo=now_local.tzinfo)
        return CalendarIntent("schedule", start, start + timedelta(days=1))
    return None


def _schedule_question(text: str) -> bool:
    """Calendar must not swallow a memory/task write mentioning a date."""
    return bool(re.search(
        r"^(?:маш(?:а|енька)?\s+)?(?:"
        r"что\s+у\s+меня(?:\s+в\s+календаре)?|"
        r"какие\s+(?:у\s+меня\s+)?план\w*|"
        r"что\s+в\s+календар\w*|"
        r"покажи\s+(?:мой\s+)?календар\w*"
        r")\b",
        text,
    ))
