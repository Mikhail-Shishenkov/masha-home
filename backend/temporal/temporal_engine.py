"""Application-owned time, absence and commitment status calculations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from pydantic import BaseModel, ConfigDict


# Moscow has used the fixed UTC+03:00 offset since 2014.  A fixed timezone keeps
# this local-first runtime independent from Windows tzdata installation.
MOSCOW = timezone(timedelta(hours=3), name="Europe/Moscow")


class Clock:
    def now_utc(self) -> datetime:
        raise NotImplementedError

    def now_local(self) -> datetime:
        return self.now_utc().astimezone(MOSCOW)


class SystemClock(Clock):
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock(Clock):
    def __init__(self, value: datetime):
        if value.tzinfo is None:
            raise ValueError("clock requires timezone-aware datetime")
        self.value = value.astimezone(timezone.utc)

    def now_utc(self) -> datetime:
        return self.value


class TemporalContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    current_utc_time: datetime
    current_local_time: datetime
    timezone: str = "Europe/Moscow"
    last_interaction_at: datetime | None
    absence_duration_seconds: int | None


class DueDateParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_text: str
    resolved_utc: datetime | None
    resolved_local: datetime | None
    timezone: str = "Europe/Moscow"
    precision: str | None
    parsing_method: str | None
    confidence: float
    ambiguity: str | None = None


class TemporalEngine:
    def __init__(self, clock: Clock | None = None):
        self.clock = clock or SystemClock()

    def context(self, last_interaction_at: datetime | None) -> TemporalContext:
        now = self.clock.now_utc()
        if now.tzinfo is None or (last_interaction_at is not None and last_interaction_at.tzinfo is None):
            raise ValueError("temporal context requires timezone-aware datetime")
        absence = None if last_interaction_at is None else max(0, int((now - last_interaction_at.astimezone(timezone.utc)).total_seconds()))
        return TemporalContext(current_utc_time=now, current_local_time=now.astimezone(MOSCOW), last_interaction_at=last_interaction_at, absence_duration_seconds=absence)

    def commitment_status(self, commitment) -> str:
        if commitment.status.value in {"completed", "cancelled"}:
            return commitment.status.value
        if commitment.due_at is not None and commitment.due_at.astimezone(timezone.utc) < self.clock.now_utc():
            return "overdue"
        return "open"

    def parse_due(self, text: str) -> DueDateParseResult:
        """Only deliberately unambiguous Russian forms; unknown text returns None."""
        local = self.clock.now_local()
        normalized = text.casefold().strip().removeprefix("до ")
        base = {"вчера": -1, "сегодня": 0, "завтра": 1, "послезавтра": 2}.get(normalized.split(" в ")[0])
        method = "relative_day"
        if base is None:
            match = re.fullmatch(r"через (\d+) (дн(?:я|ей)?|час(?:а|ов)?|минут(?:у|ы)?)", normalized)
            if match:
                amount = int(match.group(1)); unit = match.group(2)
                if unit.startswith("д"):
                    delta = timedelta(days=amount)
                elif unit.startswith("ч"):
                    delta = timedelta(hours=amount)
                else:
                    delta = timedelta(minutes=amount)
                value = local + delta
                return self._parsed(text, value, "relative_duration", "minute")
            if normalized == "через неделю":
                return self._parsed(text, local + timedelta(days=7), "relative_duration", "day")
            try:
                value = datetime.fromisoformat(normalized).replace(tzinfo=MOSCOW) if "T" not in normalized else datetime.fromisoformat(normalized).astimezone(MOSCOW)
                return self._parsed(text, value, "iso_date", "day")
            except ValueError:
                try:
                    value = datetime.strptime(normalized, "%d.%m.%Y").replace(tzinfo=MOSCOW)
                    return self._parsed(text, value, "numeric_date", "day")
                except ValueError:
                    return DueDateParseResult(source_text=text, resolved_utc=None, resolved_local=None, precision=None, parsing_method=None, confidence=0.0, ambiguity="unsupported or ambiguous expression")
        value = (local + timedelta(days=base)).replace(hour=18, minute=0, second=0, microsecond=0)
        time_match = re.search(r" в (\d{1,2}):(\d{2})$", normalized)
        precision = "day"
        if time_match:
            hour, minute = map(int, time_match.groups())
            if hour > 23 or minute > 59:
                return DueDateParseResult(source_text=text, resolved_utc=None, resolved_local=None, precision=None, parsing_method=None, confidence=0.0, ambiguity="invalid time")
            value = value.replace(hour=hour, minute=minute); precision = "minute"
        return self._parsed(text, value, method, precision)

    def extract_due(self, text: str) -> tuple[str, DueDateParseResult | None]:
        """Extract only a leading unambiguous deadline from an explicit statement."""
        match = re.match(r"^\s*(?:до\s+)?(?P<due>(?:сегодня|завтра|послезавтра|вчера)(?:\s+в\s+\d{1,2}:\d{2})?|через\s+\d+\s+(?:дн(?:я|ей)?|час(?:а|ов)?|минут(?:у|ы)?)|через\s+неделю)\s+(?:нужно\s+)?(?P<body>.+)$", text, re.IGNORECASE)
        if not match:
            return text, None
        return match.group("body").strip(), self.parse_due(match.group("due"))

    @staticmethod
    def _parsed(source: str, local: datetime, method: str, precision: str) -> DueDateParseResult:
        return DueDateParseResult(source_text=source, resolved_utc=local.astimezone(timezone.utc), resolved_local=local.astimezone(MOSCOW), precision=precision, parsing_method=method, confidence=1.0)
