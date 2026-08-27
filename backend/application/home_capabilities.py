"""Local, descriptive Home capability projection for conversation context."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.external_observation.policy import InternetAccessMode

from .capability_catalog import (
    CapabilityAvailability,
    CapabilityCatalog,
    CapabilityCatalogSnapshot,
    CapabilityDescriptor,
    CapabilityEffect,
    CapabilityOperationKind,
    CapabilityRisk,
)


_LEGACY_OPERATION_IDS = {
    "web_search": "web.search",
    "web_fetch": "web.fetch",
    "google_calendar_read": "google_calendar.read",
    "google_calendar_create": "google_calendar.event.create",
    "google_calendar_update": "google_calendar.event.update",
    "google_drive_read": "google_drive.read",
    "google_drive_document_create": "google_drive.document.create",
    "yandex_mail_read": "yandex_mail.read",
    "yandex_disk_read": "yandex_disk.read",
    "commitments": "home.commitments",
    "timed_commitments": "home.timed_commitments",
    "proactive_reminders": "home.proactive_reminders",
}


def default_home_capability_catalog() -> CapabilityCatalog:
    read = dict(
        kind=CapabilityOperationKind.READ,
        effect=CapabilityEffect.READ_ONLY,
        risk=CapabilityRisk.OBSERVE,
    )
    return CapabilityCatalog((
        CapabilityDescriptor(
            operation_id="web.search", display_name="Поиск в интернете",
            family="web", **read,
        ),
        CapabilityDescriptor(
            operation_id="web.fetch", display_name="Чтение веб-страницы",
            family="web", **read,
        ),
        CapabilityDescriptor(
            operation_id="google_calendar.read",
            display_name="Чтение Google Calendar",
            family="google_calendar", **read,
        ),
        CapabilityDescriptor(
            operation_id="google_calendar.event.create",
            display_name="Создание события Google Calendar",
            family="google_calendar", kind=CapabilityOperationKind.CREATE,
            effect=CapabilityEffect.EXTERNAL_MUTATION,
            risk=CapabilityRisk.CONSEQUENTIAL, verification_required=True,
        ),
        CapabilityDescriptor(
            operation_id="google_calendar.event.update",
            display_name="Изменение события Google Calendar",
            family="google_calendar", kind=CapabilityOperationKind.UPDATE,
            effect=CapabilityEffect.EXTERNAL_MUTATION,
            risk=CapabilityRisk.CONSEQUENTIAL, verification_required=True,
        ),
        CapabilityDescriptor(
            operation_id="google_drive.read", display_name="Чтение Google Drive",
            family="google_drive", **read,
        ),
        CapabilityDescriptor(
            operation_id="google_drive.document.create",
            display_name="Создание документа Google Drive",
            family="google_drive", kind=CapabilityOperationKind.CREATE,
            effect=CapabilityEffect.EXTERNAL_MUTATION,
            risk=CapabilityRisk.CONSEQUENTIAL, verification_required=True,
        ),
        CapabilityDescriptor(
            operation_id="yandex_mail.read", display_name="Чтение Яндекс Почты",
            family="yandex_mail", **read,
        ),
        CapabilityDescriptor(
            operation_id="yandex_disk.read", display_name="Чтение Яндекс Диска",
            family="yandex_disk", **read,
        ),
        CapabilityDescriptor(
            operation_id="home.commitments", display_name="Домашние дела",
            family="home", kind=CapabilityOperationKind.MANAGE,
            effect=CapabilityEffect.LOCAL_MUTATION,
            risk=CapabilityRisk.REVERSIBLE, verification_required=True,
            agent_eligible=True,
        ),
        CapabilityDescriptor(
            operation_id="home.timed_commitments", display_name="Дела со сроком",
            family="home", kind=CapabilityOperationKind.MANAGE,
            effect=CapabilityEffect.LOCAL_MUTATION,
            risk=CapabilityRisk.REVERSIBLE, verification_required=True,
            proactive_eligible=True, agent_eligible=True,
        ),
        CapabilityDescriptor(
            operation_id="home.proactive_reminders",
            display_name="Напоминания Дома", family="home",
            kind=CapabilityOperationKind.OBSERVE,
            effect=CapabilityEffect.READ_ONLY, risk=CapabilityRisk.OBSERVE,
            proactive_eligible=True,
        ),
    ))


class HomeCapabilitySnapshot(BaseModel):
    """Safe capability truth.  States describe availability and grant nothing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    web_search: str
    web_fetch: str
    google_calendar_read: str
    google_calendar_create: str = "unavailable"
    google_calendar_update: str = "unavailable"
    google_drive_read: str
    google_drive_document_create: str = "unavailable"
    yandex_mail_read: str
    yandex_disk_read: str
    commitments: str = "available"
    timed_commitments: str = "available"
    proactive_reminders: str


class HomeCapabilityApplicationService:
    """Derive model-safe state locally; provider calls are deliberately impossible."""

    def __init__(
        self,
        *,
        connections,
        internet_policy,
        safety_store,
        proactive_policy,
        catalog: CapabilityCatalog | None = None,
    ):
        self._connections = connections
        self._internet_policy = internet_policy
        self._safety_store = safety_store
        self._proactive_policy = proactive_policy
        self._catalog = catalog or default_home_capability_catalog()

    def snapshot(self) -> HomeCapabilitySnapshot:
        generic = self.catalog_snapshot()
        states = {
            item.operation.operation_id: item.availability.value
            for item in generic.operations
        }
        return HomeCapabilitySnapshot(**{
            field: states[operation_id]
            for field, operation_id in _LEGACY_OPERATION_IDS.items()
        })

    def catalog_snapshot(self) -> CapabilityCatalogSnapshot:
        """Describe current availability; this method never grants authority."""

        safety_blocked = self._safety_store.is_engaged()
        internet_off = self._internet_policy.load().mode is InternetAccessMode.OFF
        web_state = (
            CapabilityAvailability.BLOCKED
            if safety_blocked or internet_off
            else CapabilityAvailability.AVAILABLE
        )
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
        drive_connection = next(row for row in connection_rows if row.connector_id == "google-drive")
        drive_create = self._connector_capability_state(
            "ready" if getattr(drive_connection, "access", "read_only") == "read_and_document_create" else "needs_reconnect",
            safety_blocked, internet_off,
        )
        proactive = self._proactive_policy.load()
        reminder_state = (
            CapabilityAvailability.BLOCKED
            if safety_blocked or not proactive.enabled or not proactive.allow_commitment_reminders
            else CapabilityAvailability.AVAILABLE
        )
        return self._catalog.snapshot({
            "web.search": web_state,
            "web.fetch": web_state,
            "google_calendar.read": connector_states["google-calendar"],
            "google_calendar.event.create": calendar_create,
            "google_calendar.event.update": calendar_create,
            "google_drive.read": connector_states["google-drive"],
            "google_drive.document.create": drive_create,
            "yandex_mail.read": connector_states["yandex-mail"],
            "yandex_disk.read": connector_states["yandex-disk"],
            "home.commitments": CapabilityAvailability.AVAILABLE,
            "home.timed_commitments": CapabilityAvailability.AVAILABLE,
            "home.proactive_reminders": reminder_state,
        })

    @staticmethod
    def _connector_capability_state(config_state: str, safety_blocked: bool, internet_off: bool) -> CapabilityAvailability:
        if config_state == "disconnected":
            return CapabilityAvailability.UNAVAILABLE
        if config_state != "ready":
            return CapabilityAvailability.NEEDS_RECONNECT
        return (
            CapabilityAvailability.BLOCKED
            if safety_blocked or internet_off
            else CapabilityAvailability.AVAILABLE
        )
