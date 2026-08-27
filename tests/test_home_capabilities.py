from types import SimpleNamespace

import pytest

from backend.application.home_capabilities import (
    HomeCapabilityApplicationService,
    HomeCapabilitySnapshot,
)
from backend.conversation.conversation_service import ground_completed_capability_claims
from backend.external_observation import InternetAccessMode


class _Connections:
    def __init__(self, states, access=None):
        self.states = states
        self.access = access or {}
        self.calls = 0

    def view(self):
        self.calls += 1
        return tuple(
            SimpleNamespace(
                connector_id=connector_id,
                state=state,
                access=self.access.get(connector_id, "read_only"),
            )
            for connector_id, state in self.states.items()
        )


def _capabilities(
    *,
    mode=InternetAccessMode.EXPLICIT,
    emergency=False,
    connection_state="ready",
    calendar_access="read_only",
    drive_access="read_only",
    proactive_enabled=True,
    reminders_enabled=True,
    catalog=None,
):
    connections = _Connections({
        "google-calendar": connection_state,
        "google-drive": connection_state,
        "yandex-mail": connection_state,
        "yandex-disk": connection_state,
    }, access={
        "google-calendar": calendar_access,
        "google-drive": drive_access,
    })
    service = HomeCapabilityApplicationService(
        connections=connections,
        internet_policy=SimpleNamespace(load=lambda: SimpleNamespace(mode=mode)),
        safety_store=SimpleNamespace(is_engaged=lambda: emergency),
        proactive_policy=SimpleNamespace(load=lambda: SimpleNamespace(
            enabled=proactive_enabled,
            allow_commitment_reminders=reminders_enabled,
        )),
        catalog=catalog,
    )
    return service, connections


def test_capability_snapshot_is_local_descriptive_and_connector_aware():
    service, connections = _capabilities()

    snapshot = service.snapshot()

    assert snapshot.web_search == "available"
    assert snapshot.yandex_mail_read == "available"
    assert snapshot.timed_commitments == "available"
    assert snapshot.proactive_reminders == "available"
    assert connections.calls == 1
    assert "secret" not in snapshot.model_dump_json().casefold()


@pytest.mark.parametrize("mode, emergency", (
    (InternetAccessMode.OFF, False),
    (InternetAccessMode.EXPLICIT, True),
))
def test_network_policy_or_emergency_stop_blocks_external_capability_truth(mode, emergency):
    service, _ = _capabilities(mode=mode, emergency=emergency)

    snapshot = service.snapshot()

    assert snapshot.web_search == "blocked"
    assert snapshot.google_calendar_read == "blocked"
    assert snapshot.proactive_reminders == ("blocked" if emergency else "available")


def test_missing_connector_secret_projects_reconnect_without_provider_call():
    service, connections = _capabilities(connection_state="needs_reconnect")

    assert service.snapshot().google_drive_read == "needs_reconnect"
    assert connections.calls == 1


def test_completed_web_receipt_overrides_false_model_denial():
    assert ground_completed_capability_claims(
        "У меня нет доступа к интернету, но вот ответ.",
        completed_web=True,
    ).startswith("Я проверила доступные интернет-источники")
    assert ground_completed_capability_claims(
        "У меня нет доступа к интернету.",
        completed_web=False,
    ) == "У меня нет доступа к интернету."


def test_calendar_create_claim_cannot_exceed_snapshot_truth():
    from backend.conversation.conversation_service import stabilize_identity_and_capability_truth
    assert "недоступна" in stabilize_identity_and_capability_truth(
        "Я могу создать событие в календаре",
        capabilities={"google_calendar_create": "needs_reconnect"},
    )


def test_snapshot_contract_contains_only_allowlisted_states():
    snapshot = HomeCapabilitySnapshot(
        web_search="available",
        web_fetch="available",
        google_calendar_read="unavailable",
        google_calendar_create="unavailable",
        google_calendar_update="unavailable",
        google_drive_read="needs_reconnect",
        google_drive_document_create="unavailable",
        yandex_mail_read="blocked",
        yandex_disk_read="available",
        proactive_reminders="available",
    )
    assert set(snapshot.model_dump()) == {
        "web_search", "web_fetch", "google_calendar_read", "google_calendar_create", "google_calendar_update", "google_drive_read", "google_drive_document_create",
        "yandex_mail_read", "yandex_disk_read", "commitments", "timed_commitments",
        "proactive_reminders",
    }


def test_legacy_projection_is_identical_for_healthy_connected_home():
    service, _ = _capabilities(
        calendar_access="read_and_create",
        drive_access="read_and_document_create",
    )

    assert service.snapshot().model_dump() == {
        "web_search": "available",
        "web_fetch": "available",
        "google_calendar_read": "available",
        "google_calendar_create": "available",
        "google_calendar_update": "available",
        "google_drive_read": "available",
        "google_drive_document_create": "available",
        "yandex_mail_read": "available",
        "yandex_disk_read": "available",
        "commitments": "available",
        "timed_commitments": "available",
        "proactive_reminders": "available",
    }


@pytest.mark.parametrize(
    "mode, emergency, external_state, reminder_state",
    (
        (InternetAccessMode.OFF, False, "blocked", "available"),
        (InternetAccessMode.EXPLICIT, True, "blocked", "blocked"),
    ),
)
def test_legacy_projection_preserves_network_and_safety_state_logic(
    mode, emergency, external_state, reminder_state,
):
    service, _ = _capabilities(
        mode=mode,
        emergency=emergency,
        calendar_access="read_and_create",
        drive_access="read_and_document_create",
    )
    snapshot = service.snapshot().model_dump()

    assert all(snapshot[key] == external_state for key in (
        "web_search", "web_fetch", "google_calendar_read",
        "google_calendar_create", "google_calendar_update",
        "google_drive_read", "google_drive_document_create",
        "yandex_mail_read", "yandex_disk_read",
    ))
    assert snapshot["commitments"] == snapshot["timed_commitments"] == "available"
    assert snapshot["proactive_reminders"] == reminder_state


@pytest.mark.parametrize(
    "connection_state, read_state",
    (("disconnected", "unavailable"), ("needs_reconnect", "needs_reconnect")),
)
def test_legacy_projection_preserves_connector_state_vocabulary(connection_state, read_state):
    service, _ = _capabilities(connection_state=connection_state)
    snapshot = service.snapshot()

    assert snapshot.google_calendar_read == read_state
    assert snapshot.google_drive_read == read_state
    assert snapshot.yandex_mail_read == read_state
    assert snapshot.yandex_disk_read == read_state
    assert snapshot.google_calendar_create == "needs_reconnect"
    assert snapshot.google_calendar_update == "needs_reconnect"
    assert snapshot.google_drive_document_create == "needs_reconnect"


def test_legacy_projection_preserves_write_connection_and_proactive_states():
    disconnected_write, _ = _capabilities(
        calendar_access="read_only",
        drive_access="read_only",
        proactive_enabled=False,
    )
    connected_write, _ = _capabilities(
        calendar_access="read_and_create",
        drive_access="read_and_document_create",
        reminders_enabled=False,
    )

    first = disconnected_write.snapshot()
    second = connected_write.snapshot()
    assert first.google_calendar_create == first.google_calendar_update == "needs_reconnect"
    assert first.google_drive_document_create == "needs_reconnect"
    assert first.proactive_reminders == "blocked"
    assert second.google_calendar_create == second.google_calendar_update == "available"
    assert second.google_drive_document_create == "available"
    assert second.proactive_reminders == "blocked"


def test_home_service_generic_snapshot_can_include_future_operation_without_legacy_schema_change():
    from backend.application.capability_catalog import (
        CapabilityDescriptor,
        CapabilityEffect,
        CapabilityOperationKind,
        CapabilityRisk,
    )
    from backend.application.home_capabilities import default_home_capability_catalog

    catalog = default_home_capability_catalog()
    catalog.register(CapabilityDescriptor(
        operation_id="telegram.send_to_misha",
        display_name="Отправить сообщение Мише",
        family="telegram",
        kind=CapabilityOperationKind.CREATE,
        effect=CapabilityEffect.EXTERNAL_MUTATION,
        risk=CapabilityRisk.CONSEQUENTIAL,
        verification_required=True,
    ))
    service, _ = _capabilities(catalog=catalog)

    generic = service.catalog_snapshot()
    legacy = service.snapshot()

    assert generic.get("telegram.send_to_misha").availability.value == "unavailable"
    assert "telegram_send_to_misha" not in type(legacy).model_fields
