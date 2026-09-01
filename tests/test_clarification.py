from datetime import datetime, timezone

import pytest

from backend.application.capability_catalog import (
    CapabilityDescriptor,
    CapabilityEffect,
    CapabilityOperationKind,
    CapabilityRisk,
)
from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    ClarificationKind,
    DeterministicClarificationBuilder,
    FollowUpOutcome,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import (
    CandidateEvidence,
    CapabilityCandidate,
    CapabilityCandidateDiscovery,
    InterpretationAmbiguity,
    InterpretationFrame,
    InterpretationResolutionState,
    InterpretationSlot,
    InterpretationValueOrigin,
)
from backend.conversation.semantic_resolver import (
    SemanticProposalValidator,
    SemanticResolverFailure,
    SemanticFollowUpResult,
)
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
RESOLUTION_ID = "00000000-0000-0000-0000-000000000021"


def _catalog():
    return default_home_capability_catalog()


def _frame(utterance: str) -> InterpretationFrame:
    return CapabilityCandidateDiscovery(catalog=_catalog()).interpret(utterance)


def _build(utterance: str):
    return DeterministicClarificationBuilder(
        catalog=_catalog(),
        clock=lambda: NOW,
        resolution_id_factory=lambda: RESOLUTION_ID,
    ).build(_frame(utterance), conversation_id="conversation-1")


def _slots(frame: InterpretationFrame) -> dict[str, str | None]:
    return {slot.name: slot.value for slot in frame.slots}


def test_unresolved_referent_is_not_invented_and_explicit_material_is_bounded_evidence():
    request, pending = _build("Сохрани это")

    assert request.clarification_kind is ClarificationKind.REFERENT
    assert request.referent_expression == "это"
    assert request.prompt == "Что именно сохранить?"

    unresolved = FollowUpResolutionEngine().resolve(pending, "это")
    supplied = FollowUpResolutionEngine().resolve(
        pending,
        "Вот этот текст: Сегодня выбрали локальную модель.",
    )

    assert unresolved.outcome is FollowUpOutcome.STILL_UNRESOLVED
    assert unresolved.interpretation == pending.interpretation
    assert supplied.outcome is FollowUpOutcome.STILL_UNRESOLVED
    assert supplied.supplied_referent is not None
    assert supplied.supplied_referent.value == "Сегодня выбрали локальную модель."
    assert supplied.supplied_referent.origin is InterpretationValueOrigin.EXPLICIT
    assert supplied.interpretation.original_utterance == "Сохрани это"


@pytest.mark.parametrize("answer", ("не надо", "отмена", "забудь", "ладно, не делай"))
def test_narrow_cancel_language_cancels_only_pending_meaning(answer):
    _, pending = _build("Запиши занятие завтра в 10")

    result = FollowUpResolutionEngine().resolve(pending, answer)

    assert result.outcome is FollowUpOutcome.CANCELLED
    assert result.interpretation == pending.interpretation


def test_provider_scope_clarification_uses_catalog_operations_without_new_enum():
    catalog = _catalog()
    catalog.register(CapabilityDescriptor(
        operation_id="yandex_disk.document.create",
        display_name="Создание документа на Яндекс Диске",
        family="yandex_disk",
        kind=CapabilityOperationKind.CREATE,
        effect=CapabilityEffect.EXTERNAL_MUTATION,
        risk=CapabilityRisk.CONSEQUENTIAL,
        verification_required=True,
    ))
    candidates = tuple(
        CapabilityCandidate(
            operation_id=operation_id,
            evidence=(CandidateEvidence(signal="provider_unresolved"),),
            slot_names=("content",),
        )
        for operation_id in (
            "google_drive.document.create",
            "yandex_disk.document.create",
        )
    )
    frame = InterpretationFrame(
        original_utterance="Сохрани заметку в облаке",
        candidates=candidates,
        slots=(InterpretationSlot(
            name="content",
            value="Заметка",
            origin=InterpretationValueOrigin.EXPLICIT,
        ),),
        ambiguity=InterpretationAmbiguity.PROVIDER_SCOPE,
        resolution_state=InterpretationResolutionState.CLARIFICATION_REQUIRED,
    )
    request, pending = DeterministicClarificationBuilder(
        catalog=catalog,
        clock=lambda: NOW,
        resolution_id_factory=lambda: RESOLUTION_ID,
    ).build(frame, conversation_id="conversation-1")

    result = FollowUpResolutionEngine().resolve(pending, "На Яндекс Диске")

    assert request.prompt == "Где это сохранить?"
    assert [choice.label for choice in request.choices] == ["Google Drive", "Яндекс Диск"]
    assert result.outcome is FollowUpOutcome.RESOLVED
    assert result.selected_operation_id == "yandex_disk.document.create"


def test_clarification_models_and_engine_expose_no_execution_authority():
    request, pending = _build("Запиши занятие завтра в 10")

    assert not hasattr(request, "permission_granted")
    assert not hasattr(pending, "confirmation")
    assert not hasattr(FollowUpResolutionEngine, "execute")
    assert not hasattr(FollowUpResolutionEngine, "authorize")


def test_direct_text_answer_survives_semantic_follow_up_failure():
    class UnavailableSemanticResolver:
        def resolve_follow_up(self, *_args, **_kwargs):
            return SemanticFollowUpResult(
                failure=SemanticResolverFailure.PROVIDER_UNAVAILABLE,
                latency_ms=0,
            )

    catalog = _catalog()
    discovery = CapabilityCandidateDiscovery(catalog=catalog)
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=discovery.specifications,
        known_operation_ids=frozenset(discovery.specifications.operation_ids),
    )
    _, pending = DeterministicClarificationBuilder(
        catalog=catalog,
        clock=lambda: NOW,
        resolution_id_factory=lambda: RESOLUTION_ID,
    ).build(
        discovery.interpret("Поставь в календарь завтра в 10"),
        conversation_id="conversation-1",
    )
    engine = FollowUpResolutionEngine(
        semantic_resolver=UnavailableSemanticResolver(),
        semantic_validator=validator,
        temporal_engine=TemporalEngine(clock=FixedClock(NOW)),
    )

    result = engine.resolve(
        pending,
        "Чтобы я посмотрел заявку от Timepad",
    )

    assert result.outcome is FollowUpOutcome.RESOLVED
    assert _slots(result.interpretation)["subject"] == (
        "Чтобы я посмотрел заявку от Timepad"
    )
