from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.connectors import google_drive_cli
from backend.connectors.google_calendar.oauth import OAuthTokens
from backend.connectors.google_drive.config import GoogleDriveConfig, GoogleDriveConfigStore, GOOGLE_DRIVE_SCOPE
from backend.connectors.google_drive.network import GoogleDriveNetworkBlocked
from backend.connectors.google_drive.reader import (
    DriveFileCandidate,
    GoogleDriveDocumentTooLarge,
    GoogleDriveReader,
    GoogleDriveTokenInvalidGrant,
    GoogleDriveUnavailable,
    ResolvedDriveDocumentRequest,
)
from backend.connectors.google_drive.service import GoogleDriveConversationService
from backend.document_read import DocumentReader
from backend.document_read.reader import MAX_RAW_PDF_BYTES
from backend.external_observation.policy import InternetAccessMode, InternetAccessPolicy, InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.secrets import InMemorySecretStore
from backend.secrets import ConnectorCredentialState


def _pdf(text: str = "Drive evidence.") -> bytes:
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    target = BytesIO()
    writer.write(target)
    return target.getvalue()


class FakeTransport:
    def __init__(self, *, pages=(), document=b"%PDF- fake"):
        self.pages = list(pages)
        self.document = document
        self.calls = []

    def request_json(self, url, *, method="GET", headers=None, body=None):
        self.calls.append(("json", url, method, headers or {}, body))
        if "oauth2.googleapis.com/token" in url:
            return {"access_token": "ACCESS_TOKEN_MUST_NOT_ESCAPE"}
        return self.pages.pop(0) if self.pages else {"files": []}

    def download(self, url, *, headers=None, maximum_bytes):
        self.calls.append(("download", url, headers or {}, maximum_bytes))
        if len(self.document) > maximum_bytes:
            raise GoogleDriveDocumentTooLarge("too_large")
        return self.document


def _reader(tmp_path: Path, transport=None):
    config_store = GoogleDriveConfigStore(tmp_path / "local-data/config/google-drive.json")
    config = GoogleDriveConfig(client_id="desktop-client-identifier")
    config_store.save(config)
    secrets = InMemorySecretStore()
    secrets.put(config.secret_ref, "DRIVE_REFRESH_TOKEN_MUST_NOT_ESCAPE")
    secrets.put(config.client_secret_ref, "DRIVE_CLIENT_SECRET_MUST_NOT_ESCAPE")
    return GoogleDriveReader(config_store=config_store, secret_store=secrets, transport=transport or FakeTransport(document=_pdf())), config_store, secrets


def _files(*rows):
    return {"files": [
        {"id": file_id, "name": name, "mimeType": mime_type, "modifiedTime": "2026-08-24T10:00:00Z", "size": size}
        for file_id, name, mime_type, size in rows
    ]}


def test_drive_scope_and_safe_config_credentials(tmp_path: Path):
    reader, config_store, secrets = _reader(tmp_path)
    config = config_store.load()
    saved = config_store.path.read_text(encoding="utf-8")
    assert config.requested_scope == GOOGLE_DRIVE_SCOPE
    assert secrets.get(config.secret_ref) == "DRIVE_REFRESH_TOKEN_MUST_NOT_ESCAPE"
    assert secrets.get(config.client_secret_ref) == "DRIVE_CLIENT_SECRET_MUST_NOT_ESCAPE"
    assert "DRIVE_REFRESH_TOKEN_MUST_NOT_ESCAPE" not in saved
    assert "DRIVE_CLIENT_SECRET_MUST_NOT_ESCAPE" not in saved
    assert reader.search("SQL").status == "no_files"


def test_explicit_yandex_disk_never_routes_to_google_drive_but_drive_list_still_works(tmp_path: Path):
    from backend.connectors.google_drive.intent import drive_intent
    assert drive_intent("покажи последние файлы на Яндекс Диске") is None
    assert drive_intent("покажи файлы в Драйве").kind == "list"
    transport = FakeTransport(pages=[_files(("id-1", "Plan", "application/pdf", "100"))])
    reader, _, _ = _reader(tmp_path, transport)
    outcome = reader.search("")
    assert outcome.status == "search_completed" and outcome.files[0].name == "Plan"
    call = next(item for item in transport.calls if item[0] == "json" and "/drive/v3/files?" in item[1])
    assert "trashed+%3D+false" in call[1]


def test_restored_drive_metadata_without_credentials_needs_reconnect(tmp_path: Path):
    config = GoogleDriveConfig(client_id="desktop-client-identifier")
    missing = InMemorySecretStore()
    ready = InMemorySecretStore()
    ready.put(config.secret_ref, "DRIVE_REFRESH_TOKEN_MUST_NOT_ESCAPE")
    ready.put(config.client_secret_ref, "DRIVE_CLIENT_SECRET_MUST_NOT_ESCAPE")
    assert config.credential_state(missing) is ConnectorCredentialState.NEEDS_RECONNECT
    assert config.credential_state(ready) is ConnectorCredentialState.READY


def test_search_is_bounded_paginated_escaped_and_model_safe(tmp_path: Path):
    first = _files(*[(f"id-{index}", f"SQL {index}", "application/pdf", "100") for index in range(6)])
    first["nextPageToken"] = "next"
    second = _files(*[(f"id-x{index}", f"SQL x{index}", "application/pdf", "100") for index in range(6)])
    transport = FakeTransport(pages=[first, second], document=_pdf())
    reader, _, _ = _reader(tmp_path, transport)
    outcome = reader.search("SQL 'quoted' \\ test")
    assert outcome.status == "search_completed"
    assert len(outcome.files) == reader.MAX_RESULTS == 10
    search_urls = [call[1] for call in transport.calls if call[0] == "json" and "/drive/v3/files?" in call[1]]
    assert len(search_urls) == 2 and "pageToken=next" in search_urls[1]
    assert "%5C%27" in search_urls[0] and "%5C%5C" in search_urls[0]
    serialized = json.dumps(outcome.model_context(), ensure_ascii=False)
    assert "id-" not in serialized and "ACCESS_TOKEN_MUST_NOT_ESCAPE" not in serialized


@pytest.mark.parametrize(("mime_type", "url_fragment"), [
    ("application/pdf", "?alt=media"),
    ("application/vnd.google-apps.document", "/export?"),
    ("application/vnd.google-apps.spreadsheet", "/export?"),
    ("application/vnd.google-apps.presentation", "/export?"),
])
def test_supported_drive_files_reuse_document_reader(tmp_path: Path, mime_type: str, url_fragment: str):
    transport = FakeTransport(document=_pdf("Bounded Drive document."))
    reader, _, _ = _reader(tmp_path, transport)
    file = DriveFileCandidate("file-1", "План", mime_type, None, 100, True)
    outcome = reader.read_file(file)
    assert outcome.status == "read_completed"
    assert outcome.document_receipt is not None
    assert outcome.resolved_document_request == ResolvedDriveDocumentRequest(display_name="План")
    assert outcome.document_receipt.source_kind.value == "connector"
    assert outcome.document_receipt.evidence.pages[0].text == "Bounded Drive document."
    download = next(call for call in transport.calls if call[0] == "download")
    assert url_fragment in download[1]


def test_unsupported_and_oversized_drive_documents_are_controlled(tmp_path: Path):
    transport = FakeTransport(document=_pdf())
    reader, _, _ = _reader(tmp_path, transport)
    unsupported = reader.read_file(DriveFileCandidate("binary", "Archive", "application/zip", None, 10, False))
    oversized = reader.read_file(DriveFileCandidate("large", "Large", "application/pdf", None, MAX_RAW_PDF_BYTES + 1, True))
    assert unsupported.status == "unsupported_format"
    assert oversized.status == "document_too_large"
    assert transport.calls == []


def test_network_off_and_emergency_stop_make_zero_drive_calls(tmp_path: Path):
    transport = FakeTransport(document=_pdf())
    reader, _, _ = _reader(tmp_path, transport)
    policy = InternetAccessPolicyStore(tmp_path / "local-data/config/internet-access.json")
    reader.policy_store = policy
    policy.save(InternetAccessPolicy(mode=InternetAccessMode.OFF))
    assert reader.search("SQL").status == "unavailable"
    assert transport.calls == []
    policy.save(InternetAccessPolicy())
    safety = AutonomySafetyStore(tmp_path / "local-data/config/autonomy-safety.json")
    reader.safety_store = safety
    AutonomySafetyService(store=safety).engage()
    assert reader.search("SQL").status == "unavailable"
    assert transport.calls == []


def test_invalid_grant_deletes_refresh_but_drive_api_failure_does_not(tmp_path: Path):
    reader, config_store, secrets = _reader(tmp_path)
    class InvalidGrant(FakeTransport):
        def request_json(self, url, **kwargs):
            if "token" in url:
                raise GoogleDriveTokenInvalidGrant("invalid_grant")
            return super().request_json(url, **kwargs)
    reader.transport = InvalidGrant(document=_pdf())
    assert reader.search("SQL").status == "needs_reconnect"
    assert secrets.exists(config_store.load().secret_ref) is False

    reader, config_store, secrets = _reader(tmp_path / "drive-api")
    class Drive400(FakeTransport):
        def request_json(self, url, **kwargs):
            if "/drive/v3/" in url:
                raise GoogleDriveUnavailable("drive_http_400")
            return super().request_json(url, **kwargs)
    reader.transport = Drive400(document=_pdf())
    assert reader.search("SQL").status == "unavailable"
    assert secrets.exists(config_store.load().secret_ref) is True


def test_conversation_scoped_ordinal_and_exact_file_selection():
    first = DriveFileCandidate("first", "План обучения", "application/pdf", None, 100, True)
    second = DriveFileCandidate("second", "SQL заметки", "application/pdf", None, 100, True)
    class Reader:
        def __init__(self): self.reads = []
        def search(self, _query): return type("Found", (), {"status": "search_completed", "files": (first, second)})()
        def read_file(self, file): self.reads.append(file.file_id); return type("Read", (), {"status": "read_completed", "files": (), "document_receipt": object()})()
    reader = Reader()
    service = GoogleDriveConversationService(reader=reader)
    found = service.observe("найди документы про SQL", conversation_id="conversation-a")
    assert found.files == (first, second)
    assert service.observe("прочитай второй", conversation_id="conversation-a").status == "read_completed"
    assert reader.reads == ["second"]
    assert service.observe("прочитай второй", conversation_id="conversation-b") is None
    assert service.observe("прочитай файл План обучения", conversation_id="conversation-a").status == "read_completed"
    assert reader.reads == ["second", "first"]


def test_search_and_tell_me_what_is_there_reads_only_one_resolved_file():
    file = DriveFileCandidate("sql", "SQL план", "application/pdf", None, 100, True)
    class Reader:
        def __init__(self): self.reads = []
        def search(self, query):
            assert query == "sql"
            return type("Found", (), {"status": "search_completed", "files": (file,)})()
        def read_file(self, item): self.reads.append(item.file_id); return type("Read", (), {"status": "read_completed", "files": (), "document_receipt": object()})()
    reader = Reader()
    outcome = GoogleDriveConversationService(reader=reader).observe(
        "Найди файл про SQL и скажи, что там", conversation_id="conversation-a",
    )
    assert outcome.status == "read_completed" and reader.reads == ["sql"]


def test_cli_connect_and_disconnect_keep_drive_credentials_only_in_secret_store(tmp_path: Path, monkeypatch):
    client_json = tmp_path / "client.json"
    client_json.write_text(json.dumps({"installed": {"client_id": "desktop-client-identifier", "client_secret": "DRIVE_CLIENT_SECRET_MUST_NOT_ESCAPE"}}), encoding="utf-8")
    secrets = InMemorySecretStore()
    class Flow:
        def __init__(self, **_kwargs): pass
        def authorize(self, config, *, client_secret, timeout_seconds=180.0):
            assert config.requested_scope == GOOGLE_DRIVE_SCOPE
            assert client_secret == "DRIVE_CLIENT_SECRET_MUST_NOT_ESCAPE"
            return OAuthTokens(refresh_token="DRIVE_REFRESH_TOKEN_MUST_NOT_ESCAPE")
    monkeypatch.setattr(google_drive_cli, "WindowsCredentialManagerSecretStore", lambda: secrets)
    monkeypatch.setattr(google_drive_cli, "GoogleDesktopOAuthFlow", Flow)
    assert google_drive_cli.main(["--project-root", str(tmp_path), "connect", "--client-json", str(client_json)]) == 0
    config = GoogleDriveConfigStore(tmp_path / "local-data/config/google-drive.json").load()
    saved = (tmp_path / "local-data/config/google-drive.json").read_text(encoding="utf-8")
    assert secrets.exists(config.secret_ref) and secrets.exists(config.client_secret_ref)
    assert "DRIVE_CLIENT_SECRET_MUST_NOT_ESCAPE" not in saved and "DRIVE_REFRESH_TOKEN_MUST_NOT_ESCAPE" not in saved
    google_drive_cli.disconnect_google_drive(config_store=GoogleDriveConfigStore(tmp_path / "local-data/config/google-drive.json"), secret_store=secrets)
    assert not secrets.exists(config.secret_ref) and not secrets.exists(config.client_secret_ref)
