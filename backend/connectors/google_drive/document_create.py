"""Confirmed, narrowly-scoped Google Docs creation for Google Drive."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote, urlencode
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.backup.recovery_journal import RecoveryJournal
from backend.conversation.memory_intent import MemoryProposal, MemoryProposalStore, PendingProposalConflict, ProposalStatus
from backend.llm.model_models import MessageRole, ModelCapabilities, ModelMessage, ModelRequest, PrivacyScope
from backend.llm.model_provider import ModelProviderUnavailableError
from backend.llm.model_router import ModelCapabilityUnavailableError
from backend.connectors.provider_language import normalize_explicit_provider

from .config import GoogleDriveConfigStore
from .config import GOOGLE_DRIVE_DOCUMENT_WRITE_SCOPE
from .network import GoogleDriveNetworkBlocked, assert_google_drive_network_allowed
from .reader import GoogleDriveTokenInvalidGrant, GoogleDriveTransport, GoogleDriveUnavailable, UrllibGoogleDriveTransport


_CONFIRM = re.compile(r"^\s*(?:да|подтверждаю|создавай|создай)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$", re.I)
_REJECT = re.compile(r"^\s*(?:нет|не надо|не сейчас|отмена)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$", re.I)
_CREATE = re.compile(
    "\\b(?:\\u0441\\u043e\\u0437\\u0434\\u0430\\u0439\\s+(?:\\u0434\\u043e\\u043a\\u0443\\u043c\\u0435\\u043d\\u0442|\\u0437\\u0430\\u043c\\u0435\\u0442\\u043a\\w*|google\\s*docs?|\\u0433\\u0443\\u0433\\u043b\\s+\\u0434\\u043e\\u043a(?:\\u0441\\w*)?)|"
    "\\u0441\\u043e\\u0445\\u0440\\u0430\\u043d\\u0438\\s+(?:\\u044d\\u0442\\u043e\\s+)?(?:\\u0432|\\u043d\\u0430)|"
    "\\u0441\\u043e\\u0431\\u0435\\u0440\\u0438\\s+\\u044d\\u0442\\u043e\\s+\\u0432\\s+\\u0437\\u0430\\u043c\\u0435\\u0442\\u043a\\w*)", re.I,
)
_REFERENTIAL_MATERIAL = re.compile(r"\b(?:это|этот\s+текст|эту\s+заметку|выше)\b", re.I)
_INLINE_MATERIAL = re.compile(
    r"(?:^|\s)(?:с\s+текстом|с\s+содержимым|содержимое|текст)\s*[:—-]\s*(?P<body>.+)$|"
    r"^[^:]{1,300}:\s*(?P<after_colon>.+)$",
    re.I | re.S,
)
_CONFIRMATION_ONLY = re.compile(r"^\s*(?:да|нет|подтверждаю|не\s+надо|отмена)\s*[.!]?\s*$", re.I)
_CLARIFICATION_TEXT = re.compile(
    r"\b(?:что\s+именно\s+(?:надо\s+)?(?:записать|сохранить)|какой\s+материал\s+(?:взять|сохранить)|пришли\s+текст|уточни\s*,?\s+что)\b",
    re.I,
)


class DocumentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


class DriveDocumentCreateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str = Field(min_length=36, max_length=36)
    provider: Literal["google_drive"] = "google_drive"
    destination: Literal["my_drive"] = "my_drive"
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_draft(cls, draft: DocumentDraft) -> "DriveDocumentCreateOperation":
        normalized = draft.body.replace("\r\n", "\n").strip()
        return cls(
            operation_id=str(uuid4()), title=draft.title.strip(), body=normalized,
            content_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        )


class DriveDocumentCreateReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: DriveDocumentCreateOperation
    status: Literal["proposed", "rejected", "executing", "blocked", "failed", "created_unverified", "create_unresolved", "conflict", "verified"]
    provider_document_id: str | None = Field(default=None, min_length=1, max_length=300)
    confirmed_at: datetime | None = None
    verified_at: datetime | None = None
    marker_version: Literal["1"] | None = None
    target_mime_type: str | None = Field(default=None, max_length=100)
    create_dispatch_started_at: datetime | None = None
    outcome_detail: Literal[
        "drive_create_transport_unknown", "drive_create_missing_id",
        "marker_search_unavailable", "marker_search_zero", "marker_search_multiple",
        "docs_get_unavailable", "docs_batch_update_unknown", "verification_mismatch",
    ] | None = None


class DriveDocumentCreateReceiptStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items = self._load()

    def get(self, operation_id: str) -> DriveDocumentCreateReceipt | None:
        return self._items.get(operation_id)

    def put(self, receipt: DriveDocumentCreateReceipt) -> DriveDocumentCreateReceipt:
        items = {**self._items, receipt.operation.operation_id: receipt}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"receipts": [item.model_dump(mode="json") for item in items.values()]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        self._items = items
        return receipt

    def _load(self) -> dict[str, DriveDocumentCreateReceipt]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {item["operation"]["operation_id"]: DriveDocumentCreateReceipt.model_validate(item) for item in payload.get("receipts", [])}


class DocumentDraftBuilder(Protocol):
    def build(self, message: str, recent_messages: tuple[str, ...]) -> DocumentDraft | None: ...


class LocalDocumentDraftBuilder:
    """Uses the local model only to shape bounded text, never to authorise I/O."""

    def __init__(self, *, router, identity_kernel, model_profiles=None):
        self.router, self.identity_kernel, self.model_profiles = router, identity_kernel, model_profiles

    def build(self, message: str, recent_messages: tuple[str, ...]) -> DocumentDraft | None:
        profile = None if self.model_profiles is None else self.model_profiles.get_active_profile()
        request = ModelRequest(
            messages=(
                ModelMessage(role=MessageRole.SYSTEM, content=(
                    "Собери только проект заметки для Google Docs. Верни строго JSON: "
                    '{"title":"...","body":"..."}. Не добавляй фактов и не выполняй действий.'
                )),
                ModelMessage(role=MessageRole.USER, content="Недавний локальный контекст:\n" + "\n".join(recent_messages[-8:]) + "\n\nЗапрос:\n" + message),
            ),
            identity_context=self.identity_kernel.build_context(), private_context={"task": "google_drive_document_draft"},
            required_capabilities=ModelCapabilities(structured_output=True, tools=False), privacy_scope=PrivacyScope.LOCAL_ONLY,
            preferred_provider_id=None if profile is None else profile.provider_id,
            execution_model_id=None if profile is None else profile.model_id,
            execution_think=False,
        )
        try:
            response = self.router.generate(request)
            return DocumentDraft.model_validate(json.loads(response.text))
        except (ModelProviderUnavailableError, ModelCapabilityUnavailableError, ValueError, TypeError, json.JSONDecodeError):
            return None


def drive_document_create_intent(message: str) -> bool:
    """Only explicit create/save language owns this turn; Drive read remains separate."""
    language = normalize_explicit_provider(message)
    return language.provider_id == "google_drive" and bool(_CREATE.search(language.text))


def document_source_material(message: str, recent_messages: tuple[str, ...]) -> tuple[str, ...] | None:
    """Resolve bounded source text before an LLM may format a document.

    The model can shape supplied material but cannot turn its own clarification
    into document content.  Conservative uncertainty therefore returns None.
    """
    inline = _INLINE_MATERIAL.search(message.strip())
    if inline is not None:
        body = (inline.group("body") or inline.group("after_colon") or "").strip()
        if _substantial_material(body):
            return (body,)
    if not _REFERENTIAL_MATERIAL.search(message):
        return None
    candidates = tuple(
        value
        for value in (item.strip() for item in recent_messages[-8:])
        if _substantial_material(value)
        and not _CONFIRMATION_ONLY.match(value)
        and not _CLARIFICATION_TEXT.search(value)
        and not drive_document_create_intent(value)
    )
    return candidates[-4:] or None


def _substantial_material(value: str) -> bool:
    words = re.findall(r"[\w'-]+", value, re.UNICODE)
    return len(value) >= 12 and len(words) >= 3


class GoogleDriveDocumentWriter:
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    DOCS_ROOT = "https://docs.googleapis.com/v1/documents"
    DRIVE_ROOT = "https://www.googleapis.com/drive/v3/files"
    DOCUMENT_MIME_TYPE = "application/vnd.google-apps.document"
    MARKER_KEY = "masha_home_operation_id"
    MARKER_VERSION_KEY = "masha_home_document_create_version"
    MARKER_VERSION = "1"

    def __init__(self, *, config_store: GoogleDriveConfigStore, secret_store, receipt_store: DriveDocumentCreateReceiptStore, transport: GoogleDriveTransport | None = None, policy_store=None, safety_store=None, recovery_journal: RecoveryJournal | None = None, clock=None):
        self.config_store, self.secret_store, self.receipt_store = config_store, secret_store, receipt_store
        self.transport = transport or UrllibGoogleDriveTransport()
        self.policy_store, self.safety_store, self.recovery_journal = policy_store, safety_store, recovery_journal
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create_and_verify(self, operation: DriveDocumentCreateOperation) -> tuple[str, DriveDocumentCreateReceipt]:
        existing = self.receipt_store.get(operation.operation_id)
        if existing is not None:
            if existing.operation != operation:
                return "failed", existing
            if existing.status == "verified":
                return "verified", existing
            if existing.status in {"created_unverified", "create_unresolved", "executing"}:
                return self._reconcile(existing)
        if self._blocked():
            return "blocked", self.receipt_store.put(DriveDocumentCreateReceipt(operation=operation, status="blocked"))
        credentials = self._credentials()
        if credentials is None:
            return "needs_reconnect", self.receipt_store.put(DriveDocumentCreateReceipt(operation=operation, status="failed"))
        client_id, refresh_token, client_secret = credentials
        executing = self.receipt_store.put(DriveDocumentCreateReceipt(
            operation=operation, status="executing", confirmed_at=self.clock(),
            marker_version=self.MARKER_VERSION, target_mime_type=self.DOCUMENT_MIME_TYPE,
        ))
        try:
            token = self._access_token(client_id, refresh_token, client_secret)
        except GoogleDriveTokenInvalidGrant:
            self.secret_store.delete(self.config_store.load().document_write_secret_ref)
            return "needs_reconnect", self.receipt_store.put(executing.model_copy(update={"status": "failed"}))
        except (GoogleDriveUnavailable, GoogleDriveNetworkBlocked):
            return "failed", self.receipt_store.put(executing.model_copy(update={"status": "failed"}))
        try:
            if self._blocked():
                return "blocked", self.receipt_store.put(executing.model_copy(update={"status": "blocked"}))
            dispatch = self.receipt_store.put(executing.model_copy(update={"create_dispatch_started_at": self.clock()}))
            created = self._request(self.DRIVE_ROOT + "?fields=id,name,mimeType,appProperties,createdTime", method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, body=json.dumps({"name": operation.title, "mimeType": self.DOCUMENT_MIME_TYPE, "appProperties": self._marker(operation)}).encode("utf-8"))
            document_id = created.get("id")
            if not isinstance(document_id, str) or not document_id:
                return self._recover_by_marker(dispatch.model_copy(update={"status": "created_unverified", "outcome_detail": "drive_create_missing_id"}), token)
            receipt = self.receipt_store.put(dispatch.model_copy(update={"status": "created_unverified", "provider_document_id": document_id}))
            return self._insert_and_verify(receipt, token)
        except (GoogleDriveUnavailable, GoogleDriveNetworkBlocked):
            return self._recover_by_marker(dispatch.model_copy(update={"status": "created_unverified", "outcome_detail": "drive_create_transport_unknown"}), token)

    def _reconcile(self, receipt: DriveDocumentCreateReceipt) -> tuple[str, DriveDocumentCreateReceipt]:
        if receipt.provider_document_id is None:
            # Old Docs-API receipts have no marker and cannot be attributed.
            if receipt.marker_version is None:
                return "created_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified"}))
        if self._blocked():
            return "blocked", self.receipt_store.put(receipt.model_copy(update={"status": "blocked"}))
        credentials = self._credentials()
        if credentials is None:
            return "needs_reconnect", receipt
        try:
            token = self._access_token(*credentials)
            if receipt.provider_document_id is None:
                return self._recover_by_marker(receipt, token)
            fetched = self._get(receipt.provider_document_id, token)
            if self._matches(receipt.operation, fetched):
                return "verified", self.receipt_store.put(receipt.model_copy(update={"status": "verified", "verified_at": self.clock()}))
            if self._title_matches(receipt.operation, fetched) and not _document_text(fetched).strip():
                return self._insert_and_verify(receipt, token)
            return "conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict", "outcome_detail": "verification_mismatch"}))
        except (GoogleDriveUnavailable, GoogleDriveNetworkBlocked):
            return "created_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified", "outcome_detail": "docs_get_unavailable"}))

    def _recover_by_marker(self, receipt: DriveDocumentCreateReceipt, token: str) -> tuple[str, DriveDocumentCreateReceipt]:
        try:
            rows = self._find_marker_candidates(receipt.operation.operation_id, token)
        except (GoogleDriveUnavailable, GoogleDriveNetworkBlocked):
            return "created_unverified", self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified", "outcome_detail": "marker_search_unavailable"}))
        if not rows:
            return "create_unresolved", self.receipt_store.put(receipt.model_copy(update={"status": "create_unresolved", "outcome_detail": "marker_search_zero"}))
        if len(rows) != 1:
            return "conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict", "outcome_detail": "marker_search_multiple"}))
        candidate = rows[0]
        document_id = candidate.get("id")
        if not isinstance(document_id, str) or not document_id or not self._is_exact_marker_candidate(candidate, receipt.operation.operation_id):
            return "conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict", "outcome_detail": "verification_mismatch"}))
        known = self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified", "provider_document_id": document_id, "outcome_detail": None}))
        return self._reconcile(known)

    def _insert_and_verify(self, receipt: DriveDocumentCreateReceipt, token: str) -> tuple[str, DriveDocumentCreateReceipt]:
        assert receipt.provider_document_id is not None
        try:
            self._request(f"{self.DOCS_ROOT}/{quote(receipt.provider_document_id, safe='')}:batchUpdate", method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, body=json.dumps({"requests": [{"insertText": {"location": {"index": 1}, "text": receipt.operation.body}}]}).encode("utf-8"))
            fetched = self._get(receipt.provider_document_id, token)
            if self._matches(receipt.operation, fetched):
                return "verified", self.receipt_store.put(receipt.model_copy(update={"status": "verified", "verified_at": self.clock()}))
            return "conflict", self.receipt_store.put(receipt.model_copy(update={"status": "conflict", "outcome_detail": "verification_mismatch"}))
        except (GoogleDriveUnavailable, GoogleDriveNetworkBlocked):
            ambiguous = self.receipt_store.put(receipt.model_copy(update={"status": "created_unverified", "outcome_detail": "docs_batch_update_unknown"}))
            # The mutation may have committed after the response was lost.
            # Re-read before ever considering another body insertion.
            return self._reconcile(ambiguous)

    def reject(self, operation: DriveDocumentCreateOperation) -> DriveDocumentCreateReceipt:
        return self.receipt_store.put(DriveDocumentCreateReceipt(operation=operation, status="rejected"))

    def _credentials(self):
        config = self.config_store.load()
        if config is None or config.document_write_secret_ref is None or config.document_write_requested_scope != GOOGLE_DRIVE_DOCUMENT_WRITE_SCOPE:
            return None
        refresh, secret = self.secret_store.get(config.document_write_secret_ref), self.secret_store.get(config.client_secret_ref)
        return None if refresh is None or secret is None else (config.client_id, refresh, secret)

    def _access_token(self, client_id: str, refresh_token: str, client_secret: str) -> str:
        payload = self._request(self.TOKEN_URL, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=urlencode({"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token, "grant_type": "refresh_token"}).encode("ascii"))
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise GoogleDriveUnavailable("google_drive_unavailable")
        return token

    def _get(self, document_id: str, token: str) -> dict:
        return self._request(f"{self.DOCS_ROOT}/{quote(document_id, safe='')}", headers={"Authorization": f"Bearer {token}"})

    def _request(self, url: str, *, method="GET", headers=None, body=None) -> dict:
        assert_google_drive_network_allowed(policy_store=self.policy_store, safety_store=self.safety_store)
        return self.transport.request_json(url, method=method, headers=headers, body=body)

    def _find_marker_candidates(self, operation_id: str, token: str) -> tuple[dict, ...]:
        query = (
            f"trashed = false and mimeType = '{self.DOCUMENT_MIME_TYPE}' and "
            f"appProperties has {{ key='{self.MARKER_KEY}' and value='{operation_id}' }}"
        )
        rows: list[dict] = []
        page_token = None
        for _ in range(4):
            params = {"q": query, "pageSize": "100", "fields": "nextPageToken,files(id,name,mimeType,appProperties,createdTime)"}
            if page_token is not None:
                params["pageToken"] = page_token
            result = self._request(self.DRIVE_ROOT + "?" + urlencode(params), headers={"Authorization": f"Bearer {token}"})
            files = result.get("files")
            if not isinstance(files, list):
                raise GoogleDriveUnavailable("invalid_marker_search")
            rows.extend(item for item in files if isinstance(item, dict))
            page_token = result.get("nextPageToken")
            if not isinstance(page_token, str) or not page_token:
                return tuple(rows)
        raise GoogleDriveUnavailable("marker_search_incomplete")

    def _marker(self, operation: DriveDocumentCreateOperation) -> dict[str, str]:
        return {self.MARKER_KEY: operation.operation_id, self.MARKER_VERSION_KEY: self.MARKER_VERSION}

    def _is_exact_marker_candidate(self, item: dict, operation_id: str) -> bool:
        properties = item.get("appProperties")
        return bool(
            item.get("mimeType") == self.DOCUMENT_MIME_TYPE
            and isinstance(properties, dict)
            and properties.get(self.MARKER_KEY) == operation_id
            and properties.get(self.MARKER_VERSION_KEY) == self.MARKER_VERSION
        )

    def _blocked(self) -> bool:
        from backend.external_observation.policy import InternetAccessMode
        return bool((self.policy_store is not None and self.policy_store.load().mode is InternetAccessMode.OFF) or (self.safety_store is not None and self.safety_store.is_engaged()) or (self.recovery_journal is not None and self.recovery_journal.is_hold()))

    @staticmethod
    def _title_matches(operation, item): return item.get("title") == operation.title
    @classmethod
    def _matches(cls, operation, item): return cls._title_matches(operation, item) and _document_text(item).strip() == operation.body.strip()


def _document_text(item: dict) -> str:
    return "".join(
        element.get("textRun", {}).get("content", "")
        for part in item.get("body", {}).get("content", []) if isinstance(part, dict)
        for element in part.get("paragraph", {}).get("elements", []) if isinstance(element, dict)
    )


class GoogleDriveDocumentCreateConversationService:
    def __init__(self, *, proposal_store: MemoryProposalStore, writer: GoogleDriveDocumentWriter, draft_builder: DocumentDraftBuilder):
        self.proposal_store, self.writer, self.draft_builder = proposal_store, writer, draft_builder
        self._attempted: set[str] = set()

    def propose(self, message: str, *, conversation_id: str, recent_messages: tuple[str, ...], now_local: datetime):
        if not drive_document_create_intent(message): return None
        self._attempted.add(conversation_id)
        source_material = document_source_material(message, recent_messages)
        if source_material is None:
            return "Что именно сохранить в документе? Пришли текст или напомни, какой материал взять."
        draft = self.draft_builder.build(message, source_material)
        if draft is None: return "Не смогла безопасно собрать заметку. Ничего в Drive не создаю."
        if _CLARIFICATION_TEXT.search(f"{draft.title}\n{draft.body}"):
            return "Что именно сохранить в документе? Пришли текст или напомни, какой материал взять."
        operation = DriveDocumentCreateOperation.from_draft(draft)
        proposal = MemoryProposal(id=str(uuid4()), conversation_id=conversation_id, record_type="google_drive_document", record_payload=operation.model_dump(mode="json"), created_at=now_local, status=ProposalStatus.PENDING, operation="google_drive_document_create")
        try: self.proposal_store.create(proposal)
        except PendingProposalConflict: return "Сначала закончим предыдущее подтверждение — пока документ не создаю."
        self.writer.receipt_store.put(DriveDocumentCreateReceipt(operation=operation, status="proposed"))
        return f"Создать документ в Google Drive?\nНазвание: «{operation.title}»\nТекст:\n{operation.body}"

    def resolve(self, message: str, *, conversation_id: str, proposal_id: str | None = None):
        command = _CONFIRM.match(message) or _REJECT.match(message)
        if command is None: return None
        proposal = self.proposal_store.current_for_conversation(conversation_id)
        requested_id = proposal_id or command.group("id")
        if proposal is None or (requested_id is not None and proposal.id != requested_id) or proposal.operation != "google_drive_document_create":
            return "Нет актуального подтверждённого действия — документ в Drive не создаю." if conversation_id in self._attempted else None
        operation = DriveDocumentCreateOperation.model_validate(proposal.record_payload)
        if _REJECT.match(message):
            self.writer.reject(operation); self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            return "Хорошо, документ в Drive не создаю."
        status, _ = self.writer.create_and_verify(operation)
        if status == "verified": self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED); return f"Готово: создала и проверила документ «{operation.title}» в Google Drive."
        if status in {"created_unverified", "create_unresolved"}: return "Создание могло начаться, но я пока не смогла проверить документ. Повторно его не создаю."
        if status == "needs_reconnect": return "Для создания документа нужно отдельно подключить запись Google Docs."
        if status == "blocked": return "Сейчас внешние действия остановлены, поэтому документ в Drive не создаю."
        return "Не удалось создать документ — ничего не утверждаю как готовое."
