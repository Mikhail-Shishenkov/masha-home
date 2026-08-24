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
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from .config import GoogleCalendarConfig


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


class GoogleDesktopOAuthFlow:
    def __init__(self, *, browser_open: Callable[[str], bool] = webbrowser.open, token_post=None):
        self.browser_open = browser_open
        self.token_post = token_post or _token_post

    def authorize(self, config: GoogleCalendarConfig, *, timeout_seconds: float = 180.0) -> OAuthTokens:
        verifier, state = pkce_verifier(), oauth_state()
        callback = _LoopbackCallback(state)
        server = HTTPServer(("127.0.0.1", 0), callback.handler())
        server.timeout = timeout_seconds
        redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth/callback"
        query = {
            "client_id": config.client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": config.requested_scope, "access_type": "offline", "prompt": "consent",
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
        fields = {"code": callback.code, "client_id": config.client_id, "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier}
        if config.client_secret is not None:
            fields["client_secret"] = config.client_secret
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
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read(2 * 1024 * 1024 + 1))
    if not isinstance(payload, dict):
        raise RuntimeError("google_token_response_invalid")
    return payload
