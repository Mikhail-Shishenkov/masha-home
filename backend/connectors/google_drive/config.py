"""Secret-free local configuration for the read-only Google Drive connector."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from backend.secrets import ConnectorCredentialState, SecretRef


GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GOOGLE_DRIVE_DOCUMENT_WRITE_SCOPE = "https://www.googleapis.com/auth/drive.file"
# Compatibility import name for callers compiled against the first A3 slice.
# Its value intentionally changes: a documents-only grant cannot recover a
# Drive marker-bearing document create operation.
GOOGLE_DOCUMENTS_WRITE_SCOPE = GOOGLE_DRIVE_DOCUMENT_WRITE_SCOPE
GOOGLE_DRIVE_SECRET_REF = SecretRef(value="google-drive-primary")
GOOGLE_DRIVE_CLIENT_SECRET_REF = SecretRef(value="google-drive-client-secret")
GOOGLE_DOCUMENTS_WRITE_SECRET_REF = SecretRef(value="google-drive-documents-write-primary")


class GoogleDriveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str = Field(default="google-drive", pattern=r"^google-drive$")
    client_id: str = Field(min_length=10, max_length=300)
    secret_ref: SecretRef = GOOGLE_DRIVE_SECRET_REF
    client_secret_ref: SecretRef = GOOGLE_DRIVE_CLIENT_SECRET_REF
    requested_scope: str = Field(
        default=GOOGLE_DRIVE_SCOPE,
        pattern=r"^https://www\.googleapis\.com/auth/drive\.readonly$",
    )
    # A document-create grant remains independent from Drive read: a failed
    # re-consent cannot replace a healthy read connection.
    document_write_secret_ref: SecretRef | None = None
    document_write_requested_scope: str | None = Field(
        default=None,
        pattern=r"^https://www\.googleapis\.com/auth/(?:drive\.file|documents)$",
    )
    account_label: str | None = Field(default=None, max_length=200)

    def credential_state(self, secret_store) -> ConnectorCredentialState:
        if not secret_store.exists(self.secret_ref) or not secret_store.exists(self.client_secret_ref):
            return ConnectorCredentialState.NEEDS_RECONNECT
        return ConnectorCredentialState.READY

    def document_write_credential_state(self, secret_store) -> ConnectorCredentialState:
        if self.document_write_secret_ref is None or self.document_write_requested_scope is None:
            return ConnectorCredentialState.DISCONNECTED
        if self.document_write_requested_scope != GOOGLE_DRIVE_DOCUMENT_WRITE_SCOPE:
            return ConnectorCredentialState.NEEDS_RECONNECT
        if not secret_store.exists(self.document_write_secret_ref) or not secret_store.exists(self.client_secret_ref):
            return ConnectorCredentialState.NEEDS_RECONNECT
        return ConnectorCredentialState.READY


class GoogleDriveConfigStore:
    """Stores only safe connector metadata, never OAuth material."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> GoogleDriveConfig | None:
        if not self.path.exists():
            return None
        return GoogleDriveConfig.model_validate_json(self.path.read_bytes())

    def save(self, config: GoogleDriveConfig) -> GoogleDriveConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return config

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)
