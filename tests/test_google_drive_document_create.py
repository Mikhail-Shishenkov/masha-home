from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.backup.recovery_journal import RecoveryJournal
from backend.backup.recovery_models import RecoveryPhase, RecoveryState
from backend.connectors.google_drive.config import (
    GOOGLE_DOCUMENTS_WRITE_SCOPE, GOOGLE_DOCUMENTS_WRITE_SECRET_REF,
    GoogleDriveConfig, GoogleDriveConfigStore,
)
from backend.connectors.google_drive.document_create import (
    DocumentDraft, DriveDocumentCreateOperation, DriveDocumentCreateReceiptStore,
    GoogleDriveDocumentCreateConversationService, GoogleDriveDocumentWriter,
    drive_document_create_intent,
)
from backend.conversation.memory_intent import MemoryProposalStore
from backend.external_observation.policy import InternetAccessMode, InternetAccessPolicy, InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.secrets import InMemorySecretStore


class Drafts:
    def __init__(self, draft=DocumentDraft(title="Итоги занятия по AI", body="Обсудили локальные модели.")):
        self.draft, self.calls = draft, []

    def build(self, message, recent_messages):
        self.calls.append((message, recent_messages))
        return self.draft


class Transport:
    def __init__(self, *, fail_before_create=False, fail_after_create=False):
        self.calls, self.docs = [], {}
        self.fail_before_create, self.fail_after_create = fail_before_create, fail_after_create

    def request_json(self, url, *, method="GET", headers=None, body=None):
        self.calls.append((url, method, body))
        if "oauth2.googleapis.com/token" in url:
            if self.fail_before_create:
                from backend.connectors.google_drive.reader import GoogleDriveUnavailable
                raise GoogleDriveUnavailable("down")
            return {"access_token": "token"}
        if method == "POST" and url.endswith("/v1/documents"):
            doc_id = "doc-1"; import json
            self.docs[doc_id] = {"title": json.loads(body)["title"], "body": ""}
            if self.fail_after_create:
                from backend.connectors.google_drive.reader import GoogleDriveUnavailable
                raise GoogleDriveUnavailable("uncertain")
            return {"documentId": doc_id}
        if method == "POST" and url.endswith(":batchUpdate"):
            import json
            doc_id = url.split("/")[-1].split(":")[0]
            self.docs[doc_id]["body"] += json.loads(body)["requests"][0]["insertText"]["text"]
            return {"replies": []}
        doc_id = url.rsplit("/", 1)[-1]
        item = self.docs[doc_id]
        return {"documentId": doc_id, "title": item["title"], "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": item["body"]}}]}}]}}


def _writer(tmp_path: Path, *, transport=None, policy=None, safety=None, recovery=None):
    store = GoogleDriveConfigStore(tmp_path / "local-data/config/google-drive.json")
    config = GoogleDriveConfig(client_id="desktop-client-identifier", document_write_secret_ref=GOOGLE_DOCUMENTS_WRITE_SECRET_REF, document_write_requested_scope=GOOGLE_DOCUMENTS_WRITE_SCOPE)
    store.save(config)
    secrets = InMemorySecretStore(); secrets.put(config.client_secret_ref, "client-secret-value"); secrets.put(config.document_write_secret_ref, "refresh-token-value")
    writer = GoogleDriveDocumentWriter(config_store=store, secret_store=secrets, receipt_store=DriveDocumentCreateReceiptStore(tmp_path / "local-data/runtime/drive-docs.json"), transport=transport or Transport(), policy_store=policy, safety_store=safety, recovery_journal=recovery, clock=lambda: datetime(2026, 8, 27, tzinfo=timezone.utc))
    return writer, store, secrets


def _operation(): return DriveDocumentCreateOperation.from_draft(DocumentDraft(title="Итоги занятия по AI", body="Обсудили локальные модели."))


def test_exact_canonical_phrase_creates_preview_but_no_provider_call(tmp_path):
    proposals = MemoryProposalStore(tmp_path / "proposals.json"); writer, _, _ = _writer(tmp_path); drafts = Drafts()
    service = GoogleDriveDocumentCreateConversationService(proposal_store=proposals, writer=writer, draft_builder=drafts)
    answer = service.propose("\u041c\u0430\u0448, \u0441\u043e\u0431\u0435\u0440\u0438 \u044d\u0442\u043e \u0432 \u0437\u0430\u043c\u0435\u0442\u043a\u0443 \u0438 \u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive.", conversation_id="c", recent_messages=("\u041c\u044b \u043e\u0431\u0441\u0443\u0434\u0438\u043b\u0438 AI.",), now_local=datetime.now(timezone.utc))
    assert "Итоги занятия по AI" in answer and "Обсудили локальные модели." in answer
    assert writer.transport.calls == []
    assert proposals.current_for_conversation("c").operation == "google_drive_document_create"


def test_requires_explicit_write_and_does_not_claim_read_or_factual_phrases():
    assert drive_document_create_intent("\u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive")
    assert not drive_document_create_intent("\u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive")
    assert not drive_document_create_intent("\u0423 \u043c\u0435\u043d\u044f \u043a\u043e\u043d\u0446\u0435\u0440\u0442 \u0432\u043e \u0432\u0442\u043e\u0440\u043d\u0438\u043a")


def test_reject_is_non_mutating_and_confirmation_creates_then_verifies(tmp_path):
    proposals = MemoryProposalStore(tmp_path / "proposals.json"); writer, _, _ = _writer(tmp_path); service = GoogleDriveDocumentCreateConversationService(proposal_store=proposals, writer=writer, draft_builder=Drafts())
    service.propose("\u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive", conversation_id="one", recent_messages=(), now_local=datetime.now(timezone.utc))
    assert service.resolve("\u043d\u0435\u0442", conversation_id="one") is not None and not writer.transport.calls
    service.propose("\u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive", conversation_id="two", recent_messages=(), now_local=datetime.now(timezone.utc))
    assert service.resolve("\u0434\u0430", conversation_id="two") is not None
    assert sum(method == "POST" and url.endswith("/v1/documents") for url, method, _ in writer.transport.calls) == 1


def test_pre_mutation_failure_is_retryable_but_does_not_claim_success(tmp_path):
    transport = Transport(fail_before_create=True); writer, _, _ = _writer(tmp_path, transport=transport); op = _operation()
    assert writer.create_and_verify(op)[0] == "failed"
    transport.fail_before_create = False
    assert writer.create_and_verify(op)[0] == "verified"
    assert sum(method == "POST" and url.endswith("/v1/documents") for url, method, _ in transport.calls) == 1


def test_unknown_create_outcome_never_blindly_posts_a_second_document(tmp_path):
    transport = Transport(fail_after_create=True); writer, _, _ = _writer(tmp_path, transport=transport); op = _operation()
    assert writer.create_and_verify(op)[0] == "created_unverified"
    transport.fail_after_create = False
    assert writer.create_and_verify(op)[0] == "created_unverified"
    assert sum(method == "POST" and url.endswith("/v1/documents") for url, method, _ in transport.calls) == 1


def test_known_document_reconciles_without_duplicate_and_can_finish_body(tmp_path):
    transport = Transport(); writer, _, _ = _writer(tmp_path, transport=transport); op = _operation()
    receipt = writer.receipt_store.put(__import__("backend.connectors.google_drive.document_create", fromlist=["DriveDocumentCreateReceipt"]).DriveDocumentCreateReceipt(operation=op, status="created_unverified", provider_document_id="doc-1"))
    transport.docs["doc-1"] = {"title": op.title, "body": ""}
    assert writer.create_and_verify(op)[0] == "verified"
    assert not any(method == "POST" and url.endswith("/v1/documents") for url, method, _ in transport.calls)


def test_off_stop_and_recovery_hold_block_before_transport(tmp_path):
    policy = InternetAccessPolicyStore(tmp_path / "policy.json"); policy.save(InternetAccessPolicy(mode=InternetAccessMode.OFF))
    writer, _, _ = _writer(tmp_path / "off", policy=policy); assert writer.create_and_verify(_operation())[0] == "blocked" and not writer.transport.calls
    safety = AutonomySafetyStore(tmp_path / "safety.json"); AutonomySafetyService(store=safety).engage()
    writer, _, _ = _writer(tmp_path / "stop", safety=safety); assert writer.create_and_verify(_operation())[0] == "blocked" and not writer.transport.calls
    recovery_root = tmp_path / "recovery"; journal = RecoveryJournal(recovery_root); now = datetime.now(timezone.utc); journal.save(RecoveryState(recovery_id="recovery-0001", backup_id="backup-0000001", phase=RecoveryPhase.HOLD, restore_mode="replace", created_at=now, updated_at=now))
    writer, _, _ = _writer(tmp_path / "hold", recovery=journal); assert writer.create_and_verify(_operation())[0] == "blocked" and not writer.transport.calls


def test_write_scope_and_credentials_are_separate_and_not_serialized(tmp_path):
    writer, store, secrets = _writer(tmp_path); config = store.load(); raw = store.path.read_text(encoding="utf-8")
    assert config.requested_scope.endswith("drive.readonly") and config.document_write_requested_scope == GOOGLE_DOCUMENTS_WRITE_SCOPE
    assert secrets.exists(config.document_write_secret_ref) and "refresh-token-value" not in raw and "client-secret-value" not in raw
