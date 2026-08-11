"""UI-safe adapter over the existing synchronous ConversationService."""

from __future__ import annotations

from backend.conversation.conversation_models import ConversationMessage, ConversationRole
from backend.conversation.conversation_service import ConversationService, ConversationUnavailableError
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError

from .catalogs import error_label
from .contracts import (
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ConversationTurnResult,
    ConversationTurnStatus,
    ConversationView,
    MessageView,
)
from .model_settings import ModelSettingsService


class ConversationApplicationService:
    def __init__(self, *, conversation: ConversationService, models: ModelSettingsService):
        self._conversation = conversation
        self._models = models

    def conversation(self, conversation_id: str, *, limit: int = 16) -> ConversationView:
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
            content=message.content,
            created_at=message.created_at,
            persisted=True,
        )
