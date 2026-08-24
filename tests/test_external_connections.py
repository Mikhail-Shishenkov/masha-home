from backend.application.external_connections import ExternalConnectionApplicationService
from backend.connectors.google_calendar.config import GoogleCalendarConfig, GoogleCalendarConfigStore
from backend.connectors.google_drive.config import GoogleDriveConfig, GoogleDriveConfigStore
from backend.connectors.yandex_disk.config import YandexDiskConfig, YandexDiskConfigStore
from backend.connectors.yandex_mail.config import YandexMailConfig, YandexMailConfigStore
from backend.secrets import InMemorySecretStore


def _service(tmp_path, secrets):
    stores = {
        "google-calendar": GoogleCalendarConfigStore(tmp_path / "google-calendar.json"),
        "google-drive": GoogleDriveConfigStore(tmp_path / "google-drive.json"),
        "yandex-mail": YandexMailConfigStore(tmp_path / "yandex-mail.json"),
        "yandex-disk": YandexDiskConfigStore(tmp_path / "yandex-disk.json"),
    }
    return ExternalConnectionApplicationService(config_stores=stores, secret_store=secrets), stores


def test_connection_shelf_is_local_safe_and_keeps_every_service_separate(tmp_path):
    secrets = InMemorySecretStore()
    service, stores = _service(tmp_path, secrets)

    disconnected = service.view()
    assert [item.connector_id for item in disconnected] == [
        "google-calendar", "google-drive", "yandex-mail", "yandex-disk",
    ]
    assert {item.state for item in disconnected} == {"disconnected"}
    assert {item.access for item in disconnected} == {"read_only"}

    calendar = GoogleCalendarConfig(client_id="calendar-client-identifier")
    drive = GoogleDriveConfig(client_id="drive-client-identifier")
    mail = YandexMailConfig(client_id="mail-client", account_email="misha@example.com")
    disk = YandexDiskConfig(client_id="disk-client")
    for key, config in (("google-calendar", calendar), ("google-drive", drive), ("yandex-mail", mail), ("yandex-disk", disk)):
        stores[key].save(config)
        secrets.put(config.secret_ref, f"{key}-refresh-secret")
        secrets.put(config.client_secret_ref, f"{key}-client-secret")

    ready = service.view()
    assert {item.state for item in ready} == {"ready"}
    rendered = [item.model_dump() for item in ready]
    serialized = str(rendered)
    assert "secret_ref" not in serialized and "client_id" not in serialized
    assert "refresh-secret" not in serialized and "client-secret" not in serialized

    secrets.delete(drive.secret_ref)
    states = {item.connector_id: item.state for item in service.view()}
    assert states["google-drive"] == "needs_reconnect"
    assert states["google-calendar"] == "ready"
