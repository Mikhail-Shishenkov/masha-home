"""Local, replaceable semantic proposal boundary for Natural Language V2.

The model proposes bounded meaning only.  Home validates catalog membership,
live adoption, slots and utterance provenance before an InterpretationFrame
can exist.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.application.capability_catalog import CapabilityCatalog, CapabilityNotFoundError
from backend.identity.identity_models import (
    IdentityContext,
    ManifestStatus,
    VisualStatus,
)
from backend.llm.model_models import (
    FinishReason,
    MessageRole,
    ModelCapabilities,
    ModelMessage,
    ModelRequest,
    PrivacyScope,
)
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError
from backend.llm.model_roles import ModelRole, ModelRoleProfileStore
from backend.llm.model_router import ModelCapabilityUnavailableError
from backend.memory.text_normalization import meaningful_tokens
from backend.external_observation.intent import InformationSpace, classify_information_space
from backend.temporal.date_resolution import HomeCalendarDateResolver
from backend.temporal.duration_resolution import HomeDurationResolver

from .capability_router import normalize_utterance
from .interpretation_v2 import (
    CandidateEvidence,
    CandidateEvidenceSource,
    CapabilityCandidate,
    CapabilityCandidateDiscovery,
    InterpretationAmbiguity,
    InterpretationFrame,
    InterpretationReferent,
    InterpretationResolutionState,
    InterpretationSlot,
    InterpretationSpecificationError,
    InterpretationSpecificationRegistry,
    InterpretationValueOrigin,
)


_OPERATION_ID = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_SLOT_NAME = r"^[a-z][a-z0-9_]{0,63}$"
_PROTECTED_SHORT_FOLLOW_UP = frozenset((
    "да", "подтверждаю", "нет", "не сейчас", "не надо", "отмена",
    "забудь", "ладно не делай", "в календарь", "календарь",
    "просто напомни", "только напомни", "напоминание",
))


class StrictSemanticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticAmbiguityHint(str, Enum):
    NONE = "none"
    CAPABILITY = "capability"
    SLOT = "slot"
    REFERENT = "referent"
    PROVIDER_SCOPE = "provider_scope"


class SemanticSlotProposal(StrictSemanticModel):
    name: str = Field(pattern=_SLOT_NAME)
    value: str = Field(min_length=1, max_length=500)


class SemanticSlotMergeMode(str, Enum):
    ADD = "add"
    ENRICH = "enrich"
    CORRECT = "correct"
    CONFIRM = "confirm"


class SemanticFollowUpRelation(str, Enum):
    FOLLOW_UP = "follow_up"
    NOT_A_FOLLOW_UP = "not_a_follow_up"


class SemanticSlotUpdateProposal(StrictSemanticModel):
    name: str = Field(pattern=_SLOT_NAME)
    value: str = Field(min_length=1, max_length=500)
    mode: SemanticSlotMergeMode


class SemanticReferentUpdateProposal(StrictSemanticModel):
    expression: str = Field(min_length=1, max_length=300)
    value: str = Field(min_length=1, max_length=500)


class SemanticPendingContext(StrictSemanticModel):
    original_utterance: str = Field(min_length=1, max_length=20_000)
    candidate_operation_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    known_slots: tuple[SemanticSlotProposal, ...] = Field(default=(), max_length=24)
    missing_slots: tuple[str, ...] = Field(default=(), max_length=24)
    unresolved_referents: tuple[str, ...] = Field(default=(), max_length=8)
    clarification_kind: str = Field(min_length=1, max_length=40)
    requested_slot: str | None = Field(default=None, pattern=_SLOT_NAME)
    question_value_hint: str | None = Field(default=None, min_length=1, max_length=80)

    @classmethod
    def from_pending(cls, pending) -> "SemanticPendingContext":
        return cls(
            original_utterance=pending.interpretation.original_utterance,
            candidate_operation_ids=tuple(
                item.operation_id for item in pending.interpretation.candidates
            ),
            known_slots=tuple(
                SemanticSlotProposal(name=item.name, value=item.value)
                for item in pending.interpretation.slots
                if item.value is not None
            ),
            missing_slots=pending.interpretation.missing_slots,
            unresolved_referents=tuple(
                item.expression
                for item in pending.interpretation.referents
                if item.value is None
            ),
            clarification_kind=pending.clarification_kind.value,
            requested_slot=pending.requested_slot,
            question_value_hint=pending.active_question.value_hint,
        )


class SemanticFollowUpProposal(StrictSemanticModel):
    relation: SemanticFollowUpRelation
    selected_operation_id: str | None = Field(
        default=None, pattern=_OPERATION_ID, max_length=100,
    )
    slot_updates: tuple[SemanticSlotUpdateProposal, ...] = Field(
        default=(), max_length=24,
    )
    referent_updates: tuple[SemanticReferentUpdateProposal, ...] = Field(
        default=(), max_length=8,
    )

    @model_validator(mode="after")
    def relation_matches_payload(self):
        names = [item.name for item in self.slot_updates]
        if len(names) != len(set(names)):
            raise ValueError("semantic follow-up repeats a slot")
        expressions = [item.expression for item in self.referent_updates]
        if len(expressions) != len(set(expressions)):
            raise ValueError("semantic follow-up repeats a referent")
        if (
            self.relation is SemanticFollowUpRelation.NOT_A_FOLLOW_UP
            and (
                self.selected_operation_id is not None
                or self.slot_updates
                or self.referent_updates
            )
        ):
            raise ValueError("independent turn cannot patch pending meaning")
        return self


class SemanticInterpretationProposal(StrictSemanticModel):
    """Strict but untrusted JSON returned by the helper model."""

    ordinary_conversation: bool
    unsupported_action: bool = False
    nearby_operation_ids: tuple[str, ...] = Field(default=(), max_length=4)
    candidate_operation_ids: tuple[str, ...] = Field(
        default=(), max_length=8
    )
    extracted_slots: tuple[SemanticSlotProposal, ...] = Field(
        default=(), max_length=24
    )
    unresolved_referents: tuple[str, ...] = Field(default=(), max_length=8)
    ambiguity_hint: SemanticAmbiguityHint = SemanticAmbiguityHint.NONE

    @model_validator(mode="after")
    def structure_is_bounded_and_consistent(self):
        if any(re.fullmatch(_OPERATION_ID, item) is None for item in self.candidate_operation_ids):
            raise ValueError("semantic proposal contains invalid operation id")
        if len(self.candidate_operation_ids) != len(set(self.candidate_operation_ids)):
            raise ValueError("semantic proposal repeats an operation")
        if any(re.fullmatch(_OPERATION_ID, item) is None for item in self.nearby_operation_ids):
            raise ValueError("semantic proposal contains invalid nearby operation id")
        if len(self.nearby_operation_ids) != len(set(self.nearby_operation_ids)):
            raise ValueError("semantic proposal repeats a nearby operation")
        names = [item.name for item in self.extracted_slots]
        if len(names) != len(set(names)):
            raise ValueError("semantic proposal repeats a slot")
        if len(self.unresolved_referents) != len(set(self.unresolved_referents)):
            raise ValueError("semantic proposal repeats a referent")
        if self.ordinary_conversation and self.unsupported_action:
            raise ValueError("proposal cannot be both ordinary and unsupported")
        if self.ordinary_conversation and (
            self.candidate_operation_ids
            or self.extracted_slots
            or self.unresolved_referents
            or self.nearby_operation_ids
            or self.ambiguity_hint is not SemanticAmbiguityHint.NONE
        ):
            raise ValueError("ordinary proposal cannot carry capability structure")
        if self.unsupported_action and (
            self.candidate_operation_ids
            or self.extracted_slots
            or self.unresolved_referents
            or self.ambiguity_hint is not SemanticAmbiguityHint.NONE
        ):
            raise ValueError("unsupported action cannot carry supported capability structure")
        if not self.unsupported_action and self.nearby_operation_ids:
            raise ValueError("only unsupported action may carry nearby operations")
        if (
            not self.ordinary_conversation
            and not self.unsupported_action
            and not self.candidate_operation_ids
        ):
            raise ValueError("action proposal requires a candidate")
        return self


class SemanticVocabularyItem(StrictSemanticModel):
    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    display_name: str = Field(min_length=3, max_length=120)
    required_slots: tuple[str, ...] = Field(default=(), max_length=16)


class SemanticResolverFailure(str, Enum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    MALFORMED_OUTPUT = "malformed_output"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    ROLE_UNAVAILABLE = "role_unavailable"


class SemanticResolverResult(StrictSemanticModel):
    proposal: SemanticInterpretationProposal | None = None
    failure: SemanticResolverFailure | None = None
    latency_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def result_has_one_outcome(self):
        if (self.proposal is None) == (self.failure is None):
            raise ValueError("semantic result requires exactly one outcome")
        return self


class SemanticFollowUpResult(StrictSemanticModel):
    proposal: SemanticFollowUpProposal | None = None
    failure: SemanticResolverFailure | None = None
    latency_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def result_has_one_outcome(self):
        if (self.proposal is None) == (self.failure is None):
            raise ValueError("semantic follow-up result requires exactly one outcome")
        return self


class ValidatedSemanticSlotUpdate(StrictSemanticModel):
    slot: InterpretationSlot
    mode: SemanticSlotMergeMode


class ValidatedSemanticReferentUpdate(StrictSemanticModel):
    referent: InterpretationReferent


class ValidatedSemanticFollowUp(StrictSemanticModel):
    relation: SemanticFollowUpRelation
    selected_operation_id: str | None = Field(
        default=None, pattern=_OPERATION_ID, max_length=100,
    )
    slot_updates: tuple[ValidatedSemanticSlotUpdate, ...] = Field(
        default=(), max_length=24,
    )
    referent_updates: tuple[ValidatedSemanticReferentUpdate, ...] = Field(
        default=(), max_length=8,
    )


class SemanticResolver(Protocol):
    def resolve(
        self,
        utterance: str,
        vocabulary: tuple[SemanticVocabularyItem, ...],
        *,
        profile_id: str | None = None,
    ) -> SemanticResolverResult: ...

    def resolve_follow_up(
        self,
        utterance: str,
        vocabulary: tuple[SemanticVocabularyItem, ...],
        context: SemanticPendingContext,
        *,
        profile_id: str | None = None,
    ) -> SemanticFollowUpResult: ...


def _resolver_identity() -> IdentityContext:
    """Minimal execution scaffolding; the resolver never receives Masha Identity."""

    return IdentityContext(
        identity_version="semantic-resolver-1",
        manifest_status=ManifestStatus.APPROVED,
        persona_id="semantic-resolver",
        name="Semantic Resolver",
        role="bounded local utterance interpreter",
        core_traits=("bounded", "non-authoritative"),
        communication_principles=("return strict JSON only",),
        relationship_expressions=(),
        growth_areas=(),
        visual_status=VisualStatus.UNAPPROVED,
        canonical_asset_ids=(),
    )


class LocalSemanticResolver:
    """Structured local-model role; failure always returns a controlled result."""

    def __init__(
        self,
        *,
        router,
        role_profiles: ModelRoleProfileStore,
        timeout_seconds: float = 8.0,
        clock=perf_counter,
    ):
        if not 0 < timeout_seconds <= 15:
            raise ValueError("semantic resolver timeout must be in (0, 15]")
        self.router = router
        self.role_profiles = role_profiles
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self.last_result: SemanticResolverResult | None = None

    def resolve(
        self,
        utterance: str,
        vocabulary: tuple[SemanticVocabularyItem, ...],
        *,
        profile_id: str | None = None,
    ) -> SemanticResolverResult:
        started = self.clock()
        try:
            profile = (
                self.role_profiles.profiles.get_profile(profile_id)
                if profile_id is not None
                else self.role_profiles.profile_for(ModelRole.SEMANTIC_RESOLVER)
            )
            if not profile.enabled:
                raise ValueError("semantic profile disabled")
        except (KeyError, ValueError):
            return self._failed(SemanticResolverFailure.ROLE_UNAVAILABLE, started)
        request = ModelRequest(
            messages=(
                ModelMessage(role=MessageRole.SYSTEM, content=self._prompt(vocabulary)),
                ModelMessage(role=MessageRole.USER, content=utterance[:20_000]),
            ),
            identity_context=_resolver_identity(),
            required_capabilities=ModelCapabilities(
                structured_output=True,
                tools=False,
            ),
            privacy_scope=PrivacyScope.LOCAL_ONLY,
            preferred_provider_id=profile.provider_id,
            timeout_seconds=min(profile.timeout_seconds, self.timeout_seconds),
            execution_model_id=profile.model_id,
            execution_think=False,
        )
        try:
            response = self.router.generate(request)
            if response.finish_reason not in {FinishReason.COMPLETED, FinishReason.LENGTH}:
                return self._failed(SemanticResolverFailure.MALFORMED_OUTPUT, started)
            proposal = SemanticInterpretationProposal.model_validate(
                json.loads(response.text)
            )
        except ModelTimeoutError:
            return self._failed(SemanticResolverFailure.TIMEOUT, started)
        except ModelCapabilityUnavailableError:
            return self._failed(SemanticResolverFailure.CAPABILITY_UNAVAILABLE, started)
        except ModelProviderUnavailableError:
            return self._failed(SemanticResolverFailure.PROVIDER_UNAVAILABLE, started)
        except (json.JSONDecodeError, ValueError, TypeError):
            return self._failed(SemanticResolverFailure.MALFORMED_OUTPUT, started)
        result = SemanticResolverResult(
            proposal=proposal,
            latency_ms=max(0.0, (self.clock() - started) * 1000),
        )
        self.last_result = result
        return result

    def resolve_follow_up(
        self,
        utterance: str,
        vocabulary: tuple[SemanticVocabularyItem, ...],
        context: SemanticPendingContext,
        *,
        profile_id: str | None = None,
    ) -> SemanticFollowUpResult:
        """Interpret one turn against bounded pending meaning, never history."""

        started = self.clock()
        try:
            profile = (
                self.role_profiles.profiles.get_profile(profile_id)
                if profile_id is not None
                else self.role_profiles.profile_for(ModelRole.SEMANTIC_RESOLVER)
            )
            if not profile.enabled:
                raise ValueError("semantic profile disabled")
        except (KeyError, ValueError):
            return self._failed_follow_up(
                SemanticResolverFailure.ROLE_UNAVAILABLE, started,
            )
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content=self._follow_up_prompt(vocabulary, context),
                ),
                ModelMessage(role=MessageRole.USER, content=utterance[:20_000]),
            ),
            identity_context=_resolver_identity(),
            required_capabilities=ModelCapabilities(
                structured_output=True,
                tools=False,
            ),
            privacy_scope=PrivacyScope.LOCAL_ONLY,
            preferred_provider_id=profile.provider_id,
            timeout_seconds=min(profile.timeout_seconds, self.timeout_seconds),
            execution_model_id=profile.model_id,
            execution_think=False,
        )
        try:
            response = self.router.generate(request)
            if response.finish_reason not in {FinishReason.COMPLETED, FinishReason.LENGTH}:
                return self._failed_follow_up(
                    SemanticResolverFailure.MALFORMED_OUTPUT, started,
                )
            proposal = SemanticFollowUpProposal.model_validate(
                json.loads(response.text)
            )
        except ModelTimeoutError:
            return self._failed_follow_up(SemanticResolverFailure.TIMEOUT, started)
        except ModelCapabilityUnavailableError:
            return self._failed_follow_up(
                SemanticResolverFailure.CAPABILITY_UNAVAILABLE, started,
            )
        except ModelProviderUnavailableError:
            return self._failed_follow_up(
                SemanticResolverFailure.PROVIDER_UNAVAILABLE, started,
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return self._failed_follow_up(
                SemanticResolverFailure.MALFORMED_OUTPUT, started,
            )
        return SemanticFollowUpResult(
            proposal=proposal,
            latency_ms=max(0.0, (self.clock() - started) * 1000),
        )

    def _failed(self, failure: SemanticResolverFailure, started: float) -> SemanticResolverResult:
        result = SemanticResolverResult(
            failure=failure,
            latency_ms=max(0.0, (self.clock() - started) * 1000),
        )
        self.last_result = result
        return result

    def _failed_follow_up(
        self,
        failure: SemanticResolverFailure,
        started: float,
    ) -> SemanticFollowUpResult:
        return SemanticFollowUpResult(
            failure=failure,
            latency_ms=max(0.0, (self.clock() - started) * 1000),
        )

    @staticmethod
    def _prompt(vocabulary: tuple[SemanticVocabularyItem, ...]) -> str:
        operations = [item.model_dump(mode="json") for item in vocabulary]
        return (
            "Ты локальный семантический интерпретатор одной текущей русской реплики. "
            "Ты не отвечаешь человеку, не выполняешь действия и не даёшь разрешений. "
            "Определи основной речевой акт, даже если просьба окружена приветствием, "
            "вежливостью или разговорной вводной. Не превращай рассказ, предположение, "
            "воспоминание или вопрос-совет в действие. Используй только операции из "
            "переданного списка и только смысл текущей реплики. Не выдумывай значения. "
            "Для неоднозначного планирования верни все правдоподобные операции. "
            "Верни строго один JSON-объект без Markdown по схеме: "
            '{"ordinary_conversation":bool,"unsupported_action":bool,'
            '"candidate_operation_ids":[string],"nearby_operation_ids":[string],'
            '"extracted_slots":[{"name":string,"value":string}],'
            '"unresolved_referents":[string],'
            '"ambiguity_hint":"none|capability|slot|referent|provider_scope"}. '
            "ordinary_conversation=true означает, что человек не просит выполнить действие. "
            "unsupported_action=true означает явную просьбу о действии, для которого в "
            "каталоге нет подходящей операции; candidate/slots/referents тогда пусты, "
            "а nearby_operation_ids может содержать только действительно близкие операции каталога. "
            "Безопасный каталог операций и требуемых смысловых слотов:\n"
            + json.dumps(operations, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _follow_up_prompt(
        vocabulary: tuple[SemanticVocabularyItem, ...],
        context: SemanticPendingContext,
    ) -> str:
        operations = [item.model_dump(mode="json") for item in vocabulary]
        bounded_context = context.model_dump(mode="json")
        return (
            "Ты локальный интерпретатор одного ответа на активное уточнение. "
            "Не отвечай человеку и не выполняй действия. Определи, продолжает ли "
            "текущая реплика сохранённый intent. Выбор capability меняет только "
            "candidate, а slot update не удаляет остальные известные slots. "
            "Новый самостоятельный вопрос, рассказ или новая задача — not_a_follow_up. "
            "Для slot value копируй только выражение, реально присутствующее в текущей "
            "реплике; не вычисляй календарную дату самостоятельно. mode: add для нового "
            "slot, enrich для более точного старого значения, correct для явной замены, "
            "confirm для подтверждения прежнего. Используй только operation_id из "
            "pending context. Верни строго JSON без Markdown: "
            '{"relation":"follow_up|not_a_follow_up",'
            '"selected_operation_id":string|null,'
            '"slot_updates":[{"name":string,"value":string,'
            '"mode":"add|enrich|correct|confirm"}],'
            '"referent_updates":[{"expression":string,"value":string}]}. '
            "Безопасный каталог:\n"
            + json.dumps(operations, ensure_ascii=False, separators=(",", ":"))
            + "\nBounded pending context:\n"
            + json.dumps(bounded_context, ensure_ascii=False, separators=(",", ":"))
        )


class SemanticValidationError(ValueError):
    pass


class SemanticProposalValidator:
    """Convert model output to trusted structure using only Home-owned rules."""

    def __init__(
        self,
        *,
        catalog: CapabilityCatalog,
        specifications: InterpretationSpecificationRegistry,
        allowed_operation_ids: frozenset[str],
    ):
        self.catalog = catalog
        self.specifications = specifications
        self.allowed_operation_ids = allowed_operation_ids

    def vocabulary(self) -> tuple[SemanticVocabularyItem, ...]:
        items = []
        # The language model must see the descriptive whole-Home catalog so a
        # mature compatibility capability is not mislabeled unsupported.  The
        # separate allowed set below still prevents unadopted operations from
        # becoming Dialogue Core handoffs.
        for operation_id in self.specifications.operation_ids:
            try:
                descriptor = self.catalog.get(operation_id)
                specification = self.specifications.get(operation_id)
            except (CapabilityNotFoundError, InterpretationSpecificationError) as error:
                raise SemanticValidationError(operation_id) from error
            items.append(SemanticVocabularyItem(
                operation_id=operation_id,
                display_name=descriptor.display_name,
                required_slots=specification.required_slots,
            ))
        return tuple(items)

    def required_slots(self, operation_id: str) -> tuple[str, ...]:
        if operation_id not in self.allowed_operation_ids:
            raise SemanticValidationError("unsupported_operation")
        return self.specifications.get(operation_id).required_slots

    def validate(
        self,
        utterance: str,
        proposal: SemanticInterpretationProposal,
    ) -> InterpretationFrame:
        original = utterance.strip()
        if not original:
            raise SemanticValidationError("empty_utterance")
        if proposal.ordinary_conversation:
            return InterpretationFrame(
                original_utterance=original,
                resolution_state=InterpretationResolutionState.ORDINARY_CONVERSATION,
            )
        if proposal.unsupported_action:
            if any(
                operation_id not in self.allowed_operation_ids
                for operation_id in proposal.nearby_operation_ids
            ):
                raise SemanticValidationError("unsupported_nearby_operation")
            return InterpretationFrame(
                original_utterance=original,
                resolution_state=InterpretationResolutionState.UNSUPPORTED_ACTION,
            )
        specifications = []
        for operation_id in proposal.candidate_operation_ids:
            try:
                self.catalog.get(operation_id)
                specifications.append(self.specifications.get(operation_id))
            except (CapabilityNotFoundError, InterpretationSpecificationError) as error:
                raise SemanticValidationError("unknown_operation") from error
        if any(
            operation_id not in self.allowed_operation_ids
            for operation_id in proposal.candidate_operation_ids
        ):
            raise SemanticValidationError("unsupported_operation")
        allowed_slots = {
            slot
            for specification in specifications
            for slot in specification.required_slots
        }
        if any(slot.name not in allowed_slots for slot in proposal.extracted_slots):
            raise SemanticValidationError("unknown_slot")
        slots = tuple(
            self._validated_slot(original, slot)
            for slot in proposal.extracted_slots
        )
        slot_names = {slot.name for slot in slots}
        candidates = tuple(
            CapabilityCandidate(
                operation_id=specification.operation_id,
                evidence=(CandidateEvidence(
                    signal="local_semantic_proposal_validated",
                    source=CandidateEvidenceSource.SEMANTIC,
                ),),
                slot_names=tuple(slot.name for slot in slots),
                missing_slots=tuple(
                    name for name in specification.required_slots
                    if name not in slot_names
                ),
            )
            for specification in specifications
        )
        normalized = normalize_utterance(original)
        referents = tuple(
            InterpretationReferent(expression=expression)
            for expression in proposal.unresolved_referents
            if self._referent_is_supported(normalized, expression)
        )
        if len(referents) != len(proposal.unresolved_referents):
            raise SemanticValidationError("invented_referent")
        missing = tuple(dict.fromkeys(
            name for candidate in candidates for name in candidate.missing_slots
        ))
        ambiguity = self._ambiguity(candidates, missing, referents)
        if proposal.ambiguity_hint.value != ambiguity.value:
            raise SemanticValidationError("impossible_ambiguity")
        state = (
            InterpretationResolutionState.RESOLVED
            if ambiguity is InterpretationAmbiguity.NONE
            else InterpretationResolutionState.CLARIFICATION_REQUIRED
        )
        return InterpretationFrame(
            original_utterance=original,
            normalized_goal=(candidates[0].operation_id if len(candidates) == 1 else None),
            candidates=candidates,
            slots=slots,
            missing_slots=missing,
            referents=referents,
            ambiguity=ambiguity,
            resolution_state=state,
        )

    def validate_follow_up(
        self,
        pending,
        utterance: str,
        proposal: SemanticFollowUpProposal,
        *,
        date_resolver: HomeCalendarDateResolver,
    ) -> ValidatedSemanticFollowUp:
        """Validate a contextual proposal against the saved frame and this turn."""

        if proposal.relation is SemanticFollowUpRelation.NOT_A_FOLLOW_UP:
            return ValidatedSemanticFollowUp(relation=proposal.relation)
        candidate_ids = {
            candidate.operation_id for candidate in pending.interpretation.candidates
        }
        if (
            proposal.selected_operation_id is not None
            and proposal.selected_operation_id not in candidate_ids
        ):
            raise SemanticValidationError("follow_up_invented_candidate")
        allowed_slots = set()
        for operation_id in candidate_ids:
            try:
                specification = self.specifications.get(operation_id)
            except InterpretationSpecificationError as error:
                raise SemanticValidationError("follow_up_unknown_operation") from error
            allowed_slots.update(specification.required_slots)
        if any(item.name not in allowed_slots for item in proposal.slot_updates):
            raise SemanticValidationError("follow_up_unknown_slot")
        known = {
            item.name: item for item in pending.interpretation.slots
        }
        updates = []
        for item in proposal.slot_updates:
            slot = self._validated_follow_up_slot(
                utterance,
                item,
                date_resolver=date_resolver,
            )
            self._validate_merge_mode(known.get(item.name), slot, item.mode)
            updates.append(ValidatedSemanticSlotUpdate(slot=slot, mode=item.mode))
        unresolved = {
            item.expression
            for item in pending.interpretation.referents
            if item.value is None
        }
        referent_updates = []
        for item in proposal.referent_updates:
            if item.expression not in unresolved:
                raise SemanticValidationError("follow_up_unknown_referent")
            utterance_tokens = set(meaningful_tokens(normalize_utterance(utterance)))
            value_tokens = set(meaningful_tokens(item.value))
            if not value_tokens or not value_tokens.issubset(utterance_tokens):
                raise SemanticValidationError("follow_up_referent_not_grounded")
            referent_updates.append(ValidatedSemanticReferentUpdate(
                referent=InterpretationReferent(
                    expression=item.expression,
                    value=item.value.strip(),
                    origin=InterpretationValueOrigin.FOLLOW_UP_SEMANTIC,
                ),
            ))
        return ValidatedSemanticFollowUp(
            relation=proposal.relation,
            selected_operation_id=proposal.selected_operation_id,
            slot_updates=tuple(updates),
            referent_updates=tuple(referent_updates),
        )

    @staticmethod
    def _validated_follow_up_slot(
        utterance: str,
        proposal: SemanticSlotUpdateProposal,
        *,
        date_resolver: HomeCalendarDateResolver,
    ) -> InterpretationSlot:
        value = proposal.value.strip()
        normalized = normalize_utterance(utterance)
        if proposal.name == "date":
            if normalize_utterance(value) not in normalized:
                raise SemanticValidationError("follow_up_date_not_grounded")
            resolved = date_resolver.resolve(value)
            if resolved is None:
                raise SemanticValidationError("follow_up_date_invalid")
            return InterpretationSlot(
                name="date",
                value=resolved.canonical,
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            )
        if proposal.name == "time":
            proposed_times = _utterance_times(normalize_utterance(value))
            grounded_times = _utterance_times(normalized)
            matches = proposed_times & grounded_times
            if len(matches) != 1:
                raise SemanticValidationError("follow_up_time_not_grounded")
            return InterpretationSlot(
                name="time",
                value=next(iter(matches)),
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            )
        if proposal.name == "duration_minutes":
            if normalize_utterance(value) not in normalized:
                raise SemanticValidationError("follow_up_duration_not_grounded")
            resolved = HomeDurationResolver().resolve(value)
            if resolved is None or resolved.minutes is None:
                raise SemanticValidationError("follow_up_duration_ambiguous")
            return InterpretationSlot(
                name="duration_minutes",
                value=resolved.canonical,
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            )
        if proposal.name == "subject":
            utterance_tokens = set(meaningful_tokens(normalized))
            value_tokens = set(meaningful_tokens(value))
            if not value_tokens or not value_tokens.issubset(utterance_tokens):
                raise SemanticValidationError("follow_up_subject_not_grounded")
        elif normalize_utterance(value) not in normalized:
            raise SemanticValidationError("follow_up_value_not_grounded")
        return InterpretationSlot(
            name=proposal.name,
            value=value,
            origin=InterpretationValueOrigin.FOLLOW_UP_SEMANTIC,
        )

    @staticmethod
    def _validate_merge_mode(
        previous: InterpretationSlot | None,
        updated: InterpretationSlot,
        mode: SemanticSlotMergeMode,
    ) -> None:
        if mode is SemanticSlotMergeMode.ADD:
            if previous is not None:
                raise SemanticValidationError("follow_up_add_replaces_known_slot")
            return
        if previous is None:
            raise SemanticValidationError("follow_up_update_missing_slot")
        same_value = normalize_utterance(previous.value or "") == normalize_utterance(
            updated.value or ""
        )
        if mode is SemanticSlotMergeMode.CONFIRM:
            if not same_value:
                raise SemanticValidationError("follow_up_confirmation_changed_slot")
            return
        if mode is SemanticSlotMergeMode.ENRICH:
            before = set(meaningful_tokens(previous.value or ""))
            after = set(meaningful_tokens(updated.value or ""))
            if not before or not before < after:
                raise SemanticValidationError("follow_up_enrichment_not_stronger")
            return
        if mode is SemanticSlotMergeMode.CORRECT and same_value:
            raise SemanticValidationError("follow_up_correction_unchanged")

    @staticmethod
    def _ambiguity(candidates, missing, referents) -> InterpretationAmbiguity:
        if len(candidates) > 1:
            return InterpretationAmbiguity.CAPABILITY
        if any(item.origin is InterpretationValueOrigin.UNRESOLVED for item in referents):
            return InterpretationAmbiguity.REFERENT
        if missing:
            return InterpretationAmbiguity.SLOT
        return InterpretationAmbiguity.NONE

    @staticmethod
    def _validated_slot(utterance: str, proposal: SemanticSlotProposal) -> InterpretationSlot:
        value = proposal.value.strip()
        normalized = normalize_utterance(utterance)
        if proposal.name == "date":
            if value.casefold() not in {"сегодня", "завтра"} or re.search(
                rf"\b{re.escape(value.casefold())}\b", normalized
            ) is None:
                raise SemanticValidationError("unsupported_date")
        elif proposal.name == "time":
            if value not in _utterance_times(normalized):
                raise SemanticValidationError("unsupported_time")
        elif proposal.name == "duration_minutes":
            if normalize_utterance(value) not in normalized:
                raise SemanticValidationError("unsupported_duration")
            resolved = HomeDurationResolver().resolve(value)
            if resolved is None or resolved.minutes is None:
                raise SemanticValidationError("unsupported_duration")
            return InterpretationSlot(
                name="duration_minutes",
                value=resolved.canonical,
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            )
        elif proposal.name == "subject":
            utterance_tokens = set(meaningful_tokens(normalized))
            value_tokens = set(meaningful_tokens(value))
            if not value_tokens or not value_tokens.issubset(utterance_tokens):
                raise SemanticValidationError("invented_subject")
        elif normalize_utterance(value) not in normalized:
            raise SemanticValidationError("invented_slot_value")
        return InterpretationSlot(
            name=proposal.name,
            value=value,
            origin=InterpretationValueOrigin.SEMANTIC,
        )

    @staticmethod
    def _referent_is_supported(normalized: str, expression: str) -> bool:
        value = normalize_utterance(expression)
        return bool(value and re.search(rf"\b{re.escape(value)}\b", normalized))


_RUSSIAN_HOURS = {
    "ноль": 0, "час": 1, "один": 1, "одна": 1, "два": 2, "две": 2,
    "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7,
    "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
    "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17,
    "восемнадцать": 18, "девятнадцать": 19, "двадцать": 20,
    "двадцать один": 21, "двадцать два": 22, "двадцать три": 23,
}


def _utterance_times(normalized: str) -> frozenset[str]:
    values = set()
    for match in re.finditer(r"\b(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\b", normalized):
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            values.add(f"{hour:02d}:{minute:02d}")
    for phrase, hour in _RUSSIAN_HOURS.items():
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            values.add(f"{hour:02d}:00")
    return frozenset(values)


class HybridCapabilityCandidateDiscovery:
    """One language ingress: structural evidence plus bounded local semantics."""

    def __init__(
        self,
        *,
        deterministic: CapabilityCandidateDiscovery,
        resolver: SemanticResolver,
        validator: SemanticProposalValidator,
    ):
        self.deterministic = deterministic
        self.resolver = resolver
        self.validator = validator
        self.last_result: SemanticResolverResult | None = None
        self.last_rejection: str | None = None

    def interpret(self, utterance: str) -> InterpretationFrame:
        deterministic = self.deterministic.interpret(utterance)
        self.last_result = None
        self.last_rejection = None
        if classify_information_space(utterance) is not InformationSpace.ORDINARY_CONVERSATION:
            return deterministic
        if normalize_utterance(utterance) in _PROTECTED_SHORT_FOLLOW_UP:
            return deterministic
        try:
            vocabulary = self.validator.vocabulary()
        except SemanticValidationError as error:
            self.last_rejection = str(error)
            return deterministic
        result = self.resolver.resolve(utterance, vocabulary)
        self.last_result = result
        if result.proposal is None:
            return deterministic
        try:
            semantic = self.validator.validate(utterance, result.proposal)
            if (
                semantic.resolution_state
                is InterpretationResolutionState.UNSUPPORTED_ACTION
                and not result.proposal.nearby_operation_ids
                and not any(
                    candidate.operation_id in self.validator.allowed_operation_ids
                    for candidate in deterministic.candidates
                )
            ):
                # The current Catalog does not yet describe every mature V1
                # Memory/Reflection/read route.  Surface unsupported only when
                # Dialogue Core already has grounded candidate evidence for
                # the adopted scheduling space; otherwise preserve the legacy
                # compatibility route instead of stealing its raw utterance.
                self.last_rejection = "unsupported_action_outside_adopted_space"
                return deterministic
            if self._strict_structural_conflict(deterministic, semantic):
                self.last_rejection = "semantic_conflicts_with_structural_owner"
                return deterministic
            return semantic
        except SemanticValidationError as error:
            self.last_rejection = str(error)
            return deterministic

    @staticmethod
    def _strict_structural_conflict(
        deterministic: InterpretationFrame,
        semantic: InterpretationFrame,
    ) -> bool:
        strict = any(
            evidence.signal in {
                "explicit_home_reminder_language",
                "explicit_calendar_create_language",
            }
            for candidate in deterministic.candidates
            for evidence in candidate.evidence
        )
        if not strict:
            return False
        deterministic_operations = {
            candidate.operation_id for candidate in deterministic.candidates
        }
        semantic_operations = {
            candidate.operation_id for candidate in semantic.candidates
        }
        return not semantic_operations or not semantic_operations.issubset(
            deterministic_operations
        )
