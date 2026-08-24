"""Bounded read-only Google Drive REST adapter and Document Read bridge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from backend.document_read import (
    DocumentInput,
    DocumentReadError,
    DocumentReader,
    DocumentReadReceipt,
    DocumentReadSourceKind,
    DocumentReadStore,
)
from backend.document_read.reader import MAX_RAW_PDF_BYTES

from .config import GoogleDriveConfig, GoogleDriveConfigStore
from .network import GoogleDriveNetworkBlocked, assert_google_drive_network_allowed


class GoogleDriveTransport(Protocol):
    def request_json(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict: ...
    def download(self, url: str, *, headers: dict[str, str] | None = None, maximum_bytes: int) -> bytes: ...


class GoogleDriveUnavailable(RuntimeError):
    pass


class GoogleDriveTokenInvalidGrant(RuntimeError):
    pass


class GoogleDriveDocumentTooLarge(RuntimeError):
    pass


class UrllibGoogleDriveTransport:
    """Small HTTPS JSON/bytes transport; response bodies are never logged or stored."""

    _MAX_JSON_BYTES = 2 * 1024 * 1024

    def request_json(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict:
        request = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=12) as response:
                raw = response.read(self._MAX_JSON_BYTES + 1)
        except HTTPError as error:
            if "/token" in url and error.code == 400 and _token_error_is_invalid_grant(error):
                raise GoogleDriveTokenInvalidGrant("google_drive_reconnect_required") from error
            raise GoogleDriveUnavailable("google_drive_unavailable") from error
        except (URLError, OSError) as error:
            raise GoogleDriveUnavailable("google_drive_unavailable") from error
        if len(raw) > self._MAX_JSON_BYTES:
            raise GoogleDriveUnavailable("google_drive_unavailable")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as error:
            raise GoogleDriveUnavailable("google_drive_unavailable") from error
        if not isinstance(payload, dict):
            raise GoogleDriveUnavailable("google_drive_unavailable")
        return payload

    def download(self, url: str, *, headers: dict[str, str] | None = None, maximum_bytes: int) -> bytes:
        request = Request(url, headers=headers or {}, method="GET")
        try:
            with urlopen(request, timeout=12) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None and content_length.isdigit() and int(content_length) > maximum_bytes:
                    raise GoogleDriveDocumentTooLarge("google_drive_document_too_large")
                raw = response.read(maximum_bytes + 1)
        except GoogleDriveDocumentTooLarge:
            raise
        except HTTPError as error:
            raise GoogleDriveUnavailable("google_drive_unavailable") from error
        except (URLError, OSError) as error:
            raise GoogleDriveUnavailable("google_drive_unavailable") from error
        if len(raw) > maximum_bytes:
            raise GoogleDriveDocumentTooLarge("google_drive_document_too_large")
        return raw


@dataclass(frozen=True)
class DriveFileCandidate:
    file_id: str
    name: str
    mime_type: str
    modified_at: datetime | None
    size: int | None
    readable: bool

    def model_value(self) -> dict:
        """Never disclose Drive file IDs or raw provider fields to the model."""
        return {
            "name": self.name,
            "mime_type": _human_mime_type(self.mime_type),
            "modified_at": None if self.modified_at is None else self.modified_at.isoformat(),
            "readable": self.readable,
        }


@dataclass(frozen=True)
class ResolvedDriveDocumentRequest:
    """Application-owned meaning after a Drive file reference is resolved."""

    display_name: str
    action: str = "read_selected_document"

    def model_message(self) -> str:
        return (
            f'Пользователь выбрал документ «{self.display_name}». '
            "Прочитай выбранный документ и ответь по его содержимому. "
            "Ссылка на первый, второй, третий или имя файла уже разрешена приложением "
            "как выбор файла; не трактуй её как номер раздела, пункта или страницы документа."
        )


@dataclass(frozen=True)
class DriveReadOutcome:
    status: str
    files: tuple[DriveFileCandidate, ...] = ()
    document_receipt: DocumentReadReceipt | None = None
    resolved_document_request: ResolvedDriveDocumentRequest | None = None

    def model_context(self) -> list[dict]:
        if self.status != "search_completed":
            return []
        return [{"kind": "google_drive_search", "files": [item.model_value() for item in self.files]}]


class GoogleDriveReader:
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_ROOT = "https://www.googleapis.com/drive/v3"
    MAX_RESULTS = 10
    MAX_PAGES = 2
    _PDF_MIME = "application/pdf"
    _NATIVE_EXPORTS = {
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.spreadsheet",
        "application/vnd.google-apps.presentation",
    }

    def __init__(
        self,
        *,
        config_store: GoogleDriveConfigStore,
        secret_store,
        document_reader: DocumentReader | None = None,
        document_store: DocumentReadStore | None = None,
        transport: GoogleDriveTransport | None = None,
        policy_store=None,
        safety_store=None,
        now=None,
    ):
        self.config_store = config_store
        self.secret_store = secret_store
        self.document_reader = document_reader or DocumentReader()
        self.document_store = document_store
        self.transport = transport or UrllibGoogleDriveTransport()
        self.policy_store = policy_store
        self.safety_store = safety_store
        self._now = now or (lambda: datetime.now(timezone.utc))

    def search(self, query: str) -> DriveReadOutcome:
        credentials = self._credentials()
        if isinstance(credentials, DriveReadOutcome):
            return credentials
        config, access_token = credentials
        del config
        try:
            files = self._search_files(query, access_token)
            return DriveReadOutcome("no_files" if not files else "search_completed", files=files)
        except (GoogleDriveUnavailable, GoogleDriveNetworkBlocked):
            return DriveReadOutcome("unavailable")

    def read_file(self, file: DriveFileCandidate) -> DriveReadOutcome:
        if not file.readable:
            return DriveReadOutcome("unsupported_format")
        if file.size is not None and file.size > MAX_RAW_PDF_BYTES:
            return DriveReadOutcome("document_too_large")
        credentials = self._credentials()
        if isinstance(credentials, DriveReadOutcome):
            return credentials
        _config, access_token = credentials
        try:
            url = self._content_url(file)
            raw = self._download(url, access_token)
            evidence = self.document_reader.read(DocumentInput(
                media_type="application/pdf",
                content=raw,
                source_kind=DocumentReadSourceKind.CONNECTOR,
                display_name=file.name,
                source_reference=file.file_id,
            ))
        except GoogleDriveDocumentTooLarge:
            return DriveReadOutcome("document_too_large")
        except DocumentReadError as error:
            return DriveReadOutcome("document_too_large" if error.code == "pdf_input_too_large" else "document_unreadable")
        except (GoogleDriveUnavailable, GoogleDriveNetworkBlocked):
            return DriveReadOutcome("unavailable")
        receipt = DocumentReadReceipt(
            receipt_id=f"doc_{uuid4()}",
            source_kind=DocumentReadSourceKind.CONNECTOR,
            source_reference=file.file_id,
            source_domain="drive.google.com",
            display_name=file.name,
            evidence=evidence,
            completed_at=self._now(),
        )
        if self.document_store is not None:
            receipt = self.document_store.save(receipt)
        return DriveReadOutcome(
            "read_completed",
            document_receipt=receipt,
            resolved_document_request=ResolvedDriveDocumentRequest(display_name=file.name),
        )

    def _credentials(self) -> tuple[GoogleDriveConfig, str] | DriveReadOutcome:
        config = self.config_store.load()
        if config is None:
            return DriveReadOutcome("disconnected")
        refresh_token = self.secret_store.get(config.secret_ref)
        client_secret = self.secret_store.get(config.client_secret_ref)
        if refresh_token is None or client_secret is None:
            return DriveReadOutcome("needs_reconnect")
        try:
            payload = self._request_json(
                self.TOKEN_URL,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=urlencode({
                    "client_id": config.client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }).encode("ascii"),
            )
        except GoogleDriveTokenInvalidGrant:
            self.secret_store.delete(config.secret_ref)
            return DriveReadOutcome("needs_reconnect")
        except (GoogleDriveUnavailable, GoogleDriveNetworkBlocked):
            return DriveReadOutcome("unavailable")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return DriveReadOutcome("needs_reconnect")
        return config, access_token

    def _search_files(self, query: str, access_token: str) -> tuple[DriveFileCandidate, ...]:
        escaped = _escape_drive_query(query)
        search_query = "trashed = false" if not escaped else f"trashed = false and (name contains '{escaped}' or fullText contains '{escaped}')"
        rows: list[DriveFileCandidate] = []
        page_token: str | None = None
        for _ in range(self.MAX_PAGES):
            params = {
                "q": search_query,
                "pageSize": str(self.MAX_RESULTS),
                "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size,webViewLink)",
                "orderBy": "modifiedTime desc",
            }
            if page_token is not None:
                params["pageToken"] = page_token
            payload = self._request_json(
                f"{self.API_ROOT}/files?" + urlencode(params),
                headers={"Authorization": f"Bearer {access_token}"},
            )
            for item in payload.get("files", []):
                candidate = _candidate(item)
                if candidate is not None:
                    rows.append(candidate)
                    if len(rows) >= self.MAX_RESULTS:
                        return tuple(rows)
            page_token = payload.get("nextPageToken") if isinstance(payload.get("nextPageToken"), str) else None
            if page_token is None:
                break
        return tuple(rows)

    def _content_url(self, file: DriveFileCandidate) -> str:
        encoded_id = quote(file.file_id, safe="")
        if file.mime_type == self._PDF_MIME:
            return f"{self.API_ROOT}/files/{encoded_id}?alt=media"
        return f"{self.API_ROOT}/files/{encoded_id}/export?" + urlencode({"mimeType": self._PDF_MIME})

    def _download(self, url: str, access_token: str) -> bytes:
        assert_google_drive_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)
        return self.transport.download(url, headers={"Authorization": f"Bearer {access_token}"}, maximum_bytes=MAX_RAW_PDF_BYTES)

    def _request_json(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict:
        assert_google_drive_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)
        return self.transport.request_json(url, method=method, headers=headers, body=body)


def _escape_drive_query(value: str) -> str:
    normalized = " ".join(value.split())[:200]
    return normalized.replace("\\", "\\\\").replace("'", "\\'")


def _candidate(item: object) -> DriveFileCandidate | None:
    if not isinstance(item, dict):
        return None
    file_id, name, mime_type = item.get("id"), item.get("name"), item.get("mimeType")
    if not all(isinstance(value, str) and value for value in (file_id, name, mime_type)):
        return None
    modified_at = _parse_time(item.get("modifiedTime"))
    size_value = item.get("size")
    size = int(size_value) if isinstance(size_value, str) and size_value.isdigit() else None
    return DriveFileCandidate(
        file_id=file_id[:200],
        name=" ".join(name.split())[:300] or "Без названия",
        mime_type=mime_type[:200],
        modified_at=modified_at,
        size=size,
        readable=mime_type == GoogleDriveReader._PDF_MIME or mime_type in GoogleDriveReader._NATIVE_EXPORTS,
    )


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _human_mime_type(value: str) -> str:
    return {
        "application/pdf": "PDF",
        "application/vnd.google-apps.document": "Google Документ",
        "application/vnd.google-apps.spreadsheet": "Google Таблица",
        "application/vnd.google-apps.presentation": "Google Презентация",
    }.get(value, "другой формат")


def _token_error_is_invalid_grant(error: HTTPError) -> bool:
    try:
        payload = json.loads(error.read(64 * 1024))
        return isinstance(payload, dict) and payload.get("error") == "invalid_grant"
    except (OSError, UnicodeDecodeError, ValueError):
        return False
