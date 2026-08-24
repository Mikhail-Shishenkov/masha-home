import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from backend.connectors.google_calendar.config import GoogleCalendarConfig, GoogleCalendarConfigStore
from backend.connectors.google_calendar.intent import calendar_intent
from backend.connectors.google_calendar.oauth import GoogleDesktopOAuthFlow, pkce_challenge, pkce_verifier
from backend.connectors.google_calendar.reader import GoogleCalendarReader
from backend.connectors.google_calendar.service import GoogleCalendarConversationService
from backend.secrets import InMemorySecretStore


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, url, *, method="GET", headers=None, body=None):
        self.calls.append((url, method, headers or {}, body))
        if "oauth2.googleapis.com/token" in url:
            return {"access_token": "ACCESS_TOKEN_MUST_NOT_ESCAPE"}
        if "calendarList" in url:
            return {"items": [
                {"id": "primary", "summary": "Личный", "primary": True},
                {"id": "hidden", "summary": "Скрытый", "selected": False},
            ]}
        if "pageToken=next" in url:
            return {"items": [{"id": "two", "summary": "Вторая", "start": {"date": "2026-08-25"}, "end": {"date": "2026-08-26"}}]}
        return {"items": [{
            "id": "one", "summary": "Созвон", "location": "Дом", "status": "confirmed",
            "start": {"dateTime": "2026-08-24T10:00:00Z"}, "end": {"dateTime": "2026-08-24T11:00:00Z"},
        }], "nextPageToken": "next"}


def _reader(tmp_path: Path, transport=None):
    config_store = GoogleCalendarConfigStore(tmp_path / "local-data/config/google-calendar.json")
    config = GoogleCalendarConfig(client_id="desktop-client-identifier")
    config_store.save(config)
    secrets = InMemorySecretStore()
    secrets.put(config.secret_ref, "REFRESH_TOKEN_MUST_NOT_ESCAPE")
    return GoogleCalendarReader(config_store=config_store, secret_store=secrets, transport=transport or FakeTransport()), config_store, secrets


def test_pkce_is_s256_and_oauth_callback_writes_only_refresh_token(tmp_path: Path):
    verifier = pkce_verifier()
    assert 43 <= len(verifier) <= 128
    assert pkce_challenge(verifier) != verifier
    config = GoogleCalendarConfig(client_id="desktop-client-identifier")
    secrets = InMemorySecretStore()

    def browser(url):
        query = parse_qs(urlparse(url).query)
        assert query["scope"] == ["https://www.googleapis.com/auth/calendar.readonly"]
        assert query["code_challenge_method"] == ["S256"]
        callback = query["redirect_uri"][0] + "?code=auth-code&state=" + query["state"][0]
        threading.Thread(target=lambda: urlopen(callback, timeout=5).read(), daemon=True).start()
        return True

    flow = GoogleDesktopOAuthFlow(browser_open=browser, token_post=lambda fields: ({"refresh_token": "REFRESH_TOKEN_MUST_NOT_ESCAPE"} if fields["code"] == "auth-code" else {}))
    tokens = flow.authorize(config, timeout_seconds=5)
    secrets.put(config.secret_ref, tokens.refresh_token)
    assert secrets.get(config.secret_ref) == "REFRESH_TOKEN_MUST_NOT_ESCAPE"
    assert "REFRESH_TOKEN_MUST_NOT_ESCAPE" not in config.model_dump_json()


def test_disconnect_deletes_credential_and_config(tmp_path: Path):
    reader, config_store, secrets = _reader(tmp_path)
    config = config_store.load()
    secrets.delete(config.secret_ref)
    config_store.delete()
    assert config_store.load() is None
    assert secrets.exists(config.secret_ref) is False


def test_calendar_reader_normalizes_timezones_all_day_and_pagination(tmp_path: Path):
    transport = FakeTransport()
    reader, _, _ = _reader(tmp_path, transport)
    outcome = reader.read(
        start=datetime(2026, 8, 24, tzinfo=timezone.utc), end=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    assert outcome.status == "completed"
    assert [event.title for event in outcome.events] == ["Созвон", "Вторая"]
    assert outcome.events[0].all_day is False and outcome.events[0].start.tzinfo is timezone.utc
    assert outcome.events[1].all_day is True and outcome.events[1].start.isoformat() == "2026-08-25"
    assert not any("hidden" in call[0] for call in transport.calls)


def test_invalid_refresh_marks_reconnect_and_never_sends_network_when_disconnected(tmp_path: Path):
    reader, config_store, secrets = _reader(tmp_path)
    class InvalidTransport(FakeTransport):
        def request(self, *args, **kwargs):
            from backend.connectors.google_calendar.reader import GoogleCalendarReconnectRequired
            raise GoogleCalendarReconnectRequired("invalid_grant")
    reader.transport = InvalidTransport()
    result = reader.read(start=datetime(2026, 8, 24, tzinfo=timezone.utc), end=datetime(2026, 8, 25, tzinfo=timezone.utc))
    assert result.status == "needs_reconnect"
    assert secrets.exists(config_store.load().secret_ref) is False
    reader.transport.calls.clear()
    assert reader.read(start=datetime(2026, 8, 24, tzinfo=timezone.utc), end=datetime(2026, 8, 25, tzinfo=timezone.utc)).status == "needs_reconnect"
    assert reader.transport.calls == []


def test_conversation_calendar_intents_and_safe_model_context(tmp_path: Path):
    reader, _, _ = _reader(tmp_path)
    service = GoogleCalendarConversationService(reader=reader)
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    assert calendar_intent("что у меня сегодня?", now) is not None
    assert calendar_intent("какие планы на эту неделю?", now) is not None
    assert calendar_intent("когда следующая встреча?", now) is not None
    assert calendar_intent("свободен ли я сегодня вечером?", now) is not None
    outcome = service.observe("что у меня завтра?", now_local=now)
    serialized = json.dumps(outcome.model_context(), ensure_ascii=False)
    assert "REFRESH_TOKEN_MUST_NOT_ESCAPE" not in serialized
    assert "ACCESS_TOKEN_MUST_NOT_ESCAPE" not in serialized
