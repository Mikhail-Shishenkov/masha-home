"""Controlled live adoption boundary for Natural Language Router V2.

The coordinator owns conversation-scoped semantic state only.  It cannot
authorize or execute a capability.  A resolved handoff still has to cross an
application adapter, domain validation, policy and confirmation boundaries.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .clarification import (
    ClarificationBuildError,
    ClarificationRequest,
    DeterministicClarificationBuilder,
    FollowUpOutcome,
    FollowUpResolutionEngine,
)
from .interpretation_v2 import (
    CapabilityCandidateDiscovery,
    InterpretationFrame,
    InterpretationResolutionState,
    InterpretationSlot,
    InterpretationValueOrigin,
)
from .pending_resolution import (
    PendingResolutionStore,
    PendingResolutionStoreError,
)


_OPERATION_ID = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"


class StrictCoordinatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoordinationStatus(str, Enum):
    PASS_THROUGH = "pass_through"
    CLARIFICATION = "clarification"
    RESOLVED_HANDOFF = "resolved_handoff"
    CANCELLED = "cancelled"
    STILL_UNRESOLVED = "still_unresolved"
    FAILED = "failed"


class ResolvedCapabilityHandoff(StrictCoordinatorModel):
    """Resolved human meaning, explicitly not permission or confirmation."""

    conversation_id: str = Field(min_length=1, max_length=200)
    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    original_utterance: str = Field(min_length=1, max_length=20_000)
    slots: tuple[InterpretationSlot, ...] = Field(max_length=24)
    resolution_id: str | None = Field(default=None, min_length=36, max_length=36)

    @model_validator(mode="after")
    def slots_are_resolved_and_unique(self):
        names = [slot.name for slot in self.slots]
        if len(names) != len(set(names)):
            raise ValueError("handoff contains duplicate slots")
        if any(
            slot.value is None
            or slot.origin is InterpretationValueOrigin.UNRESOLVED
            for slot in self.slots
        ):
            raise ValueError("handoff cannot contain unresolved slots")
        return self

    @classmethod
    def from_interpretation(
        cls,
        frame: InterpretationFrame,
        *,
        conversation_id: str,
        resolution_id: str,
    ) -> "ResolvedCapabilityHandoff":
        if (
            frame.resolution_state is not InterpretationResolutionState.RESOLVED
            or len(frame.candidates) != 1
        ):
            raise ValueError("handoff requires one resolved interpretation candidate")
        return cls(
            conversation_id=conversation_id,
            operation_id=frame.candidates[0].operation_id,
            original_utterance=frame.original_utterance,
            slots=frame.slots,
            resolution_id=resolution_id,
        )

    def slot(self, name: str) -> InterpretationSlot:
        match = next((slot for slot in self.slots if slot.name == name), None)
        if match is None:
            raise KeyError(name)
        return match


class V2RoutingDiagnostic(StrictCoordinatorModel):
    inspected: bool = True
    status: CoordinationStatus
    candidate_operation_ids: tuple[str, ...] = Field(default=(), max_length=8)
    pending_outcome: str | None = Field(default=None, max_length=80)


class ConversationCoordinationOutcome(StrictCoordinatorModel):
    status: CoordinationStatus
    response: str | None = Field(default=None, max_length=500)
    clarification: ClarificationRequest | None = None
    handoff: ResolvedCapabilityHandoff | None = None
    diagnostic: V2RoutingDiagnostic

    @model_validator(mode="after")
    def payload_matches_status(self):
        if self.status is CoordinationStatus.PASS_THROUGH:
            if self.response is not None or self.clarification is not None or self.handoff is not None:
                raise ValueError("pass-through cannot carry handled output")
        elif self.status is CoordinationStatus.RESOLVED_HANDOFF:
            if self.handoff is None or self.response is not None or self.clarification is not None:
                raise ValueError("resolved outcome requires only a handoff")
        elif self.status in {CoordinationStatus.CLARIFICATION, CoordinationStatus.STILL_UNRESOLVED}:
            if self.clarification is None or self.response != self.clarification.prompt or self.handoff is not None:
                raise ValueError("clarification outcome requires deterministic request")
        elif self.response is None or self.clarification is not None or self.handoff is not None:
            raise ValueError("terminal human outcome requires only a response")
        return self


class V2LiveAdoptionPolicy:
    """Application-owned feature gate; discovery alone never grants ownership."""

    def __init__(
        self,
        supported_operation_ids: frozenset[str] | None = None,
    ):
        self.supported_operation_ids = supported_operation_ids or frozenset((
            "google_calendar.event.create",
            "home.timed_commitments",
        ))

    def supports_frame(self, frame: InterpretationFrame) -> bool:
        operations = {candidate.operation_id for candidate in frame.candidates}
        return bool(operations) and operations.issubset(self.supported_operation_ids)

    def supports_operation(self, operation_id: str) -> bool:
        return operation_id in self.supported_operation_ids


class NaturalLanguageResolutionCoordinator:
    """Coordinate V2 meaning while leaving domain execution to adapters."""

    FAILURE_RESPONSE = "Не смогла безопасно сохранить уточнение. Ничего не выполняю."
    CANCELLED_RESPONSE = "Хорошо, это пока не делаем."

    def __init__(
        self,
        *,
        discovery: CapabilityCandidateDiscovery,
        builder: DeterministicClarificationBuilder,
        engine: FollowUpResolutionEngine,
        store: PendingResolutionStore,
        adoption: V2LiveAdoptionPolicy | None = None,
    ):
        self.discovery = discovery
        self.builder = builder
        self.engine = engine
        self.store = store
        self.adoption = adoption or V2LiveAdoptionPolicy()
        self.last_decision: V2RoutingDiagnostic | None = None

    def coordinate(
        self,
        utterance: str,
        *,
        conversation_id: str,
    ) -> ConversationCoordinationOutcome:
        try:
            active = self.store.active_for_conversation(conversation_id)
            frame = self.discovery.interpret(utterance)
            if active is None:
                if (
                    frame.resolution_state
                    is InterpretationResolutionState.CLARIFICATION_REQUIRED
                    and self.adoption.supports_frame(frame)
                ):
                    request, pending = self.builder.build(
                        frame,
                        conversation_id=conversation_id,
                    )
                    self.store.save(pending)
                    return self._handled(
                        CoordinationStatus.CLARIFICATION,
                        frame,
                        clarification=request,
                    )
                return self._pass(frame)

            # A proven new adopted request replaces an older semantic question.
            # Unsupported candidates never supersede state in this migration slice.
            if frame.candidates:
                if not self.adoption.supports_frame(frame):
                    return self._pass(frame, pending_outcome="unsupported_new_intent")
                if frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED:
                    request, pending = self.builder.build(
                        frame,
                        conversation_id=conversation_id,
                    )
                    self.store.save(pending, supersede_active=True)
                    return self._handled(
                        CoordinationStatus.CLARIFICATION,
                        frame,
                        clarification=request,
                        pending_outcome="superseded",
                    )
                # A complete adopted request remains owned by its mature legacy
                # route, but it is sufficient proof to retire the old question.
                self.store.supersede(
                    active.resolution_id,
                    reason="superseded_by_supported_request",
                )
                return self._pass(frame, pending_outcome="superseded")

            follow_up = self.engine.resolve(active, utterance)
            if follow_up.outcome is FollowUpOutcome.RESOLVED:
                if not self.adoption.supports_operation(
                    follow_up.selected_operation_id or ""
                ):
                    return self._pass(frame, pending_outcome="unsupported_resolution")
                stored = self.store.resolve(
                    active.resolution_id,
                    follow_up.interpretation,
                )
                handoff = ResolvedCapabilityHandoff.from_interpretation(
                    stored.interpretation,
                    conversation_id=conversation_id,
                    resolution_id=stored.resolution_id,
                )
                return self._handled(
                    CoordinationStatus.RESOLVED_HANDOFF,
                    stored.interpretation,
                    handoff=handoff,
                    pending_outcome="resolved",
                )
            if follow_up.outcome is FollowUpOutcome.CANCELLED:
                self.store.cancel(active.resolution_id)
                return self._handled(
                    CoordinationStatus.CANCELLED,
                    active.interpretation,
                    response=self.CANCELLED_RESPONSE,
                    pending_outcome="cancelled",
                )
            if follow_up.outcome is FollowUpOutcome.NOT_A_FOLLOW_UP:
                return self._pass(frame, pending_outcome="not_a_follow_up")

            request = self.builder.build_request(
                follow_up.interpretation,
                conversation_id=conversation_id,
                resolution_id=active.resolution_id,
            )
            if follow_up.interpretation != active.interpretation:
                self.store.update_pending(
                    active.resolution_id,
                    follow_up.interpretation,
                    clarification_kind=request.clarification_kind,
                    choices=request.choices,
                    requested_slot=request.requested_slot,
                    referent_expression=request.referent_expression,
                )
            return self._handled(
                CoordinationStatus.STILL_UNRESOLVED,
                follow_up.interpretation,
                clarification=request,
                pending_outcome="still_unresolved",
            )
        except (PendingResolutionStoreError, ClarificationBuildError, ValueError):
            return self._failed()

    def supersede_for_domain_proposal(self, conversation_id: str) -> bool:
        """Retire older semantic state once a mature proposal proves ownership."""

        try:
            active = self.store.active_for_conversation(conversation_id)
            if active is None:
                return False
            self.store.supersede(
                active.resolution_id,
                reason="superseded_by_domain_proposal",
            )
            return True
        except PendingResolutionStoreError:
            self._failed()
            return False

    def _pass(
        self,
        frame: InterpretationFrame,
        *,
        pending_outcome: str | None = None,
    ) -> ConversationCoordinationOutcome:
        return self._handled(
            CoordinationStatus.PASS_THROUGH,
            frame,
            pending_outcome=pending_outcome,
        )

    def _failed(self) -> ConversationCoordinationOutcome:
        diagnostic = V2RoutingDiagnostic(
            status=CoordinationStatus.FAILED,
            pending_outcome="infrastructure_failure",
        )
        self.last_decision = diagnostic
        return ConversationCoordinationOutcome(
            status=CoordinationStatus.FAILED,
            response=self.FAILURE_RESPONSE,
            diagnostic=diagnostic,
        )

    def _handled(
        self,
        status: CoordinationStatus,
        frame: InterpretationFrame,
        *,
        response: str | None = None,
        clarification: ClarificationRequest | None = None,
        handoff: ResolvedCapabilityHandoff | None = None,
        pending_outcome: str | None = None,
    ) -> ConversationCoordinationOutcome:
        diagnostic = V2RoutingDiagnostic(
            status=status,
            candidate_operation_ids=tuple(
                candidate.operation_id for candidate in frame.candidates
            ),
            pending_outcome=pending_outcome,
        )
        self.last_decision = diagnostic
        return ConversationCoordinationOutcome(
            status=status,
            response=response or (clarification.prompt if clarification else None),
            clarification=clarification,
            handoff=handoff,
            diagnostic=diagnostic,
        )


class DomainProposalContext(StrictCoordinatorModel):
    project_id: str = Field(min_length=1, max_length=200)
    now_local: AwareDatetime


class DomainProposalResult(StrictCoordinatorModel):
    response: str = Field(min_length=1, max_length=2000)


class ResolvedCapabilityAdapter(Protocol):
    operation_id: str

    def propose(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult: ...


class ResolvedCapabilityAdapterError(RuntimeError):
    pass


class ResolvedCapabilityAdapterRegistry:
    """Generic operation-id dispatch; registering a future adapter needs no enum."""

    def __init__(self, adapters: tuple[ResolvedCapabilityAdapter, ...] = ()):
        self._adapters: dict[str, ResolvedCapabilityAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ResolvedCapabilityAdapter) -> None:
        if adapter.operation_id in self._adapters:
            raise ResolvedCapabilityAdapterError(adapter.operation_id)
        self._adapters[adapter.operation_id] = adapter

    def propose(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> DomainProposalResult:
        adapter = self._adapters.get(handoff.operation_id)
        if adapter is None:
            raise ResolvedCapabilityAdapterError(handoff.operation_id)
        return adapter.propose(handoff, context)
