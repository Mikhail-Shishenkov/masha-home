"""Confirmed Yandex Mail delete/move over a real presented message."""

from __future__ import annotations

import email
import imaplib
import json
import re
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from backend.backup.recovery_journal import RecoveryJournal
from backend.connectors.presented_read_sets import parse_presented_entity_reference
from backend.conversation.memory_intent import (
    MemoryProposal,
    MemoryProposalStore,
    PendingProposalConflict,
    ProposalStatus,
)
from backend.runtime.action_contracts import (
    ProposalPreparation,
    ProposalPreparationStatus,
)

from .config import YandexMailConfigStore
from .models import MailMessageSummary, safe_message_id
from .network import YandexMailNetworkBlocked, assert_yandex_mail_network_allowed
from .reader import (
    YandexMailInvalidGrant,
    YandexMailUnavailable,
    _decode,
    _token_post,
)


class MailTargetState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uid: str = Field(min_length=1, max_length=100)
    uidvalidity: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=300)
    sender: str = Field(min_length=1, max_length=300)
    received_at: AwareDatetime | None = None
    size: int | None = Field(default=None, ge=0, le=100 * 1024 * 1024)
    message_id: str = Field(min_length=1, max_length=500)

    @field_validator("message_id")
    @classmethod
    def message_id_is_safe_for_imap_search(cls, value: str) -> str:
        if safe_message_id(value) != value:
            raise ValueError("unsafe mail Message-ID")
        return value


class MailMutationOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(min_length=36, max_length=36)
    action: Literal["delete", "move"]
    source_mailbox: Literal["INBOX"] = "INBOX"
    destination_role: Literal["trash", "archive"]
    destination_mailbox: str = Field(min_length=1, max_length=500)
    target: MailTargetState

    @field_validator("destination_mailbox")
    @classmethod
    def destination_mailbox_has_no_command_delimiters(cls, value: str) -> str:
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("unsafe mail destination")
        return value


class MailMutationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: MailMutationOperation
    status: Literal[
        "proposed", "rejected", "executing", "blocked", "failed",
        "moved_unverified", "conflict", "target_missing", "verified",
    ]
    confirmed_at: AwareDatetime | None = None
    dispatch_started_at: AwareDatetime | None = None
    verified_at: AwareDatetime | None = None


class MailMutationReceiptStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items = self._load()

    def get(self, operation_id: str) -> MailMutationReceipt | None:
        return self._items.get(operation_id)

    def put(self, receipt: MailMutationReceipt) -> MailMutationReceipt:
        items = {**self._items, receipt.operation.operation_id: receipt}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"receipts": [item.model_dump(mode="json") for item in items.values()]},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        self._items = items
        return receipt

    def _load(self) -> dict[str, MailMutationReceipt]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            row["operation"]["operation_id"]: MailMutationReceipt.model_validate(row)
            for row in payload.get("receipts", [])
        }


class MailMutationSession(Protocol):
    def bind(self, mailbox: str, uid: str) -> MailTargetState | None: ...
    def special_mailbox(self, role: str) -> str | None: ...
    def move(self, source_mailbox: str, target: MailTargetState, destination: str) -> None: ...
    def destination_count(self, destination: str, message_id: str) -> int: ...
    def close(self) -> None: ...


class ImapYandexMutationSession:
    """Uses atomic UID MOVE only; no COPY+STORE+EXPUNGE emulation."""

    _ROLE_FLAG = {"trash": r"\Trash", "archive": r"\Archive"}
    _MAX_DESTINATION_VERIFY_CANDIDATES = 20

    def __init__(self, email_address: str, access_token: str):
        self.client = imaplib.IMAP4_SSL("imap.yandex.com", 993)
        payload = (
            f"user={email_address}\x01auth=Bearer {access_token}\x01\x01".encode()
        )
        self.client.authenticate("XOAUTH2", lambda _: payload)

    def bind(self, mailbox: str, uid: str) -> MailTargetState | None:
        uidvalidity = self._select(mailbox, readonly=True)
        typ, data = self.client.uid(
            "FETCH",
            uid,
            "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)] RFC822.SIZE)",
        )
        if typ != "OK":
            raise YandexMailUnavailable("mail_target_unavailable")
        raw = next(
            (
                item[1]
                for item in data or ()
                if isinstance(item, tuple) and isinstance(item[1], bytes)
            ),
            b"",
        )
        if not raw:
            return None
        message = email.message_from_bytes(raw)
        name, address = parseaddr(_decode(message.get("From", "")))
        sender = (name or address or "Неизвестный отправитель")[:300]
        try:
            received = parsedate_to_datetime(message.get("Date"))
            if received is not None:
                received = received.astimezone(timezone.utc)
        except Exception:
            received = None
        message_id = str(message.get("Message-ID") or "").strip()[:500]
        if not message_id:
            raise YandexMailUnavailable("mail_message_id_unavailable")
        size_match = re.search(
            rb"RFC822\.SIZE (\d+)",
            b" ".join(
                item[0]
                for item in data or ()
                if isinstance(item, tuple) and isinstance(item[0], bytes)
            ),
        )
        return MailTargetState(
            uid=uid,
            uidvalidity=uidvalidity,
            subject=_decode(message.get("Subject")) or "Без темы",
            sender=sender,
            received_at=received,
            size=None if size_match is None else int(size_match.group(1)),
            message_id=message_id,
        )

    def special_mailbox(self, role: str) -> str | None:
        required_flag = self._ROLE_FLAG.get(role)
        if required_flag is None:
            return None
        typ, data = self.client.list()
        if typ != "OK":
            raise YandexMailUnavailable("mail_folders_unavailable")
        for raw in data or ():
            if not isinstance(raw, bytes):
                continue
            text = raw.decode("ascii", errors="replace")
            flags = text.partition(")")[0] + ")"
            if required_flag.casefold() not in flags.casefold():
                continue
            match = re.search(r'(?P<name>"(?:[^"\\]|\\.)*"|[^ ]+)$', text)
            if match is None:
                continue
            return match.group("name")[:500]
        return None

    def move(
        self,
        source_mailbox: str,
        target: MailTargetState,
        destination: str,
    ) -> None:
        uidvalidity = self._select(source_mailbox, readonly=False)
        if uidvalidity != target.uidvalidity:
            raise MailMutationConflict("mail_uidvalidity_changed")
        capabilities = {
            value.decode("ascii", errors="ignore").upper()
            if isinstance(value, bytes) else str(value).upper()
            for value in getattr(self.client, "capabilities", ())
        }
        if "MOVE" not in capabilities:
            raise YandexMailUnavailable("imap_move_unavailable")
        typ, _ = self.client.uid("MOVE", target.uid, destination)
        if typ != "OK":
            raise YandexMailUnavailable("mail_move_unavailable")

    def destination_count(self, destination: str, message_id: str) -> int:
        self._select(destination, readonly=True)
        typ, data = self.client.uid(
            "SEARCH",
            None,
            "HEADER",
            "Message-ID",
            f'"{message_id}"',
        )
        if typ == "OK":
            return len((data or [b""])[0].split())

        # Yandex can return a transient backend error for HEADER searches even
        # while ordinary UID SEARCH/FETCH remains healthy.  Inspect only a
        # bounded tail of the destination and retain exact Message-ID identity.
        typ, data = self.client.uid("SEARCH", None, "ALL")
        if typ != "OK":
            raise YandexMailUnavailable("mail_verify_unavailable")
        raw_uids = (data or [b""])[0]
        if not isinstance(raw_uids, bytes):
            raise YandexMailUnavailable("mail_verify_unavailable")
        matches = 0
        for raw_uid in raw_uids.split()[
            -self._MAX_DESTINATION_VERIFY_CANDIDATES:
        ]:
            try:
                uid = raw_uid.decode("ascii")
            except UnicodeDecodeError:
                continue
            candidate = self.bind(destination, uid)
            if candidate is not None and candidate.message_id == message_id:
                matches += 1
        return matches

    def _select(self, mailbox: str, *, readonly: bool) -> str:
        typ, _ = self.client.select(mailbox, readonly=readonly)
        if typ != "OK":
            raise YandexMailUnavailable("mailbox_unavailable")
        _, values = self.client.response("UIDVALIDITY")
        raw = next((item for item in values or () if isinstance(item, bytes)), b"")
        match = re.search(rb"\d+", raw)
        if match is None:
            raise YandexMailUnavailable("mail_uidvalidity_unavailable")
        return match.group().decode("ascii")

    def close(self) -> None:
        try:
            self.client.logout()
        except Exception:
            pass


class MailMutationConflict(RuntimeError):
    pass


class MailManageReconnectRequired(RuntimeError):
    pass


class YandexMailMutationWriter:
    def __init__(
        self,
        *,
        config_store: YandexMailConfigStore,
        secret_store,
        receipt_store: MailMutationReceiptStore,
        session_factory=None,
        policy_store=None,
        safety_store=None,
        token_post=None,
        clock=None,
        recovery_journal: RecoveryJournal | None = None,
    ):
        self.config_store = config_store
        self.secret_store = secret_store
        self.receipt_store = receipt_store
        self.session_factory = session_factory or ImapYandexMutationSession
        self.policy_store = policy_store
        self.safety_store = safety_store
        self.token_post = token_post or _token_post
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.recovery_journal = recovery_journal

    def bind(
        self,
        summary: MailMessageSummary,
        *,
        action: Literal["delete", "move"],
    ) -> tuple[str, MailMutationOperation | None]:
        if self._recovery_blocked():
            return "blocked", None
        if summary.uidvalidity is None or summary.message_id is None:
            return "refresh_required", None
        session = None
        try:
            config, token = self._write_token()
            session = self._session(config.account_email, token)
            target = session.bind("INBOX", summary.message_ref)
            if target is None:
                return "not_found", None
            if not self._same_presented_message(summary, target):
                return "conflict", None
            role = "trash" if action == "delete" else "archive"
            destination = session.special_mailbox(role)
            if destination is None:
                return "destination_unavailable", None
            return "resolved", MailMutationOperation(
                operation_id=str(uuid4()),
                action=action,
                destination_role=role,
                destination_mailbox=destination,
                target=target,
            )
        except YandexMailInvalidGrant:
            self._delete_write_secret()
            return "needs_reconnect", None
        except MailManageReconnectRequired:
            return "needs_reconnect", None
        except (
            YandexMailUnavailable,
            YandexMailNetworkBlocked,
            imaplib.IMAP4.error,
            OSError,
        ):
            return "unavailable", None
        finally:
            if session is not None:
                session.close()

    def execute(
        self,
        operation: MailMutationOperation,
    ) -> tuple[str, MailMutationReceipt]:
        existing = self.receipt_store.get(operation.operation_id)
        if existing is not None:
            if existing.operation != operation:
                return "failed", existing
            if existing.status == "verified":
                return "verified", existing
            if existing.status in {"executing", "moved_unverified"}:
                return self._reconcile(existing)
            if existing.status not in {"proposed", "blocked", "failed"}:
                return existing.status, existing
        if self._recovery_blocked():
            return "blocked", self.receipt_store.put(MailMutationReceipt(
                operation=operation,
                status="blocked",
                confirmed_at=None if existing is None else existing.confirmed_at,
            ))
        confirmed = self.receipt_store.put(MailMutationReceipt(
            operation=operation,
            status="executing",
            confirmed_at=(
                existing.confirmed_at
                if existing is not None and existing.confirmed_at is not None
                else self.clock()
            ),
            dispatch_started_at=(
                None if existing is None else existing.dispatch_started_at
            ),
        ))
        return self._reconcile(confirmed)

    def _reconcile(
        self,
        receipt: MailMutationReceipt,
    ) -> tuple[str, MailMutationReceipt]:
        if self._recovery_blocked():
            return "blocked", self.receipt_store.put(
                receipt.model_copy(update={"status": "blocked"})
            )
        session = None
        try:
            config, token = self._write_token()
            session = self._session(config.account_email, token)
            source = session.bind(
                receipt.operation.source_mailbox,
                receipt.operation.target.uid,
            )
            if source is None:
                if receipt.dispatch_started_at is None:
                    return "target_missing", self.receipt_store.put(
                        receipt.model_copy(update={"status": "target_missing"})
                    )
                return self._verify_destination(receipt, session)
            if source != receipt.operation.target:
                return "conflict", self.receipt_store.put(
                    receipt.model_copy(update={"status": "conflict"})
                )
            dispatched = receipt
            if receipt.dispatch_started_at is None:
                dispatched = self.receipt_store.put(receipt.model_copy(update={
                    "status": "executing",
                    "dispatch_started_at": self.clock(),
                }))
            session.move(
                dispatched.operation.source_mailbox,
                dispatched.operation.target,
                dispatched.operation.destination_mailbox,
            )
            return self._verify_destination(dispatched, session)
        except MailMutationConflict:
            return "conflict", self.receipt_store.put(
                receipt.model_copy(update={"status": "conflict"})
            )
        except YandexMailInvalidGrant:
            self._delete_write_secret()
            return "needs_reconnect", self.receipt_store.put(
                receipt.model_copy(update={"status": "failed"})
            )
        except MailManageReconnectRequired:
            return "needs_reconnect", self.receipt_store.put(
                receipt.model_copy(update={"status": "failed"})
            )
        except (
            YandexMailUnavailable,
            YandexMailNetworkBlocked,
            imaplib.IMAP4.error,
            OSError,
        ):
            current = (
                self.receipt_store.get(receipt.operation.operation_id)
                or receipt
            )
            status = (
                "moved_unverified"
                if current.dispatch_started_at is not None
                else "failed"
            )
            return status, self.receipt_store.put(
                current.model_copy(update={"status": status})
            )
        finally:
            if session is not None:
                session.close()

    def _verify_destination(
        self,
        receipt: MailMutationReceipt,
        session: MailMutationSession,
    ) -> tuple[str, MailMutationReceipt]:
        count = session.destination_count(
            receipt.operation.destination_mailbox,
            receipt.operation.target.message_id,
        )
        if count == 1:
            return "verified", self.receipt_store.put(receipt.model_copy(update={
                "status": "verified",
                "verified_at": self.clock(),
            }))
        if count > 1:
            return "conflict", self.receipt_store.put(
                receipt.model_copy(update={"status": "conflict"})
            )
        return "moved_unverified", self.receipt_store.put(
            receipt.model_copy(update={"status": "moved_unverified"})
        )

    def reject(self, operation: MailMutationOperation) -> MailMutationReceipt:
        return self.receipt_store.put(MailMutationReceipt(
            operation=operation,
            status="rejected",
        ))

    def _write_token(self):
        assert_yandex_mail_network_allowed(
            policy_store=self.policy_store,
            safety_store=self.safety_store,
        )
        config = self.config_store.load()
        if (
            config is None
            or config.write_secret_ref is None
            or config.write_requested_scope is None
        ):
            raise MailManageReconnectRequired("mail_manage_reconnect_required")
        refresh = self.secret_store.get(config.write_secret_ref)
        client_secret = self.secret_store.get(config.client_secret_ref)
        if refresh is None or client_secret is None:
            raise MailManageReconnectRequired("mail_manage_reconnect_required")
        payload = self.token_post({
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": config.client_id,
            "client_secret": client_secret,
        })
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise MailManageReconnectRequired("mail_manage_reconnect_required")
        replacement = payload.get("refresh_token")
        if isinstance(replacement, str) and replacement:
            self.secret_store.put(config.write_secret_ref, replacement)
        return config, token

    def _session(self, email_address: str, token: str):
        assert_yandex_mail_network_allowed(
            policy_store=self.policy_store,
            safety_store=self.safety_store,
        )
        return self.session_factory(email_address, token)

    def _delete_write_secret(self) -> None:
        config = self.config_store.load()
        if config is not None and config.write_secret_ref is not None:
            self.secret_store.delete(config.write_secret_ref)

    def _recovery_blocked(self) -> bool:
        return bool(
            self.recovery_journal is not None
            and self.recovery_journal.is_hold()
        )

    @staticmethod
    def _same_presented_message(
        summary: MailMessageSummary,
        target: MailTargetState,
    ) -> bool:
        normalize = lambda value: " ".join(value.casefold().replace("ё", "е").split())
        return bool(
            summary.uidvalidity == target.uidvalidity
            and summary.message_id == target.message_id
            and normalize(summary.subject) == normalize(target.subject)
            and normalize(summary.sender) == normalize(target.sender)
            and (summary.size is None or target.size is None or summary.size == target.size)
        )


class YandexMailMutationConversationService:
    def __init__(
        self,
        *,
        proposal_store: MemoryProposalStore,
        writer: YandexMailMutationWriter,
        presented_read_sets,
    ):
        self.proposal_store = proposal_store
        self.writer = writer
        self.presented_read_sets = presented_read_sets

    def prepare_from_resolved_intent(
        self,
        *,
        action: Literal["delete", "move"],
        target: str,
        conversation_id: str,
        now_local: datetime,
    ) -> ProposalPreparation:
        context = self.presented_read_sets.current_context(conversation_id)
        if (
            context is None
            or context.owner != "yandex_mail"
            or context.entity_kind != "письмо"
        ):
            return self._no_action("Сначала покажи нужные письма, чтобы я безопасно выбрала одно.")
        reference = parse_presented_entity_reference(
            target,
            entity_kind="письмо",
            visible_labels=tuple(item.subject for item in context.items),
            require_read_action=False,
        )
        if reference is None:
            return self._no_action("Уточни, какое именно показанное письмо выбрать.")
        resolved = self.presented_read_sets.resolve(
            conversation_id,
            owner="yandex_mail",
            entity_kind="письмо",
            reference=reference,
            label_of=lambda item: item.subject,
        )
        if resolved.item is None:
            return self._no_action("Уточни одно письмо — наугад ничего не меняю.")
        status, operation = self.writer.bind(resolved.item, action=action)
        if status != "resolved" or operation is None:
            return self._no_action({
                "not_found": "Этого письма уже нет во входящих — ничего не меняю.",
                "conflict": "Письмо изменилось после показа. Обнови список — ничего не меняю.",
                "refresh_required": "Сначала обнови список писем — старого показа недостаточно для безопасного действия.",
                "needs_reconnect": "Для этого нужно отдельно подключить управление Яндекс Почтой.",
                "destination_unavailable": "Не нашла безопасную системную папку для этого действия.",
                "blocked": "Сейчас внешние действия остановлены, поэтому письмо не меняю.",
            }.get(status, "Сейчас не удалось безопасно проверить письмо."))
        proposal = MemoryProposal(
            id=str(uuid4()),
            conversation_id=conversation_id,
            record_type="yandex_mail_message",
            record_payload=operation.model_dump(mode="json"),
            created_at=now_local,
            status=ProposalStatus.PENDING,
            operation=f"yandex_mail_{action}",
        )
        try:
            self.proposal_store.create(proposal)
        except PendingProposalConflict:
            return self._no_action(
                "Сначала закончим предыдущее подтверждение — письмо пока не меняю."
            )
        self.writer.receipt_store.put(MailMutationReceipt(
            operation=operation,
            status="proposed",
        ))
        verb = "Переместить в корзину" if action == "delete" else "Переместить в архив"
        return ProposalPreparation(
            response=f"{verb} письмо «{operation.target.subject}» от {operation.target.sender}?",
            status=ProposalPreparationStatus.PENDING_CONFIRMATION,
            application_operation=f"yandex_mail_{action}",
        )

    def resolve(
        self,
        message: str,
        *,
        conversation_id: str,
        proposal_id: str | None = None,
    ) -> str | None:
        confirm = re.match(
            r"^\s*(?:да|подтверждаю|перемести|удали)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$",
            message,
            re.IGNORECASE,
        )
        reject = re.match(
            r"^\s*(?:нет|не надо|не сейчас|отмена)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$",
            message,
            re.IGNORECASE,
        )
        command = confirm or reject
        if command is None:
            return None
        proposal = self.proposal_store.current_for_conversation(conversation_id)
        expected = proposal_id or command.group("id")
        if (
            proposal is None
            or (expected is not None and proposal.id != expected)
            or proposal.operation not in {"yandex_mail_delete", "yandex_mail_move"}
        ):
            return None
        try:
            operation = MailMutationOperation.model_validate(proposal.record_payload)
        except Exception:
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            return "Не смогла безопасно проверить действие, поэтому письмо не меняла."
        if reject is not None:
            receipt = self.writer.receipt_store.get(operation.operation_id)
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            if receipt is not None and receipt.dispatch_started_at is not None:
                return (
                    "Хорошо, пока не проверяю. Перемещение могло уже примениться; "
                    "не утверждаю, что письмо осталось на месте."
                )
            self.writer.reject(operation)
            return "Хорошо, письмо оставляю на месте."
        status, _ = self.writer.execute(operation)
        if status == "verified":
            self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
            return (
                f"Готово: письмо «{operation.target.subject}» переместила "
                f"{'в корзину' if operation.action == 'delete' else 'в архив'}."
            )
        if status == "moved_unverified":
            return "Перемещение могло выполниться, но я пока не смогла его проверить."
        if status == "conflict":
            self.proposal_store.set_status(
                proposal.id,
                ProposalStatus.CANCELLED,
            )
            return "Письмо изменилось после предпросмотра. Я его не перемещала."
        if status == "target_missing":
            self.proposal_store.set_status(
                proposal.id,
                ProposalStatus.CANCELLED,
            )
            return "Письма уже нет во входящих; не утверждаю, что его переместила я."
        if status == "needs_reconnect":
            return "Для этого нужно отдельно подключить управление Яндекс Почтой."
        return "Не удалось переместить письмо — ничего не утверждаю как готовое."

    @staticmethod
    def _no_action(response: str) -> ProposalPreparation:
        return ProposalPreparation(
            response=response,
            status=ProposalPreparationStatus.NO_ACTION,
        )
