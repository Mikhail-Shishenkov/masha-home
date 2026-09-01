import json

import pytest

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.interpretation_v2 import (
    CapabilityCandidateDiscovery,
    InterpretationResolutionState,
)
from backend.conversation.clarification import DeterministicClarificationBuilder
from backend.conversation.resolution_coordinator import V2LiveAdoptionPolicy
from backend.conversation.semantic_resolver import (
    ActionRequestEvidence,
    HybridCapabilityCandidateDiscovery,
    LocalSemanticResolver,
    OperationSelectionEvidence,
    OrdinaryProposal,
    SemanticFollowUpProposal,
    SemanticAmbiguityHint,
    SupportedActionProposal,
    UnsupportedActionProposal,
    SemanticProposalValidator,
    SemanticResolverFailure,
    SemanticResolverResult,
    SemanticPendingContext,
    SemanticSlotProposal,
    SemanticValidationError,
    parse_semantic_interpretation,
    semantic_interpretation_json_schema,
)
from backend.conversation.file_read_semantics import normalize_file_read_mode
from backend.conversation.turn_context import (
    TurnContextEnvelope,
    TurnPresentedEntityHint,
    TurnTemporalContext,
)
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_models import ModelCapabilities
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_roles import ModelRole, ModelRoleProfileStore
from backend.llm.model_router import ModelRouter
from backend.temporal.date_resolution import HomeCalendarDateResolver
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from datetime import datetime, timezone


def _boundaries(tmp_path, *, provider=None):
    catalog = default_home_capability_catalog()
    deterministic = CapabilityCandidateDiscovery(catalog=catalog)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=deterministic.specifications,
        known_operation_ids=frozenset(deterministic.specifications.operation_ids),
        date_resolver=HomeCalendarDateResolver(TemporalEngine(clock=FixedClock(
            datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)
        ))),
    )
    profiles = ModelProfileStore(tmp_path / "model-profiles.json")
    roles = ModelRoleProfileStore(tmp_path / "model-roles.json", profiles=profiles)
    provider = provider or FakeProvider(
        provider_id="ollama-local",
        capabilities=ModelCapabilities(structured_output=True),
    )
    resolver = LocalSemanticResolver(
        router=ModelRouter([provider]),
        role_profiles=roles,
    )
    hybrid = HybridCapabilityCandidateDiscovery(
        deterministic=deterministic,
        resolver=resolver,
        validator=validator,
    )
    return provider, resolver, validator, hybrid, roles


def _schedule_proposal(
    *, candidates=None, subject="занятие", time="11",
    selection_evidence=None, action_evidence="Запиши",
):
    return {
        "kind": "supported_action",
        "candidate_operation_ids": candidates or [
            "google_calendar.event.create",
            "home.timed_commitments",
        ],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": subject},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": time},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "capability" if len(candidates or (1, 2)) > 1 else "none",
        "action_request_evidence": {"evidence_text": action_evidence},
        "operation_selection_evidence": selection_evidence or {
            "operation_id": None,
            "evidence_text": None,
        },
    }


def _presented_mail_context() -> TurnContextEnvelope:
    temporal = TemporalEngine(clock=FixedClock(
        datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc),
    )).context(None, user_message="Прочитай его")
    return TurnContextEnvelope(
        temporal=TurnTemporalContext.from_temporal_context(temporal),
        presented_entities=(TurnPresentedEntityHint(
            reference="P1",
            position=1,
            owner_operation_id="yandex_mail.read",
            kind="письмо",
            human_label="Письмо от Анны о занятии",
            time_text="сегодня в 10:00",
        ),),
    )


def test_local_resolver_uses_configured_role_and_strict_structured_request(tmp_path):
    provider, resolver, validator, _, roles = _boundaries(tmp_path)
    provider.response_text = json.dumps(_schedule_proposal(), ensure_ascii=False)

    result = resolver.resolve(
        "Доброе утро, Маша! Запиши занятие завтра в 11",
        validator.vocabulary(),
    )

    assert result.proposal is not None and result.failure is None
    assert provider.last_request.required_capabilities.structured_output is True
    assert provider.last_request.required_capabilities.tools is False
    assert provider.last_request.private_context == {}
    assert provider.last_request.execution_model_id == roles.profile_for(ModelRole.SEMANTIC_RESOLVER).model_id
    assert provider.last_request.timeout_seconds == 15.0
    assert provider.last_request.identity_context.persona_id == "semantic-resolver"
    assert "qwen3.5" not in provider.last_request.messages[0].content
    assert "supported_action" in provider.last_request.messages[0].content
    assert "Registry-derived operation-selection rules" in provider.last_request.messages[0].content
    assert "selection_evidence_examples" in provider.last_request.messages[0].content
    assert "operation_kind" in provider.last_request.messages[0].content
    assert "сами по себе никогда не доказывают create" in provider.last_request.messages[0].content
    assert "никогда не возвращай null для supported_action" in provider.last_request.messages[0].content
    assert "Bounded Home turn context" not in provider.last_request.messages[0].content
    assert provider.last_request.structured_output_schema is not None
    assert provider.last_request.generation_temperature == 0
    schema = provider.last_request.structured_output_schema
    assert schema == semantic_interpretation_json_schema()
    assert schema["type"] == "object"
    assert "anyOf" not in schema
    kind_shapes = schema["allOf"][0]["oneOf"]
    assert {
        shape["properties"]["kind"]["const"] for shape in kind_shapes
    } == {"ordinary", "supported_action", "unsupported_action"}
    supported_shape = next(
        shape for shape in kind_shapes
        if shape["properties"]["kind"]["const"] == "supported_action"
    )
    unsupported_shape = next(
        shape for shape in kind_shapes
        if shape["properties"]["kind"]["const"] == "unsupported_action"
    )
    assert supported_shape["properties"]["candidate_operation_ids"]["minItems"] == 1
    assert unsupported_shape["properties"]["candidate_operation_ids"]["maxItems"] == 0
    assert set(schema["required"]) >= {
        "kind",
        "candidate_operation_ids",
        "nearby_operation_ids",
        "extracted_slots",
        "unresolved_referents",
        "ambiguity_hint",
        "action_request_evidence",
        "operation_selection_evidence",
    }
    selection_schema = schema["$defs"]["OperationSelectionEvidence"]
    assert set(selection_schema["required"]) == {
        "operation_id", "evidence_text",
    }
    assert schema["properties"]["operation_selection_evidence"]["$ref"] == (
        "#/$defs/OperationSelectionEvidence"
    )
    action_schema = schema["$defs"]["ActionRequestEvidence"]
    assert set(action_schema["required"]) == {"evidence_text"}
    assert schema["properties"]["action_request_evidence"]["$ref"] == (
        "#/$defs/ActionRequestEvidence"
    )
    assert roles.profile_for(ModelRole.SEMANTIC_RESOLVER).profile_id == "fast"


@pytest.mark.parametrize(("evidence", "expected"), (
    ("пожалуйста, прочитай", "read"),
    ("покажи что-нибудь самое свежее", "recent"),
    ("можешь поискать", "search"),
    ("дай посмотреть, что есть", "list"),
))
def test_file_read_mode_normalizes_action_evidence_not_whole_phrases(
    evidence, expected,
):
    assert normalize_file_read_mode(evidence) == expected


def test_file_read_mode_is_materialized_from_grounded_turn_when_model_omits_slot(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_disk.read"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "slot",
        "action_request_evidence": {"evidence_text": "что у меня есть"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate("Что у меня есть на Яндекс Диске?", proposal)

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert {item.name: item.value for item in frame.slots} == {"mode": "list"}


@pytest.mark.parametrize(("operation_id", "slot_name"), (
    ("home.memory.remember", "memory_content"),
    ("home.memory.forget", "target"),
    ("home.continuity.open", "topic"),
    ("home.commitments.create", "subject"),
))
def test_pure_deictic_pointer_never_becomes_a_durable_slot(
    tmp_path, operation_id, slot_name,
):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": [operation_id],
        "nearby_operation_ids": [],
        "extracted_slots": [{"name": slot_name, "evidence_text": "эту тему"}],
        "unresolved_referents": ["эту тему"],
        "ambiguity_hint": "referent",
        "action_request_evidence": {"evidence_text": "Сделай"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate("Сделай эту тему", proposal)

    assert slot_name in frame.missing_slots
    assert all(item.name != slot_name for item in frame.slots)
    assert frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED
    assert any(
        item.name == slot_name
        and not item.accepted
        and item.reason == "unresolved_deictic_slot_value"
        for item in validator.last_trace.slots
    )


def test_one_presented_entity_can_ground_a_deictic_target_in_same_family(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.delete"],
        "nearby_operation_ids": [],
        "extracted_slots": [{"name": "target", "evidence_text": "это письмо"}],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Удали"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate(
        "Удали это письмо",
        proposal,
        turn_context=_presented_mail_context(),
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert [(item.name, item.value) for item in frame.slots] == [
        ("target", "это письмо")
    ]
    assert validator.last_trace.slots[0].accepted is True


def test_home_materializes_omitted_deictic_target_only_from_one_presented_family(
    tmp_path,
):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.move"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Убери"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate(
        "Убери это письмо в архив",
        proposal,
        turn_context=_presented_mail_context(),
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert [(item.name, item.value) for item in frame.slots] == [("target", "это")]
    assert validator.last_trace.slots[-1].reason == "single_presented_entity_grounded"


def test_presented_deictic_target_stays_unresolved_when_context_is_ambiguous(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.delete"],
        "nearby_operation_ids": [],
        "extracted_slots": [{"name": "target", "evidence_text": "это письмо"}],
        "unresolved_referents": [],
        "ambiguity_hint": "referent",
        "action_request_evidence": {"evidence_text": "Удали"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })
    context = _presented_mail_context()
    context = context.model_copy(update={
        "presented_entities": (
            *context.presented_entities,
            context.presented_entities[0].model_copy(update={
                "reference": "P2",
                "position": 2,
                "human_label": "Письмо от Бориса о встрече",
            }),
        ),
    })

    frame = validator.validate(
        "Удали это письмо",
        proposal,
        turn_context=context,
    )

    assert frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED
    assert "target" in frame.missing_slots
    assert validator.last_trace.slots[0].reason == "unresolved_deictic_slot_value"


def test_memory_content_normalizer_removes_only_grounded_complementizer(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation({
        "kind": "supported_action",
        "candidate_operation_ids": ["home.memory.remember"],
        "nearby_operation_ids": [],
        "extracted_slots": [{
            "name": "memory_content", "evidence_text": "что я люблю зелёный чай",
        }],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Запомни"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })

    frame = validator.validate("Запомни, что я люблю зелёный чай", proposal)

    assert {item.name: item.value for item in frame.slots} == {
        "memory_content": "я люблю зелёный чай",
    }


def test_bounded_turn_context_reaches_local_resolver_without_authority_handles(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.read"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Прочитай"},
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(
        "Прочитай его",
        turn_context=_presented_mail_context(),
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert [item.operation_id for item in frame.candidates] == ["yandex_mail.read"]
    system = provider.last_request.messages[0].content
    assert "Bounded Home turn context" in system
    assert '\"reference\":\"P1\"' in system
    assert "Письмо от Анны о занятии" in system
    assert "yandex_mail.read" in system
    assert "provider_id" not in system
    assert "conversation_id" not in system
    assert "Только текущая реплика" in system


def test_turn_context_cannot_invent_an_action_absent_from_current_utterance(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.read"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Прочитай"},
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(
        "Это письмо интересное",
        turn_context=_presented_mail_context(),
    )

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert frame.candidates == ()
    assert hybrid.last_rejection == "invented_action_request_evidence"


def test_follow_up_resolver_receives_only_bounded_pending_context(tmp_path):
    provider, resolver, validator, _, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "relation": "follow_up",
        "selected_operation_id": "google_calendar.event.create",
        "operation_selection_evidence": "в календарь",
        "slot_updates": [],
    })
    frame = CapabilityCandidateDiscovery(
        catalog=default_home_capability_catalog(),
    ).interpret("Запиши занятие завтра в 11")
    _, pending = DeterministicClarificationBuilder(
        catalog=default_home_capability_catalog(),
    ).build(frame, conversation_id="bounded-conversation")

    result = resolver.resolve_follow_up(
        "Давай в календарь",
        validator.vocabulary(),
        SemanticPendingContext.from_pending(pending),
    )

    assert result.proposal.selected_operation_id == "google_calendar.event.create"
    request = provider.last_request
    assert request.required_capabilities.structured_output is True
    assert request.required_capabilities.tools is False
    assert request.private_context == {}
    assert [message.content for message in request.messages[1:]] == [
        "Давай в календарь",
    ]
    system = request.messages[0].content
    assert pending.interpretation.original_utterance in system
    assert "known_slots" in system and "missing_slots" in system
    assert "Memory" not in system
    assert "credential" not in system.casefold()


def test_follow_up_timeout_is_controlled_and_cannot_patch_pending_state(tmp_path):
    provider, resolver, validator, _, _ = _boundaries(tmp_path)
    provider.simulate_timeout = True
    frame = CapabilityCandidateDiscovery(
        catalog=default_home_capability_catalog(),
    ).interpret("Запиши занятие завтра в 11")
    _, pending = DeterministicClarificationBuilder(
        catalog=default_home_capability_catalog(),
    ).build(frame, conversation_id="timeout-conversation")

    result = resolver.resolve_follow_up(
        "Лучше в Дом",
        validator.vocabulary(),
        SemanticPendingContext.from_pending(pending),
    )

    assert result.proposal is None
    assert result.failure is SemanticResolverFailure.TIMEOUT
    assert {item.name: item.value for item in pending.interpretation.slots} == {
        "date": "завтра",
        "time": "11:00",
        "subject": "занятие",
    }


def test_follow_up_operation_selection_evidence_must_be_grounded(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    frame = CapabilityCandidateDiscovery(
        catalog=default_home_capability_catalog(),
    ).interpret("Запиши занятие завтра в 11")
    _, pending = DeterministicClarificationBuilder(
        catalog=default_home_capability_catalog(),
    ).build(frame, conversation_id="selection-grounding")
    proposal = SemanticFollowUpProposal.model_validate({
        "relation": "follow_up",
        "selected_operation_id": "google_calendar.event.create",
        "operation_selection_evidence": "в календарь",
        "slot_updates": [],
        "referent_updates": [],
    })

    validated = validator.validate_follow_up(
        pending,
        "давай туда",
        proposal,
        date_resolver=validator.date_resolver,
    )

    assert validated.selected_operation_id is None
    assert validator.last_follow_up_trace.operation_selection.reason == (
        "follow_up_operation_selection_not_grounded"
    )


def test_word_time_is_validated_against_current_utterance(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation(
        _schedule_proposal(
            candidates=["home.timed_commitments"],
            time="одиннадцать",
            action_evidence="надо не забыть",
            selection_evidence={
                "operation_id": "home.timed_commitments",
                "evidence_text": "надо не забыть",
            },
        )
    )

    frame = validator.validate(
        "Маш, у меня завтра в одиннадцать занятие, надо не забыть",
        proposal,
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert frame.slots[-1].value == "11:00"


def test_validator_rejects_an_unknown_operation_but_keeps_no_partial_authority(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation(
        _schedule_proposal(candidates=["future.unknown"])
    )

    with pytest.raises(SemanticValidationError, match="unknown_operation"):
        validator.validate("Запиши занятие завтра в 11", proposal)


def test_model_cannot_invent_subject_or_resolved_referent(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    invented_subject = parse_semantic_interpretation(
        _schedule_proposal(
            candidates=["home.timed_commitments"], subject="стоматолог"
        )
    )
    invented_referent = SupportedActionProposal(
        kind="supported_action",
        candidate_operation_ids=("home.timed_commitments",),
        nearby_operation_ids=(),
        extracted_slots=(
            SemanticSlotProposal(name="subject", evidence_text="занятие"),
            SemanticSlotProposal(name="date", evidence_text="завтра"),
            SemanticSlotProposal(name="time", evidence_text="11"),
        ),
        unresolved_referents=("это",),
        ambiguity_hint=SemanticAmbiguityHint.REFERENT,
        action_request_evidence=ActionRequestEvidence(
            evidence_text="Напомни",
        ),
        operation_selection_evidence=OperationSelectionEvidence(
            operation_id=None,
            evidence_text=None,
        ),
    )

    subject_frame = validator.validate(
        "Запиши: у меня завтра в 11 занятие", invented_subject,
    )
    referent_frame = validator.validate(
        "Напомни: у меня завтра в 11 занятие", invented_referent,
    )

    assert "subject" in subject_frame.missing_slots
    assert all(item.name != "subject" for item in subject_frame.slots)
    assert referent_frame.referents == ()
    assert any(not item.accepted for item in validator.last_trace.referents)


def test_subject_provenance_rejects_supported_noun_with_invented_detail(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = parse_semantic_interpretation(
        _schedule_proposal(
            candidates=["home.timed_commitments"],
            subject="занятие с выдуманным преподавателем",
            action_evidence="Напомни",
        )
    )

    frame = validator.validate("Напомни: у меня завтра в 11 занятие", proposal)

    assert "subject" in frame.missing_slots
    assert any(
        item.name == "subject" and not item.accepted
        for item in validator.last_trace.slots
    )


@pytest.mark.parametrize(
    "response_text,simulate_timeout,failure",
    (
        ("not-json", False, SemanticResolverFailure.JSON_WIRE_ERROR),
        ("{}", False, SemanticResolverFailure.SCHEMA_ERROR),
        ("{}", True, SemanticResolverFailure.TIMEOUT),
    ),
)
def test_malformed_and_timeout_fail_to_deterministic_ordinary_path(
    tmp_path, response_text, simulate_timeout, failure
):
    provider = FakeProvider(
        provider_id="ollama-local",
        capabilities=ModelCapabilities(structured_output=True),
        response_text=response_text,
        simulate_timeout=simulate_timeout,
    )
    _, _, _, hybrid, _ = _boundaries(tmp_path, provider=provider)

    frame = hybrid.interpret("Доброе утро, Маша")

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert hybrid.last_result.failure is failure


def test_one_bounded_schema_repair_preserves_grounding_and_context(tmp_path):
    invalid = json.dumps({
        "kind": "unsupported_action",
        "candidate_operation_ids": ["yandex_mail.message.delete"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": None},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    })
    valid = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["yandex_mail.message.delete"],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Удали"},
        "operation_selection_evidence": {
            "operation_id": None, "evidence_text": None,
        },
    }, ensure_ascii=False)

    class SequencedProvider(FakeProvider):
        def __init__(self):
            super().__init__(
                provider_id="ollama-local",
                capabilities=ModelCapabilities(structured_output=True),
            )
            self.responses = iter((invalid, valid))

        def generate(self, request):
            self.response_text = next(self.responses)
            return super().generate(request)

    provider = SequencedProvider()
    _, _, _, hybrid, _ = _boundaries(tmp_path, provider=provider)

    frame = hybrid.interpret(
        "Удали это письмо",
        turn_context=_presented_mail_context(),
    )

    assert [item.operation_id for item in frame.candidates] == [
        "yandex_mail.message.delete"
    ]
    assert [(item.name, item.value) for item in frame.slots] == [("target", "это")]
    assert len(provider.requests) == 2
    assert provider.requests[1].timeout_seconds <= provider.requests[0].timeout_seconds
    assert "Schema repair" in provider.requests[1].messages[0].content


def test_semantic_ordinary_conversation_remains_ordinary(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "ordinary",
        "candidate_operation_ids": [],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": None},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
    })

    frame = hybrid.interpret("Как ты сегодня?")

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION


def test_clear_update_language_corrects_calendar_create_to_update_kind(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["google_calendar.event.create"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": "созвон с мамой"},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": "14"},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": "Перенеси"},
        "operation_selection_evidence": {
            "operation_id": "google_calendar.event.create",
            "evidence_text": "календаре",
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(
        "Перенеси в гугл календаре созвон с мамой завтра на 14:00"
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert [item.operation_id for item in frame.candidates] == [
        "google_calendar.event.update"
    ]
    assert hybrid.last_rejection is None


@pytest.mark.parametrize(("utterance", "subject"), (
    ("Перенеси созвон с мамой завтра с 14 на 13", "созвон с мамой"),
    ("Перенеси завтра созвон с мамой с 14 на 13", "созвон с мамой"),
    ("Маш, перенеси завтра созвониться с мамой с 14 на 13 часов", "созвониться с мамой"),
    ("Завтра созвон с мамой перенеси с 14 на 13", "созвон с мамой"),
    ("Созвон с мамой завтра сдвинь на 13", "созвон с мамой"),
))
def test_explicit_update_meaning_cannot_degrade_to_timed_commitment(
    tmp_path, utterance, subject,
):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "supported_action",
        "candidate_operation_ids": ["home.timed_commitments"],
        "nearby_operation_ids": [],
        "extracted_slots": [
            {"name": "subject", "evidence_text": subject},
            {"name": "date", "evidence_text": "завтра"},
            {"name": "time", "evidence_text": "13"},
            *(
                [{"name": "old_time", "evidence_text": "14"}]
                if "14" in utterance else []
            ),
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {
            "evidence_text": (
                "перенеси" if "перенеси" in utterance.casefold() else "сдвинь"
            ),
        },
        "operation_selection_evidence": {
            "operation_id": "home.timed_commitments",
            "evidence_text": "перенеси" if "перенеси" in utterance.casefold() else "сдвинь",
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(utterance)

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert [item.operation_id for item in frame.candidates] == [
        "google_calendar.event.update"
    ]
    assert "home.timed_commitments" not in {
        item.operation_id for item in frame.candidates
    }
    assert "google_calendar.event.create" not in {
        item.operation_id for item in frame.candidates
    }


@pytest.mark.parametrize("utterance", (
    "Электронная почта сильно изменила общение",
    "Интернет изменил людей",
))
def test_factual_update_shaped_words_are_not_action_authority(tmp_path, utterance):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "ordinary",
        "candidate_operation_ids": [],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": None},
        "operation_selection_evidence": {
            "operation_id": None,
            "evidence_text": None,
        },
    }, ensure_ascii=False)

    frame = hybrid.interpret(utterance)

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert frame.candidates == ()
    assert hybrid.last_rejection is None


def test_vocabulary_describes_slots_and_home_defaults_without_authorization(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    calendar = next(
        item for item in validator.vocabulary()
        if item.operation_id == "google_calendar.event.create"
    )

    duration = next(item for item in calendar.slots if item.name == "duration_minutes")

    assert calendar.purpose
    assert calendar.operation_kind == "create"
    assert calendar.selection_evidence_meaning
    assert "в календарь" in calendar.selection_evidence_examples
    assert duration.required is False
    assert duration.default_value == "60"


def test_semantic_explicit_unsupported_action_stays_distinct_from_conversation(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = UnsupportedActionProposal(
        kind="unsupported_action",
        candidate_operation_ids=(),
        nearby_operation_ids=(
            "google_calendar.event.create",
            "home.timed_commitments",
        ),
        extracted_slots=(),
        unresolved_referents=(),
        ambiguity_hint="none",
        action_request_evidence=ActionRequestEvidence(evidence_text="Запиши"),
        operation_selection_evidence=OperationSelectionEvidence(
            operation_id=None,
            evidence_text=None,
        ),
    )

    frame = validator.validate(
        "Запиши меня на внешнее занятие завтра в 9",
        proposal,
    )

    assert frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION
    assert frame.candidates == ()
    assert frame.slots == ()


def test_untrusted_semantics_cannot_erase_explicit_calendar_destination(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "kind": "ordinary",
        "candidate_operation_ids": [],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
        "action_request_evidence": {"evidence_text": None},
        "operation_selection_evidence": {"operation_id": None, "evidence_text": None},
    })

    frame = hybrid.interpret(
        "Поставь встречу в календарь завтра в 19 на час"
    )

    assert [item.operation_id for item in frame.candidates] == [
        "google_calendar.event.create"
    ]
    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert hybrid.last_rejection == "semantic_conflicts_with_structural_owner"


def test_docs_content_stays_structural_but_external_information_reaches_semantics(tmp_path):
    class ExplodingResolver:
        def resolve(self, *_args, **_kwargs):
            raise AssertionError("protected deterministic ownership")

    catalog = default_home_capability_catalog()
    deterministic = CapabilityCandidateDiscovery(catalog=catalog)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=deterministic.specifications,
        known_operation_ids=frozenset(deterministic.specifications.operation_ids),
    )
    hybrid = HybridCapabilityCandidateDiscovery(
        deterministic=deterministic,
        resolver=ExplodingResolver(),
        validator=validator,
    )

    docs = hybrid.interpret(
        "Создай документ на Гугл Диске: Сегодня мы продолжили делать наш Дом"
    )
    assert [item.operation_id for item in docs.candidates] == [
        "google_drive.document.create"
    ]

    class OrdinaryResolver:
        calls = 0
        def resolve(self, *_args, **_kwargs):
            self.calls += 1
            return SemanticResolverResult(
                proposal=parse_semantic_interpretation({
                    "kind": "ordinary",
                    "candidate_operation_ids": [],
                    "nearby_operation_ids": [],
                    "extracted_slots": [],
                    "unresolved_referents": [],
                    "ambiguity_hint": "none",
                    "action_request_evidence": {"evidence_text": None},
                    "operation_selection_evidence": {
                        "operation_id": None, "evidence_text": None,
                    },
                }),
                latency_ms=1,
            )

    resolver = OrdinaryResolver()
    hybrid.resolver = resolver
    web = hybrid.interpret("Поищи в интернете последнюю версию Ollama")

    assert resolver.calls == 1
    assert web.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION


def test_model_role_can_switch_profile_without_router_code_change(tmp_path):
    _, _, _, _, roles = _boundaries(tmp_path)

    selected = roles.assign(ModelRole.SEMANTIC_RESOLVER, "fast")

    assert selected.model_id == roles.profiles.get_profile("fast").model_id
    restarted = ModelRoleProfileStore(roles.path, profiles=roles.profiles)
    assert restarted.profile_for(ModelRole.SEMANTIC_RESOLVER).profile_id == "fast"
