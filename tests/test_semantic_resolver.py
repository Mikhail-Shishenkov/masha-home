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
    HybridCapabilityCandidateDiscovery,
    LocalSemanticResolver,
    SemanticAmbiguityHint,
    SemanticInterpretationProposal,
    SemanticProposalValidator,
    SemanticResolverFailure,
    SemanticResolverResult,
    SemanticPendingContext,
    SemanticSlotProposal,
    SemanticValidationError,
)
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_models import ModelCapabilities
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_roles import ModelRole, ModelRoleProfileStore
from backend.llm.model_router import ModelRouter


def _boundaries(tmp_path, *, provider=None):
    catalog = default_home_capability_catalog()
    deterministic = CapabilityCandidateDiscovery(catalog=catalog)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=deterministic.specifications,
        allowed_operation_ids=adoption.supported_operation_ids,
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


def _schedule_proposal(*, candidates=None, subject="занятие", time="11:00"):
    return {
        "ordinary_conversation": False,
        "candidate_operation_ids": candidates or [
            "google_calendar.event.create",
            "home.timed_commitments",
        ],
        "extracted_slots": [
            {"name": "subject", "value": subject},
            {"name": "date", "value": "завтра"},
            {"name": "time", "value": time},
        ],
        "unresolved_referents": [],
        "ambiguity_hint": "capability" if len(candidates or (1, 2)) > 1 else "none",
    }


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
    assert provider.last_request.execution_model_id == "qwen3.5:9b"
    assert provider.last_request.identity_context.persona_id == "semantic-resolver"
    assert "qwen3.5" not in provider.last_request.messages[0].content
    assert '"unsupported_action":bool' in provider.last_request.messages[0].content
    assert roles.profile_for(ModelRole.SEMANTIC_RESOLVER).profile_id == "primary"


def test_follow_up_resolver_receives_only_bounded_pending_context(tmp_path):
    provider, resolver, validator, _, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "relation": "follow_up",
        "selected_operation_id": "google_calendar.event.create",
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


def test_hybrid_understands_wrapped_schedule_and_home_derives_ambiguity(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps(_schedule_proposal(), ensure_ascii=False)

    frame = hybrid.interpret(
        "Доброе утро, Маша! Запиши занятие завтра в 11"
    )

    assert frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED
    assert [item.operation_id for item in frame.candidates] == [
        "google_calendar.event.create",
        "home.timed_commitments",
    ]
    assert {item.name: item.value for item in frame.slots} == {
        "subject": "занятие",
        "date": "завтра",
        "time": "11:00",
    }


def test_word_time_is_validated_against_current_utterance(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = SemanticInterpretationProposal.model_validate(
        _schedule_proposal(candidates=["home.timed_commitments"])
    )

    frame = validator.validate(
        "Маш, у меня завтра в одиннадцать занятие, надо не забыть",
        proposal,
    )

    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert frame.slots[-1].value == "11:00"


@pytest.mark.parametrize(
    "payload,error",
    (
        (
            _schedule_proposal(candidates=["future.unknown"]),
            "unknown_operation",
        ),
        (
            _schedule_proposal(candidates=["google_drive.document.create"]),
            "unsupported_operation",
        ),
        (
            {
                **_schedule_proposal(candidates=["home.timed_commitments"]),
                "extracted_slots": [{"name": "provider_id", "value": "secret"}],
                "ambiguity_hint": "slot",
            },
            "unknown_slot",
        ),
    ),
)
def test_validator_rejects_unknown_unsupported_and_unknown_slot(tmp_path, payload, error):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = SemanticInterpretationProposal.model_validate(payload)

    with pytest.raises(SemanticValidationError, match=error):
        validator.validate("Запиши занятие завтра в 11", proposal)


def test_model_cannot_invent_subject_or_resolved_referent(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    invented_subject = SemanticInterpretationProposal.model_validate(
        _schedule_proposal(
            candidates=["home.timed_commitments"], subject="стоматолог"
        )
    )
    invented_referent = SemanticInterpretationProposal(
        ordinary_conversation=False,
        candidate_operation_ids=("home.timed_commitments",),
        extracted_slots=(
            SemanticSlotProposal(name="subject", value="занятие"),
            SemanticSlotProposal(name="date", value="завтра"),
            SemanticSlotProposal(name="time", value="11:00"),
        ),
        unresolved_referents=("это",),
        ambiguity_hint=SemanticAmbiguityHint.REFERENT,
    )

    with pytest.raises(SemanticValidationError, match="invented_subject"):
        validator.validate("У меня завтра в 11 занятие", invented_subject)
    with pytest.raises(SemanticValidationError, match="invented_referent"):
        validator.validate("У меня завтра в 11 занятие", invented_referent)


def test_subject_provenance_rejects_supported_noun_with_invented_detail(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = SemanticInterpretationProposal.model_validate(
        _schedule_proposal(
            candidates=["home.timed_commitments"],
            subject="занятие с выдуманным преподавателем",
        )
    )

    with pytest.raises(SemanticValidationError, match="invented_subject"):
        validator.validate("У меня завтра в 11 занятие", proposal)


@pytest.mark.parametrize(
    "response_text,simulate_timeout,failure",
    (
        ("not-json", False, SemanticResolverFailure.MALFORMED_OUTPUT),
        ("{}", False, SemanticResolverFailure.MALFORMED_OUTPUT),
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


def test_semantic_ordinary_conversation_remains_ordinary(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "ordinary_conversation": True,
        "candidate_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
    })

    frame = hybrid.interpret("Как ты сегодня?")

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION


def test_semantic_explicit_unsupported_action_stays_distinct_from_conversation(tmp_path):
    _, _, validator, _, _ = _boundaries(tmp_path)
    proposal = SemanticInterpretationProposal(
        ordinary_conversation=False,
        unsupported_action=True,
        nearby_operation_ids=(
            "google_calendar.event.create",
            "home.timed_commitments",
        ),
    )

    frame = validator.validate(
        "Запиши меня на внешнее занятие завтра в 9",
        proposal,
    )

    assert frame.resolution_state is InterpretationResolutionState.UNSUPPORTED_ACTION
    assert frame.candidates == ()
    assert frame.slots == ()


def test_untrusted_semantics_cannot_erase_strict_structural_calendar_owner(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "ordinary_conversation": True,
        "candidate_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
    })

    frame = hybrid.interpret("Поставь встречу завтра в 19 на час")

    assert [item.operation_id for item in frame.candidates] == [
        "google_calendar.event.create"
    ]
    assert frame.resolution_state is InterpretationResolutionState.RESOLVED
    assert hybrid.last_rejection == "semantic_conflicts_with_structural_owner"


def test_unsupported_without_adopted_evidence_does_not_steal_legacy_route(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "ordinary_conversation": False,
        "unsupported_action": True,
        "candidate_operation_ids": [],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
    })

    frame = hybrid.interpret("Обнови память о выбранной модели")

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert hybrid.last_rejection == "unsupported_action_outside_adopted_space"


def test_untrusted_unsupported_proposal_cannot_steal_connector_read_owner(tmp_path):
    provider, _, _, hybrid, _ = _boundaries(tmp_path)
    provider.response_text = json.dumps({
        "ordinary_conversation": False,
        "unsupported_action": True,
        "candidate_operation_ids": [],
        "nearby_operation_ids": [],
        "extracted_slots": [],
        "unresolved_referents": [],
        "ambiguity_hint": "none",
    })

    frame = hybrid.interpret("Посмотри мою почту")

    assert [item.operation_id for item in frame.candidates] == ["yandex_mail.read"]
    assert provider.requests == []
    assert hybrid.last_rejection is None


def test_docs_content_and_explicit_information_spaces_never_reach_semantic_model(tmp_path):
    class ExplodingResolver:
        def resolve(self, *_args, **_kwargs):
            raise AssertionError("protected deterministic ownership")

    catalog = default_home_capability_catalog()
    deterministic = CapabilityCandidateDiscovery(catalog=catalog)
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=deterministic.specifications,
        allowed_operation_ids=adoption.supported_operation_ids,
    )
    hybrid = HybridCapabilityCandidateDiscovery(
        deterministic=deterministic,
        resolver=ExplodingResolver(),
        validator=validator,
    )

    docs = hybrid.interpret(
        "Создай документ на Гугл Диске: Сегодня мы продолжили делать наш Дом"
    )
    web = hybrid.interpret("Поищи в интернете последнюю версию Ollama")

    assert [item.operation_id for item in docs.candidates] == [
        "google_drive.document.create"
    ]
    assert web.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION


def test_model_role_can_switch_profile_without_router_code_change(tmp_path):
    _, _, _, _, roles = _boundaries(tmp_path)

    selected = roles.assign(ModelRole.SEMANTIC_RESOLVER, "fast")

    assert selected.model_id == "qwen3.5:4b"
    restarted = ModelRoleProfileStore(roles.path, profiles=roles.profiles)
    assert restarted.profile_for(ModelRole.SEMANTIC_RESOLVER).profile_id == "fast"
