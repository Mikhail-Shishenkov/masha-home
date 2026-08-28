"""Application adapters from resolved V2 meaning to existing proposal owners."""

from __future__ import annotations

from backend.conversation.resolution_coordinator import (
    DomainProposalContext,
    DomainProposalResult,
    ResolvedCapabilityAdapterError,
    ResolvedCapabilityHandoff,
)


class CalendarCreateHandoffAdapter:
    operation_id = "google_calendar.event.create"

    def __init__(self, service):
        self.service = service

    def propose(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        try:
            response = self.service.propose_from_resolved_intent(
                subject=handoff.slot("subject").value,
                date=handoff.slot("date").value,
                time=handoff.slot("time").value,
                duration_minutes=handoff.slot("duration_minutes").value,
                conversation_id=handoff.conversation_id,
                now_local=context.now_local,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        if not response:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        return DomainProposalResult(response=response)


class TimedCommitmentHandoffAdapter:
    operation_id = "home.timed_commitments"

    def __init__(self, handler):
        self.handler = handler

    def propose(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        try:
            result = self.handler.propose_timed_commitment_from_resolved_intent(
                subject=handoff.slot("subject").value,
                date=handoff.slot("date").value,
                time=handoff.slot("time").value,
                conversation_id=handoff.conversation_id,
                project_id=context.project_id,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ResolvedCapabilityAdapterError(self.operation_id) from error
        if not result.handled or not result.response:
            raise ResolvedCapabilityAdapterError(self.operation_id)
        return DomainProposalResult(response=result.response)
