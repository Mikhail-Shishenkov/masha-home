from datetime import datetime, timedelta, timezone

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import (
    CandidateEvidence, CapabilityCandidate, CapabilityCandidateDiscovery,
    InterpretationFrame, InterpretationResolutionState,
)
from backend.conversation.pending_resolution import (
    PendingResolutionStatus,
    PendingResolutionStore,
)
from backend.conversation.resolution_coordinator import (
    CoordinationStatus,
    DomainProposalContext,
    DomainProposalResult,
    NaturalLanguageResolutionCoordinator,
    ResolvedCapabilityAdapterRegistry,
    ResolvedCapabilityHandoff,
)


NOW = datetime(2026, 8, 28, 9, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value


def _coordinator(tmp_path, clock=None):
    clock = clock or MutableClock()
    catalog = default_home_capability_catalog()
    store = PendingResolutionStore(tmp_path / "pending-resolutions.json", clock=clock)
    coordinator = NaturalLanguageResolutionCoordinator(
        discovery=CapabilityCandidateDiscovery(catalog=catalog),
        builder=DeterministicClarificationBuilder(catalog=catalog, clock=clock),
        engine=FollowUpResolutionEngine(),
        store=store,
    )
    return coordinator, store, clock


def test_adapter_registry_accepts_future_operation_without_coordinator_change():
    class SyntheticAdapter:
        operation_id = "future.notes.create"

        def resolve(self, handoff, context):
            return DomainProposalResult(
                response=f"{handoff.slot('subject').value}:{context.project_id}",
                projection_state="waiting_confirmation",
                pending_application_operation="future_note_create",
            )

    from backend.conversation.interpretation_v2 import (
        InterpretationSlot,
        InterpretationValueOrigin,
    )

    handoff = ResolvedCapabilityHandoff(
        conversation_id="c1",
        operation_id="future.notes.create",
        original_utterance="Сохрани заметку",
        slots=(InterpretationSlot(
            name="subject", value="заметка",
            origin=InterpretationValueOrigin.EXPLICIT,
        ),),
    )
    registry = ResolvedCapabilityAdapterRegistry((SyntheticAdapter(),))

    result = registry.resolve(
        handoff,
        DomainProposalContext(project_id="project", now_local=NOW),
    )

    assert result.response == "заметка:project"


def test_corrupt_store_fails_safely_without_handoff(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("not-json", encoding="utf-8")

    outcome = coordinator.coordinate(
        "Запиши занятие завтра в 10", conversation_id="c1"
    )

    assert outcome.status is CoordinationStatus.FAILED
    assert outcome.handoff is None
    assert outcome.response == coordinator.FAILURE_RESPONSE
    assert outcome.diagnostic.pending_outcome == "infrastructure_failure"


def test_proven_domain_proposal_retires_stale_semantic_pending(tmp_path):
    coordinator, store, _ = _coordinator(tmp_path)
    coordinator.coordinate("Запиши занятие завтра в 10", conversation_id="c1")
    pending = store.active_for_conversation("c1")

    assert coordinator.supersede_for_domain_proposal("c1") is True
    assert store.active_for_conversation("c1") is None
    assert store.get(pending.resolution_id).status is PendingResolutionStatus.SUPERSEDED
