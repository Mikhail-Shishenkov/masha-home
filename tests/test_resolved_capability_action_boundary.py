from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.application.resolved_capabilities import (
    CalendarCreateHandoffAdapter,
    GoogleDriveReadHandoffAdapter,
)
from backend.connectors.google_drive.reader import (
    DriveReadOutcome,
    ResolvedDriveDocumentRequest,
)
from backend.conversation.interpretation_v2 import (
    InterpretationSlot,
    InterpretationValueOrigin,
)
from backend.conversation.memory_intent import (
    MemoryProposal,
    MemoryProposalStore,
    ProposalStatus,
)
from backend.conversation.resolution_coordinator import (
    DomainProposalContext,
    DomainProposalResult,
    DomainReadResult,
    ResolvedCapabilityAdapterRegistry,
    ResolvedCapabilityAdapterError,
    ResolvedCapabilityHandoff,
)
from backend.document_read import (
    DocumentEvidence,
    DocumentPageEvidence,
    DocumentReadReceipt,
    DocumentReadSourceKind,
)
from backend.runtime.action_contracts import (
    ProposalPreparation,
    ProposalPreparationStatus,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


def _handoff() -> ResolvedCapabilityHandoff:
    return ResolvedCapabilityHandoff(
        conversation_id="conversation",
        operation_id="google_calendar.event.create",
        original_utterance="Поставь встречу завтра в 10",
        slots=tuple(
            InterpretationSlot(
                name=name,
                value=value,
                origin=InterpretationValueOrigin.EXPLICIT,
            )
            for name, value in (
                ("subject", "встреча"),
                ("date", "2026-08-31"),
                ("time", "10:00"),
                ("duration_minutes", "60"),
            )
        ),
    )


def test_waiting_confirmation_projection_requires_durable_operation_evidence():
    with pytest.raises(ValidationError):
        DomainProposalResult(
            response="Подтвердить?",
            projection_state="waiting_confirmation",
        )


def test_adapter_rejects_preview_when_service_did_not_create_receipt(tmp_path):
    class Service:
        def __init__(self):
            self.proposal_store = MemoryProposalStore(tmp_path / "proposals.json")
            self.writer = type(
                "Writer",
                (),
                {"receipt_store": type("Receipts", (), {"get": lambda *_: None})()},
            )()

        def prepare_from_resolved_intent(self, **_kwargs):
            self.proposal_store.create(MemoryProposal(
                id="proposal",
                conversation_id="conversation",
                record_type="google_calendar_event",
                record_payload={"operation_id": "operation"},
                created_at=NOW,
                status=ProposalStatus.PENDING,
                operation="google_calendar_create",
            ))
            return ProposalPreparation(
                response="Поставить встречу?",
                status=ProposalPreparationStatus.PENDING_CONFIRMATION,
                application_operation="google_calendar_create",
            )

    with pytest.raises(ResolvedCapabilityAdapterError):
        CalendarCreateHandoffAdapter(Service()).resolve(
            _handoff(),
            DomainProposalContext(project_id="project", now_local=NOW),
        )


def test_no_action_result_cannot_masquerade_as_waiting_confirmation(tmp_path):
    class Service:
        def __init__(self):
            self.proposal_store = MemoryProposalStore(tmp_path / "proposals.json")

        def prepare_from_resolved_intent(self, **_kwargs):
            return ProposalPreparation(
                response="Сейчас не удалось проверить календарь для изменения.",
                status=ProposalPreparationStatus.NO_ACTION,
            )

    result = CalendarCreateHandoffAdapter(Service()).resolve(
        _handoff(),
        DomainProposalContext(project_id="project", now_local=NOW),
    )

    assert result.projection_state == "failed"
    assert result.pending_application_operation is None


def test_resolved_document_read_projects_bounded_evidence_and_links_receipt():
    receipt = DocumentReadReceipt(
        receipt_id="doc_receipt",
        source_kind=DocumentReadSourceKind.CONNECTOR,
        source_reference="provider-file-id-must-stay-in-home",
        source_domain="drive.google.com",
        display_name="Планы.pdf",
        evidence=DocumentEvidence(
            title="Планы",
            page_count=1,
            pages_read=1,
            extracted_chars=12,
            content_sha256="a" * 64,
            pages=(DocumentPageEvidence(
                page_number=1, text="Планы готовы", truncated=False,
            ),),
        ),
        completed_at=NOW,
    )

    class Store:
        def __init__(self): self.links = []
        def attach_assistant_message(self, receipt_id, message_id):
            self.links.append((receipt_id, message_id))

    class Service:
        def __init__(self):
            self.reader = type("Reader", (), {"document_store": Store()})()
        def observe_resolved(self, **_kwargs):
            return DriveReadOutcome(
                "read_completed",
                document_receipt=receipt,
                resolved_document_request=ResolvedDriveDocumentRequest("Планы.pdf"),
            )
        @staticmethod
        def human_result(_outcome): return "failure"

    service = Service()
    adapter = GoogleDriveReadHandoffAdapter(service)
    registry = ResolvedCapabilityAdapterRegistry((adapter,))
    result = registry.resolve(
        ResolvedCapabilityHandoff(
            conversation_id="conversation",
            operation_id="google_drive.read",
            original_utterance="Прочитай второй файл",
            slots=(
                InterpretationSlot(
                    name="mode", value="read",
                    origin=InterpretationValueOrigin.SEMANTIC,
                ),
                InterpretationSlot(
                    name="target", value="второй",
                    origin=InterpretationValueOrigin.SEMANTIC,
                ),
            ),
        ),
        DomainProposalContext(project_id="project", now_local=NOW),
    )

    assert isinstance(result, DomainReadResult)
    assert result.completed_capability == "files"
    assert result.information_contract == "document"
    assert "provider-file-id-must-stay-in-home" not in str(result.external_information)
    registry.attach_assistant_message(result, "assistant-message")
    assert service.reader.document_store.links == [
        ("doc_receipt", "assistant-message"),
    ]
