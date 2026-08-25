"""UI-safe adapter over the existing synchronous ConversationService."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.conversation.conversation_models import (
    ConversationMessage,
    ConversationMessageOrigin,
    ConversationRole,
)
from backend.conversation.human_reference import PresentedEntitySet
from backend.conversation.response_expression import (
    ResponseExpressionClassifier,
)
from backend.conversation.conversation_service import ConversationService, ConversationUnavailableError
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError
from backend.document_read import DocumentReadReceipt

from .catalogs import error_label
from .contracts import (
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ConversationTurnResult,
    ConversationTurnStatus,
    ConfirmationResolutionResult,
    ConfirmationResolutionStatus,
    ConversationPageView,
    ConversationSummaryView,
    ConversationView,
    ExternalObservationView,
    DocumentReadView,
    ExternalSourceView,
    FetchedPageView,
    MessageView,
    ResponseExpressionCue,
    PendingConfirmationView,
)
from .model_settings import ModelSettingsService
from .local_documents import LocalDocumentTurnService


class LastApplicationAction(BaseModel):
    """One-turn application-owned truth after a confirmation decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str
    entity_type: str
    entity_id: str | None
    operation: str
    subject: str
    result: Literal["confirmed", "rejected", "failed"]
    occurred_at: datetime


class ConversationApplicationService:
    _PROPOSAL_ID = re.compile(
        r"(?:ID предложения:\s*|Подтверди:\s*да\s+)[0-9a-f-]{36}",
        re.IGNORECASE,
    )
    _ACTION_OUTCOME_FOLLOW_UP = re.compile(
        r"(?:\bзначит\b|\bто\s+есть\b|\bполучается\b|\bвыходит\b|\bну\s+вс[её]\b)"
        r"[\s,!?.—-]*(?:(?:ты|мы)\s+)?(?:вс[её]-?таки\s+)?"
        r"(?:е[её]\s+|эту\s+(?:нить|тему)\s+)?"
        r"(?:закрыл(?:а|и|ась)?|завершил(?:а|и)?|убрал(?:а|и)?)\b",
        re.IGNORECASE,
    )

    def __init__(self,*,
        conversation: ConversationService,
        models: ModelSettingsService,
        expression_classifier: ResponseExpressionClassifier | None = None,
        local_documents: LocalDocumentTurnService | None = None,
    ):
        self._conversation = conversation
        self._models = models
        self._expression_classifier = expression_classifier
        self._local_documents = local_documents
        # Session-scoped typed context; SharedContinuityService remains the
        # owner of the actual thread and its lifecycle.
        self._active_continuity_by_conversation: dict[str, str] = {}
        self._last_application_action_by_conversation: dict[str, LastApplicationAction] = {}

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

    def conversation_page(
        self,
        *,
        offset: int = 0,
        limit: int = 10,
        query: str | None = None,
    ) -> ConversationPageView:
        """Bounded summary page; `query` reserves the future search boundary."""
        if offset < 0 or limit < 1:
            raise ValueError("invalid conversation page")
        rows = self.recent_conversations()
        # Search is intentionally not implemented in this stabilization pass.
        if query not in {None, ""}:
            raise ValueError("conversation search is not available")
        page = rows[offset : offset + limit]
        next_offset = offset + len(page)
        has_more = next_offset < len(rows)
        return ConversationPageView(
            items=page,
            offset=offset,
            page_size=limit,
            total=len(rows),
            has_more=has_more,
            next_offset=next_offset if has_more else None,
            query=None,
        )

    def pending_confirmation(self, conversation_id: str) -> PendingConfirmationView | None:
        handler = self._conversation.memory_intent_handler
        if handler is None:
            return None
        proposal = handler.proposal_store.current_for_conversation(conversation_id)
        if proposal is None:
            return None
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

    def remember_presented_entity_set(self, presented: PresentedEntitySet) -> None:
        """Register one application-rendered list in the existing reference truth."""
        handler = self._conversation.memory_intent_handler
        if handler is not None:
            handler.remember_presented_entity_set(presented)

    def presented_entity_set(self, conversation_id: str) -> PresentedEntitySet | None:
        handler = self._conversation.memory_intent_handler
        return None if handler is None else handler.presented_entity_set(conversation_id)

    def discard_presented_entity_set(self, conversation_id: str) -> None:
        handler = self._conversation.memory_intent_handler
        if handler is not None:
            handler.discard_presented_entity_set(conversation_id)

    def open_external_source(self, observation_id: str, source_id: str) -> bool:
        return self._conversation.open_external_source(observation_id, source_id)

    def activate_continuity_thread(
        self,
        thread_id: str,
        *,
        conversation_id: str,
    ) -> None:
        """Select a thread for the live conversation without sending a turn."""
        self._conversation.history.get(conversation_id)
        self._active_continuity_by_conversation[conversation_id] = thread_id

    def clear_continuity_thread(self, *, conversation_id: str) -> None:
        self._active_continuity_by_conversation.pop(conversation_id, None)

    def active_continuity_thread_id(
        self,
        *,
        conversation_id: str,
    ) -> str | None:
        return self._active_continuity_by_conversation.get(conversation_id)

    def _confirmation_copy(self, proposal):
        payload = proposal.record_payload
        if proposal.operation == "google_calendar_create":
            title = str(payload.get("title") or "Событие")
            start = str(payload.get("start") or "")
            return "google_calendar_create", "Поставить событие в Основной календарь?", f"{title} · {start}"[:500]
        if proposal.operation == "forget":
            return "memory_forget", "Убрать воспоминание?", ConversationApplicationService._proposal_subject(proposal)
        if proposal.operation == "restore":
            return "memory_restore", "Вернуть запись в обычную память?", ConversationApplicationService._proposal_subject(proposal)
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
            handler = self._conversation.memory_intent_handler
            continuity = None if handler is None else handler.shared_continuity
            open_ids = (
                set()
                if continuity is None
                else {follow_up.id for _, follow_up in continuity.open_follow_ups()}
            )
            resolved = next(
                (
                    item
                    for item in rows
                    if item.get("status") == "resolved" and item.get("id") in open_ids
                ),
                None,
            )
            subject = (resolved or (rows[-1] if rows else {})).get("summary", "Общая нить")
            if resolved is not None:
                return "continuity_update", "Убрать открытую тему?", str(subject)
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
        handler = self._conversation.memory_intent_handler
        proposal = None if handler is None else handler.proposal_store.get(proposal_id)
        action = None if proposal is None else self._proposal_action(proposal)
        response, proposal_status = self._conversation.resolve_memory_proposal(
            conversation_id=conversation_id,
            proposal_id=proposal_id,
            confirm=decision == "confirm",
            project_id=project_id,
        )
        active_thread_id = self._active_continuity_by_conversation.get(conversation_id)
        if active_thread_id is not None:
            handler = self._conversation.memory_intent_handler
            continuity = None if handler is None else handler.shared_continuity
            if continuity is None or not any(
                follow_up.id == active_thread_id
                for _, follow_up in continuity.open_follow_ups()
            ):
                self._active_continuity_by_conversation.pop(conversation_id, None)
        messages = self._conversation.history.messages(conversation_id, limit=2)
        user = next(item for item in messages if item.role is ConversationRole.USER)
        assistant = next(item for item in messages if item.role is ConversationRole.ASSISTANT)
        if proposal_status == "confirmed":
            status = ConfirmationResolutionStatus.CONFIRMED
        elif proposal_status == "cancelled":
            status = ConfirmationResolutionStatus.REJECTED
        else:
            status = ConfirmationResolutionStatus.FAILED
        if action is not None:
            self._last_application_action_by_conversation[conversation_id] = (
                action.model_copy(
                    update={
                        "result": status.value,
                        "occurred_at": datetime.now(timezone.utc),
                    }
                )
            )
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
        allow_capability_routing: bool = True,
        active_continuity_thread_id: str | None = None,
        home_moment: str = "ordinary",
        document_receipt: DocumentReadReceipt | None = None,
    ) -> ConversationTurnResult:
        active_profile_id = self._models.current().profile_id
        resolved_id = conversation_id
        action_follow_up = None if document_receipt is not None else self._action_follow_up(
            content,
            conversation_id=conversation_id,
            profile_id=active_profile_id,
        )
        if action_follow_up is not None:
            return action_follow_up
        active_thread_id = active_continuity_thread_id or (
            None
            if conversation_id is None
            else self._active_continuity_by_conversation.get(conversation_id)
        )
        try:
            resolved_id, response_text = self._conversation.send(
                content,
                project_id=project_id,
                conversation_id=conversation_id,
                allow_capability_routing=allow_capability_routing,
                active_continuity_thread_id=active_thread_id,
                home_moment=home_moment,
                document_receipt=document_receipt,
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
        if active_continuity_thread_id is not None and resolved_id is not None:
            self._active_continuity_by_conversation[resolved_id] = (
                active_continuity_thread_id
            )
        if document_receipt is not None and resolved_id is not None and self._local_documents is not None:
            messages = self._conversation.history.messages(resolved_id, limit=1)
            if messages and messages[-1].role is ConversationRole.ASSISTANT:
                self._local_documents.store.attach_assistant_message(
                    document_receipt.receipt_id,
                    messages[-1].id,
                )

        expression_cue: ResponseExpressionCue = "warm"

        if (
                resolved_id is not None
                and self._expression_classifier is not None
        ):
            try:
                latest_messages = self._conversation.history.messages(
                    resolved_id,
                    limit=1,
                )
            except KeyError:
                latest_messages = ()

            latest = (
                latest_messages[-1]
                if latest_messages
                else None
            )

            if (
                    latest is not None
                    and latest.role is ConversationRole.ASSISTANT
                    and latest.origin is ConversationMessageOrigin.MODEL
            ):
                try:
                    expression_cue = self._expression_classifier.classify(
                        user_message=content,
                        assistant_message=response_text,
                    )
                except Exception:
                    # Эмоциональный слой не имеет права ломать разговор.
                    expression_cue = "warm"

        return self._result(
            content=content,
            conversation_id=resolved_id,
            status=ConversationTurnStatus.COMPLETED,
            profile_id=active_profile_id,
            expression_cue=expression_cue,
        )

    def send_message_with_document(
        self,
        content: str,
        *,
        token: str,
        project_id: str,
        conversation_id: str | None = None,
        home_moment: str = "ordinary",
    ) -> ConversationTurnResult:
        if self._local_documents is None:
            raise RuntimeError("local_document_unavailable")
        receipt = self._local_documents.consume_for_turn(token)
        return self.send_message(
            content,
            project_id=project_id,
            conversation_id=conversation_id,
            home_moment=home_moment,
            document_receipt=receipt,
        )

    def _action_follow_up(
        self,
        content: str,
        *,
        conversation_id: str | None,
        profile_id: str,
    ) -> ConversationTurnResult | None:
        if conversation_id is None:
            return None
        action = self._last_application_action_by_conversation.pop(
            conversation_id,
            None,
        )
        if (
            action is None
            or action.operation != "resolve"
            or not self._ACTION_OUTCOME_FOLLOW_UP.search(content)
        ):
            return None
        user = self._conversation.history.append(
            conversation_id,
            ConversationRole.USER,
            content,
        )
        if action.result == "confirmed":
            response = (
                f"Да, закрыла — нить «{action.subject}» действительно завершена."
            )
        elif action.result == "rejected":
            response = (
                "Нет, не закрыла — ты выбрал «не сейчас», поэтому нить "
                f"«{action.subject}» осталась открытой."
            )
        else:
            response = (
                "Нет подтверждения, что нить была закрыта: применение изменения "
                "не завершилось."
            )
        assistant = self._conversation.history.append(
            conversation_id,
            ConversationRole.ASSISTANT,
            response,
            origin=ConversationMessageOrigin.APPLICATION,
        )
        return ConversationTurnResult(
            conversation_id=conversation_id,
            user_message=self._message(user),
            assistant_message=self._message(assistant),
            status=ConversationTurnStatus.COMPLETED,
            active_profile_id=profile_id,
            pending_confirmation=self.pending_confirmation(conversation_id),
        )

    def _proposal_action(self, proposal) -> LastApplicationAction:
        _, _, subject = self._confirmation_copy(proposal)
        entity_id = None
        operation = proposal.operation
        entity_type = proposal.record_type
        if proposal.record_type == "continuity_state":
            rows = proposal.record_payload.get("intended_follow_ups") or []
            handler = self._conversation.memory_intent_handler
            continuity = None if handler is None else handler.shared_continuity
            open_ids = (
                set()
                if continuity is None
                else {item.id for _, item in continuity.open_follow_ups()}
            )
            resolved = next(
                (
                    item
                    for item in rows
                    if item.get("status") == "resolved" and item.get("id") in open_ids
                ),
                None,
            )
            if resolved is not None:
                entity_type = "continuity_thread"
                entity_id = resolved.get("id")
                operation = "resolve"
        return LastApplicationAction(
            conversation_id=proposal.conversation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            subject=subject,
            result="failed",
            occurred_at=datetime.now(timezone.utc),
        )

    def _result(
        self,
        *,
        content: str,
        conversation_id: str | None,
        status: ConversationTurnStatus,
        profile_id: str,
        expression_cue: ResponseExpressionCue = "warm",
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
            expression_cue=expression_cue,
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

    def _message(self, message: ConversationMessage) -> MessageView:
        observations = tuple(
            item for item in self._conversation.external_observations_for_message(message.id)
            if item.status.value == "completed"
        )
        views = tuple(self._external_observation(observation) for observation in observations)
        local_documents = ()
        if self._local_documents is not None:
            local_documents = tuple(
                self._document_view(receipt)
                for receipt in self._local_documents.store.for_assistant_message(message.id)
                if receipt.source_kind.value == "local"
            )
        return MessageView(
            message_id=message.id,
            conversation_id=message.conversation_id,
            role=message.role.value,
            content=ConversationApplicationService._human_content(message.content),
            created_at=message.created_at,
            persisted=True,
            external_observation=(None if not views else views[-1]),
            external_observations=views,
            local_documents=local_documents,
        )

    @staticmethod
    def _document_view(receipt: DocumentReadReceipt) -> DocumentReadView:
        document = receipt.evidence
        return DocumentReadView(
            title=document.title,
            source_kind=receipt.source_kind.value,
            display_name=receipt.display_name,
            domain=receipt.source_domain,
            page_count=document.page_count,
            pages_read=document.pages_read,
            extracted_chars=document.extracted_chars,
            truncated=document.truncated,
            extractor=document.extractor_id,
        )

    def _external_observation(self, observation) -> ExternalObservationView:
        page = observation.fetched_page
        service = self._conversation.external_observation_service
        receipt = None if service is None else service.document_receipt(observation)
        document = None if receipt is None else receipt.evidence
        return ExternalObservationView(
            observation_id=observation.request.observation_id,
            kind=observation.request.kind.value,
            sources=tuple(
                ExternalSourceView(
                    source_id=item.source_id,
                    title=item.title,
                    domain=item.domain,
                    retrieved_at=item.retrieved_at,
                    source_time=None if item.source_time.value is None else item.source_time.value.isoformat(),
                    freshness_status=item.freshness_status.value,
                )
                for item in observation.evidence
            ),
            page=None if page is None else FetchedPageView(
                title=page.title, domain=page.domain, content_type=page.content_type,
                fetched_at=page.fetched_at, truncated=page.truncated, extractor=page.extractor_id,
            ),
            document=None if document is None else DocumentReadView(
                title=document.title,
                source_kind=receipt.source_kind.value,
                display_name=receipt.display_name,
                domain=receipt.source_domain or "unknown",
                page_count=document.page_count,
                pages_read=document.pages_read,
                extracted_chars=document.extracted_chars,
                truncated=document.truncated,
                extractor=document.extractor_id,
            ),
        )

    @classmethod
    def _human_content(cls, content: str) -> str:
        return cls._PROPOSAL_ID.sub("Подтверди или выбери «не сейчас»", content)

    @staticmethod
    def _preview(content: str) -> str:
        normalized = " ".join(content.split())
        return normalized if len(normalized) <= 157 else f"{normalized[:156].rstrip()}…"
