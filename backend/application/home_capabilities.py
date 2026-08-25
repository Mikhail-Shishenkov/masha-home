"""Local, descriptive Home capability projection for conversation context."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.external_observation.policy import InternetAccessMode


class HomeCapabilitySnapshot(BaseModel):
    """Safe capability truth.  States describe availability and grant nothing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    web_search: str
    web_fetch: str
    google_calendar_read: str
    google_calendar_create: str = "unavailable"
    google_drive_read: str
    yandex_mail_read: str
    yandex_disk_read: str
    commitments: str = "available"
    timed_commitments: str = "available"
    proactive_reminders: str


class HomeCapabilityApplicationService:
    """Derive model-safe state locally; provider calls are deliberately impossible."""

    def __init__(self, *, connections, internet_policy, safety_store, proactive_policy):
        self._connections = connections
        self._internet_policy = internet_policy
        self._safety_store = safety_store
        self._proactive_policy = proactive_policy

    def snapshot(self) -> HomeCapabilitySnapshot:
        safety_blocked = self._safety_store.is_engaged()
        internet_off = self._internet_policy.load().mode is InternetAccessMode.OFF
        web_state = "blocked" if safety_blocked or internet_off else "available"
        connection_rows = self._connections.view()
        connector_states = {
            row.connector_id: self._connector_capability_state(row.state, safety_blocked, internet_off)
            for row in connection_rows
        }
        calendar_connection = next(row for row in connection_rows if row.connector_id == "google-calendar")
        calendar_create = self._connector_capability_state(
            "ready" if getattr(calendar_connection, "access", "read_only") == "read_and_create" else "needs_reconnect",
            safety_blocked,
            internet_off,
        )
        proactive = self._proactive_policy.load()
        reminder_state = (
            "blocked"
            if safety_blocked or not proactive.enabled or not proactive.allow_commitment_reminders
            else "available"
        )
        return HomeCapabilitySnapshot(
            web_search=web_state,
            web_fetch=web_state,
            google_calendar_read=connector_states["google-calendar"],
            google_calendar_create=calendar_create,
            google_drive_read=connector_states["google-drive"],
            yandex_mail_read=connector_states["yandex-mail"],
            yandex_disk_read=connector_states["yandex-disk"],
            proactive_reminders=reminder_state,
        )

    @staticmethod
    def _connector_capability_state(config_state: str, safety_blocked: bool, internet_off: bool) -> str:
        if config_state == "disconnected":
            return "unavailable"
        if config_state != "ready":
            return "needs_reconnect"
        return "blocked" if safety_blocked or internet_off else "available"
