from datetime import datetime, timezone

from backend.backup.recovery_journal import RecoveryJournal
from backend.backup.recovery_models import RecoveryPhase, RecoveryState, RestoreMode
from backend.connectors import yandex_mail_cli
from backend.connectors.presented_read_sets import PresentedReadSetRegistry
from backend.connectors.yandex_mail.config import (
    YANDEX_MAIL_WRITE_SCOPE,
    YANDEX_MAIL_WRITE_SECRET_REF,
    YandexMailConfig,
    YandexMailConfigStore,
)
from backend.connectors.yandex_mail.models import MailMessageSummary
from backend.connectors.yandex_mail.mutations import (
    ImapYandexMutationSession,
    MailMutationReceiptStore,
    MailTargetState,
    YandexMailMutationConversationService,
    YandexMailMutationWriter,
)
from backend.connectors.yandex_mail.reader import (
    YandexMailInvalidGrant,
    YandexMailUnavailable,
)
from backend.conversation.memory_intent import MemoryProposalStore, ProposalStatus
from backend.external_observation.policy import (
    InternetAccessMode,
    InternetAccessPolicy,
    InternetAccessPolicyStore,
)
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.secrets import ConnectorCredentialState, InMemorySecretStore


NOW = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)


def _recovery_state(phase: RecoveryPhase) -> RecoveryState:
    return RecoveryState(
        recovery_id="recovery-mail-0001",
        backup_id="backup-mail-0001",
        restore_mode=RestoreMode.REPLACE,
        phase=phase,
        created_at=NOW,
        updated_at=NOW,
    )


def _summary():
    return MailMessageSummary(
        "yandex",
        "42",
        "Итоги занятия",
        "Анна",
        NOW,
        512,
        False,
        "9001",
        "<lesson-42@example.test>",
    )


def _target():
    return MailTargetState(
        uid="42",
        uidvalidity="9001",
        subject="Итоги занятия",
        sender="Анна",
        received_at=NOW,
        size=512,
        message_id="<lesson-42@example.test>",
    )


class _Mailbox:
    def __init__(self):
        self.source = {"42": _target()}
        self.destinations = {"Trash": [], "Archive": []}
        self.move_calls = []
        self.sessions = 0
        self.fail_after_move = False


class _Session:
    def __init__(self, mailbox):
        self.mailbox = mailbox
        self.mailbox.sessions += 1

    def bind(self, mailbox, uid):
        assert mailbox == "INBOX"
        return self.mailbox.source.get(uid)

    def special_mailbox(self, role):
        return {"trash": "Trash", "archive": "Archive"}.get(role)

    def move(self, source_mailbox, target, destination):
        assert source_mailbox == "INBOX"
        self.mailbox.move_calls.append((target.uid, destination))
        moved = self.mailbox.source.pop(target.uid)
        self.mailbox.destinations[destination].append(moved)
        if self.mailbox.fail_after_move:
            self.mailbox.fail_after_move = False
            raise YandexMailUnavailable("lost_move_response")

    def destination_count(self, destination, message_id):
        return sum(
            item.message_id == message_id
            for item in self.mailbox.destinations[destination]
        )

    def close(self):
        return None


def _service(tmp_path, *, policy_store=None, safety_store=None):
    config_store = YandexMailConfigStore(
        tmp_path / "local-data/config/yandex-mail.json"
    )
    config = YandexMailConfig(
        client_id="mail-client",
        account_email="misha@yandex.ru",
        write_secret_ref=YANDEX_MAIL_WRITE_SECRET_REF,
        write_requested_scope=YANDEX_MAIL_WRITE_SCOPE,
    )
    config_store.save(config)
    secrets = InMemorySecretStore()
    secrets.put(config.secret_ref, "READ_REFRESH")
    secrets.put(config.client_secret_ref, "CLIENT_SECRET")
    secrets.put(config.write_secret_ref, "WRITE_REFRESH")
    mailbox = _Mailbox()
    token_calls = []
    writer = YandexMailMutationWriter(
        config_store=config_store,
        secret_store=secrets,
        receipt_store=MailMutationReceiptStore(
            tmp_path / "local-data/runtime/yandex-mail-mutations.json"
        ),
        session_factory=lambda *_: _Session(mailbox),
        policy_store=policy_store,
        safety_store=safety_store,
        token_post=lambda fields: token_calls.append(fields) or {"access_token": "ACCESS"},
        clock=lambda: NOW,
    )
    presented = PresentedReadSetRegistry()
    presented.present(
        "mail-conversation",
        "yandex_mail",
        (_summary(),),
        entity_kind="письмо",
        presentation_kind="unread",
    )
    service = YandexMailMutationConversationService(
        proposal_store=MemoryProposalStore(
            tmp_path / "local-data/runtime/memory-proposals.json"
        ),
        writer=writer,
        presented_read_sets=presented,
    )
    return service, writer, mailbox, config_store, secrets, token_calls


def test_manage_scope_is_separate_and_secret_values_never_enter_config(tmp_path):
    _, _, _, store, secrets, _ = _service(tmp_path)
    config = store.load()
    serialized = store.path.read_text(encoding="utf-8")

    assert config.requested_scope == "mail:imap_ro"
    assert config.write_requested_scope == "mail:imap_full"
    assert config.write_credential_state(secrets) is ConnectorCredentialState.READY
    assert "READ_REFRESH" not in serialized
    assert "WRITE_REFRESH" not in serialized
    assert "CLIENT_SECRET" not in serialized
    assert "9001" not in str(_summary().model_value())
    assert "lesson-42@example.test" not in str(_summary().model_value())


def test_old_presented_mail_without_stable_identity_requires_refresh_without_network(
    tmp_path,
):
    service, _, mailbox, _, _, token_calls = _service(tmp_path)
    service.presented_read_sets.present(
        "mail-conversation",
        "yandex_mail",
        (MailMessageSummary(
            "yandex", "42", "Итоги занятия", "Анна", NOW, 512, False,
        ),),
        entity_kind="письмо",
        presentation_kind="unread",
    )

    preparation = service.prepare_from_resolved_intent(
        action="delete",
        target="это письмо",
        conversation_id="mail-conversation",
        now_local=NOW,
    )

    assert preparation.status.value == "no_action"
    assert "обнови список" in preparation.response
    assert token_calls == [] and mailbox.sessions == 0 and mailbox.move_calls == []


def test_delete_and_archive_require_confirmation_then_verify_one_atomic_move(tmp_path):
    for action, destination in (("delete", "Trash"), ("move", "Archive")):
        root = tmp_path / action
        service, writer, mailbox, _, _, _ = _service(root)

        preparation = service.prepare_from_resolved_intent(
            action=action,
            target="это письмо",
            conversation_id="mail-conversation",
            now_local=NOW,
        )
        proposal = service.proposal_store.current_for_conversation(
            "mail-conversation"
        )

        assert preparation.status.value == "pending_confirmation"
        assert proposal is not None and proposal.status is ProposalStatus.PENDING
        assert mailbox.move_calls == []
        response = service.resolve("да", conversation_id="mail-conversation")
        receipt = writer.receipt_store.get(proposal.record_payload["operation_id"])
        repeated_status, _ = writer.execute(receipt.operation)

        assert "Готово" in response
        assert mailbox.move_calls == [("42", destination)]
        assert receipt.status == "verified" and receipt.verified_at == NOW
        assert repeated_status == "verified"
        assert mailbox.move_calls == [("42", destination)]


def test_lost_move_response_reconciles_by_message_id_without_second_move(tmp_path):
    service, writer, mailbox, _, _, _ = _service(tmp_path)
    service.prepare_from_resolved_intent(
        action="move",
        target="это письмо",
        conversation_id="mail-conversation",
        now_local=NOW,
    )
    proposal = service.proposal_store.current_for_conversation("mail-conversation")
    operation = writer.receipt_store.get(proposal.record_payload["operation_id"]).operation
    mailbox.fail_after_move = True

    first_status, first = writer.execute(operation)
    second_status, second = writer.execute(operation)

    assert first_status == "moved_unverified"
    assert first.dispatch_started_at == NOW
    assert second_status == "verified" and second.verified_at == NOW
    assert first.operation.operation_id == second.operation.operation_id
    assert mailbox.move_calls == [("42", "Archive")]


def test_yandex_header_search_backend_error_uses_bounded_exact_identity_fallback():
    class Client:
        capabilities = (b"IMAP4rev1", b"MOVE", b"UIDPLUS")

        def __init__(self):
            self.calls = []

        def select(self, mailbox, readonly=False):
            self.calls.append(("SELECT", mailbox, readonly))
            return "OK", [b"2"]

        def response(self, name):
            assert name == "UIDVALIDITY"
            return "OK", [b"777"]

        def uid(self, command, *args):
            self.calls.append((command, *args))
            if command == "SEARCH" and args[-1] != "ALL":
                return "NO", [b"[UNAVAILABLE] UID SEARCH Backend error"]
            if command == "SEARCH":
                return "OK", [b"40 41"]
            uid = args[0]
            message_id = (
                "<other@example.test>"
                if uid == "40"
                else "<lesson-42@example.test>"
            )
            raw = (
                "Subject: Итоги занятия\r\n"
                "From: Анна <anna@example.test>\r\n"
                f"Message-ID: {message_id}\r\n"
                "Date: Mon, 31 Aug 2026 09:00:00 +0000\r\n\r\n"
            ).encode("utf-8")
            return "OK", [(b"RFC822.SIZE 512", raw)]

        def logout(self):
            return "BYE", []

    session = object.__new__(ImapYandexMutationSession)
    session.client = Client()

    count = session.destination_count("Trash", "<lesson-42@example.test>")

    assert count == 1
    fetch_calls = [call for call in session.client.calls if call[0] == "FETCH"]
    assert len(fetch_calls) == 2
    assert all("BODY.PEEK[HEADER.FIELDS" in call[2] for call in fetch_calls)


def test_changed_or_unpresented_target_fails_closed_without_move(tmp_path):
    service, writer, mailbox, _, _, _ = _service(tmp_path)
    service.prepare_from_resolved_intent(
        action="delete",
        target="это письмо",
        conversation_id="mail-conversation",
        now_local=NOW,
    )
    proposal = service.proposal_store.current_for_conversation("mail-conversation")
    operation = writer.receipt_store.get(proposal.record_payload["operation_id"]).operation
    mailbox.source["42"] = _target().model_copy(update={"subject": "Другая тема"})

    status, _ = writer.execute(operation)

    assert status == "conflict"
    assert mailbox.move_calls == []
    response = service.resolve("да", conversation_id="mail-conversation")
    assert "изменилось" in response
    assert service.proposal_store.get(proposal.id).status is ProposalStatus.CANCELLED
    assert service.proposal_store.current_for_conversation("mail-conversation") is None

    isolated = YandexMailMutationConversationService(
        proposal_store=MemoryProposalStore(tmp_path / "isolated-proposals.json"),
        writer=writer,
        presented_read_sets=PresentedReadSetRegistry(),
    )
    result = isolated.prepare_from_resolved_intent(
        action="delete",
        target="это письмо",
        conversation_id="no-context",
        now_local=NOW,
    )
    assert result.status.value == "no_action"
    assert mailbox.move_calls == []


def test_off_and_emergency_stop_make_zero_token_session_or_move_calls(tmp_path):
    policy = InternetAccessPolicyStore(tmp_path / "internet.json")
    policy.save(InternetAccessPolicy(mode=InternetAccessMode.OFF))
    service, _, mailbox, _, _, token_calls = _service(
        tmp_path / "off",
        policy_store=policy,
    )

    off = service.prepare_from_resolved_intent(
        action="delete",
        target="это письмо",
        conversation_id="mail-conversation",
        now_local=NOW,
    )

    assert off.status.value == "no_action"
    assert token_calls == [] and mailbox.sessions == 0 and mailbox.move_calls == []

    safety = AutonomySafetyStore(tmp_path / "safety.json")
    AutonomySafetyService(store=safety).engage()
    service, _, mailbox, _, _, token_calls = _service(
        tmp_path / "stop",
        safety_store=safety,
    )
    stopped = service.prepare_from_resolved_intent(
        action="move",
        target="это письмо",
        conversation_id="mail-conversation",
        now_local=NOW,
    )
    assert stopped.status.value == "no_action"
    assert token_calls == [] and mailbox.sessions == 0 and mailbox.move_calls == []


def test_recovery_hold_blocks_mail_manage_before_token_or_session(tmp_path):
    service, writer, mailbox, _, _, token_calls = _service(tmp_path)
    journal = RecoveryJournal(tmp_path)
    journal.save(_recovery_state(RecoveryPhase.HOLD))
    writer.recovery_journal = journal

    blocked = service.prepare_from_resolved_intent(
        action="delete",
        target="это письмо",
        conversation_id="mail-conversation",
        now_local=NOW,
    )

    assert blocked.status.value == "no_action"
    assert "остановлены" in blocked.response
    assert token_calls == [] and mailbox.sessions == 0 and mailbox.move_calls == []


def test_invalid_manage_grant_deletes_only_write_credential(tmp_path):
    service, writer, mailbox, store, secrets, _ = _service(tmp_path)
    writer.token_post = lambda _fields: (_ for _ in ()).throw(
        YandexMailInvalidGrant("invalid_grant")
    )

    result = service.prepare_from_resolved_intent(
        action="move",
        target="это письмо",
        conversation_id="mail-conversation",
        now_local=NOW,
    )
    config = store.load()

    assert result.status.value == "no_action"
    assert "отдельно подключить" in result.response
    assert not secrets.exists(config.write_secret_ref)
    assert secrets.exists(config.secret_ref)
    assert secrets.exists(config.client_secret_ref)
    assert mailbox.sessions == 0 and mailbox.move_calls == []


def test_connect_write_stores_only_separate_manage_secret_and_disconnects_all(
    tmp_path, monkeypatch,
):
    config_store = YandexMailConfigStore(
        tmp_path / "local-data/config/yandex-mail.json"
    )
    config = YandexMailConfig(
        client_id="mail-client",
        account_email="misha@yandex.ru",
    )
    config_store.save(config)
    secrets = InMemorySecretStore()
    secrets.put(config.secret_ref, "READ_REFRESH")
    secrets.put(config.client_secret_ref, "CLIENT_SECRET")
    authorize_calls = []
    monkeypatch.setattr(
        yandex_mail_cli,
        "WindowsCredentialManagerSecretStore",
        lambda: secrets,
    )
    monkeypatch.setattr(
        yandex_mail_cli,
        "authorize",
        lambda **kwargs: authorize_calls.append(kwargs) or {
            "refresh_token": "WRITE_REFRESH",
        },
    )

    assert yandex_mail_cli.main([
        "--project-root", str(tmp_path), "connect-write",
    ]) == 0
    saved = config_store.load()
    serialized = config_store.path.read_text(encoding="utf-8")

    assert authorize_calls[0]["scope"] == YANDEX_MAIL_WRITE_SCOPE
    assert saved.write_secret_ref == YANDEX_MAIL_WRITE_SECRET_REF
    assert secrets.get(saved.write_secret_ref) == "WRITE_REFRESH"
    assert "CLIENT_SECRET" not in serialized
    assert "READ_REFRESH" not in serialized
    assert "WRITE_REFRESH" not in serialized

    assert yandex_mail_cli.main([
        "--project-root", str(tmp_path), "disconnect",
    ]) == 0
    assert config_store.load() is None
    assert not secrets.exists(config.secret_ref)
    assert not secrets.exists(config.client_secret_ref)
    assert not secrets.exists(YANDEX_MAIL_WRITE_SECRET_REF)
