"""Secret-free application contracts for future connector credentials."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _SecretModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SecretRef(_SecretModel):
    """Validated local key; deliberately carries no credential material."""

    value: str = Field(min_length=3, max_length=120, pattern=r"^[a-z][a-z0-9-]{1,118}[a-z0-9]$")


class ConnectorCredentialState(str, Enum):
    READY = "ready"
    NEEDS_RECONNECT = "needs_reconnect"
    DISCONNECTED = "disconnected"


class ConnectorCredentialMetadata(_SecretModel):
    """Persistable-safe connector state: a reference is not a secret."""

    connector_id: str = Field(min_length=3, max_length=100, pattern=r"^[a-z][a-z0-9-]{1,98}[a-z0-9]$")
    secret_ref: SecretRef | None = None

    def credential_state(self, secret_store) -> ConnectorCredentialState:
        if self.secret_ref is None:
            return ConnectorCredentialState.DISCONNECTED
        return (
            ConnectorCredentialState.READY
            if secret_store.exists(self.secret_ref)
            else ConnectorCredentialState.NEEDS_RECONNECT
        )
