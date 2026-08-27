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


@dataclass(frozen=True)
class CalendarCreateIntent:
    title: str | None
    start: datetime | None
    end: datetime | None
    clarification: str | None = None


_CREATE_VERB = re.compile(r"^(?:маш(?:а)?\s*,?\s*)?(?:поставь|запланируй|создай)\b", re.IGNORECASE)
_CREATE_WITH_CALENDAR = re.compile(r"^(?:маш(?:а)?\s*,?\s*)?добавь\b.*\b(?:в\s+)?календар", re.IGNORECASE)
_LEADING_TEMPORAL_CREATE = re.compile(r"^(?:сегодня|завтра)\s+в\s*\d{1,2}(?::\d{2})?\s+(?:поставь|запланируй|создай)\b", re.IGNORECASE)
_REMINDER_OWNERSHIP = re.compile(r"\b(?:напомни|напоминани\w*)\b", re.IGNORECASE)
_TIME_RANGE = re.compile(r"\bс\s*(\d{1,2})(?::(\d{2}))?\s*(?:до|по)\s*(\d{1,2})(?::(\d{2}))?\b", re.IGNORECASE)
_TIME_AT = re.compile(r"\b(?:в|на)\s*(\d{1,2})(?::(\d{2}))?\b", re.IGNORECASE)
_DURATION = re.compile(r"\bна\s*(?:(\d{1,2}|два|две)\s*)?(час(?:а|ов)?|минут(?:у|ы)?)\b", re.IGNORECASE)
_TODAY = re.compile(r"\bсегодня\b", re.IGNORECASE)


def calendar_create_intent(message: str, now_local: datetime) -> CalendarCreateIntent | None:
    """A deliberately narrow deterministic create parser; unknown parts clarify."""
    # Keep ':' intact until the bounded time grammar has parsed it.
    normalized = _SPACE.sub(" ", re.sub(r"[^\w\s:'-]+", " ", message.casefold().replace("ё", "е"))).strip()
    # A reminder is an explicit Home commitment entity, not a generic
    # scheduling verb.  Leave it for the established reminder pipeline.
    if _REMINDER_OWNERSHIP.search(normalized):
        return None
    if not (_CREATE_VERB.search(normalized) or _CREATE_WITH_CALENDAR.search(normalized) or _LEADING_TEMPORAL_CREATE.search(normalized)):
        return None
    if not (_TODAY.search(normalized) or any(token in normalized for token in ("завтра", "понедель", "вторник", "сред", "четверг", "пятниц", "суббот", "воскрес", " в ", " на "))):
        return CalendarCreateIntent(None, None, None, "На какой день поставить?")
    date_value = _create_date(normalized, now_local)
    if date_value is None:
        return CalendarCreateIntent(None, None, None, "На какой день поставить?")
    range_match = _TIME_RANGE.search(normalized)
    at_match = None if range_match else _TIME_AT.search(normalized)
    if range_match:
        start = _at(date_value, range_match.group(1), range_match.group(2), now_local)
        end = _at(date_value, range_match.group(3), range_match.group(4), now_local)
    elif at_match:
        start = _at(date_value, at_match.group(1), at_match.group(2), now_local)
        duration = _duration(normalized)
        end = None if duration is None else start + duration
    else:
        return CalendarCreateIntent(None, None, None, "Во сколько поставить?")
    if end is None:
        return CalendarCreateIntent(None, start, None, "На сколько времени поставить?")
    if end <= start:
        return CalendarCreateIntent(None, None, None, "Время окончания должно быть позже начала.")
    title = _create_title(message)
    if not title:
        return CalendarCreateIntent(None, start, end, "Что поставить в календарь?")
    return CalendarCreateIntent(title, start, end)


def _create_date(text: str, now_local: datetime):
    today = now_local.date()
    if "завтра" in text:
        return today + timedelta(days=1)
    if _TODAY.search(text):
        return today
    for word, weekday in _WEEKDAYS.items():
        if re.search(rf"\b{word}\b", text):
            delta = (weekday - today.weekday()) % 7
            # Same-weekday without an explicit relative marker is ambiguous.
            if delta == 0 and "эту" not in text and not _TODAY.search(text):
                return None
            return today + timedelta(days=delta)
    return None


def _at(day, hours: str, minutes: str | None, now_local: datetime) -> datetime:
    hour, minute = int(hours), int(minutes or 0)
    if hour > 23 or minute > 59:
        raise ValueError("calendar_time_invalid")
    return datetime.combine(day, time(hour, minute), tzinfo=now_local.tzinfo)


def _duration(text: str) -> timedelta | None:
    match = _DURATION.search(text)
    if match is None:
        return None
    amount = (match.group(1) or "1").casefold()
    value, unit = (2 if amount in {"два", "две"} else int(amount)), match.group(2)
    return timedelta(minutes=value if unit.startswith("мин") else value * 60)


def _create_title(message: str) -> str:
    text = message.strip(" .,!?")
    text = re.sub(r"^\s*(?:сегодня|завтра)\s+в\s*\d{1,2}(?::\d{2})?\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:маш(?:а)?\s*,?\s*)?(?:поставь|запланируй|создай)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*добавь\s+(?:в\s+)?календар(?:ь|е)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:сегодня|завтра|в\s+(?:понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье))\b", "", text, flags=re.IGNORECASE)
    text = _TIME_RANGE.sub("", text)
    text = _TIME_AT.sub("", text)
    text = _DURATION.sub("", text)
    text = re.sub(r"\b(?:на|в)\s+(?:календарь|календаре)\b", "", text, flags=re.IGNORECASE)
    return _SPACE.sub(" ", text).strip(" ,.-")[:500]


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
