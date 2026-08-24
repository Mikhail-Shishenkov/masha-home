"""Interactive Yandex verification-code OAuth for the Disk-only scope."""

from __future__ import annotations

import base64
import hashlib
import secrets
import webbrowser
from urllib.parse import urlencode

from .config import YANDEX_DISK_SCOPE
from .network import assert_yandex_disk_network_allowed
from .reader import token_post


REDIRECT_URI = "https://oauth.yandex.ru/verification_code"


def verifier() -> str:
    return secrets.token_urlsafe(64)[:128]


def challenge(value: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).rstrip(b"=").decode()


def authorize(*, client_id: str, client_secret: str, authorization_code: str | None = None, code_prompt=input, prompt_open=webbrowser.open, policy_store=None, safety_store=None) -> dict:
    assert_yandex_disk_network_allowed(policy_store=policy_store, safety_store=safety_store)
    value = verifier()
    prompt_open("https://oauth.yandex.ru/authorize?" + urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "scope": YANDEX_DISK_SCOPE, "code_challenge": challenge(value), "code_challenge_method": "S256",
    }))
    code = authorization_code or code_prompt("Yandex authorization code: ")
    assert_yandex_disk_network_allowed(policy_store=policy_store, safety_store=safety_store)
    return token_post({"grant_type": "authorization_code", "code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": REDIRECT_URI, "code_verifier": value})
