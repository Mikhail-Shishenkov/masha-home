"""Read-only application answers for exact clock and calendar questions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .temporal_engine import Daypart, TemporalContext


_TIME = re.compile(
    r"^\s*(?:а\s+)?(?:сколько\s+сейчас\s+времени|который\s+час)\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"^\s*(?:какое\s+сегодня\s+число|какая\s+сегодня\s+дата)\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_WEEKDAY = re.compile(
    r"^\s*какой\s+сегодня\s+день\s+недели\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_DAYPART = re.compile(
    r"^\s*сейчас\s+(?:уже\s+)?(?P<part>утро|день|вечер|ночь)\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_STILL_DATE = re.compile(
    r"^\s*сегодня\s+(?:ещ[ёе]\s+)?(?P<day>\d{1,2})\s+"
    r"(?P<month>января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s*[?!.]*\s*$",
    re.IGNORECASE,
)

_WEEKDAYS = {
    "monday": "понедельник",
    "tuesday": "вторник",
    "wednesday": "среда",
    "thursday": "четверг",
    "friday": "пятница",
    "saturday": "суббота",
    "sunday": "воскресенье",
}
_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
_MONTH_BY_NUMBER = {value: key for key, value in _MONTHS.items()}
_DAYPART_WORDS = {
    Daypart.NIGHT: "ночь",
    Daypart.MORNING: "утро",
    Daypart.DAY: "день",
    Daypart.EVENING: "вечер",
    Daypart.LATE_EVENING: "поздний вечер",
}
_ASKED_DAYPARTS = {
    "утро": {Daypart.MORNING},
    "день": {Daypart.DAY},
    "вечер": {Daypart.EVENING, Daypart.LATE_EVENING},
    "ночь": {Daypart.NIGHT},
}


@dataclass(frozen=True)
class TemporalReadout:
    response: str


def temporal_readout(message: str, context: TemporalContext) -> TemporalReadout | None:
    local = context.current_local_time
    if _TIME.match(message):
        return TemporalReadout(f"Сейчас {local:%H:%M}.")
    if _DATE.match(message):
        return TemporalReadout(
            f"Сегодня {local.day} {_MONTH_BY_NUMBER[local.month]} {local.year} года."
        )
    if _WEEKDAY.match(message):
        return TemporalReadout(f"Сегодня {_WEEKDAYS[context.local_weekday.value]}.")
    if match := _DAYPART.match(message):
        asked = match.group("part").casefold()
        if context.daypart in _ASKED_DAYPARTS[asked]:
            return TemporalReadout(f"Да, сейчас {_DAYPART_WORDS[context.daypart]}.")
        return TemporalReadout(f"Нет, сейчас {_DAYPART_WORDS[context.daypart]}.")
    if match := _STILL_DATE.match(message):
        asked_day = int(match.group("day"))
        asked_month = _MONTHS[match.group("month").casefold()]
        matches = local.day == asked_day and local.month == asked_month
        prefix = "Да" if matches else "Нет"
        return TemporalReadout(
            f"{prefix}, сегодня {local.day} {_MONTH_BY_NUMBER[local.month]} {local.year} года."
        )
    return None
