"""Read-only Google Calendar REST adapter; raw responses and tokens stay ephemeral."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .config import GoogleCalendarConfig, GoogleCalendarConfigStore
from .network import GoogleCalendarNetworkBlocked, assert_google_network_allowed


class GoogleCalendarTransport(Protocol):
    def request(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict: ...


class GoogleCalendarUnavailable(RuntimeError):
    pass


class GoogleCalendarHttpFailure(GoogleCalendarUnavailable):
    """A bounded HTTP status, retained only for application-side decisions."""

    def __init__(self, status_code: int):
        super().__init__("google_calendar_unavailable")
        self.status_code = status_code


class GoogleCalendarReconnectRequired(RuntimeError):
    pass


class GoogleTokenInvalidGrant(GoogleCalendarReconnectRequired):
    pass


class UrllibGoogleCalendarTransport:
    """Small bounded JSON-only HTTPS transport; it never logs request headers."""

    def request(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict:
        request = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=12) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
        except HTTPError as error:
            if "/token" in url and error.code == 400 and _token_error_is_invalid_grant(error):
                raise GoogleTokenInvalidGrant("google_reconnect_required") from error
            raise GoogleCalendarHttpFailure(error.code) from error
        except (URLError, OSError) as error:
            raise GoogleCalendarUnavailable("google_calendar_unavailable") from error
        if len(raw) > 2 * 1024 * 1024:
            raise GoogleCalendarUnavailable("google_calendar_unavailable")
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as error:
            raise GoogleCalendarUnavailable("google_calendar_unavailable") from error
        if not isinstance(payload, dict):
            raise GoogleCalendarUnavailable("google_calendar_unavailable")
        return payload


@dataclass(frozen=True)
class CalendarEventEvidence:
    calendar_id: str
    calendar_name: str
    event_id: str
    title: str
    start: datetime | date
    end: datetime | date
    all_day: bool
    location: str | None
    status: str

    def model_value(self) -> dict:
        """Model-safe event evidence; provider identities remain Home-owned."""
        return {
            "calendar": self.calendar_name,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "all_day": self.all_day,
            "location": self.location,
            "status": self.status,
        }


@dataclass(frozen=True)
class CalendarReadOutcome:
    status: str
    events: tuple[CalendarEventEvidence, ...] = ()
    start: datetime | None = None
    end: datetime | None = None

    def model_context(self) -> list[dict]:
        if self.status != "completed":
            return []
        return [{
            "kind": "google_calendar",
            "events": [event.model_value() for event in self.events],
            "window_start": None if self.start is None else self.start.isoformat(),
            "window_end": None if self.end is None else self.end.isoformat(),
        }]


class GoogleCalendarReader:
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_ROOT = "https://www.googleapis.com/calendar/v3"
    MAX_EVENTS = 50

    def __init__(self, *, config_store: GoogleCalendarConfigStore, secret_store, transport: GoogleCalendarTransport | None = None, policy_store=None, safety_store=None):
        self.config_store = config_store
        self.secret_store = secret_store
        self.transport = transport or UrllibGoogleCalendarTransport()
        self.policy_store = policy_store
        self.safety_store = safety_store

    def read(self, *, start: datetime, end: datetime) -> CalendarReadOutcome:
        config = self.config_store.load()
        if config is None:
            return CalendarReadOutcome("disconnected", start=start, end=end)
        refresh_token = self.secret_store.get(config.secret_ref)
        client_secret = self.secret_store.get(config.client_secret_ref)
        if refresh_token is None or client_secret is None:
            return CalendarReadOutcome("needs_reconnect", start=start, end=end)
        try:
            access_token = self._access_token(config, refresh_token, client_secret)
            calendars = self._calendars(access_token)
            events = self._events(access_token, calendars, start, end)
            return CalendarReadOutcome("completed", tuple(events), start, end)
        except GoogleTokenInvalidGrant:
            self.secret_store.delete(config.secret_ref)
            return CalendarReadOutcome("needs_reconnect", start=start, end=end)
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            return CalendarReadOutcome("unavailable", start=start, end=end)

    def _access_token(self, config: GoogleCalendarConfig, refresh_token: str, client_secret: str) -> str:
        fields = {
            "client_id": config.client_id, "client_secret": client_secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token",
        }
        payload = self._request(
            self.TOKEN_URL, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=urlencode(fields).encode("ascii"),
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise GoogleCalendarReconnectRequired("google_reconnect_required")
        return token

    def _calendars(self, access_token: str) -> tuple[tuple[str, str], ...]:
        payload = self._request(
            f"{self.API_ROOT}/users/me/calendarList?" + urlencode({"minAccessRole": "reader", "maxResults": 50}),
            headers={"Authorization": f"Bearer {access_token}"},
        )
        rows = []
        for item in payload.get("items", []):
            if not isinstance(item, dict) or (item.get("selected") is False and item.get("primary") is not True):
                continue
            identifier, summary = item.get("id"), item.get("summary")
            if isinstance(identifier, str) and isinstance(summary, str):
                rows.append((identifier, summary[:300]))
        return tuple(rows[:20])

    def _events(self, access_token: str, calendars: tuple[tuple[str, str], ...], start: datetime, end: datetime) -> list[CalendarEventEvidence]:
        events: list[CalendarEventEvidence] = []
        for calendar_id, calendar_name in calendars:
            page_token: str | None = None
            while len(events) < self.MAX_EVENTS:
                params = {"timeMin": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "timeMax": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "singleEvents": "true", "orderBy": "startTime", "maxResults": str(min(50, self.MAX_EVENTS - len(events)))}
                if page_token is not None:
                    params["pageToken"] = page_token
                payload = self._request(
                    f"{self.API_ROOT}/calendars/{quote(calendar_id, safe='')}/events?" + urlencode(params),
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                for item in payload.get("items", []):
                    event = _normalize_event(item, calendar_id, calendar_name, start.tzinfo)
                    if event is not None:
                        events.append(event)
                        if len(events) >= self.MAX_EVENTS:
                            break
                page_token = payload.get("nextPageToken") if isinstance(payload.get("nextPageToken"), str) else None
                if page_token is None:
                    break
        return sorted(events, key=lambda event: (event.start.isoformat(), event.event_id))[:self.MAX_EVENTS]

    def _request(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict:
        assert_google_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)
        return self.transport.request(url, method=method, headers=headers, body=body)


def _normalize_event(item: object, calendar_id: str, calendar_name: str, home_timezone) -> CalendarEventEvidence | None:
    if not isinstance(item, dict):
        return None
    event_id, title = item.get("id"), item.get("summary")
    start_data, end_data = item.get("start"), item.get("end")
    if not isinstance(event_id, str) or not isinstance(title, str) or not isinstance(start_data, dict) or not isinstance(end_data, dict):
        return None
    if isinstance(start_data.get("date"), str) and isinstance(end_data.get("date"), str):
        try:
            start, end = date.fromisoformat(start_data["date"]), date.fromisoformat(end_data["date"])
        except ValueError:
            return None
        return CalendarEventEvidence(calendar_id, calendar_name, event_id[:300], title[:500], start, end, True, _bounded(item.get("location")), _bounded(item.get("status")) or "confirmed")
    if not isinstance(start_data.get("dateTime"), str) or not isinstance(end_data.get("dateTime"), str):
        return None
    try:
        start = datetime.fromisoformat(start_data["dateTime"].replace("Z", "+00:00")).astimezone(home_timezone)
        end = datetime.fromisoformat(end_data["dateTime"].replace("Z", "+00:00")).astimezone(home_timezone)
    except ValueError:
        return None
    return CalendarEventEvidence(calendar_id, calendar_name, event_id[:300], title[:500], start, end, False, _bounded(item.get("location")), _bounded(item.get("status")) or "confirmed")


def _bounded(value: object) -> str | None:
    return value.strip()[:300] or None if isinstance(value, str) else None


def _token_error_is_invalid_grant(error: HTTPError) -> bool:
    try:
        payload = json.loads(error.read(64 * 1024 + 1))
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("error") == "invalid_grant"
