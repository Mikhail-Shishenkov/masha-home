"""Quiet, local-only projection of independently connected read services."""

from __future__ import annotations

from backend.secrets import ConnectorCredentialState

from .contracts import ExternalConnectionView


class ExternalConnectionApplicationService:
    """Read config and Credential Manager state without contacting a provider."""

    _ROWS = (
        ("google-calendar", "Google Calendar"),
        ("google-drive", "Google Drive"),
        ("yandex-mail", "Яндекс Почта"),
        ("yandex-disk", "Яндекс Диск"),
    )

    def __init__(self, *, config_stores: dict[str, object], secret_store):
        self._config_stores = config_stores
        self._secret_store = secret_store

    def view(self) -> tuple[ExternalConnectionView, ...]:
        return tuple(
            ExternalConnectionView(
                connector_id=connector_id,
                display_name=display_name,
                state=self._state(connector_id),
                access=self._access(connector_id),
            )
            for connector_id, display_name in self._ROWS
        )

    def _state(self, connector_id: str) -> str:
        store = self._config_stores[connector_id]
        try:
            config = store.load()
            if config is None:
                return "disconnected"
            state = config.credential_state(self._secret_store)
        except Exception:
            # Existing metadata that cannot be safely used must reconnect; do
            # not inspect a provider or reveal configuration diagnostics here.
            return "needs_reconnect"
        return (
            "ready"
            if state is ConnectorCredentialState.READY
            else "needs_reconnect"
        )

    def _access(self, connector_id: str) -> str:
        if connector_id != "google-calendar":
            return "read_only"
        try:
            config = self._config_stores[connector_id].load()
            if config is None:
                return "read_only"
            return (
                "read_and_create"
                if config.write_credential_state(self._secret_store) is ConnectorCredentialState.READY
                else "read_with_create_setup"
            )
        except Exception:
            return "read_with_create_setup"
