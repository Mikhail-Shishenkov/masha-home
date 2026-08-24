"""Bounded, metadata-only Yandex Disk search and PDF read bridge."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from backend.document_read import DocumentInput, DocumentReadError, DocumentReader, DocumentReadReceipt, DocumentReadSourceKind, DocumentReadStore
from backend.document_read.reader import MAX_RAW_PDF_BYTES

from .config import YandexDiskConfig, YandexDiskConfigStore
from .network import YandexDiskNetworkBlocked, assert_yandex_disk_network_allowed


class YandexDiskTransport(Protocol):
    def request_json(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict: ...
    def download(self, url: str, *, headers: dict[str, str] | None = None, maximum_bytes: int) -> bytes: ...


class YandexDiskUnavailable(RuntimeError):
    pass


class YandexDiskInvalidGrant(RuntimeError):
    pass


class YandexDiskDocumentTooLarge(RuntimeError):
    pass


class UrllibYandexDiskTransport:
    _MAX_JSON_BYTES = 2 * 1024 * 1024

    def request_json(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict:
        request = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=12) as response:
                raw = response.read(self._MAX_JSON_BYTES + 1)
        except HTTPError as error:
            if "/token" in url and error.code == 400 and _invalid_grant(error):
                raise YandexDiskInvalidGrant("yandex_disk_reconnect_required") from error
            raise YandexDiskUnavailable("yandex_disk_unavailable") from error
        except (URLError, OSError) as error:
            raise YandexDiskUnavailable("yandex_disk_unavailable") from error
        if len(raw) > self._MAX_JSON_BYTES:
            raise YandexDiskUnavailable("yandex_disk_unavailable")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as error:
            raise YandexDiskUnavailable("yandex_disk_unavailable") from error
        if not isinstance(payload, dict):
            raise YandexDiskUnavailable("yandex_disk_unavailable")
        return payload

    def download(self, url: str, *, headers: dict[str, str] | None = None, maximum_bytes: int) -> bytes:
        request = Request(url, headers=headers or {}, method="GET")
        try:
            with urlopen(request, timeout=12) as response:
                size = response.headers.get("Content-Length")
                if size is not None and size.isdigit() and int(size) > maximum_bytes:
                    raise YandexDiskDocumentTooLarge("yandex_disk_document_too_large")
                raw = response.read(maximum_bytes + 1)
        except YandexDiskDocumentTooLarge:
            raise
        except (HTTPError, URLError, OSError) as error:
            raise YandexDiskUnavailable("yandex_disk_unavailable") from error
        if len(raw) > maximum_bytes:
            raise YandexDiskDocumentTooLarge("yandex_disk_document_too_large")
        return raw


@dataclass(frozen=True)
class DiskFileCandidate:
    resource_path: str
    name: str
    mime_type: str | None
    size: int | None
    modified_at: datetime | None
    created_at: datetime | None
    readable: bool

    def model_value(self) -> dict:
        return {
            "name": self.name,
            "mime_type": "PDF" if self.readable else "другой формат",
            "modified_at": None if self.modified_at is None else self.modified_at.isoformat(),
            "readable": self.readable,
        }


@dataclass(frozen=True)
class ResolvedYandexDiskDocumentRequest:
    display_name: str

    def model_message(self) -> str:
        return (
            f'Пользователь выбрал файл «{self.display_name}» на Яндекс Диске. '
            "Выбор уже разрешён приложением. Прочитай выбранный документ и ответь по его содержимому. "
            "Не трактуй «первый», «второй» или «третий» как номер раздела, пункта или страницы."
        )


@dataclass(frozen=True)
class DiskReadOutcome:
    status: str
    files: tuple[DiskFileCandidate, ...] = ()
    document_receipt: DocumentReadReceipt | None = None
    resolved_document_request: ResolvedYandexDiskDocumentRequest | None = None
    scan_limited: bool = False

    def model_context(self) -> list[dict]:
        return [] if self.status != "search_completed" else [{"kind": "yandex_disk_search", "files": [item.model_value() for item in self.files]}]


class YandexDiskReader:
    TOKEN_URL = "https://oauth.yandex.ru/token"
    API_ROOT = "https://cloud-api.yandex.net/v1/disk"
    PAGE_SIZE = 100
    MAX_PAGES = 5
    MAX_RESULTS = 10
    _FIELDS = "items.name,items.path,items.mime_type,items.size,items.modified,items.created,items.type,limit,offset"

    def __init__(self, *, config_store: YandexDiskConfigStore, secret_store, document_reader: DocumentReader | None = None, document_store: DocumentReadStore | None = None, transport: YandexDiskTransport | None = None, policy_store=None, safety_store=None, now=None):
        self.config_store = config_store
        self.secret_store = secret_store
        self.document_reader = document_reader or DocumentReader()
        self.document_store = document_store
        self.transport = transport or UrllibYandexDiskTransport()
        self.policy_store = policy_store
        self.safety_store = safety_store
        self._now = now or (lambda: datetime.now(timezone.utc))

    def recent(self) -> DiskReadOutcome:
        credentials = self._credentials()
        if isinstance(credentials, DiskReadOutcome):
            return credentials
        _config, token = credentials
        try:
            payload = self._request_json(self.API_ROOT + "/resources/last-uploaded?" + urlencode({"limit": self.MAX_RESULTS, "fields": self._FIELDS}), token)
            rows = tuple(filter(None, (_candidate(item) for item in payload.get("items", []))))[:self.MAX_RESULTS]
            return DiskReadOutcome("no_files" if not rows else "search_completed", files=rows)
        except (YandexDiskUnavailable, YandexDiskNetworkBlocked):
            return DiskReadOutcome("unavailable")

    def list_files(self) -> DiskReadOutcome:
        """One provider-ordered metadata page; this is not a recent-files claim."""
        credentials = self._credentials()
        if isinstance(credentials, DiskReadOutcome):
            return credentials
        _config, token = credentials
        try:
            payload = self._request_json(self.API_ROOT + "/resources/files?" + urlencode({"limit": self.MAX_RESULTS, "offset": 0, "fields": self._FIELDS}), token)
            rows = tuple(filter(None, (_candidate(item) for item in payload.get("items", []))))[:self.MAX_RESULTS]
            return DiskReadOutcome("no_files" if not rows else "search_completed", files=rows)
        except (YandexDiskUnavailable, YandexDiskNetworkBlocked):
            return DiskReadOutcome("unavailable")

    def search(self, query: str) -> DiskReadOutcome:
        tokens = _query_tokens(query)
        if not tokens:
            return DiskReadOutcome("no_files")
        credentials = self._credentials()
        if isinstance(credentials, DiskReadOutcome):
            return credentials
        _config, token = credentials
        rows: list[DiskFileCandidate] = []
        offset = 0
        scan_limited = False
        try:
            for page in range(self.MAX_PAGES):
                payload = self._request_json(self.API_ROOT + "/resources/files?" + urlencode({"limit": self.PAGE_SIZE, "offset": offset, "fields": self._FIELDS}), token)
                items = payload.get("items", [])
                if not isinstance(items, list):
                    raise YandexDiskUnavailable("yandex_disk_unavailable")
                for item in items:
                    candidate = _candidate(item)
                    if candidate is not None and _matches(candidate, tokens):
                        rows.append(candidate)
                        if len(rows) >= self.MAX_RESULTS:
                            return DiskReadOutcome("search_completed", files=tuple(rows), scan_limited=True)
                if len(items) < self.PAGE_SIZE:
                    break
                offset += self.PAGE_SIZE
                scan_limited = page == self.MAX_PAGES - 1
            return DiskReadOutcome("no_files" if not rows else "search_completed", files=tuple(rows), scan_limited=scan_limited)
        except (YandexDiskUnavailable, YandexDiskNetworkBlocked):
            return DiskReadOutcome("unavailable")

    def read_file(self, file: DiskFileCandidate) -> DiskReadOutcome:
        if not file.readable:
            return DiskReadOutcome("unsupported_format")
        if file.size is not None and file.size > MAX_RAW_PDF_BYTES:
            return DiskReadOutcome("document_too_large")
        credentials = self._credentials()
        if isinstance(credentials, DiskReadOutcome):
            return credentials
        _config, token = credentials
        try:
            href_payload = self._request_json(self.API_ROOT + "/resources/download?" + urlencode({"path": file.resource_path}), token)
            href = href_payload.get("href")
            if not isinstance(href, str) or not href.startswith("https://"):
                raise YandexDiskUnavailable("yandex_disk_unavailable")
            self._guard_network()
            raw = self.transport.download(href, maximum_bytes=MAX_RAW_PDF_BYTES)
            evidence = self.document_reader.read(DocumentInput(media_type="application/pdf", content=raw, source_kind=DocumentReadSourceKind.CONNECTOR, display_name=file.name, source_reference=file.resource_path))
        except YandexDiskDocumentTooLarge:
            return DiskReadOutcome("document_too_large")
        except DocumentReadError as error:
            return DiskReadOutcome("document_too_large" if error.code == "pdf_input_too_large" else "document_unreadable")
        except (YandexDiskUnavailable, YandexDiskNetworkBlocked):
            return DiskReadOutcome("unavailable")
        receipt = DocumentReadReceipt(receipt_id=f"doc_{uuid4()}", source_kind=DocumentReadSourceKind.CONNECTOR, source_reference=file.resource_path, source_domain="cloud-api.yandex.net", display_name=file.name, evidence=evidence, completed_at=self._now())
        if self.document_store is not None:
            receipt = self.document_store.save(receipt)
        return DiskReadOutcome("read_completed", document_receipt=receipt, resolved_document_request=ResolvedYandexDiskDocumentRequest(file.name))

    def _credentials(self) -> tuple[YandexDiskConfig, str] | DiskReadOutcome:
        config = self.config_store.load()
        if config is None:
            return DiskReadOutcome("disconnected")
        refresh = self.secret_store.get(config.secret_ref)
        client_secret = self.secret_store.get(config.client_secret_ref)
        if not refresh or not client_secret:
            return DiskReadOutcome("needs_reconnect")
        try:
            payload = self._request_json(self.TOKEN_URL, None, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=urlencode({"grant_type": "refresh_token", "refresh_token": refresh, "client_id": config.client_id, "client_secret": client_secret}).encode())
        except YandexDiskInvalidGrant:
            self.secret_store.delete(config.secret_ref)
            return DiskReadOutcome("needs_reconnect")
        except (YandexDiskUnavailable, YandexDiskNetworkBlocked):
            return DiskReadOutcome("unavailable")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            return DiskReadOutcome("needs_reconnect")
        replacement = payload.get("refresh_token")
        if isinstance(replacement, str) and replacement:
            self.secret_store.put(config.secret_ref, replacement)
        return config, token

    def _guard_network(self) -> None:
        assert_yandex_disk_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)

    def _request_json(self, url: str, token: str | None, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None) -> dict:
        self._guard_network()
        all_headers = dict(headers or {})
        if token is not None:
            all_headers["Authorization"] = f"OAuth {token}"
        return self.transport.request_json(url, method=method, headers=all_headers, body=body)


def token_post(fields: dict[str, str]) -> dict:
    return UrllibYandexDiskTransport().request_json(YandexDiskReader.TOKEN_URL, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=urlencode(fields).encode())


def _invalid_grant(error: HTTPError) -> bool:
    try:
        return json.loads(error.read(8192)).get("error") == "invalid_grant"
    except Exception:
        return False


def _candidate(item: object) -> DiskFileCandidate | None:
    if not isinstance(item, dict):
        return None
    path, name = item.get("path"), item.get("name")
    if not isinstance(path, str) or not path or not isinstance(name, str) or not name:
        return None
    mime_type = item.get("mime_type") if isinstance(item.get("mime_type"), str) else None
    size = item.get("size") if isinstance(item.get("size"), int) and item["size"] >= 0 else None
    return DiskFileCandidate(path[:200], " ".join(name.split())[:300] or "Без названия", None if mime_type is None else mime_type[:200], size, _time(item.get("modified")), _time(item.get("created")), mime_type == "application/pdf" or name.casefold().endswith(".pdf"))


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _query_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in re.findall(r"[\w]+", value.casefold().replace("ё", "е"))[:8] if len(token) > 1)


def _matches(candidate: DiskFileCandidate, tokens: tuple[str, ...]) -> bool:
    haystack = (candidate.name + " " + candidate.resource_path).casefold().replace("ё", "е")
    return all(token in haystack for token in tokens)
