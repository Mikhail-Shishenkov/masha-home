"""Application-owned time, absence and commitment status calculations."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import Enum
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .conversation_grounding import (
    GreetingKind,
    greeting_kind,
    greeting_matches_daypart,
)
from .timezone_provider import HomeTimeZone, HomeTimeZoneProvider


class Daypart(str, Enum):
    NIGHT = "night"
    MORNING = "morning"
    DAY = "day"
    EVENING = "evening"
    LATE_EVENING = "late_evening"


class LocalWeekday(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class PreviousTurnRelation(str, Enum):
    SAME_LOCAL_DAY = "same_local_day"
    PREVIOUS_LOCAL_DAY = "previous_local_day"
    OLDER_LOCAL_DAY = "older_local_day"
    FUTURE_CLOCK_SKEW = "future_clock_skew"


class Clock:
    def now_utc(self) -> datetime:
        raise NotImplementedError


class SystemClock(Clock):
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock(Clock):
    def __init__(self, value: datetime):
        self.set(value)

    def set(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("clock requires timezone-aware datetime")
        self.value = value.astimezone(timezone.utc)

    def now_utc(self) -> datetime:
        return self.value


class TemporalContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_utc_time: datetime
    current_local_time: datetime
    timezone: str
    timezone_resolution: Literal[
        "named_zone",
        "configured_offset_fallback",
        "system_local",
    ]
    local_date: date
    local_weekday: LocalWeekday
    daypart: Daypart
    last_interaction_at: datetime | None
    last_interaction_local_time: datetime | None
    last_interaction_local_date: date | None
    absence_duration_seconds: int | None
    same_local_date_as_last_interaction: bool | None
    local_day_delta_from_last_interaction: int | None
    previous_turn_relation: PreviousTurnRelation | None
    greeting_kind: GreetingKind
    greeting_matches_current_daypart: bool | None


class DueDateParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_text: str
    resolved_utc: datetime | None
    resolved_local: datetime | None
    timezone: str
    precision: str | None
    parsing_method: str | None
    confidence: float
    ambiguity: str | None = None


class TemporalEngine:
    def __init__(
        self,
        clock: Clock | None = None,
        timezone_provider: HomeTimeZoneProvider | None = None,
    ):
        self.clock = clock or SystemClock()
        self.home_timezone: HomeTimeZone = (
            timezone_provider or HomeTimeZoneProvider()
        ).resolve()

    def now_local(self) -> datetime:
        return self.clock.now_utc().astimezone(self.home_timezone.tzinfo)

    def context(
        self,
        last_interaction_at: datetime | None,
        *,
        user_message: str = "",
    ) -> TemporalContext:
        now = self.clock.now_utc()
        if now.tzinfo is None or (
            last_interaction_at is not None and last_interaction_at.tzinfo is None
        ):
            raise ValueError("temporal context requires timezone-aware datetime")
        local = now.astimezone(self.home_timezone.tzinfo)
        previous_local = (
            None
            if last_interaction_at is None
            else last_interaction_at.astimezone(self.home_timezone.tzinfo)
        )
        absence = (
            None
            if last_interaction_at is None
            else max(
                0,
                int(
                    (
                        now - last_interaction_at.astimezone(timezone.utc)
                    ).total_seconds()
                ),
            )
        )
        day_delta = (
            None
            if previous_local is None
            else (local.date() - previous_local.date()).days
        )
        part = self.daypart(local)
        greeting = greeting_kind(user_message)
        return TemporalContext(
            current_utc_time=now,
            current_local_time=local,
            timezone=self.home_timezone.name,
            timezone_resolution=self.home_timezone.resolution,
            local_date=local.date(),
            local_weekday=LocalWeekday(list(LocalWeekday)[local.weekday()]),
            daypart=part,
            last_interaction_at=last_interaction_at,
            last_interaction_local_time=previous_local,
            last_interaction_local_date=(
                None if previous_local is None else previous_local.date()
            ),
            absence_duration_seconds=absence,
            same_local_date_as_last_interaction=(
                None if day_delta is None else day_delta == 0
            ),
            local_day_delta_from_last_interaction=day_delta,
            previous_turn_relation=self._previous_relation(day_delta),
            greeting_kind=greeting,
            greeting_matches_current_daypart=greeting_matches_daypart(
                greeting, part.value
            ),
        )

    @staticmethod
    def daypart(value: datetime) -> Daypart:
        hour = value.hour
        if hour < 6:
            return Daypart.NIGHT
        if hour < 12:
            return Daypart.MORNING
        if hour < 18:
            return Daypart.DAY
        if hour < 22:
            return Daypart.EVENING
        return Daypart.LATE_EVENING

    @staticmethod
    def _previous_relation(day_delta: int | None) -> PreviousTurnRelation | None:
        if day_delta is None:
            return None
        if day_delta < 0:
            return PreviousTurnRelation.FUTURE_CLOCK_SKEW
        if day_delta == 0:
            return PreviousTurnRelation.SAME_LOCAL_DAY
        if day_delta == 1:
            return PreviousTurnRelation.PREVIOUS_LOCAL_DAY
        return PreviousTurnRelation.OLDER_LOCAL_DAY

    def commitment_status(self, commitment) -> str:
        if commitment.status.value in {"completed", "cancelled"}:
            return commitment.status.value
        if (
            commitment.due_at is not None
            and commitment.due_at.astimezone(timezone.utc) < self.clock.now_utc()
        ):
            return "overdue"
        return "open"

    def parse_due(self, text: str) -> DueDateParseResult:
        """Only deliberately unambiguous Russian forms; unknown text returns None."""
        local = self.now_local()
        normalized = text.casefold().strip().removeprefix("до ")
        base = {
            "вчера": -1,
            "сегодня": 0,
            "завтра": 1,
            "послезавтра": 2,
        }.get(normalized.split(" в ")[0])
        method = "relative_day"
        if base is None:
            match = re.fullmatch(
                r"через (\d+) (дн(?:я|ей)?|час(?:а|ов)?|минут(?:у|ы)?)",
                normalized,
            )
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                if unit.startswith("д"):
                    delta = timedelta(days=amount)
                elif unit.startswith("ч"):
                    delta = timedelta(hours=amount)
                else:
                    delta = timedelta(minutes=amount)
                return self._parsed(
                    text, local + delta, "relative_duration", "minute"
                )
            if normalized == "через неделю":
                return self._parsed(
                    text, local + timedelta(days=7), "relative_duration", "day"
                )
            try:
                value = (
                    datetime.fromisoformat(normalized).replace(
                        tzinfo=self.home_timezone.tzinfo
                    )
                    if "T" not in normalized
                    else datetime.fromisoformat(normalized).astimezone(
                        self.home_timezone.tzinfo
                    )
                )
                return self._parsed(text, value, "iso_date", "day")
            except ValueError:
                try:
                    value = datetime.strptime(normalized, "%d.%m.%Y").replace(
                        tzinfo=self.home_timezone.tzinfo
                    )
                    return self._parsed(text, value, "numeric_date", "day")
                except ValueError:
                    return DueDateParseResult(
                        source_text=text,
                        resolved_utc=None,
                        resolved_local=None,
                        timezone=self.home_timezone.name,
                        precision=None,
                        parsing_method=None,
                        confidence=0.0,
                        ambiguity="unsupported or ambiguous expression",
                    )
        value = (local + timedelta(days=base)).replace(
            hour=18, minute=0, second=0, microsecond=0
        )
        time_match = re.search(r" в (\d{1,2}):(\d{2})$", normalized)
        precision = "day"
        if time_match:
            hour, minute = map(int, time_match.groups())
            if hour > 23 or minute > 59:
                return DueDateParseResult(
                    source_text=text,
                    resolved_utc=None,
                    resolved_local=None,
                    timezone=self.home_timezone.name,
                    precision=None,
                    parsing_method=None,
                    confidence=0.0,
                    ambiguity="invalid time",
                )
            value = value.replace(hour=hour, minute=minute)
            precision = "minute"
        return self._parsed(text, value, method, precision)

    def extract_due(self, text: str) -> tuple[str, DueDateParseResult | None]:
        """Extract one clear leading or terminal deadline from an explicit statement."""
        due = (
            r"(?:сегодня|завтра|послезавтра|вчера)(?:\s+в\s+\d{1,2}:\d{2})?"
            r"|через\s+\d+\s+(?:дн(?:я|ей)?|час(?:а|ов)?|минут(?:у|ы)?)"
            r"|через\s+неделю"
        )
        leading = re.match(
            rf"^\s*(?:до\s+)?(?P<due>{due})\s+(?:нужно\s+)?(?P<body>.+)$",
            text,
            re.IGNORECASE,
        )
        if leading:
            return leading.group("body").strip(), self.parse_due(leading.group("due"))
        trailing = re.match(
            rf"^\s*(?P<body>.+?)\s+(?P<due>{due})\s*$",
            text,
            re.IGNORECASE,
        )
        if trailing:
            return trailing.group("body").strip(), self.parse_due(trailing.group("due"))
        return text, None

    def _parsed(
        self, source: str, local: datetime, method: str, precision: str
    ) -> DueDateParseResult:
        local = local.astimezone(self.home_timezone.tzinfo)
        return DueDateParseResult(
            source_text=source,
            resolved_utc=local.astimezone(timezone.utc),
            resolved_local=local,
            timezone=self.home_timezone.name,
            precision=precision,
            parsing_method=method,
            confidence=1.0,
        )
