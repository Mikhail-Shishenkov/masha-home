"""Confirmed, idempotent deletion of one real primary-calendar event."""

from __future__ import annotations

import json
import re
from datetime import date as calendar_date, datetime, time
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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

from .network import GoogleCalendarNetworkBlocked
from .reader import (
    GoogleCalendarHttpFailure,
    GoogleCalendarReconnectRequired,
    GoogleCalendarUnavailable,
    GoogleTokenInvalidGrant,
)
from .update import (
    CalendarEventState,
    CalendarUpdateIntent,
    GoogleCalendarUpdater,
)


class CalendarDeleteOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(min_length=36, max_length=36)
    calendar_id: Literal["primary"] = "primary"
    calendar_label: Literal["Основной календарь"] = "Основной календарь"
    provider_event_id: str = Field(min_length=1, max_length=300)
    before: CalendarEventState
    etag: str = Field(min_length=1, max_length=500)
    home_timezone: str = Field(min_length=1, max_length=100)


class CalendarDeleteReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: CalendarDeleteOperation
    status: Literal[
        "proposed", "rejected", "executing", "blocked", "failed",
        "deleted_unverified", "conflict", "verified",
    ]
    confirmed_at: AwareDatetime | None = None
    dispatch_started_at: AwareDatetime | None = None
    verified_at: AwareDatetime | None = None


class CalendarDeleteReceiptStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items = self._load()

    def get(self, operation_id: str) -> CalendarDeleteReceipt | None:
        return self._items.get(operation_id)

    def put(self, receipt: CalendarDeleteReceipt) -> CalendarDeleteReceipt:
        items = {**self._items, receipt.operation.operation_id: receipt}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"receipts": [row.model_dump(mode="json") for row in items.values()]},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        self._items = items
        return receipt

    def _load(self) -> dict[str, CalendarDeleteReceipt]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            row["operation"]["operation_id"]: CalendarDeleteReceipt.model_validate(row)
            for row in payload.get("receipts", [])
        }


class GoogleCalendarDeleter:
    """Resolve through the read owner, delete with ETag, verify by provider GET."""

    def __init__(
        self,
        *,
        target_resolver: GoogleCalendarUpdater,
        receipt_store: CalendarDeleteReceiptStore,
    ):
        self.target_resolver = target_resolver
        self.receipt_store = receipt_store
        self.clock = target_resolver.clock

    def resolve(
        self,
        intent: CalendarUpdateIntent,
    ) -> tuple[str, CalendarDeleteOperation | None]:
        status, target = self.target_resolver.resolve_target(intent)
        if status != "resolved" or target is None:
            return status, None
        return "resolved", CalendarDeleteOperation(
            operation_id=str(uuid4()),
            provider_event_id=target.provider_event_id,
            before=target.before,
            etag=target.etag,
            home_timezone=target.home_timezone,
        )

    def delete_and_verify(
        self,
        operation: CalendarDeleteOperation,
    ) -> tuple[str, CalendarDeleteReceipt]:
        existing = self.receipt_store.get(operation.operation_id)
        if existing is not None:
            if existing.operation != operation:
                return "failed", existing
            if existing.status == "verified":
                return "verified", existing
            if existing.status in {"executing", "deleted_unverified"}:
                return self._reconcile(existing)
            if existing.status not in {"proposed", "blocked", "failed"}:
                return existing.status, existing
        if self.target_resolver._blocked():
            return "blocked", self.receipt_store.put(CalendarDeleteReceipt(
                operation=operation,
                status="blocked",
                confirmed_at=None if existing is None else existing.confirmed_at,
            ))
        executing = self.receipt_store.put(CalendarDeleteReceipt(
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
        return self._reconcile(executing)

    def _reconcile(
        self,
        receipt: CalendarDeleteReceipt,
    ) -> tuple[str, CalendarDeleteReceipt]:
        if self.target_resolver._blocked():
            return "blocked", self.receipt_store.put(
                receipt.model_copy(update={"status": "blocked"})
            )
        try:
            token = self.target_resolver._write_token()
            current, etag = self.target_resolver._fetch_event(
                receipt.operation.provider_event_id,
                receipt.operation.before.start.tzinfo,
                token,
            )
        except GoogleCalendarHttpFailure as error:
            if error.status_code == 404:
                return self._verified(receipt)
            return self._unverified(receipt)
        except GoogleTokenInvalidGrant:
            self.target_resolver._delete_write_secret()
            return "needs_reconnect", self.receipt_store.put(
                receipt.model_copy(update={"status": "failed"})
            )
        except (
            GoogleCalendarUnavailable,
            GoogleCalendarReconnectRequired,
            GoogleCalendarNetworkBlocked,
        ):
            return self._unverified(receipt)
        if current != receipt.operation.before or etag != receipt.operation.etag:
            return "conflict", self.receipt_store.put(
                receipt.model_copy(update={"status": "conflict"})
            )
        return self._delete_then_verify(receipt, token)

    def _delete_then_verify(
        self,
        receipt: CalendarDeleteReceipt,
        token: str,
    ) -> tuple[str, CalendarDeleteReceipt]:
        dispatched = receipt
        if receipt.dispatch_started_at is None:
            dispatched = self.receipt_store.put(receipt.model_copy(update={
                "status": "executing",
                "dispatch_started_at": self.clock(),
            }))
        operation = dispatched.operation
        try:
            self.target_resolver._request(
                f"{self.target_resolver.API_ROOT}/calendars/primary/events/"
                f"{quote(operation.provider_event_id, safe='')}",
                method="DELETE",
                headers={
                    "Authorization": f"Bearer {token}",
                    "If-Match": operation.etag,
                },
            )
        except GoogleCalendarHttpFailure as error:
            if error.status_code == 404:
                return self._verified(dispatched)
            if error.status_code == 412:
                return "conflict", self.receipt_store.put(
                    dispatched.model_copy(update={"status": "conflict"})
                )
            return self._unverified(dispatched)
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            return self._unverified(dispatched)
        try:
            self.target_resolver._fetch_event(
                operation.provider_event_id,
                operation.before.start.tzinfo,
                token,
            )
        except GoogleCalendarHttpFailure as error:
            if error.status_code == 404:
                return self._verified(dispatched)
            return self._unverified(dispatched)
        except (GoogleCalendarUnavailable, GoogleCalendarNetworkBlocked):
            return self._unverified(dispatched)
        return "conflict", self.receipt_store.put(
            dispatched.model_copy(update={"status": "conflict"})
        )

    def reject(self, operation: CalendarDeleteOperation) -> CalendarDeleteReceipt:
        return self.receipt_store.put(CalendarDeleteReceipt(
            operation=operation,
            status="rejected",
        ))

    def _unverified(
        self,
        receipt: CalendarDeleteReceipt,
    ) -> tuple[str, CalendarDeleteReceipt]:
        status = (
            "deleted_unverified"
            if receipt.dispatch_started_at is not None
            else "failed"
        )
        return status, self.receipt_store.put(
            receipt.model_copy(update={"status": status})
        )

    def _verified(
        self,
        receipt: CalendarDeleteReceipt,
    ) -> tuple[str, CalendarDeleteReceipt]:
        return "verified", self.receipt_store.put(receipt.model_copy(update={
            "status": "verified",
            "verified_at": self.clock(),
        }))


class GoogleCalendarDeleteConversationService:
    def __init__(
        self,
        *,
        proposal_store: MemoryProposalStore,
        deleter: GoogleCalendarDeleter,
    ):
        self.proposal_store = proposal_store
        self.deleter = deleter

    def prepare_from_resolved_intent(
        self,
        *,
        subject: str,
        date: str,
        conversation_id: str,
        now_local: datetime,
        time_value: str | None = None,
    ) -> ProposalPreparation:
        try:
            day = datetime.combine(
                calendar_date.fromisoformat(date),
                time.min,
                tzinfo=now_local.tzinfo,
            )
        except (TypeError, ValueError):
            return self._no_action(
                "Не смогла безопасно разобрать дату. Ничего в календаре не удаляю."
            )
        if not subject.strip() or (
            time_value is not None
            and re.fullmatch(r"\d{2}:\d{2}", time_value) is None
        ):
            return self._no_action(
                "Не смогла безопасно определить событие. Ничего в календаре не удаляю."
            )
        status, operation = self.deleter.resolve(CalendarUpdateIntent(
            lookup_title=subject.strip(),
            date=day,
            old_start_time=time_value,
        ))
        if status != "resolved" or operation is None:
            return self._no_action({
                "not_found": "Не нашла это событие в Основном календаре — ничего не удаляю.",
                "unsupported": "Не могу безопасно удалить повторяющееся или особое событие.",
                "ambiguous": "Нашла несколько похожих событий. Уточни время — ничего не удаляю.",
                "blocked": "Сейчас внешние действия остановлены, поэтому ничего не удаляю.",
                "needs_reconnect": "Для удаления нужно переподключить доступ Google Calendar.",
            }.get(status, "Сейчас не удалось проверить календарь для удаления."))
        proposal = MemoryProposal(
            id=str(uuid4()),
            conversation_id=conversation_id,
            record_type="google_calendar_event",
            record_payload=operation.model_dump(mode="json"),
            created_at=now_local,
            status=ProposalStatus.PENDING,
            operation="google_calendar_delete",
        )
        try:
            self.proposal_store.create(proposal)
        except PendingProposalConflict:
            return self._no_action(
                "Сначала закончим предыдущее подтверждение — пока ничего не удаляю."
            )
        self.deleter.receipt_store.put(CalendarDeleteReceipt(
            operation=operation,
            status="proposed",
        ))
        return ProposalPreparation(
            response=(
                f"Удалить «{operation.before.title}» из Основного календаря "
                f"{operation.before.start:%d.%m, %H:%M}–{operation.before.end:%H:%M}?"
            ),
            status=ProposalPreparationStatus.PENDING_CONFIRMATION,
            application_operation="google_calendar_delete",
        )

    def resolve(
        self,
        message: str,
        *,
        conversation_id: str,
        proposal_id: str | None = None,
    ) -> str | None:
        confirm = re.match(
            r"^\s*(?:да|подтверждаю|удали)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$",
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
            or proposal.operation != "google_calendar_delete"
        ):
            return None
        try:
            operation = CalendarDeleteOperation.model_validate(proposal.record_payload)
        except Exception:
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            return "Не смогла безопасно проверить удаление, поэтому ничего не меняла."
        if reject is not None:
            receipt = self.deleter.receipt_store.get(operation.operation_id)
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            if receipt is not None and receipt.dispatch_started_at is not None:
                return (
                    "Хорошо, пока не проверяю. Удаление могло уже примениться; "
                    "не утверждаю, что событие осталось в календаре."
                )
            self.deleter.reject(operation)
            return "Хорошо, событие оставляю в календаре."
        status, _ = self.deleter.delete_and_verify(operation)
        if status == "verified":
            self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
            return f"Готово: «{operation.before.title}» удалено из Основного календаря."
        if status == "deleted_unverified":
            return (
                "Удаление могло примениться, но я пока не смогла это проверить. "
                "Повторно ничего не создаю и не изменяю."
            )
        if status == "conflict":
            self.proposal_store.set_status(
                proposal.id,
                ProposalStatus.CANCELLED,
            )
            return "Событие изменилось после предпросмотра. Я его не удаляла."
        if status == "needs_reconnect":
            return "Для удаления нужно переподключить доступ Google Calendar."
        if status == "blocked":
            return "Сейчас внешние действия остановлены, поэтому ничего не удаляю."
        return "Не удалось удалить событие — ничего не утверждаю как готовое."

    @staticmethod
    def _no_action(response: str) -> ProposalPreparation:
        return ProposalPreparation(
            response=response,
            status=ProposalPreparationStatus.NO_ACTION,
        )
