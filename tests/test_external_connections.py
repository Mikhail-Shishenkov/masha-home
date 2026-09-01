from backend.application.external_connections import ExternalConnectionApplicationService
from backend.connectors.google_calendar.config import (
    GOOGLE_CALENDAR_WRITE_SCOPE, GOOGLE_CALENDAR_WRITE_SECRET_REF,
    GoogleCalendarConfig, GoogleCalendarConfigStore,
)
from backend.connectors.google_drive.config import (
    GOOGLE_DOCUMENTS_WRITE_SCOPE, GOOGLE_DOCUMENTS_WRITE_SECRET_REF,
    GoogleDriveConfig, GoogleDriveConfigStore,
)
from backend.connectors.yandex_disk.config import YandexDiskConfig, YandexDiskConfigStore
from backend.connectors.yandex_mail.config import (
    YANDEX_MAIL_WRITE_SCOPE,
    YANDEX_MAIL_WRITE_SECRET_REF,
    YandexMailConfig,
    YandexMailConfigStore,
)
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


def test_calendar_connection_projects_separate_read_and_create_truth(tmp_path):
    secrets = InMemorySecretStore()
    service, stores = _service(tmp_path, secrets)
    calendar = GoogleCalendarConfig(client_id="calendar-client-identifier")
    stores["google-calendar"].save(calendar)
    secrets.put(calendar.secret_ref, "READ_TOKEN")
    secrets.put(calendar.client_secret_ref, "CLIENT_SECRET")
    row = next(item for item in service.view() if item.connector_id == "google-calendar")
    assert (row.state, row.access) == ("ready", "read_with_create_setup")
    configured = calendar.model_copy(update={
        "write_secret_ref": GOOGLE_CALENDAR_WRITE_SECRET_REF,
        "write_requested_scope": GOOGLE_CALENDAR_WRITE_SCOPE,
    })
    stores["google-calendar"].save(configured)
    secrets.put(GOOGLE_CALENDAR_WRITE_SECRET_REF, "WRITE_TOKEN")
    row = next(item for item in service.view() if item.connector_id == "google-calendar")
    assert (row.state, row.access) == ("ready", "read_and_create")
    secrets.delete(GOOGLE_CALENDAR_WRITE_SECRET_REF)
    row = next(item for item in service.view() if item.connector_id == "google-calendar")
    assert (row.state, row.access) == ("ready", "read_with_create_setup")


def test_drive_connection_projects_separate_document_create_truth(tmp_path):
    secrets = InMemorySecretStore()
    service, stores = _service(tmp_path, secrets)
    drive = GoogleDriveConfig(client_id="drive-client-identifier")
    stores["google-drive"].save(drive)
    secrets.put(drive.secret_ref, "READ_TOKEN")
    secrets.put(drive.client_secret_ref, "CLIENT_SECRET")
    row = next(item for item in service.view() if item.connector_id == "google-drive")
    assert (row.state, row.access) == ("ready", "read_with_document_create_setup")
    configured = drive.model_copy(update={"document_write_secret_ref": GOOGLE_DOCUMENTS_WRITE_SECRET_REF, "document_write_requested_scope": GOOGLE_DOCUMENTS_WRITE_SCOPE})
    stores["google-drive"].save(configured)
    secrets.put(GOOGLE_DOCUMENTS_WRITE_SECRET_REF, "WRITE_TOKEN")
    row = next(item for item in service.view() if item.connector_id == "google-drive")
    assert (row.state, row.access) == ("ready", "read_and_document_create")


def test_mail_connection_projects_separate_manage_truth(tmp_path):
    secrets = InMemorySecretStore()
    service, stores = _service(tmp_path, secrets)
    mail = YandexMailConfig(
        client_id="mail-client",
        account_email="misha@example.com",
    )
    stores["yandex-mail"].save(mail)
    secrets.put(mail.secret_ref, "READ_TOKEN")
    secrets.put(mail.client_secret_ref, "CLIENT_SECRET")
    row = next(
        item for item in service.view() if item.connector_id == "yandex-mail"
    )
    assert (row.state, row.access) == ("ready", "read_with_manage_setup")

    configured = mail.model_copy(update={
        "write_secret_ref": YANDEX_MAIL_WRITE_SECRET_REF,
        "write_requested_scope": YANDEX_MAIL_WRITE_SCOPE,
    })
    stores["yandex-mail"].save(configured)
    secrets.put(YANDEX_MAIL_WRITE_SECRET_REF, "WRITE_TOKEN")
    row = next(
        item for item in service.view() if item.connector_id == "yandex-mail"
    )
    assert (row.state, row.access) == ("ready", "read_and_manage")
