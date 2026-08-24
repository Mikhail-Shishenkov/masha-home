"""Secret-free local configuration for the one Google Calendar connector."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from backend.secrets import ConnectorCredentialMetadata, SecretRef


GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GOOGLE_CALENDAR_SECRET_REF = SecretRef(value="google-calendar-primary")


class GoogleCalendarConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str = Field(default="google-calendar", pattern=r"^google-calendar$")
    client_id: str = Field(min_length=10, max_length=300)
    client_secret: str | None = Field(default=None, min_length=1, max_length=300)
    secret_ref: SecretRef = GOOGLE_CALENDAR_SECRET_REF
    requested_scope: str = Field(default=GOOGLE_CALENDAR_SCOPE, pattern=r"^https://www\.googleapis\.com/auth/calendar\.readonly$")
    account_label: str | None = Field(default=None, max_length=200)

    def credential_metadata(self) -> ConnectorCredentialMetadata:
        return ConnectorCredentialMetadata(connector_id=self.connector_id, secret_ref=self.secret_ref)


class GoogleCalendarConfigStore:
    """Stores only reconnectable connector metadata, never OAuth tokens."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> GoogleCalendarConfig | None:
        if not self.path.exists():
            return None
        return GoogleCalendarConfig.model_validate_json(self.path.read_bytes())

    def save(self, config: GoogleCalendarConfig) -> GoogleCalendarConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return config

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)
