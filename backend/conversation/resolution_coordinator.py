"""Controlled live adoption boundary for Natural Language Router V2.

The coordinator owns conversation-scoped semantic state only.  It cannot
authorize or execute a capability.  A resolved handoff still has to cross an
application adapter, domain validation, policy and confirmation boundaries.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .clarification import (
    ClarificationBuildError,
    ClarificationRequest,
    DeterministicClarificationBuilder,
    FollowUpOutcome,
    FollowUpResolutionResult,
    FollowUpResolutionEngine,
    cancelled_follow_up_remainder,
)
from .interpretation_v2 import (
    CapabilityCandidateDiscovery,
    InterpretationFrame,
    InterpretationResolutionState,
    InterpretationSlot,
    InterpretationValueOrigin,
)
from .pending_resolution import (
    ActiveQuestion,
    PendingResolutionStore,
    PendingResolutionStoreError,
    PendingResolutionStatus,
)
from .semantic_resolver import (
    SemanticFollowUpProposal,
    SemanticInterpretationProposal,
    SemanticValidationTrace,
)
from .turn_context import TurnContextEnvelope


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
    UNSUPPORTED_ACTION = "unsupported_action"


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
        resolution_id: str | None,
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
    pending_resolution_id: str | None = Field(default=None, min_length=36, max_length=36)
    prior_known_slots: tuple[InterpretationSlot, ...] = Field(default=(), max_length=24)
    follow_up_proposal: SemanticFollowUpProposal | None = None
    proposed_semantic_command: (
        SemanticInterpretationProposal | SemanticFollowUpProposal | None
    ) = None
    semantic_command_status: Literal["accepted", "rejected"] | None = None
    semantic_rejection: str | None = Field(default=None, max_length=120)
    information_space: str | None = Field(default=None, max_length=80)
    semantic_validation: SemanticValidationTrace | None = None
    merged_slots: tuple[InterpretationSlot, ...] = Field(default=(), max_length=24)
    remaining_missing_slots: tuple[str, ...] = Field(default=(), max_length=24)
    resolved_candidate: str | None = Field(
        default=None, pattern=_OPERATION_ID, max_length=100,
    )
    turn_context: "TurnContextDiagnosticSummary | None" = None


class TurnContextDiagnosticSummary(StrictCoordinatorModel):
    """Content-free proof of which Home context layers were available."""

    local_date: str = Field(min_length=10, max_length=10)
    timezone: str = Field(min_length=1, max_length=100)
    recent_turn_count: int = Field(ge=0, le=8)
    memory_hint_count: int = Field(ge=0, le=6)
    presented_entity_count: int = Field(ge=0, le=10)
    capability_count: int = Field(ge=0, le=32)
    active_continuity_present: bool

    @classmethod
    def from_envelope(
        cls, envelope: TurnContextEnvelope,
    ) -> "TurnContextDiagnosticSummary":
        return cls(
            local_date=envelope.temporal.local_date.isoformat(),
            timezone=envelope.temporal.timezone,
            recent_turn_count=len(envelope.recent_turns),
            memory_hint_count=len(envelope.memory_hints),
            presented_entity_count=len(envelope.presented_entities),
            capability_count=len(envelope.capabilities),
            active_continuity_present=envelope.active_continuity is not None,
        )


class DialogueFlowSnapshot(StrictCoordinatorModel):
    flow_id: str = Field(min_length=36, max_length=36)
    status: PendingResolutionStatus
    original_utterance: str = Field(min_length=1, max_length=20_000)
    candidate_operation_ids: tuple[str, ...] = Field(default=(), max_length=8)
    selected_operation_id: str | None = Field(
        default=None, pattern=_OPERATION_ID, max_length=100,
    )
    validated_slots: tuple[InterpretationSlot, ...] = Field(default=(), max_length=24)
    missing_slots: tuple[str, ...] = Field(default=(), max_length=24)
    active_question: ActiveQuestion
    created_at: AwareDatetime
    updated_at: AwareDatetime
    expires_at: AwareDatetime


class DialogueStateSnapshot(StrictCoordinatorModel):
    version: Literal["2.0"] = "2.0"
    conversation_id: str = Field(min_length=1, max_length=200)
    flow_stack: tuple[DialogueFlowSnapshot, ...] = Field(default=(), max_length=1)
    active_flow_id: str | None = Field(default=None, min_length=36, max_length=36)
    last_decision: V2RoutingDiagnostic | None = None


class DialogueDiagnosticSnapshot(StrictCoordinatorModel):
    """Bounded read-only observation of routing and application handoff truth."""

    dialogue_state: DialogueStateSnapshot
    application_handoff_type: str | None = Field(
        default=None, pattern=_OPERATION_ID, max_length=100,
    )
    response_projection_state: Literal[
        "none", "clarification", "waiting_confirmation", "completed_read",
        "failed", "unsupported"
    ] = "none"


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
            "google_calendar.event.update",
            "google_calendar.event.delete",
            "google_calendar.read",
            "home.timed_commitments",
            "home.commitments",
            "home.commitments.create",
            "home.commitments.complete",
            "yandex_mail.read",
            "yandex_mail.message.delete",
            "yandex_mail.message.move",
            "google_drive.read",
            "yandex_disk.read",
            "home.memory.recall",
            "home.memory.inspect",
            "home.memory.remember",
            "home.memory.forget",
            "home.continuity.read",
            "home.continuity.open",
            "home.continuity.resolve",
            "web.search",
            "web.fetch",
        ))

    def supports_frame(self, frame: InterpretationFrame) -> bool:
        operations = {candidate.operation_id for candidate in frame.candidates}
        return bool(operations) and operations.issubset(self.supported_operation_ids)

    def supports_operation(self, operation_id: str) -> bool:
        return operation_id in self.supported_operation_ids


class DialogueCore:
    """The sole owner of conversation-scoped task-dialogue transitions."""

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
        self._diagnostic_conversation_id: str | None = None
        self._decisions_by_conversation: dict[str, V2RoutingDiagnostic] = {}
        self._turn_context_summary: TurnContextDiagnosticSummary | None = None

    def coordinate(
        self,
        utterance: str,
        *,
        conversation_id: str,
        turn_context: TurnContextEnvelope | None = None,
    ) -> ConversationCoordinationOutcome:
        self._diagnostic_conversation_id = conversation_id
        self._turn_context_summary = (
            None
            if turn_context is None
            else TurnContextDiagnosticSummary.from_envelope(turn_context)
        )
        try:
            active = self.store.active_for_conversation(conversation_id)
            cancelled_before_new_turn = False
            replacement = (
                None
                if active is None
                else cancelled_follow_up_remainder(utterance)
            )
            if active is not None and replacement is not None:
                self.store.cancel(
                    active.resolution_id,
                    reason="cancelled_before_new_turn",
                )
                active = None
                utterance = replacement
                cancelled_before_new_turn = True
            frame = None
            if active is not None:
                follow_up = self.engine.resolve(
                    active,
                    utterance,
                    turn_context=turn_context,
                )
                continued = self._continue_pending(
                    active,
                    follow_up,
                    conversation_id=conversation_id,
                )
                if continued is not None:
                    if (
                        follow_up.outcome is FollowUpOutcome.STILL_UNRESOLVED
                        and follow_up.interpretation == active.interpretation
                        and follow_up.semantic_proposal is None
                    ):
                        frame = self.discovery.interpret(
                            utterance,
                            turn_context=turn_context,
                        )
                        if not frame.candidates:
                            return continued
                    else:
                        return continued
            frame = frame or self.discovery.interpret(
                utterance,
                turn_context=turn_context,
            )
            if active is None:
                if frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION:
                    return self._handled(
                        CoordinationStatus.UNSUPPORTED_ACTION,
                        frame,
                        response=self._unsupported_action_response(),
                        pending_outcome="unsupported_action",
                    )
                if (
                    frame.resolution_state is InterpretationResolutionState.RESOLVED
                    and self.adoption.supports_frame(frame)
                ):
                    return self._handled(
                        CoordinationStatus.RESOLVED_HANDOFF,
                        frame,
                        handoff=ResolvedCapabilityHandoff.from_interpretation(
                            self._handoff_frame(frame),
                            conversation_id=conversation_id,
                            resolution_id=None,
                        ),
                        pending_outcome=(
                            "cancelled_then_resolved"
                            if cancelled_before_new_turn
                            else "semantic_resolved"
                        ),
                    )
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
                        pending_outcome=(
                            "cancelled_then_clarification"
                            if cancelled_before_new_turn
                            else None
                        ),
                    )
                if self._has_strict_legacy_owner(frame):
                    return self._pass(frame, pending_outcome="strict_legacy_owner")
                if frame.candidates:
                    return self._handled(
                        CoordinationStatus.UNSUPPORTED_ACTION,
                        frame,
                        response=self._known_action_unavailable_response(frame),
                        pending_outcome="known_operation_not_adopted",
                    )
                return self._pass(frame)

            # A proven new adopted request replaces an older semantic question.
            # Unsupported candidates never supersede state in this migration slice.
            if frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION:
                return self._handled(
                    CoordinationStatus.UNSUPPORTED_ACTION,
                    frame,
                    response=self._unsupported_action_response(),
                    pending_outcome="unsupported_action_active_flow_preserved",
                )
            if frame.candidates:
                if self._has_strict_legacy_owner(frame):
                    return self._pass(frame, pending_outcome="strict_legacy_owner")
                if not self.adoption.supports_frame(frame):
                    return self._handled(
                        CoordinationStatus.UNSUPPORTED_ACTION,
                        frame,
                        response=self._known_action_unavailable_response(frame),
                        pending_outcome="known_new_operation_not_adopted",
                    )
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
                self.store.supersede(
                    active.resolution_id,
                    reason="superseded_by_supported_request",
                )
                return self._handled(
                    CoordinationStatus.RESOLVED_HANDOFF,
                    frame,
                    handoff=ResolvedCapabilityHandoff.from_interpretation(
                        self._handoff_frame(frame),
                        conversation_id=conversation_id,
                        resolution_id=None,
                    ),
                    pending_outcome="superseded_resolved",
                )

            return self._pass(frame, pending_outcome="not_a_follow_up")
        except (PendingResolutionStoreError, ClarificationBuildError, ValueError):
            return self._failed()

    def bind_temporal_engine(self, temporal_engine) -> None:
        """Keep all Home-owned temporal normalization on the current injected clock."""

        discovery = getattr(self.discovery, "deterministic", self.discovery)
        binder = getattr(discovery, "bind_temporal_engine", None)
        if binder is not None:
            binder(temporal_engine)
        validator = getattr(self.discovery, "validator", None)
        if validator is None:
            validator = getattr(self.engine, "semantic_validator", None)
        validator_binder = getattr(validator, "bind_date_resolver", None)
        if validator_binder is not None:
            from backend.temporal.date_resolution import HomeCalendarDateResolver

            validator_binder(HomeCalendarDateResolver(temporal_engine))
        engine_binder = getattr(self.engine, "bind_temporal_engine", None)
        if engine_binder is not None:
            engine_binder(temporal_engine)

    def _continue_pending(
        self,
        active,
        follow_up: FollowUpResolutionResult,
        *,
        conversation_id: str,
    ) -> ConversationCoordinationOutcome | None:
        if follow_up.outcome is FollowUpOutcome.NOT_A_FOLLOW_UP:
            return None
        trace = self._follow_up_trace(active.resolution_id, follow_up)
        if follow_up.outcome is FollowUpOutcome.RESOLVED:
            if not self.adoption.supports_operation(
                follow_up.selected_operation_id or ""
            ):
                return self._handled(
                    CoordinationStatus.UNSUPPORTED_ACTION,
                    follow_up.interpretation,
                    response=self._known_action_unavailable_response(
                        follow_up.interpretation,
                    ),
                    pending_outcome="known_resolution_not_adopted",
                    trace=trace,
                )
            stored = self.store.resolve(
                active.resolution_id,
                follow_up.interpretation,
            )
            handoff = ResolvedCapabilityHandoff.from_interpretation(
                self._handoff_frame(stored.interpretation),
                conversation_id=conversation_id,
                resolution_id=stored.resolution_id,
            )
            return self._handled(
                CoordinationStatus.RESOLVED_HANDOFF,
                stored.interpretation,
                handoff=handoff,
                pending_outcome="resolved",
                trace=trace,
            )
        if follow_up.outcome is FollowUpOutcome.CANCELLED:
            self.store.cancel(active.resolution_id)
            return self._handled(
                CoordinationStatus.CANCELLED,
                active.interpretation,
                response=self.CANCELLED_RESPONSE,
                pending_outcome="cancelled",
                trace=trace,
            )
        request = self.builder.build_request(
            follow_up.interpretation,
            conversation_id=conversation_id,
            resolution_id=active.resolution_id,
            active_question=follow_up.active_question,
        )
        next_question = (
            follow_up.active_question
            if follow_up.active_question is not None
            else request.as_active_question()
        )
        if (
            follow_up.interpretation != active.interpretation
            or next_question != active.active_question
        ):
            self.store.update_pending(
                active.resolution_id,
                follow_up.interpretation,
                clarification_kind=request.clarification_kind,
                choices=request.choices,
                requested_slot=request.requested_slot,
                referent_expression=request.referent_expression,
                active_question=next_question,
            )
        return self._handled(
            CoordinationStatus.STILL_UNRESOLVED,
            follow_up.interpretation,
            clarification=request,
            pending_outcome="still_unresolved",
            trace=trace,
        )

    def _follow_up_trace(
        self,
        resolution_id: str,
        follow_up: FollowUpResolutionResult,
    ) -> dict:
        semantic_result = getattr(self.engine, "last_semantic_result", None)
        proposed = follow_up.semantic_proposal or (
            None if semantic_result is None else semantic_result.proposal
        )
        rejection = getattr(self.engine, "last_semantic_rejection", None)
        validation = getattr(
            getattr(self.engine, "semantic_validator", None),
            "last_follow_up_trace", None,
        )
        return {
            "pending_resolution_id": resolution_id,
            "prior_known_slots": follow_up.prior_slots,
            "follow_up_proposal": follow_up.semantic_proposal,
            "proposed_semantic_command": proposed,
            "semantic_command_status": (
                "rejected" if rejection else ("accepted" if proposed is not None else None)
            ),
            "semantic_rejection": rejection,
            "semantic_validation": validation,
            "merged_slots": follow_up.merged_slots,
            "remaining_missing_slots": follow_up.remaining_missing_slots,
            "resolved_candidate": follow_up.selected_operation_id,
        }

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

    def snapshot(self, conversation_id: str) -> DialogueStateSnapshot:
        """Return bounded read-only state; never expose store mutation methods."""

        active = self.store.active_for_conversation(conversation_id)
        if active is None:
            stack = ()
            active_flow_id = None
        else:
            selected = (
                active.interpretation.candidates[0].operation_id
                if len(active.interpretation.candidates) == 1
                else None
            )
            stack = (DialogueFlowSnapshot(
                flow_id=active.flow_id,
                status=active.status,
                original_utterance=active.interpretation.original_utterance,
                candidate_operation_ids=tuple(
                    item.operation_id for item in active.interpretation.candidates
                ),
                selected_operation_id=selected,
                validated_slots=active.interpretation.slots,
                missing_slots=active.interpretation.missing_slots,
                active_question=active.active_question,
                created_at=active.created_at,
                updated_at=active.updated_at,
                expires_at=active.expires_at,
            ),)
            active_flow_id = active.flow_id
        return DialogueStateSnapshot(
            conversation_id=conversation_id,
            flow_stack=stack,
            active_flow_id=active_flow_id,
            last_decision=self._decisions_by_conversation.get(conversation_id),
        )

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

    def _handoff_frame(self, frame: InterpretationFrame) -> InterpretationFrame:
        """Add declared Home defaults only at the non-durable handoff boundary."""

        validator = getattr(self.discovery, "validator", None)
        if validator is None:
            validator = getattr(self.engine, "semantic_validator", None)
        materialize = getattr(validator, "materialize_defaults", None)
        return materialize(frame) if materialize is not None else frame

    def _unsupported_action_response(self) -> str:
        result = getattr(self.discovery, "last_result", None)
        proposal = None if result is None else getattr(result, "proposal", None)
        nearby = () if proposal is None else proposal.nearby_operation_ids
        # Never dump the whole growing capability catalog into one human
        # failure.  Alternatives are meaningful only when the semantic layer
        # explicitly identified a bounded nearby operation.
        labels = self.builder.human_operation_labels(nearby[:3])
        if not labels:
            return "Такое действие я пока не умею выполнять. Ничего не делаю."
        alternatives = " или ".join(label.casefold() for label in labels)
        return (
            "Такое действие я пока не умею выполнять. "
            f"Могу предложить безопасные варианты: {alternatives}."
        )

    def _known_action_unavailable_response(self, frame: InterpretationFrame) -> str:
        labels = self.builder.human_operation_labels(
            tuple(candidate.operation_id for candidate in frame.candidates),
        )
        label = labels[0].casefold() if len(labels) == 1 else "это действие"
        return (
            f"Я поняла, что ты просишь {label}, но этот путь пока не готов "
            "к безопасному выполнению. Ничего не запускаю."
        )

    @staticmethod
    def _has_strict_legacy_owner(frame: InterpretationFrame) -> bool:
        """Preserve capability paths that own the turn before DialogueCore."""

        return any(
            evidence.signal == "explicit_google_drive_document_create"
            for candidate in frame.candidates
            for evidence in candidate.evidence
        )

    def _failed(self) -> ConversationCoordinationOutcome:
        diagnostic = V2RoutingDiagnostic(
            status=CoordinationStatus.FAILED,
            pending_outcome="infrastructure_failure",
            turn_context=self._turn_context_summary,
        )
        self.last_decision = diagnostic
        self._remember_decision(diagnostic)
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
        trace: dict | None = None,
    ) -> ConversationCoordinationOutcome:
        diagnostic = V2RoutingDiagnostic(
            status=status,
            candidate_operation_ids=tuple(
                candidate.operation_id for candidate in frame.candidates
            ),
            pending_outcome=pending_outcome,
            **{**self._semantic_trace(), **(trace or {})},
        )
        self.last_decision = diagnostic
        self._remember_decision(diagnostic)
        return ConversationCoordinationOutcome(
            status=status,
            response=response or (clarification.prompt if clarification else None),
            clarification=clarification,
            handoff=handoff,
            diagnostic=diagnostic,
        )

    def _semantic_trace(self) -> dict:
        result = getattr(self.discovery, "last_result", None)
        rejection = getattr(self.discovery, "last_rejection", None)
        information_space = getattr(self.discovery, "last_information_space", None)
        validation = getattr(getattr(self.discovery, "validator", None), "last_trace", None)
        base = {
            "information_space": (
                None if information_space is None else getattr(information_space, "value", str(information_space))
            ),
            "semantic_validation": validation,
            "turn_context": self._turn_context_summary,
        }
        if result is None:
            return base
        proposal = getattr(result, "proposal", None)
        failure = getattr(result, "failure", None)
        if proposal is not None:
            return {
                **base,
                "proposed_semantic_command": proposal,
                "semantic_command_status": "rejected" if rejection else "accepted",
                "semantic_rejection": rejection,
            }
        if failure is not None:
            return {
                **base,
                "semantic_command_status": "rejected",
                "semantic_rejection": getattr(failure, "value", str(failure)),
            }
        return base

    def _remember_decision(self, diagnostic: V2RoutingDiagnostic) -> None:
        conversation_id = self._diagnostic_conversation_id
        if conversation_id is None:
            return
        self._decisions_by_conversation[conversation_id] = diagnostic
        while len(self._decisions_by_conversation) > 100:
            self._decisions_by_conversation.pop(next(iter(self._decisions_by_conversation)))


# Compatibility import for Slice 2A–2D callers. It is not a second owner.
NaturalLanguageResolutionCoordinator = DialogueCore


class DomainProposalContext(StrictCoordinatorModel):
    project_id: str = Field(min_length=1, max_length=200)
    now_local: AwareDatetime
    origin_message_id: str | None = Field(default=None, min_length=1, max_length=100)
    recent_messages: tuple[str, ...] = Field(default=(), max_length=8)
    conversation_message_ids: tuple[str, ...] = ()
    active_continuity_thread_id: str | None = Field(
        default=None, min_length=1, max_length=200,
    )


class DomainProposalResult(StrictCoordinatorModel):
    response: str = Field(min_length=1, max_length=2000)
    projection_state: Literal["waiting_confirmation", "failed"]
    pending_application_operation: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def pending_operation_matches_projection(self):
        if (
            self.projection_state == "waiting_confirmation"
            and self.pending_application_operation is None
        ):
            raise ValueError("waiting confirmation requires durable pending evidence")
        if (
            self.projection_state != "waiting_confirmation"
            and self.pending_application_operation is not None
        ):
            raise ValueError("non-pending projection cannot name a pending operation")
        return self


class DomainReadResult(StrictCoordinatorModel):
    """Safe normalized evidence or a controlled application read response."""

    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    projection_state: Literal["completed_read", "failed", "none"]
    delivery: Literal[
        "model_evidence", "application_response", "conversation_fallback"
    ]
    external_information: tuple[dict, ...] = Field(default=(), max_length=5)
    information_contract: Literal[
        "calendar", "mail", "document", "external"
    ] | None = None
    model_request_override: str | None = Field(default=None, max_length=1000)
    response: str | None = Field(default=None, min_length=1, max_length=2000)
    completed_capability: Literal[
        "calendar", "mail", "files", "memory", "continuity", "web"
    ] | None = None
    application_attachment_id: str | None = Field(
        default=None, min_length=8, max_length=100,
    )
    external_observation_ids: tuple[str, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def delivery_matches_payload(self):
        if self.delivery == "model_evidence":
            if (
                self.projection_state != "completed_read"
                or not self.external_information
                or self.information_contract is None
                or self.response is not None
                or self.completed_capability is None
            ):
                raise ValueError("model evidence requires completed normalized read truth")
        elif self.delivery == "application_response" and (
            self.response is None
            or self.external_information
            or self.information_contract is not None
            or self.model_request_override is not None
        ):
            raise ValueError("application response cannot carry model evidence")
        elif self.delivery == "conversation_fallback" and (
            self.projection_state != "none"
            or self.response is not None
            or self.external_information
            or self.information_contract is not None
            or self.model_request_override is not None
            or self.completed_capability is not None
            or self.application_attachment_id is not None
            or self.external_observation_ids
        ):
            raise ValueError("conversation fallback cannot carry action truth")
        return self


ResolvedCapabilityResult = DomainProposalResult | DomainReadResult


class ResolvedCapabilityAdapter(Protocol):
    operation_id: str

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> ResolvedCapabilityResult: ...


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

    @property
    def operation_ids(self) -> frozenset[str]:
        return frozenset(self._adapters)

    def resolve(
        self,
        handoff: ResolvedCapabilityHandoff,
        context: DomainProposalContext,
    ) -> ResolvedCapabilityResult:
        adapter = self._adapters.get(handoff.operation_id)
        if adapter is None:
            raise ResolvedCapabilityAdapterError(handoff.operation_id)
        return adapter.resolve(handoff, context)

    def attach_assistant_message(
        self,
        result: DomainReadResult,
        message_id: str,
    ) -> None:
        """Delegate optional receipt linkage to the owning application adapter."""

        if result.application_attachment_id is None:
            return
        adapter = self._adapters.get(result.operation_id)
        attach = None if adapter is None else getattr(adapter, "attach_assistant_message", None)
        if attach is None:
            raise ResolvedCapabilityAdapterError(result.operation_id)
        attach(result, message_id)
