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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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


class SemanticSlotEvidenceProposal(StrictSemanticModel):
    name: str = Field(pattern=_SLOT_NAME)
    evidence_text: str = Field(
        min_length=1,
        max_length=500,
        description="Exact substring copied from the current user utterance.",
    )


# Compatibility name for code importing the old type.  The wire field is no
# longer ``value`` and this alias does not preserve the old JSON contract.
SemanticSlotProposal = SemanticSlotEvidenceProposal


class SemanticKnownSlot(StrictSemanticModel):
    name: str = Field(pattern=_SLOT_NAME)
    value: str = Field(min_length=1, max_length=500)


class OperationSelectionEvidence(StrictSemanticModel):
    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    evidence_text: str = Field(
        min_length=1,
        max_length=300,
        description=(
            "Exact current-utterance substring explicitly selecting this operation "
            "inside its operation_selection_group; empty array when no destination "
            "or operation type was explicitly selected."
        ),
    )


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
    evidence_text: str = Field(min_length=1, max_length=500)
    mode: SemanticSlotMergeMode


class SemanticReferentUpdateProposal(StrictSemanticModel):
    expression: str = Field(min_length=1, max_length=300)
    value: str = Field(min_length=1, max_length=500)


class SemanticPendingContext(StrictSemanticModel):
    original_utterance: str = Field(min_length=1, max_length=20_000)
    candidate_operation_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    known_slots: tuple[SemanticKnownSlot, ...] = Field(default=(), max_length=24)
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
                SemanticKnownSlot(name=item.name, value=item.value)
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
    operation_selection_evidence: str | None = Field(
        default=None, min_length=1, max_length=300,
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
                or self.operation_selection_evidence is not None
                or self.slot_updates
                or self.referent_updates
            )
        ):
            raise ValueError("independent turn cannot patch pending meaning")
        if (self.selected_operation_id is None) != (
            self.operation_selection_evidence is None
        ):
            raise ValueError("operation selection requires grounded evidence")
        return self


class SemanticProposalKind(str, Enum):
    ORDINARY = "ordinary"
    SUPPORTED_ACTION = "supported_action"
    UNSUPPORTED_ACTION = "unsupported_action"


class SemanticInterpretationProposal(StrictSemanticModel):
    """One discriminated wire object; Home validates the kind-specific shape."""

    kind: SemanticProposalKind
    candidate_operation_ids: tuple[str, ...] = Field(
        max_length=8,
        description="Catalog operations that can satisfy the requested action.",
    )
    nearby_operation_ids: tuple[str, ...] = Field(max_length=4)
    extracted_slots: tuple[SemanticSlotEvidenceProposal, ...] = Field(
        max_length=24
    )
    unresolved_referents: tuple[str, ...] = Field(max_length=8)
    ambiguity_hint: SemanticAmbiguityHint
    operation_selection_evidence: OperationSelectionEvidence | None = Field(
        description=(
            "One grounded explicit operation selection, or null when the user did "
            "not choose a destination/type inside an ambiguity group."
        ),
    )

    def validate_home_shape(self) -> None:
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
        if (
            self.operation_selection_evidence is not None
            and self.operation_selection_evidence.operation_id
            not in self.candidate_operation_ids
        ):
            raise ValueError("selection evidence must refer to a proposed operation")
        if self.kind is SemanticProposalKind.ORDINARY and (
            self.candidate_operation_ids
            or self.nearby_operation_ids
            or self.extracted_slots
            or self.unresolved_referents
            or self.operation_selection_evidence
            or self.ambiguity_hint is not SemanticAmbiguityHint.NONE
        ):
            raise ValueError("ordinary proposal cannot carry capability structure")
        if self.kind is SemanticProposalKind.UNSUPPORTED_ACTION and (
            self.candidate_operation_ids
            or self.extracted_slots
            or self.unresolved_referents
            or self.operation_selection_evidence
            or self.ambiguity_hint is not SemanticAmbiguityHint.NONE
        ):
            raise ValueError("unsupported action cannot carry supported structure")
        if self.kind is SemanticProposalKind.SUPPORTED_ACTION:
            if not self.candidate_operation_ids:
                raise ValueError("supported action requires a candidate")
            if self.nearby_operation_ids:
                raise ValueError("supported action cannot carry nearby operations")
        return None


def parse_semantic_interpretation(value) -> SemanticInterpretationProposal:
    """Validate the fresh one-kind wire contract at narrow API boundaries."""

    return SemanticInterpretationProposal.model_validate(value)


# Narrow source-compatibility aliases; all three names share the same strict
# one-kind wire model and do not reintroduce boolean truth.
OrdinaryProposal = SemanticInterpretationProposal
SupportedActionProposal = SemanticInterpretationProposal
UnsupportedActionProposal = SemanticInterpretationProposal


class SemanticVocabularyItem(StrictSemanticModel):
    operation_id: str = Field(pattern=_OPERATION_ID, max_length=100)
    display_name: str = Field(min_length=3, max_length=120)
    required_slots: tuple[str, ...] = Field(default=(), max_length=16)
    operation_selection_group: str | None = Field(default=None, max_length=64)


class SemanticResolverFailure(str, Enum):
    PROVIDER_ERROR = "provider_error"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    JSON_WIRE_ERROR = "json/wire_error"
    SCHEMA_ERROR = "schema_error"
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
            structured_output_schema=SemanticInterpretationProposal.model_json_schema(),
            generation_temperature=0,
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
        except json.JSONDecodeError:
            return self._failed(SemanticResolverFailure.JSON_WIRE_ERROR, started)
        except (ValidationError, ValueError, TypeError):
            return self._failed(SemanticResolverFailure.SCHEMA_ERROR, started)
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
            structured_output_schema=SemanticFollowUpProposal.model_json_schema(),
            generation_temperature=0,
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
        except json.JSONDecodeError:
            return self._failed_follow_up(
                SemanticResolverFailure.JSON_WIRE_ERROR, started,
            )
        except (ValidationError, ValueError, TypeError):
            return self._failed_follow_up(
                SemanticResolverFailure.SCHEMA_ERROR, started,
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
            "переданного списка и только смысл текущей реплики. Не выдумывай значения "
            "и не вычисляй даты, время или длительность. Для каждого slot верни "
            "evidence_text — точный фрагмент текущей реплики. Для неоднозначного "
            "действия верни все правдоподобные операции. kind обязан быть ровно "
            "одним из ordinary, supported_action, unsupported_action. "
            "ordinary — человек не просит выполнить действие. supported_action — "
            "в каталоге есть хотя бы одна операция, подходящая по смыслу просьбы; "
            "тогда верни candidate_operation_ids и grounded slot evidence. "
            "unsupported_action — явное действие, для которого в каталоге нет ни "
            "одной подходящей операции; не выбирай его, если подходящая операция "
            "в каталоге существует. nearby_operation_ids допустимы только для "
            "unsupported_action. "
            "operation_selection_evidence добавляй только когда точный фрагмент "
            "реплики явно выбирает конкретное место или тип действия; общая просьба "
            "запланировать не является таким выбором. Для personal_scheduling "
            "явное указание календаря выбирает google_calendar.event.create, а "
            "явная просьба именно напомнить выбирает home.timed_commitments; скопируй "
            "реальные слова человека как evidence_text. Если явного выбора нет, "
            "верни operation_selection_evidence=null, даже если предлагаешь один candidate. "
            "unresolved_referents содержит только реально присутствующее указание "
            "на неизвестный объект (например «это»), а не отсутствующий slot. "
            "Короткие примеры только для selection semantics: явное «напомни» -> "
            '{"operation_id":"home.timed_commitments","evidence_text":"напомни"}; '
            "явное «в календарь» -> "
            '{"operation_id":"google_calendar.event.create","evidence_text":"в календарь"}; '
            "общее «запланируй занятие» -> null. Не ставь confidence. "
            "Верни только JSON, соответствующий response schema. "
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
            "Если выбираешь operation, скопируй в operation_selection_evidence "
            "точный фрагмент текущей реплики, который делает этот выбор явным. "
            "Новый самостоятельный вопрос, рассказ или новая задача — not_a_follow_up. "
            "Для slot evidence_text копируй только выражение, реально присутствующее в текущей "
            "реплике; не вычисляй календарную дату, время или длительность самостоятельно. mode: add для нового "
            "slot, enrich для более точного старого значения, correct для явной замены, "
            "confirm для подтверждения прежнего. Используй только operation_id из "
            "pending context. Верни строго JSON без Markdown по response schema. "
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
        date_resolver: HomeCalendarDateResolver | None = None,
    ):
        self.catalog = catalog
        self.specifications = specifications
        self.allowed_operation_ids = allowed_operation_ids
        self.date_resolver = date_resolver

    def bind_date_resolver(self, date_resolver: HomeCalendarDateResolver) -> None:
        self.date_resolver = date_resolver

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
                operation_selection_group=specification.operation_selection_group,
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
        try:
            proposal.validate_home_shape()
        except ValueError as error:
            raise SemanticValidationError(str(error)) from error
        if proposal.kind is SemanticProposalKind.ORDINARY:
            return InterpretationFrame(
                original_utterance=original,
                resolution_state=InterpretationResolutionState.ORDINARY_CONVERSATION,
            )
        if proposal.kind is SemanticProposalKind.UNSUPPORTED_ACTION:
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
        selection = self._validated_operation_selection(original, proposal)
        specifications = self._preserve_selection_group_ambiguity(
            specifications,
            selected_operation_id=selection,
        )
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

    def _validated_operation_selection(
        self,
        utterance: str,
        proposal: SupportedActionProposal,
    ) -> str | None:
        if proposal.operation_selection_evidence is None:
            return None
        evidence = proposal.operation_selection_evidence
        if evidence.operation_id not in self.allowed_operation_ids:
            raise SemanticValidationError("unsupported_operation_selection")
        if not self._evidence_is_grounded(utterance, evidence.evidence_text):
            raise SemanticValidationError("invented_operation_selection_evidence")
        return evidence.operation_id

    def _preserve_selection_group_ambiguity(
        self,
        proposed_specifications: list,
        *,
        selected_operation_id: str | None,
    ) -> list:
        if selected_operation_id is not None:
            return [
                item for item in proposed_specifications
                if item.operation_id == selected_operation_id
            ]
        by_id = {item.operation_id: item for item in proposed_specifications}
        groups = {
            item.operation_selection_group
            for item in proposed_specifications
            if item.operation_selection_group is not None
        }
        for operation_id in sorted(self.allowed_operation_ids):
            specification = self.specifications.get(operation_id)
            if specification.operation_selection_group in groups:
                by_id.setdefault(operation_id, specification)
        return [by_id[operation_id] for operation_id in sorted(by_id)]

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
        if (
            proposal.operation_selection_evidence is not None
            and not self._evidence_is_grounded(
                utterance,
                proposal.operation_selection_evidence,
            )
        ):
            raise SemanticValidationError(
                "follow_up_operation_selection_not_grounded"
            )
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
        value = proposal.evidence_text.strip()
        normalized = normalize_utterance(utterance)
        if not SemanticProposalValidator._evidence_is_grounded(utterance, value):
            raise SemanticValidationError(
                "follow_up_subject_not_grounded"
                if proposal.name == "subject"
                else "follow_up_value_not_grounded"
            )
        if proposal.name == "date":
            resolved = date_resolver.resolve(value)
            if resolved is None:
                raise SemanticValidationError("follow_up_date_invalid")
            return InterpretationSlot(
                name="date",
                value=resolved.canonical,
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            )
        if proposal.name == "time":
            proposed_times = _utterance_times(value.casefold().replace("ё", "е"))
            grounded_times = _utterance_times(
                utterance.casefold().replace("ё", "е")
            )
            matches = proposed_times & grounded_times
            if len(matches) != 1:
                raise SemanticValidationError("follow_up_time_not_grounded")
            return InterpretationSlot(
                name="time",
                value=next(iter(matches)),
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            )
        if proposal.name == "duration_minutes":
            resolved = HomeDurationResolver().resolve(value)
            if resolved is None:
                raise SemanticValidationError("follow_up_duration_invalid")
            if resolved.minutes is None:
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

    def _validated_slot(
        self,
        utterance: str,
        proposal: SemanticSlotEvidenceProposal,
    ) -> InterpretationSlot:
        value = proposal.evidence_text.strip()
        normalized = normalize_utterance(utterance)
        if not self._evidence_is_grounded(utterance, value):
            raise SemanticValidationError(
                "invented_subject"
                if proposal.name == "subject"
                else "slot_evidence_not_grounded"
            )
        if proposal.name == "date":
            if self.date_resolver is None:
                raise SemanticValidationError("date_normalization_unavailable")
            resolved = self.date_resolver.resolve(value)
            if resolved is None:
                raise SemanticValidationError("date_normalization_error")
            return InterpretationSlot(
                name="date",
                value=resolved.canonical,
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            )
        elif proposal.name == "time":
            proposed_times = _utterance_times(value.casefold().replace("ё", "е"))
            if len(proposed_times) != 1:
                raise SemanticValidationError("time_normalization_error")
            return InterpretationSlot(
                name="time",
                value=next(iter(proposed_times)),
                origin=InterpretationValueOrigin.TEMPORAL_NORMALIZED,
            )
        elif proposal.name == "duration_minutes":
            resolved = HomeDurationResolver().resolve(value)
            if resolved is None or resolved.minutes is None:
                raise SemanticValidationError("duration_normalization_error")
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
        return InterpretationSlot(
            name=proposal.name,
            value=value,
            origin=InterpretationValueOrigin.SEMANTIC,
        )

    @staticmethod
    def _evidence_is_grounded(utterance: str, evidence_text: str) -> bool:
        evidence = normalize_utterance(evidence_text)
        source = normalize_utterance(utterance)
        return bool(evidence and evidence in source)

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
