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
    LocalDocumentDraftBuilder, drive_document_create_intent,
    document_source_material,
)
from backend.application.conversation import ConversationApplicationService
from backend.conversation.memory_intent import MemoryProposalStore
from backend.external_observation.policy import InternetAccessMode, InternetAccessPolicy, InternetAccessPolicyStore
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_models import ModelCapabilities, PrivacyScope
from backend.llm.model_router import ModelRouter
from backend.secrets import InMemorySecretStore


ROOT = Path(__file__).resolve().parents[1]


class Drafts:
    def __init__(self, draft=DocumentDraft(title="Итоги занятия по AI", body="Обсудили локальные модели.")):
        self.draft, self.calls = draft, []

    def build(self, message, recent_messages):
        self.calls.append((message, recent_messages))
        return self.draft


class Transport:
    def __init__(self, *, fail_before_create=False, fail_after_create=False, hide_marker_once=False, fail_after_batch=False):
        self.calls, self.docs = [], {}
        self.fail_before_create, self.fail_after_create = fail_before_create, fail_after_create
        self.hide_marker_once, self.fail_after_batch = hide_marker_once, fail_after_batch

    def request_json(self, url, *, method="GET", headers=None, body=None):
        self.calls.append((url, method, body))
        if "oauth2.googleapis.com/token" in url:
            if self.fail_before_create:
                from backend.connectors.google_drive.reader import GoogleDriveUnavailable
                raise GoogleDriveUnavailable("down")
            return {"access_token": "token"}
        if method == "POST" and "/drive/v3/files" in url:
            doc_id = "doc-1"; import json
            payload = json.loads(body)
            self.docs[doc_id] = {"title": payload["name"], "body": "", "marker": payload["appProperties"]}
            if self.fail_after_create:
                from backend.connectors.google_drive.reader import GoogleDriveUnavailable
                raise GoogleDriveUnavailable("uncertain")
            return {"id": doc_id, "name": payload["name"], "mimeType": payload["mimeType"], "appProperties": payload["appProperties"]}
        if method == "GET" and "/drive/v3/files?" in url:
            if self.hide_marker_once:
                self.hide_marker_once = False
                return {"files": []}
            files = [{"id": doc_id, "name": item["title"], "mimeType": "application/vnd.google-apps.document", "appProperties": item["marker"]} for doc_id, item in self.docs.items()]
            return {"files": files}
        if method == "POST" and url.endswith(":batchUpdate"):
            import json
            doc_id = url.split("/")[-1].split(":")[0]
            self.docs[doc_id]["body"] += json.loads(body)["requests"][0]["insertText"]["text"]
            if self.fail_after_batch:
                from backend.connectors.google_drive.reader import GoogleDriveUnavailable
                raise GoogleDriveUnavailable("uncertain")
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


def test_local_draft_builder_uses_public_identity_context_and_returns_valid_draft():
    identity = IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json"))
    assert not hasattr(identity, "context")
    provider = FakeProvider(
        response_text='{"title":"AI notes","body":"Qwen was selected."}',
        capabilities=ModelCapabilities(structured_output=True),
    )
    builder = LocalDocumentDraftBuilder(
        router=ModelRouter([provider]), identity_kernel=identity,
    )

    draft = builder.build("Create a document in Drive", ("We discussed Qwen.",))

    assert draft == DocumentDraft(title="AI notes", body="Qwen was selected.")
    assert provider.last_request is not None
    assert provider.last_request.identity_context == identity.build_context()
    assert provider.last_request.privacy_scope is PrivacyScope.LOCAL_ONLY
    assert provider.last_request.required_capabilities.tools is False


def test_local_draft_builder_rejects_malformed_structured_response():
    identity = IdentityKernel(IdentityStore(ROOT / "identity" / "masha.identity.json"))
    provider = FakeProvider(
        response_text="not-json",
        capabilities=ModelCapabilities(structured_output=True),
    )
    builder = LocalDocumentDraftBuilder(
        router=ModelRouter([provider]), identity_kernel=identity,
    )

    assert builder.build("Create a document in Drive", ()) is None


def test_exact_canonical_phrase_creates_preview_but_no_provider_call(tmp_path):
    proposals = MemoryProposalStore(tmp_path / "proposals.json"); writer, _, _ = _writer(tmp_path); drafts = Drafts()
    service = GoogleDriveDocumentCreateConversationService(proposal_store=proposals, writer=writer, draft_builder=drafts)
    answer = service.propose("\u041c\u0430\u0448, \u0441\u043e\u0431\u0435\u0440\u0438 \u044d\u0442\u043e \u0432 \u0437\u0430\u043c\u0435\u0442\u043a\u0443 \u0438 \u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive.", conversation_id="c", recent_messages=("\u041c\u044b \u043e\u0431\u0441\u0443\u0434\u0438\u043b\u0438 AI.",), now_local=datetime.now(timezone.utc))
    assert "Итоги занятия по AI" in answer and "Обсудили локальные модели." in answer
    assert writer.transport.calls == []
    assert proposals.current_for_conversation("c").operation == "google_drive_document_create"


def test_inline_drive_document_material_owns_temporal_words_without_provider_call(tmp_path):
    message = (
        "Создай документ в Google Drive: Короткий итог сегодняшнего занятия — "
        "мы навели порядок в ветках Git, обновили main и продолжили работу "
        "над созданием Google Docs."
    )
    drafts = Drafts(DocumentDraft(
        title="Короткий итог занятия",
        body="Навели порядок в ветках Git, обновили main и продолжили работу над Google Docs.",
    ))
    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    writer, _, _ = _writer(tmp_path)
    service = GoogleDriveDocumentCreateConversationService(
        proposal_store=proposals, writer=writer, draft_builder=drafts,
    )

    preview = service.propose(
        message, conversation_id="live", recent_messages=(),
        now_local=datetime.now(timezone.utc),
    )

    proposal = proposals.current_for_conversation("live")
    assert "Короткий итог занятия" in preview
    assert "Навели порядок" in preview
    assert proposal.operation == "google_drive_document_create"
    assert proposal.record_payload["title"] == "Короткий итог занятия"
    assert proposal.record_payload["body"] == "Навели порядок в ветках Git, обновили main и продолжили работу над Google Docs."
    assert drafts.calls == [(message, ("Короткий итог сегодняшнего занятия — мы навели порядок в ветках Git, обновили main и продолжили работу над созданием Google Docs.",))]
    assert writer.transport.calls == []


def test_inline_drive_document_material_with_today_and_tomorrow_is_still_a_document(tmp_path):
    message = "Создай документ в Google Drive: Сегодня на занятии обсудили задачи на завтра."
    proposals = MemoryProposalStore(tmp_path / "proposals.json")
    writer, _, _ = _writer(tmp_path)
    service = GoogleDriveDocumentCreateConversationService(
        proposal_store=proposals, writer=writer, draft_builder=Drafts(),
    )

    assert service.propose(message, conversation_id="temporal-material", recent_messages=(), now_local=datetime.now(timezone.utc)) is not None
    assert proposals.current_for_conversation("temporal-material").operation == "google_drive_document_create"
    assert writer.transport.calls == []


def test_requires_explicit_write_and_does_not_claim_read_or_factual_phrases():
    assert drive_document_create_intent("\u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive")
    assert not drive_document_create_intent("\u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive")
    assert not drive_document_create_intent("\u0423 \u043c\u0435\u043d\u044f \u043a\u043e\u043d\u0446\u0435\u0440\u0442 \u0432\u043e \u0432\u0442\u043e\u0440\u043d\u0438\u043a")


def test_reject_is_non_mutating_and_confirmation_creates_then_verifies(tmp_path):
    proposals = MemoryProposalStore(tmp_path / "proposals.json"); writer, _, _ = _writer(tmp_path); service = GoogleDriveDocumentCreateConversationService(proposal_store=proposals, writer=writer, draft_builder=Drafts())
    service.propose("\u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive: AI notes for the team", conversation_id="one", recent_messages=(), now_local=datetime.now(timezone.utc))
    assert service.resolve("\u043d\u0435\u0442", conversation_id="one") is not None and not writer.transport.calls
    service.propose("\u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive: AI notes for the team", conversation_id="two", recent_messages=(), now_local=datetime.now(timezone.utc))
    assert service.resolve("\u0434\u0430", conversation_id="two") is not None
    assert sum(method == "POST" and "/drive/v3/files" in url for url, method, _ in writer.transport.calls) == 1


def test_missing_referent_clarifies_without_draft_proposal_receipt_or_provider(tmp_path):
    proposals = MemoryProposalStore(tmp_path / "proposals.json"); writer, _, _ = _writer(tmp_path); drafts = Drafts()
    service = GoogleDriveDocumentCreateConversationService(proposal_store=proposals, writer=writer, draft_builder=drafts)

    answer = service.propose("\u041c\u0430\u0448, \u0441\u043e\u0431\u0435\u0440\u0438 \u044d\u0442\u043e \u0432 \u0437\u0430\u043c\u0435\u0442\u043a\u0443 \u0438 \u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive.", conversation_id="missing", recent_messages=(), now_local=datetime.now(timezone.utc))

    assert "\u0427\u0442\u043e \u0438\u043c\u0435\u043d\u043d\u043e" in answer
    assert drafts.calls == []
    assert proposals.current_for_conversation("missing") is None
    assert not writer.receipt_store.path.exists()
    assert writer.transport.calls == []


def test_model_clarification_cannot_become_body_even_with_source_material(tmp_path):
    clarification = DocumentDraft(title="Question", body="\u0427\u0442\u043e \u0438\u043c\u0435\u043d\u043d\u043e \u043d\u0430\u0434\u043e \u0437\u0430\u043f\u0438\u0441\u0430\u0442\u044c? \u041f\u0440\u0438\u0448\u043b\u0438 \u0442\u0435\u043a\u0441\u0442.")
    drafts = Drafts(clarification); proposals = MemoryProposalStore(tmp_path / "proposals.json"); writer, _, _ = _writer(tmp_path)
    service = GoogleDriveDocumentCreateConversationService(proposal_store=proposals, writer=writer, draft_builder=drafts)

    answer = service.propose("\u0441\u043e\u0431\u0435\u0440\u0438 \u044d\u0442\u043e \u0432 \u0437\u0430\u043c\u0435\u0442\u043a\u0443 \u0438 \u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive", conversation_id="missing", recent_messages=("Qwen was selected as the local model.",), now_local=datetime.now(timezone.utc))

    assert "\u0427\u0442\u043e \u0438\u043c\u0435\u043d\u043d\u043e" in answer
    assert len(drafts.calls) == 1
    assert proposals.current_for_conversation("missing") is None


def test_valid_material_is_frozen_into_exact_preview_without_second_draft_call(tmp_path):
    drafts = Drafts(DocumentDraft(title="Exact title", body="Exact body from source.")); proposals = MemoryProposalStore(tmp_path / "proposals.json"); writer, _, _ = _writer(tmp_path)
    service = GoogleDriveDocumentCreateConversationService(proposal_store=proposals, writer=writer, draft_builder=drafts)
    service.propose("\u0441\u043e\u0431\u0435\u0440\u0438 \u044d\u0442\u043e \u0432 \u0437\u0430\u043c\u0435\u0442\u043a\u0443 \u0438 \u0441\u043e\u0437\u0434\u0430\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0432 Drive", conversation_id="valid", recent_messages=("Qwen was selected as the local model.",), now_local=datetime.now(timezone.utc))
    proposal = proposals.current_for_conversation("valid")
    application = object.__new__(ConversationApplicationService)
    application._conversation = type("Conversation", (), {"memory_intent_handler": type("Handler", (), {"proposal_store": proposals})()})()

    preview = application.pending_confirmation("valid")

    assert proposal.record_payload["title"] == preview.preview_title == "Exact title"
    assert proposal.record_payload["body"] == preview.preview_body == "Exact body from source."
    assert len(drafts.calls) == 1 and writer.transport.calls == []


def test_pre_mutation_failure_is_retryable_but_does_not_claim_success(tmp_path):
    transport = Transport(fail_before_create=True); writer, _, _ = _writer(tmp_path, transport=transport); op = _operation()
    assert writer.create_and_verify(op)[0] == "failed"
    transport.fail_before_create = False
    assert writer.create_and_verify(op)[0] == "verified"
    assert sum(method == "POST" and "/drive/v3/files" in url for url, method, _ in transport.calls) == 1


def test_lost_create_response_recovers_by_marker_without_second_create(tmp_path):
    transport = Transport(fail_after_create=True); writer, _, _ = _writer(tmp_path, transport=transport); op = _operation()
    assert writer.create_and_verify(op)[0] == "verified"
    transport.fail_after_create = False
    assert writer.create_and_verify(op)[0] == "verified"
    assert sum(method == "POST" and "/drive/v3/files" in url for url, method, _ in transport.calls) == 1


def test_drive_create_carries_exact_marker_and_persists_provider_id(tmp_path):
    transport = Transport(); writer, _, _ = _writer(tmp_path, transport=transport); operation = _operation()

    status, receipt = writer.create_and_verify(operation)

    create_call = next(body for url, method, body in transport.calls if method == "POST" and "/drive/v3/files" in url)
    import json
    payload = json.loads(create_call)
    assert status == "verified"
    assert receipt.provider_document_id == "doc-1"
    assert payload["mimeType"] == "application/vnd.google-apps.document"
    assert payload["appProperties"] == {
        "masha_home_operation_id": operation.operation_id,
        "masha_home_document_create_version": "1",
    }


def test_zero_marker_candidate_is_unresolved_then_later_recovery_never_recreates(tmp_path):
    transport = Transport(fail_after_create=True, hide_marker_once=True)
    writer, _, _ = _writer(tmp_path, transport=transport); operation = _operation()

    first, receipt = writer.create_and_verify(operation)
    second, recovered = writer.create_and_verify(operation)

    assert (first, receipt.status, receipt.outcome_detail) == ("create_unresolved", "create_unresolved", "marker_search_zero")
    assert (second, recovered.status) == ("verified", "verified")
    assert sum(method == "POST" and "/drive/v3/files" in url for url, method, _ in transport.calls) == 1


def test_multiple_marker_candidates_and_content_mismatches_fail_closed(tmp_path):
    transport = Transport(fail_after_create=True)
    writer, _, _ = _writer(tmp_path, transport=transport); operation = _operation()
    transport.docs["doc-2"] = {"title": operation.title, "body": "", "marker": writer._marker(operation)}

    status, receipt = writer.create_and_verify(operation)

    assert (status, receipt.status, receipt.outcome_detail) == ("conflict", "conflict", "marker_search_multiple")
    assert not any(method == "POST" and url.endswith(":batchUpdate") for url, method, _ in transport.calls)


def test_structural_blank_is_inserted_once_and_lost_batch_response_is_verified_by_get(tmp_path):
    transport = Transport(fail_after_batch=True)
    writer, _, _ = _writer(tmp_path, transport=transport); operation = _operation()

    status, receipt = writer.create_and_verify(operation)

    assert status == "verified"
    assert receipt.status == "verified"
    assert transport.docs["doc-1"]["body"] == operation.body
    assert sum(method == "POST" and url.endswith(":batchUpdate") for url, method, _ in transport.calls) == 1


def test_legacy_unmarked_receipt_remains_unresolved_without_network_search_or_create(tmp_path):
    transport = Transport(); writer, _, _ = _writer(tmp_path, transport=transport); operation = _operation()
    writer.receipt_store.put(__import__("backend.connectors.google_drive.document_create", fromlist=["DriveDocumentCreateReceipt"]).DriveDocumentCreateReceipt(operation=operation, status="created_unverified"))

    status, receipt = writer.create_and_verify(operation)

    assert (status, receipt.status) == ("created_unverified", "created_unverified")
    assert transport.calls == []


def test_known_document_reconciles_without_duplicate_and_can_finish_body(tmp_path):
    transport = Transport(); writer, _, _ = _writer(tmp_path, transport=transport); op = _operation()
    receipt = writer.receipt_store.put(__import__("backend.connectors.google_drive.document_create", fromlist=["DriveDocumentCreateReceipt"]).DriveDocumentCreateReceipt(operation=op, status="created_unverified", provider_document_id="doc-1"))
    transport.docs["doc-1"] = {"title": op.title, "body": ""}
    assert writer.create_and_verify(op)[0] == "verified"
    assert not any(method == "POST" and "/drive/v3/files" in url for url, method, _ in transport.calls)


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


def test_legacy_documents_only_write_grant_requires_reconnect_before_mutation(tmp_path):
    writer, store, _ = _writer(tmp_path)
    store.save(store.load().model_copy(update={"document_write_requested_scope": "https://www.googleapis.com/auth/documents"}))

    assert writer.create_and_verify(_operation())[0] == "needs_reconnect"
    assert writer.transport.calls == []
