"""Desktop OAuth authorization code flow with PKCE and one loopback callback."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from .config import GoogleCalendarConfig
from .network import assert_google_network_allowed


AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def pkce_verifier() -> str:
    return secrets.token_urlsafe(64)[:128]


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def oauth_state() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class OAuthTokens:
    refresh_token: str
    account_label: str | None = None


class GoogleOAuthTokenError(RuntimeError):
    """Controlled token-exchange failure; never carries an HTTP response body."""

    pass


class GoogleDesktopOAuthFlow:
    def __init__(self, *, browser_open: Callable[[str], bool] = webbrowser.open, token_post=None, policy_store=None, safety_store=None):
        self.browser_open = browser_open
        self.token_post = token_post or _token_post
        self.policy_store = policy_store
        self.safety_store = safety_store

    def authorize(self, config: GoogleCalendarConfig, *, client_secret: str, timeout_seconds: float = 180.0, scope: str | None = None) -> OAuthTokens:
        assert_google_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)
        verifier, state = pkce_verifier(), oauth_state()
        callback = _LoopbackCallback(state)
        server = HTTPServer(("127.0.0.1", 0), callback.handler())
        server.timeout = timeout_seconds
        redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth/callback"
        query = {
            "client_id": config.client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": scope or config.requested_scope, "access_type": "offline", "prompt": "consent",
            "state": state, "code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256",
        }
        url = AUTHORIZATION_URL + "?" + urlencode(query)
        if not self.browser_open(url):
            server.server_close()
            raise RuntimeError("google_browser_open_failed")
        try:
            server.handle_request()
        finally:
            server.server_close()
        if callback.error is not None or callback.code is None:
            raise RuntimeError("google_authorization_failed")
        fields = {
            "code": callback.code,
            "client_id": config.client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }
        assert_google_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)
        payload = self.token_post(fields)
        refresh_token = payload.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise RuntimeError("google_refresh_token_missing")
        return OAuthTokens(refresh_token=refresh_token)


class _LoopbackCallback:
    def __init__(self, expected_state: str):
        self.expected_state = expected_state
        self.code: str | None = None
        self.error: str | None = None

    def handler(self):
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                values = parse_qs(parsed.query)
                state = values.get("state", [None])[0]
                code = values.get("code", [None])[0]
                if parsed.path != "/oauth/callback" or state != receiver.expected_state or not isinstance(code, str):
                    receiver.error = "callback_invalid"
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write("Authorization was not accepted.".encode("utf-8"))
                else:
                    receiver.code = code
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write("Google Calendar connected. You may close this window.".encode("utf-8"))

            def log_message(self, _format, *_args):
                return

        return Handler


def _token_post(fields: dict[str, str]) -> dict:
    request = Request(TOKEN_URL, data=urlencode(fields).encode("ascii"), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
    except HTTPError as error:
        raise GoogleOAuthTokenError(_safe_oauth_error_code(error)) from error
    except (URLError, OSError) as error:
        raise GoogleOAuthTokenError("google_token_exchange_unavailable") from error
    if len(raw) > 2 * 1024 * 1024:
        raise GoogleOAuthTokenError("google_token_response_invalid")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as error:
        raise GoogleOAuthTokenError("google_token_response_invalid") from error
    if not isinstance(payload, dict):
        raise GoogleOAuthTokenError("google_token_response_invalid")
    return payload


def _safe_oauth_error_code(error: HTTPError) -> str:
    """Classify only bounded OAuth error metadata; never retain or print its body."""

    try:
        payload = json.loads(error.read(8 * 1024))
        value = payload.get("error") if isinstance(payload, dict) else None
        # Reading description is deliberately bounded but it is not surfaced in errors.
        _description = payload.get("error_description") if isinstance(payload, dict) else None
        if isinstance(_description, str):
            _description[:512]
        if isinstance(value, str) and value.replace("_", "").isalnum() and len(value) <= 80:
            return f"google_oauth_{value}"
    except (OSError, UnicodeDecodeError, ValueError):
        pass
    return "google_token_exchange_failed"
