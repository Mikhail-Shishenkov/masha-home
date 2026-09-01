"""Application adapters from resolved V2 meaning to existing proposal owners."""

from __future__ import annotations

from backend.conversation.resolution_coordinator import (
    DomainProposalContext,
    DomainProposalResult,
    DomainReadResult,
    ResolvedCapabilityAdapterError,
    ResolvedCapabilityHandoff,
)
from backend.conversation.memory_intent import ProposalStatus
from backend.runtime.action_contracts import ProposalPreparationStatus


def _optional_slot(handoff: ResolvedCapabilityHandoff, name: str) -> str | None:
    return next((slot.value for slot in handoff.slots if slot.name == name), None)


def _pending_proposal(service, conversation_id: str, *, operation: str):
    store = getattr(service, "proposal_store", None)
    if store is None:
        return None
    proposal = store.current_for_conversation(conversation_id)
    if (
        proposal is None
        or proposal.status is not ProposalStatus.PENDING
        or proposal.operation != operation
    ):
        return None
    return proposal


def _calendar_receipt(service, proposal, *, owner: str):
    payload_operation_id = proposal.record_payload.get("operation_id")
    if not isinstance(payload_operation_id, str):
        return None
    writer = getattr(service, owner, None)
    receipt_store = getattr(writer, "receipt_store", None)
    receipt = None if receipt_store is None else receipt_store.get(payload_operation_id)
    if (
        receipt is None
        or receipt.status != "proposed"
        or receipt.operation.operation_id != payload_operation_id
        or receipt.confirmed_at is not None
        or receipt.verified_at is not None
    ):
        return None
    return receipt


def _mail_mutation_receipt(service, proposal):
    operation_id = proposal.record_payload.get("operation_id")
    receipt = (
        None
        if not isinstance(operation_id, str)
        else service.writer.receipt_store.get(operation_id)
    )
    if (
        receipt is None
        or receipt.status != "proposed"
        or receipt.operation.operation_id != operation_id
        or receipt.confirmed_at is not None
        or receipt.dispatch_started_at is not None
        or receipt.verified_at is not None
    ):
        return None
    return receipt


def _project(preparation, *, pending_operation: str | None) -> DomainProposalResult:
    if preparation.status is ProposalPreparationStatus.NO_ACTION:
        return DomainProposalResult(
            response=preparation.response,
            projection_state="failed",
        )
    if pending_operation is None:
        raise ResolvedCapabilityAdapterError("pending proposal evidence is missing")
    if preparation.application_operation != pending_operation:
        raise ResolvedCapabilityAdapterError("pending proposal operation mismatch")
    return DomainProposalResult(
        response=preparation.response,
        projection_state="waiting_confirmation",
        pending_application_operation=pending_operation,
    )


class CalendarCreateHandoffAdapter:
    operation_id = "google_calendar.event.create"

    def __init__(self, service):
        self.service = service

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        try:
            preparation = self.service.prepare_from_resolved_intent(
                subject=handoff.slot("subject").value,
                date=handoff.slot("date").value,
                time=handoff.slot("time").value,
                duration_minutes=handoff.slot("duration_minutes").value,
                conversation_id=handoff.conversation_id,
                now_local=context.now_local,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        proposal = _pending_proposal(
            self.service,
            handoff.conversation_id,
            operation="google_calendar_create",
        )
        if proposal is not None and _calendar_receipt(
            self.service,
            proposal,
            owner="writer",
        ) is None:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        return _project(
            preparation,
            pending_operation=(None if proposal is None else proposal.operation),
        )


class CalendarUpdateHandoffAdapter:
    """Validated meaning enters the existing A2 lookup/preview owner only."""

    operation_id = "google_calendar.event.update"

    def __init__(self, service):
        self.service = service

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        try:
            old_time = next(
                (slot.value for slot in handoff.slots if slot.name == "old_time"),
                None,
            )
            duration = next(
                (slot.value for slot in handoff.slots if slot.name == "duration_minutes"),
                None,
            )
            preparation = self.service.prepare_from_resolved_intent(
                subject=handoff.slot("subject").value,
                date=handoff.slot("date").value,
                start_time=handoff.slot("time").value,
                old_time=old_time,
                duration_minutes=duration,
                conversation_id=handoff.conversation_id,
                now_local=context.now_local,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        proposal = _pending_proposal(
            self.service,
            handoff.conversation_id,
            operation="google_calendar_update",
        )
        if proposal is not None and _calendar_receipt(
            self.service,
            proposal,
            owner="updater",
        ) is None:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        return _project(
            preparation,
            pending_operation=(None if proposal is None else proposal.operation),
        )


class CalendarDeleteHandoffAdapter:
    operation_id = "google_calendar.event.delete"

    def __init__(self, service):
        self.service = service

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        try:
            preparation = self.service.prepare_from_resolved_intent(
                subject=handoff.slot("subject").value,
                date=handoff.slot("date").value,
                time_value=_optional_slot(handoff, "time"),
                conversation_id=handoff.conversation_id,
                now_local=context.now_local,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        proposal = _pending_proposal(
            self.service,
            handoff.conversation_id,
            operation="google_calendar_delete",
        )
        if proposal is not None and _calendar_receipt(
            self.service,
            proposal,
            owner="deleter",
        ) is None:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        return _project(
            preparation,
            pending_operation=(None if proposal is None else proposal.operation),
        )


class TimedCommitmentHandoffAdapter:
    operation_id = "home.timed_commitments"

    def __init__(self, handler):
        self.handler = handler

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        try:
            preparation = self.handler.prepare_timed_commitment_from_resolved_intent(
                subject=handoff.slot("subject").value,
                date=handoff.slot("date").value,
                time=handoff.slot("time").value,
                conversation_id=handoff.conversation_id,
                project_id=context.project_id,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        proposal = _pending_proposal(
            self.handler,
            handoff.conversation_id,
            operation="create",
        )
        if proposal is not None and proposal.record_type != "commitment":
            raise ResolvedCapabilityAdapterError(self.operation_id)
        return _project(
            preparation,
            pending_operation=(
                None if proposal is None else "commitment_create"
            ),
        )


class CalendarReadHandoffAdapter:
    operation_id = "google_calendar.read"

    def __init__(self, service):
        self.service = service

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainReadResult:
        try:
            outcome = self.service.observe_period(
                handoff.slot("period").value,
                now_local=context.now_local,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        if outcome is None:
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="failed",
                delivery="application_response",
                response="Не смогла безопасно определить период календаря. Ничего не читаю.",
            )
        if outcome.status != "completed":
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="failed",
                delivery="application_response",
                response=self.service.human_failure(outcome),
            )
        return DomainReadResult(
            operation_id=self.operation_id,
            projection_state="completed_read",
            delivery="model_evidence",
            external_information=tuple(outcome.model_context()),
            information_contract="calendar",
            completed_capability="calendar",
        )


class YandexMailReadHandoffAdapter:
    operation_id = "yandex_mail.read"

    def __init__(self, service):
        self.service = service

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainReadResult:
        del context
        outcome = self.service.observe_resolved(
            conversation_id=handoff.conversation_id,
            original_utterance=handoff.original_utterance,
            view=_optional_slot(handoff, "view"),
            sender=_optional_slot(handoff, "sender"),
            topic=_optional_slot(handoff, "topic"),
            target=_optional_slot(handoff, "target"),
        )
        if outcome.status == "read_completed" and outcome.content is not None:
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="completed_read",
                delivery="model_evidence",
                external_information=(outcome.content.model_value(),),
                information_contract="mail",
                model_request_override=(
                    None
                    if outcome.resolved_request is None
                    else outcome.resolved_request.model_message()
                ),
                completed_capability="mail",
            )
        if outcome.status == "important_completed":
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="completed_read",
                delivery="model_evidence",
                external_information=({
                    "kind": "mail_summaries",
                    "messages": [item.model_value() for item in outcome.messages],
                },),
                information_contract="mail",
                completed_capability="mail",
            )
        completed = outcome.status in {
            "search_completed",
            "no_unread",
            "no_messages",
        }
        return DomainReadResult(
            operation_id=self.operation_id,
            projection_state="completed_read" if completed else "failed",
            delivery="application_response",
            response=self.service.human_result(outcome),
            completed_capability="mail" if completed else None,
        )


class _YandexMailMutationHandoffAdapter:
    action: str

    def __init__(self, service):
        self.service = service

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        try:
            preparation = self.service.prepare_from_resolved_intent(
                action=self.action,
                target=handoff.slot("target").value,
                conversation_id=handoff.conversation_id,
                now_local=context.now_local,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        expected_operation = f"yandex_mail_{self.action}"
        proposal = _pending_proposal(
            self.service,
            handoff.conversation_id,
            operation=expected_operation,
        )
        if proposal is not None and _mail_mutation_receipt(
            self.service, proposal,
        ) is None:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        return _project(
            preparation,
            pending_operation=(None if proposal is None else proposal.operation),
        )


class YandexMailDeleteHandoffAdapter(_YandexMailMutationHandoffAdapter):
    operation_id = "yandex_mail.message.delete"
    action = "delete"


class YandexMailMoveHandoffAdapter(_YandexMailMutationHandoffAdapter):
    operation_id = "yandex_mail.message.move"
    action = "move"


def _document_information(receipt) -> dict:
    return {
        "kind": "document_read",
        "source_kind": receipt.source_kind.value,
        "display_name": receipt.display_name,
        "format": receipt.evidence.format.value,
        "title": receipt.evidence.title,
        "page_count": receipt.evidence.page_count,
        "pages_read": receipt.evidence.pages_read,
        "truncated": receipt.evidence.truncated,
        "pages": [
            {
                "page_number": page.page_number,
                "text": page.text,
                "truncated": page.truncated,
            }
            for page in receipt.evidence.pages
        ],
    }


class _FileReadHandoffAdapter:
    """Shared application projection for resolved connector file reads."""

    service = None

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainReadResult:
        del context
        outcome = self.service.observe_resolved(
            conversation_id=handoff.conversation_id,
            original_utterance=handoff.original_utterance,
            mode=handoff.slot("mode").value,
            query=_optional_slot(handoff, "query"),
            target=_optional_slot(handoff, "target"),
        )
        if outcome.status == "read_completed":
            receipt = outcome.document_receipt
            if receipt is None or outcome.resolved_document_request is None:
                raise ResolvedCapabilityAdapterError(self.operation_id)
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="completed_read",
                delivery="model_evidence",
                external_information=(_document_information(receipt),),
                information_contract="document",
                model_request_override=outcome.resolved_document_request.model_message(),
                completed_capability="files",
                application_attachment_id=receipt.receipt_id,
            )
        completed = outcome.status in {"search_completed", "no_files"}
        return DomainReadResult(
            operation_id=self.operation_id,
            projection_state="completed_read" if completed else "failed",
            delivery="application_response",
            response=self.service.human_result(outcome),
            completed_capability="files" if completed else None,
        )

    def attach_assistant_message(
        self,
        result: DomainReadResult,
        message_id: str,
    ) -> None:
        store = self.service.reader.document_store
        if store is None or result.application_attachment_id is None:
            return
        store.attach_assistant_message(result.application_attachment_id, message_id)


class GoogleDriveReadHandoffAdapter(_FileReadHandoffAdapter):
    operation_id = "google_drive.read"

    def __init__(self, service):
        self.service = service


class YandexDiskReadHandoffAdapter(_FileReadHandoffAdapter):
    operation_id = "yandex_disk.read"

    def __init__(self, service):
        self.service = service


class _HomeProposalHandoffAdapter:
    handler = None

    def _prepare(self, handoff, context):
        raise NotImplementedError

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        try:
            preparation = self._prepare(handoff, context)
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        return _project(
            preparation,
            pending_operation=preparation.application_operation,
        )


class HomeCommitmentCreateHandoffAdapter(_HomeProposalHandoffAdapter):
    operation_id = "home.commitments.create"

    def __init__(self, handler):
        self.handler = handler

    def _prepare(self, handoff, context):
        return self.handler.prepare_commitment_from_resolved_intent(
            subject=handoff.slot("subject").value,
            conversation_id=handoff.conversation_id,
            project_id=context.project_id,
        )


class HomeCommitmentCompleteHandoffAdapter(_HomeProposalHandoffAdapter):
    operation_id = "home.commitments.complete"

    def __init__(self, handler):
        self.handler = handler

    def _prepare(self, handoff, context):
        del context
        return self.handler.prepare_commitment_completion_from_resolved_intent(
            target=handoff.slot("target").value,
            conversation_id=handoff.conversation_id,
        )


class HomeMemoryRememberHandoffAdapter(_HomeProposalHandoffAdapter):
    operation_id = "home.memory.remember"

    def __init__(self, handler):
        self.handler = handler

    def _prepare(self, handoff, context):
        return self.handler.prepare_memory_remember_from_resolved_intent(
            content=handoff.slot("memory_content").value,
            record_kind=_optional_slot(handoff, "record_kind"),
            conversation_id=handoff.conversation_id,
            project_id=context.project_id,
        )


class HomeMemoryForgetHandoffAdapter(_HomeProposalHandoffAdapter):
    operation_id = "home.memory.forget"

    def __init__(self, handler):
        self.handler = handler

    def _prepare(self, handoff, context):
        return self.handler.prepare_memory_forget_from_resolved_intent(
            target=handoff.slot("target").value,
            conversation_id=handoff.conversation_id,
            project_id=context.project_id,
        )


class HomeContinuityOpenHandoffAdapter(_HomeProposalHandoffAdapter):
    operation_id = "home.continuity.open"

    def __init__(self, handler):
        self.handler = handler

    def _prepare(self, handoff, context):
        del context
        return self.handler.prepare_continuity_open_from_resolved_intent(
            topic=handoff.slot("topic").value,
            conversation_id=handoff.conversation_id,
        )


class HomeContinuityResolveHandoffAdapter(_HomeProposalHandoffAdapter):
    operation_id = "home.continuity.resolve"

    def __init__(self, handler):
        self.handler = handler

    def _prepare(self, handoff, context):
        del context
        return self.handler.prepare_continuity_resolve_from_resolved_intent(
            target=handoff.slot("target").value,
            conversation_id=handoff.conversation_id,
        )


class _HomeReadHandoffAdapter:
    handler = None
    completed_capability = None

    def _read(self, handoff, context):
        raise NotImplementedError

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainReadResult:
        outcome = self._read(handoff, context)
        if not outcome.handled or outcome.response is None:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        return DomainReadResult(
            operation_id=self.operation_id,
            projection_state="completed_read",
            delivery="application_response",
            response=outcome.response,
            completed_capability=self.completed_capability,
        )


class HomeMemoryRecallHandoffAdapter(_HomeReadHandoffAdapter):
    operation_id = "home.memory.recall"
    completed_capability = "memory"

    def __init__(self, handler):
        self.handler = handler

    def _read(self, handoff, context):
        return self.handler.recall_from_resolved_intent(
            query=_optional_slot(handoff, "query"),
            project_id=context.project_id,
            conversation_id=handoff.conversation_id,
        )


class HomeCommitmentsReadHandoffAdapter(_HomeReadHandoffAdapter):
    operation_id = "home.commitments"
    completed_capability = "memory"

    def __init__(self, handler):
        self.handler = handler

    def _read(self, handoff, context):
        return self.handler.read_commitments_from_resolved_intent(
            query=_optional_slot(handoff, "query"),
            project_id=context.project_id,
        )


class HomeMemoryInspectHandoffAdapter(_HomeReadHandoffAdapter):
    operation_id = "home.memory.inspect"
    completed_capability = "memory"

    def __init__(self, handler):
        self.handler = handler

    def _read(self, handoff, context):
        return self.handler.inspect_memory_from_resolved_intent(
            query=_optional_slot(handoff, "query"),
            project_id=context.project_id,
            conversation_id=handoff.conversation_id,
        )


class HomeContinuityReadHandoffAdapter(_HomeReadHandoffAdapter):
    operation_id = "home.continuity.read"
    completed_capability = "continuity"

    def __init__(self, handler):
        self.handler = handler

    def _read(self, handoff, context):
        del context
        return self.handler.read_continuity_from_resolved_intent(
            query=_optional_slot(handoff, "query"),
            conversation_id=handoff.conversation_id,
        )


class WebSearchHandoffAdapter:
    """Translate semantic information need into Home-owned observation policy."""

    operation_id = "web.search"

    def __init__(self, service):
        self.service = service

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainReadResult:
        if context.origin_message_id is None:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        observation = self.service.observe_resolved_search(
            handoff.original_utterance,
            query_hint=handoff.slot("query").value,
            origin_message_id=context.origin_message_id,
            recent_messages=context.recent_messages,
            project_id=context.project_id,
            active_continuity_thread_id=context.active_continuity_thread_id,
        )
        if observation is None:
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="none",
                delivery="conversation_fallback",
            )
        attachment = observation.request.observation_id
        if observation.status.value != "completed":
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="failed",
                delivery="application_response",
                response=self.service.human_failure(observation),
                application_attachment_id=attachment,
                external_observation_ids=(attachment,),
            )
        return DomainReadResult(
            operation_id=self.operation_id,
            projection_state="completed_read",
            delivery="model_evidence",
            external_information=tuple(self.service.model_context(observation)),
            information_contract="external",
            completed_capability="web",
            application_attachment_id=attachment,
            external_observation_ids=(attachment,),
        )

    def attach_assistant_message(
        self,
        result: DomainReadResult,
        message_id: str,
    ) -> None:
        if result.application_attachment_id is not None:
            self.service.attach_assistant_message(
                result.application_attachment_id,
                message_id,
            )


class WebFetchHandoffAdapter:
    """Read a public source while Home retains URL and source-reference authority."""

    operation_id = "web.fetch"

    def __init__(self, service):
        self.service = service

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainReadResult:
        if context.origin_message_id is None:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        observations = self.service.observe_fetch_request(
            handoff.original_utterance,
            origin_message_id=context.origin_message_id,
            conversation_message_ids=context.conversation_message_ids,
            recent_messages=context.recent_messages,
            project_id=context.project_id,
            active_continuity_thread_id=context.active_continuity_thread_id,
        )
        if not observations:
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="failed",
                delivery="application_response",
                response=(
                    "Я поняла просьбу прочитать источник, но не смогла "
                    "безопасно определить разрешённую страницу. Ничего не открываю."
                ),
            )
        observation_ids = tuple(
            item.request.observation_id for item in observations
        )
        failed = next(
            (item for item in reversed(observations) if item.status.value != "completed"),
            None,
        )
        if failed is not None:
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="failed",
                delivery="application_response",
                response=self.service.human_failure(failed),
                application_attachment_id=observation_ids[-1],
                external_observation_ids=observation_ids,
            )
        external_information = tuple(
            row
            for observation in observations
            for row in self.service.model_context(observation)
        )[-5:]
        if not external_information:
            return DomainReadResult(
                operation_id=self.operation_id,
                projection_state="failed",
                delivery="application_response",
                response="Источник прочитан, но безопасного текста для ответа в нём не оказалось.",
                application_attachment_id=observation_ids[-1],
                external_observation_ids=observation_ids,
            )
        return DomainReadResult(
            operation_id=self.operation_id,
            projection_state="completed_read",
            delivery="model_evidence",
            external_information=external_information,
            information_contract="external",
            completed_capability="web",
            application_attachment_id=observation_ids[-1],
            external_observation_ids=observation_ids,
        )

    def attach_assistant_message(
        self,
        result: DomainReadResult,
        message_id: str,
    ) -> None:
        for observation_id in result.external_observation_ids:
            self.service.attach_assistant_message(observation_id, message_id)
