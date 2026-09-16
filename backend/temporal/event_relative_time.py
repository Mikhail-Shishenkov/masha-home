"""Normalize quoted lead time against an application-owned event timestamp.

This is time arithmetic after semantic interpretation, never action routing.
"""
from datetime import datetime, timedelta, timezone
import re

from .duration_resolution import HomeDurationResolver


_BEFORE = re.compile(r"^за\s+(?P<duration>.+?)\s+до(?:\s+.+)?$", re.IGNORECASE)
_EARLIER = re.compile(r"^(?:на\s+)?(?P<duration>.+?)\s+раньше(?:\s+.+)?$", re.IGNORECASE)


def resolve_event_lead_time(expression: str, starts_at: datetime) -> datetime | None:
    if starts_at.utcoffset() is None or starts_at.second or starts_at.microsecond:
        return None
    text = " ".join(expression.strip(" .!?\n").split())
    match = _BEFORE.fullmatch(text) or _EARLIER.fullmatch(text)
    if match is None:
        return None
    duration = HomeDurationResolver().resolve(match.group("duration"), allow_embedded=False)
    if duration is None or duration.minutes is None:
        return None
    return starts_at.astimezone(timezone.utc) - timedelta(minutes=duration.minutes)
