"""Conversation boundary for the confirmed Google Calendar create action."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import uuid4

from backend.conversation.memory_intent import MemoryProposal, MemoryProposalStore, ProposalStatus, PendingProposalConflict

from .intent import calendar_create_intent
from .writer import CalendarCreateOperation, CalendarCreateReceipt, GoogleCalendarWriter


_CONFIRM = re.compile(r"^\s*(?:да|подтверждаю|создавай|создай)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$", re.IGNORECASE)
_REJECT = re.compile(r"^\s*(?:нет|не надо|не сейчас|отмена)(?:\s+(?P<id>[0-9a-f-]{36}))?\s*[.!]?\s*$", re.IGNORECASE)


class GoogleCalendarCreateConversationService:
    """Owns calendar action parsing and execution, never the memory handler."""

    def __init__(self, *, proposal_store: MemoryProposalStore, writer: GoogleCalendarWriter):
        self.proposal_store = proposal_store
        self.writer = writer

    def propose(self, message: str, *, conversation_id: str, now_local: datetime):
        intent = calendar_create_intent(message, now_local)
        if intent is None:
            return None
        if intent.clarification is not None:
            return intent.clarification
        assert intent.title is not None and intent.start is not None and intent.end is not None
        operation = CalendarCreateOperation(
            operation_id=str(uuid4()), title=intent.title, start=intent.start, end=intent.end,
            home_timezone=str(intent.start.tzinfo),
        )
        proposal = MemoryProposal(
            id=str(uuid4()), conversation_id=conversation_id, record_type="google_calendar_event",
            record_payload=operation.model_dump(mode="json"), created_at=now_local,
            status=ProposalStatus.PENDING, operation="google_calendar_create",
        )
        try:
            self.proposal_store.create(proposal)
        except PendingProposalConflict:
            return "Сначала закончим предыдущее подтверждение — пока ничего нового не создаю."
        self.writer.receipt_store.put(
            CalendarCreateReceipt(
                operation=operation, status="proposed",
                provider_event_id=operation.provider_event_id(),
            )
        )
        return f"Поставить «{operation.title}» в Основной календарь: {operation.start:%d.%m в %H:%M}–{operation.end:%H:%M}?"

    def resolve(self, message: str, *, conversation_id: str, proposal_id: str | None = None):
        command = _CONFIRM.match(message) or _REJECT.match(message)
        if command is None:
            return None
        proposal = self.proposal_store.current_for_conversation(conversation_id)
        requested_id = proposal_id or command.group("id")
        if proposal is None or (requested_id is not None and proposal.id != requested_id) or proposal.operation != "google_calendar_create":
            return None
        try:
            operation = CalendarCreateOperation.model_validate(proposal.record_payload)
        except Exception:
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            return "Не смогла безопасно проверить это действие, поэтому ничего в календаре не меняла."
        if _REJECT.match(message):
            self.writer.reject(operation)
            self.proposal_store.set_status(proposal.id, ProposalStatus.CANCELLED)
            return "Хорошо, ничего в календаре не меняю."
        status, _ = self.writer.create_and_verify(operation)
        if status == "verified":
            self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
            return f"Готово: «{operation.title}» поставила в Основной календарь на {operation.start:%d.%m в %H:%M}."
        if status == "created_unverified":
            self.proposal_store.set_status(proposal.id, ProposalStatus.CONFIRMED)
            return "Запрос отправлен, но я пока не смогла проверить событие. Повторно его не создаю."
        if status == "needs_reconnect":
            return "Для создания событий нужно отдельно переподключить Google Calendar."
        if status == "blocked":
            return "Сейчас внешние действия остановлены, поэтому ничего в календаре не меняю."
        return "Не удалось создать событие — ничего не утверждаю как готовое."
