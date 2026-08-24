"""Secret-free configuration for the bounded Yandex Disk reader."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from backend.secrets import ConnectorCredentialState, SecretRef


YANDEX_DISK_SCOPE = "cloud_api:disk.read"
YANDEX_DISK_SECRET_REF = SecretRef(value="yandex-disk-primary")
YANDEX_DISK_CLIENT_SECRET_REF = SecretRef(value="yandex-disk-client-secret")


class YandexDiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str = Field(default="yandex-disk", pattern=r"^yandex-disk$")
    provider: str = Field(default="yandex", pattern=r"^yandex$")
    client_id: str = Field(min_length=3, max_length=300)
    secret_ref: SecretRef = YANDEX_DISK_SECRET_REF
    client_secret_ref: SecretRef = YANDEX_DISK_CLIENT_SECRET_REF
    requested_scope: str = Field(default=YANDEX_DISK_SCOPE, pattern=r"^cloud_api:disk\.read$")
    account_label: str | None = Field(default=None, max_length=200)

    def credential_state(self, secret_store) -> ConnectorCredentialState:
        return (
            ConnectorCredentialState.READY
            if secret_store.exists(self.secret_ref) and secret_store.exists(self.client_secret_ref)
            else ConnectorCredentialState.NEEDS_RECONNECT
        )


class YandexDiskConfigStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> YandexDiskConfig | None:
        return None if not self.path.exists() else YandexDiskConfig.model_validate_json(self.path.read_bytes())

    def save(self, config: YandexDiskConfig) -> YandexDiskConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return config

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)
