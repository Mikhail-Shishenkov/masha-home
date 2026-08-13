"""UI-safe adapter over the existing synchronous ConversationService."""

from __future__ import annotations

import re

from backend.conversation.conversation_models import ConversationMessage, ConversationRole
from backend.conversation.conversation_service import ConversationService, ConversationUnavailableError
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError

from .catalogs import error_label
from .contracts import (
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ConversationTurnResult,
    ConversationTurnStatus,
    ConfirmationResolutionResult,
    ConfirmationResolutionStatus,
    ConversationSummaryView,
    ConversationView,
    MessageView,
    PendingConfirmationView,
)
from .model_settings import ModelSettingsService


class ConversationApplicationService:
    _PROPOSAL_ID = re.compile(
        r"(?:ID предложения:\s*|Подтверди:\s*да\s+)[0-9a-f-]{36}",
        re.IGNORECASE,
    )
    def __init__(self, *, conversation: ConversationService, models: ModelSettingsService):
        self._conversation = conversation
        self._models = models

    def conversation(self, conversation_id: str, *, limit: int | None = None) -> ConversationView:
        try:
            conversation = self._conversation.history.get(conversation_id)
            messages = self._conversation.history.messages(conversation_id, limit=limit)
        except KeyError as error:
            raise ApplicationBoundaryError(ApplicationErrorCode.CONVERSATION_NOT_FOUND) from error
        return ConversationView(
            conversation_id=conversation.id,
            created_at=conversation.created_at,
            messages=tuple(self._message(item) for item in messages),
        )

    def latest_conversation(self, *, limit: int | None = None) -> ConversationView | None:
        """Return the conversation owning the latest actual message, if any."""
        latest_message = self._conversation.history.latest_message()
        if latest_message is None:
            return None
        return self.conversation(latest_message.conversation_id, limit=limit)

    def recent_conversations(self, *, limit: int | None = None) -> tuple[ConversationSummaryView, ...]:
        """Return short human-readable summaries without duplicating history."""
        summaries: list[ConversationSummaryView] = []
        for conversation in self._conversation.history.recent(limit=limit):
            messages = self._conversation.history.messages(conversation.id, limit=1)
            if messages:
                latest = messages[-1]
                preview = self._preview(self._human_content(latest.content))
                last_interaction_at = latest.created_at
            else:
                preview = "Новый разговор"
                last_interaction_at = conversation.created_at
            summaries.append(
                ConversationSummaryView(
                    conversation_id=conversation.id,
                    created_at=conversation.created_at,
                    last_interaction_at=last_interaction_at,
                    preview=preview,
                )
            )
        return tuple(summaries)

    def pending_confirmation(self, conversation_id: str) -> PendingConfirmationView | None:
        handler = self._conversation.memory_intent_handler
        if handler is None:
            return None
        proposals = handler.proposal_store.pending_for_conversation(conversation_id)
        if len(proposals) != 1:
            return None
        proposal = proposals[0]
        payload = proposal.record_payload
        confirmation_type, title, subject = self._confirmation_copy(proposal)
        return PendingConfirmationView(
            proposal_id=proposal.id,
            conversation_id=proposal.conversation_id,
            confirmation_type=confirmation_type,
            title=title,
            subject=subject,
            due_at=payload.get("due_at"),
            created_at=proposal.created_at,
        )

    @staticmethod
    def _confirmation_copy(proposal):
        payload = proposal.record_payload
        if proposal.operation == "forget":
            return "memory_forget", "Убрать запись из активной памяти?", ConversationApplicationService._proposal_subject(proposal)
        if proposal.record_type == "commitment":
            completion = proposal.operation != "create"
            return (
                "commitment_complete" if completion else "commitment_create",
                "Отметить обязательство выполненным?" if completion else "Сохранить обязательство?",
                str(payload.get("text") or "Обязательство"),
            )
        if proposal.record_type == "relationship_memory":
            content = payload.get("content")
            text = content.get("text") if isinstance(content, dict) else content
            return "shared_moment_create", "Сохранить наш общий момент?", str(text or payload.get("title") or "Наш момент")
        if proposal.record_type == "continuity_state":
            rows = payload.get("intended_follow_ups") or []
            subject = rows[-1].get("summary") if rows else "Общая нить"
            return "continuity_update", "Обновить нашу общую нить?", str(subject)
        if proposal.operation in {"edit", "supersede"}:
            return "memory_update", "Обновить подтверждённую память?", ConversationApplicationService._proposal_subject(proposal)
        return "memory_create", "Сохранить это в память?", ConversationApplicationService._proposal_subject(proposal)

    @staticmethod
    def _proposal_subject(proposal) -> str:
        payload = proposal.record_payload
        return str(
            payload.get("value")
            or payload.get("decision")
            or payload.get("summary")
            or payload.get("text")
            or payload.get("title")
            or "Подтверждённая запись"
        )[:500]

    def resolve_confirmation(
        self,
        *,
        conversation_id: str,
        proposal_id: str,
        decision: str,
        project_id: str,
    ) -> ConfirmationResolutionResult:
        if decision not in {"confirm", "reject"}:
            raise ValueError("unsupported confirmation decision")
        response, proposal_status = self._conversation.resolve_memory_proposal(
            conversation_id=conversation_id,
            proposal_id=proposal_id,
            confirm=decision == "confirm",
            project_id=project_id,
        )
        messages = self._conversation.history.messages(conversation_id, limit=2)
        user = next(item for item in messages if item.role is ConversationRole.USER)
        assistant = next(item for item in messages if item.role is ConversationRole.ASSISTANT)
        if proposal_status == "confirmed":
            status = ConfirmationResolutionStatus.CONFIRMED
        elif proposal_status == "cancelled":
            status = ConfirmationResolutionStatus.REJECTED
        else:
            status = ConfirmationResolutionStatus.FAILED
        return ConfirmationResolutionResult(
            proposal_id=proposal_id,
            conversation_id=conversation_id,
            status=status,
            user_message=self._message(user),
            assistant_message=self._message(assistant),
            pending_confirmation=self.pending_confirmation(conversation_id),
        )

    def send_message(
        self,
        content: str,
        *,
        project_id: str,
        conversation_id: str | None = None,
    ) -> ConversationTurnResult:
        active_profile_id = self._models.current().profile_id
        resolved_id = conversation_id
        try:
            resolved_id, _ = self._conversation.send(
                content,
                project_id=project_id,
                conversation_id=conversation_id,
            )
        except ConversationUnavailableError as error:
            resolved_id = self._resolved_conversation_id(resolved_id)
            code = (
                ApplicationErrorCode.MODEL_TIMEOUT
                if isinstance(error.__cause__, ModelTimeoutError)
                else ApplicationErrorCode.MODEL_UNAVAILABLE
            )
            status = (
                ConversationTurnStatus.TIMEOUT
                if code is ApplicationErrorCode.MODEL_TIMEOUT
                else ConversationTurnStatus.MODEL_UNAVAILABLE
            )
            return self._result(
                content=content,
                conversation_id=resolved_id,
                status=status,
                profile_id=active_profile_id,
                error_code=code,
            )
        except (ModelProviderUnavailableError, ModelTimeoutError) as error:
            resolved_id = self._resolved_conversation_id(resolved_id)
            code = (
                ApplicationErrorCode.MODEL_TIMEOUT
                if isinstance(error, ModelTimeoutError)
                else ApplicationErrorCode.MODEL_UNAVAILABLE
            )
            status = (
                ConversationTurnStatus.TIMEOUT
                if code is ApplicationErrorCode.MODEL_TIMEOUT
                else ConversationTurnStatus.MODEL_UNAVAILABLE
            )
            return self._result(
                content=content,
                conversation_id=resolved_id,
                status=status,
                profile_id=active_profile_id,
                error_code=code,
            )
        except Exception:
            resolved_id = self._resolved_conversation_id(resolved_id)
            return self._result(
                content=content,
                conversation_id=resolved_id,
                status=ConversationTurnStatus.FAILED,
                profile_id=active_profile_id,
                error_code=ApplicationErrorCode.CONVERSATION_FAILED,
            )
        return self._result(
            content=content,
            conversation_id=resolved_id,
            status=ConversationTurnStatus.COMPLETED,
            profile_id=active_profile_id,
        )

    def _result(
        self,
        *,
        content: str,
        conversation_id: str | None,
        status: ConversationTurnStatus,
        profile_id: str,
        error_code: ApplicationErrorCode | None = None,
    ) -> ConversationTurnResult:
        messages = ()
        if conversation_id is not None:
            try:
                messages = self._conversation.history.messages(conversation_id, limit=2)
            except KeyError:
                messages = ()
        user = next((item for item in reversed(messages) if item.role is ConversationRole.USER), None)
        assistant = None
        if user is not None:
            assistant = next(
                (
                    item
                    for item in reversed(messages)
                    if item.role is ConversationRole.ASSISTANT and item.created_at >= user.created_at
                ),
                None,
            )
        user_view = (
            self._message(user)
            if user is not None
            else MessageView(
                message_id=None,
                conversation_id=conversation_id,
                role="user",
                content=content,
                created_at=None,
                persisted=False,
            )
        )
        return ConversationTurnResult(
            conversation_id=conversation_id,
            user_message=user_view,
            assistant_message=None if assistant is None else self._message(assistant),
            status=status,
            active_profile_id=profile_id,
            error_code=error_code,
            error_label=None if error_code is None else error_label(error_code),
            pending_confirmation=(
                None
                if conversation_id is None
                else self.pending_confirmation(conversation_id)
            ),
        )

    def _resolved_conversation_id(self, conversation_id: str | None) -> str | None:
        if conversation_id is not None:
            return conversation_id
        latest = self._conversation.history.latest()
        return None if latest is None else latest.id

    @staticmethod
    def _message(message: ConversationMessage) -> MessageView:
        return MessageView(
            message_id=message.id,
            conversation_id=message.conversation_id,
            role=message.role.value,
            content=ConversationApplicationService._human_content(message.content),
            created_at=message.created_at,
            persisted=True,
        )

    @classmethod
    def _human_content(cls, content: str) -> str:
        return cls._PROPOSAL_ID.sub("Подтверди или выбери «не сейчас»", content)

    @staticmethod
    def _preview(content: str) -> str:
        normalized = " ".join(content.split())
        return normalized if len(normalized) <= 157 else f"{normalized[:156].rstrip()}…"
