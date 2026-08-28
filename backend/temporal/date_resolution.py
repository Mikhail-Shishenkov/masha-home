"""Home-owned normalization of bounded Russian calendar-date expressions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from backend.memory.text_normalization import normalize_search_text

from .temporal_engine import TemporalEngine


_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_WEEKDAYS = {
    "понедельник": 0, "понедельника": 0,
    "вторник": 1, "вторника": 1,
    "среда": 2, "среду": 2,
    "четверг": 3, "четверга": 3,
    "пятница": 4, "пятницу": 4,
    "суббота": 5, "субботу": 5,
    "воскресенье": 6,
}
_NUMBERS = {
    "один": 1, "одну": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7,
}


@dataclass(frozen=True)
class ResolvedCalendarDate:
    value: date
    source_expression: str
    method: str

    @property
    def canonical(self) -> str:
        return self.value.isoformat()


class HomeCalendarDateResolver:
    """Normalize meaning already grounded to a date slot; never infer intent."""

    def __init__(self, temporal_engine: TemporalEngine):
        self.temporal_engine = temporal_engine

    def resolve(self, expression: str) -> ResolvedCalendarDate | None:
        source = expression.strip()
        if not source:
            return None
        today = self.temporal_engine.now_local().date()
        raw = source.casefold().replace("ё", "е")
        iso = re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})\s*", raw)
        if iso:
            return self._date(source, "iso_date", *map(int, iso.groups()))
        text = normalize_search_text(raw)
        words = set(text.split())
        if "послезавтра" in words:
            return ResolvedCalendarDate(today + timedelta(days=2), source, "relative_day")
        if "завтра" in words or any(word.startswith("завтрашн") for word in words):
            return ResolvedCalendarDate(today + timedelta(days=1), source, "relative_day")
        if "сегодня" in words or any(word.startswith("сегодняшн") for word in words):
            return ResolvedCalendarDate(today, source, "relative_day")
        relative = re.search(
            r"\bчерез\s+(?P<count>\d+|один|одну|два|две|три|четыре|пять|шесть|семь)\s+дн(?:я|ей|ь)\b",
            text,
        )
        if relative:
            token = relative.group("count")
            count = int(token) if token.isdigit() else _NUMBERS[token]
            if 1 <= count <= 366:
                return ResolvedCalendarDate(
                    today + timedelta(days=count), source, "relative_duration",
                )
        explicit = re.search(
            r"\b(?P<day>\d{1,2})\s+(?P<month>" + "|".join(_MONTHS) + r")"
            r"(?:\s+(?P<year>\d{4}))?\b",
            text,
        )
        if explicit:
            day = int(explicit.group("day"))
            month = _MONTHS[explicit.group("month")]
            year = int(explicit.group("year") or today.year)
            candidate = self._date(source, "russian_calendar_date", year, month, day)
            if candidate is not None and explicit.group("year") is None and candidate.value < today:
                candidate = self._date(source, "russian_calendar_date", year + 1, month, day)
            return candidate
        for word, weekday in _WEEKDAYS.items():
            if word in words:
                delta = (weekday - today.weekday()) % 7
                if delta == 0:
                    delta = 7
                return ResolvedCalendarDate(
                    today + timedelta(days=delta), source, "weekday",
                )
        return None

    @staticmethod
    def _date(
        source: str,
        method: str,
        year: int,
        month: int,
        day: int,
    ) -> ResolvedCalendarDate | None:
        try:
            value = date(year, month, day)
        except ValueError:
            return None
        return ResolvedCalendarDate(value, source, method)
