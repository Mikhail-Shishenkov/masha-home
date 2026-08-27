from types import SimpleNamespace

import pytest

from backend.application.home_capabilities import (
    HomeCapabilityApplicationService,
    HomeCapabilitySnapshot,
)
from backend.conversation.conversation_service import ground_completed_capability_claims
from backend.external_observation import InternetAccessMode


class _Connections:
    def __init__(self, states):
        self.states = states
        self.calls = 0

    def view(self):
        self.calls += 1
        return tuple(
            SimpleNamespace(connector_id=connector_id, state=state)
            for connector_id, state in self.states.items()
        )


def _capabilities(*, mode=InternetAccessMode.EXPLICIT, emergency=False, connection_state="ready"):
    connections = _Connections({
        "google-calendar": connection_state,
        "google-drive": connection_state,
        "yandex-mail": connection_state,
        "yandex-disk": connection_state,
    })
    service = HomeCapabilityApplicationService(
        connections=connections,
        internet_policy=SimpleNamespace(load=lambda: SimpleNamespace(mode=mode)),
        safety_store=SimpleNamespace(is_engaged=lambda: emergency),
        proactive_policy=SimpleNamespace(load=lambda: SimpleNamespace(
            enabled=True,
            allow_commitment_reminders=True,
        )),
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
