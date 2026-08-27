import pytest
from pydantic import ValidationError

from backend.application.capability_catalog import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityEffect,
    CapabilityOperationKind,
    CapabilityRisk,
)
from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.capability_router import NaturalLanguageCapabilityRouter
from backend.conversation.interpretation_v2 import (
    CandidateEvidence,
    CapabilityCandidate,
    CapabilityCandidateDiscovery,
    InterpretationAmbiguity,
    InterpretationFrame,
    InterpretationReferent,
    InterpretationResolutionState,
    InterpretationSlot,
    InterpretationSpecification,
    InterpretationSpecificationError,
    InterpretationSpecificationRegistry,
    InterpretationValueOrigin,
    explicit_file_provider_id,
)


def _discovery() -> CapabilityCandidateDiscovery:
    return CapabilityCandidateDiscovery(catalog=default_home_capability_catalog())


def _slots(frame: InterpretationFrame) -> dict[str, str | None]:
    return {slot.name: slot.value for slot in frame.slots}


def test_explicit_calendar_language_is_a_resolved_structural_candidate():
    frame = _discovery().interpret("Поставь завтра в 19 занятие по AI")

    assert [candidate.operation_id for candidate in frame.candidates] == [
        "google_calendar.event.create"
    ]
    assert _slots(frame) == {
        "date": "завтра",
        "time": "19:00",
        "subject": "занятие по ai",
    }
    assert frame.ambiguity is InterpretationAmbiguity.NONE
    assert frame.resolution_state is InterpretationResolutionState.RESOLVED


def test_ambiguous_schedule_preserves_both_plausible_capabilities():
    frame = _discovery().interpret("Запиши занятие завтра в 10")

    assert [candidate.operation_id for candidate in frame.candidates] == [
        "google_calendar.event.create",
        "home.timed_commitments",
    ]
    assert _slots(frame) == {
        "date": "завтра",
        "time": "10:00",
        "subject": "занятие",
    }
    assert frame.ambiguity is InterpretationAmbiguity.CAPABILITY
    assert frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED


def test_document_material_is_not_independently_routed_by_temporal_words():
    material = "Сегодня мы продолжили делать наш Дом"
    frame = _discovery().interpret(
        f"Создай документ на Гугл Диске: {material}"
    )

    assert [candidate.operation_id for candidate in frame.candidates] == [
        "google_drive.document.create"
    ]
    assert _slots(frame) == {"target": "google_drive", "content": material}
    assert "date" not in _slots(frame)
    assert frame.resolution_state is InterpretationResolutionState.RESOLVED


def test_mail_read_candidate_is_descriptive_and_contains_no_mutation_authority():
    catalog = default_home_capability_catalog()
    frame = CapabilityCandidateDiscovery(catalog=catalog).interpret("Посмотри мою почту")
    candidate = frame.candidates[0]

    assert candidate.operation_id == "yandex_mail.read"
    assert catalog.get(candidate.operation_id).effect is CapabilityEffect.READ_ONLY
    assert set(candidate.model_dump()) == {
        "operation_id", "evidence", "slot_names", "missing_slots"
    }
    assert not hasattr(candidate, "allowed_to_execute")
    assert not hasattr(candidate, "permission_granted")
    assert not hasattr(candidate, "executor")


def test_today_word_boundary_does_not_match_today_adjective():
    frame = _discovery().interpret("Короткий итог сегодняшнего занятия")

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert frame.candidates == ()
    assert frame.slots == ()


def test_unscoped_save_preserves_unresolved_referent_without_invention():
    frame = _discovery().interpret("Сохрани это")

    assert [candidate.operation_id for candidate in frame.candidates] == [
        "google_drive.document.create",
        "home.timed_commitments",
    ]
    assert frame.referents == (
        InterpretationReferent(expression="это"),
    )
    assert frame.referents[0].value is None
    assert frame.ambiguity is InterpretationAmbiguity.CAPABILITY
    assert frame.resolution_state is InterpretationResolutionState.CLARIFICATION_REQUIRED


def test_companion_conversation_is_a_first_class_ordinary_state():
    frame = _discovery().interpret("Маш, иди сюда, хочу немного побыть с тобой")

    assert frame.resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION
    assert frame.ambiguity is InterpretationAmbiguity.NONE
    assert frame.candidates == ()


@pytest.mark.parametrize(
    "alias",
    ("Гугл Диск", "Гугл Диске", "Гугл Диска", "Гугл Диском"),
)
def test_google_drive_inflections_use_provider_normalization_without_an_intent_enum(alias):
    assert explicit_file_provider_id(alias) == "google_drive"
    assert _discovery().interpret(alias).resolution_state is InterpretationResolutionState.ORDINARY_CONVERSATION


def test_synthetic_catalog_operation_fits_generic_candidate_and_frame_contracts():
    descriptor = CapabilityDescriptor(
        operation_id="telegram.send_to_misha",
        display_name="Отправить сообщение Мише",
        family="telegram",
        kind=CapabilityOperationKind.CREATE,
        effect=CapabilityEffect.EXTERNAL_MUTATION,
        risk=CapabilityRisk.CONSEQUENTIAL,
        verification_required=True,
    )
    catalog = CapabilityCatalog((descriptor,))
    candidate = CapabilityCandidate(
        operation_id=catalog.get("telegram.send_to_misha").operation_id,
        evidence=(CandidateEvidence(signal="synthetic_fixture"),),
    )
    frame = InterpretationFrame(
        original_utterance="Напиши Мише в Telegram",
        normalized_goal="telegram.send_to_misha",
        candidates=(candidate,),
        resolution_state=InterpretationResolutionState.RESOLVED,
    )

    assert frame.candidates[0].operation_id == "telegram.send_to_misha"
    assert "telegram" not in InterpretationAmbiguity.__members__


def test_interpretation_specifications_are_catalog_keyed_and_fail_closed():
    catalog = default_home_capability_catalog()
    specification = InterpretationSpecification(
        operation_id="google_calendar.event.create",
        required_slots=("subject", "date", "time"),
    )
    registry = InterpretationSpecificationRegistry(
        catalog=catalog, specifications=(specification,)
    )

    assert registry.get(specification.operation_id) == specification
    with pytest.raises(InterpretationSpecificationError):
        registry.register(specification)
    with pytest.raises(InterpretationSpecificationError):
        registry.register(InterpretationSpecification(operation_id="telegram.unknown"))


def test_strict_models_reject_unresolved_values_and_extra_authority_fields():
    with pytest.raises(ValidationError):
        InterpretationSlot(
            name="referent",
            value="invented",
            origin=InterpretationValueOrigin.UNRESOLVED,
        )
    with pytest.raises(ValidationError):
        CapabilityCandidate(
            operation_id="web.search",
            evidence=(CandidateEvidence(signal="explicit"),),
            permission_granted=True,
        )


def test_v2_discovery_does_not_replace_or_mutate_v1_router_contract():
    router = NaturalLanguageCapabilityRouter()
    before = router.route("Поставь завтра в 19 занятие по AI")

    _discovery().interpret("Поставь завтра в 19 занятие по AI")

    assert router.route("Поставь завтра в 19 занятие по AI") == before
    assert not hasattr(CapabilityCandidateDiscovery, "execute")
    assert not hasattr(CapabilityCandidateDiscovery, "authorize")
