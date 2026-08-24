from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from backend.secrets import ConnectorCredentialState, SecretRef

YANDEX_MAIL_SCOPE = "mail:imap_ro"
YANDEX_MAIL_SECRET_REF = SecretRef(value="yandex-mail-primary")
YANDEX_MAIL_CLIENT_SECRET_REF = SecretRef(value="yandex-mail-client-secret")

class YandexMailConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    connector_id: str = Field(default="yandex-mail", pattern=r"^yandex-mail$")
    provider: str = Field(default="yandex", pattern=r"^yandex$")
    client_id: str = Field(min_length=3, max_length=300)
    account_email: str = Field(min_length=3, max_length=300)
    secret_ref: SecretRef = YANDEX_MAIL_SECRET_REF
    client_secret_ref: SecretRef = YANDEX_MAIL_CLIENT_SECRET_REF
    requested_scope: str = Field(default=YANDEX_MAIL_SCOPE, pattern=r"^mail:imap_ro$")
    def credential_state(self, store) -> ConnectorCredentialState:
        return ConnectorCredentialState.READY if store.exists(self.secret_ref) and store.exists(self.client_secret_ref) else ConnectorCredentialState.NEEDS_RECONNECT

class YandexMailConfigStore:
    def __init__(self, path: Path): self.path = Path(path)
    def load(self): return None if not self.path.exists() else YandexMailConfig.model_validate_json(self.path.read_bytes())
    def save(self, config):
        self.path.parent.mkdir(parents=True, exist_ok=True); temp = self.path.with_suffix(".tmp")
        temp.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8"); temp.replace(self.path); return config
    def delete(self): self.path.unlink(missing_ok=True)
