import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import DeterministicClarificationBuilder, FollowUpResolutionEngine
from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery
from backend.conversation.pending_resolution import PendingResolutionStore
from backend.conversation.resolution_coordinator import NaturalLanguageResolutionCoordinator, V2LiveAdoptionPolicy
from backend.conversation.semantic_resolver import (
    SemanticFollowUpProposal,
    SemanticFollowUpResult,
    parse_semantic_interpretation,
    SemanticProposalValidator,
    SemanticResolverFailure,
)
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.temporal.date_resolution import HomeCalendarDateResolver


FIXTURES = Path(__file__).parent / "fixtures"
BENCHMARK = FIXTURES / "misha_contextual_follow_up_benchmark.json"
SCHEMA = FIXTURES / "misha_contextual_follow_up_benchmark.schema.json"
NOW = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)


class FixtureResolver:
    def __init__(self, proposals):
        self.proposals = proposals

    def resolve_follow_up(self, utterance, vocabulary, context, *, profile_id=None):
        payload = self.proposals.get(utterance)
        if payload is None:
            return SemanticFollowUpResult(failure=SemanticResolverFailure.MALFORMED_OUTPUT, latency_ms=0)
        return SemanticFollowUpResult(
            proposal=SemanticFollowUpProposal.model_validate(payload), latency_ms=0,
        )


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_contextual_follow_up_benchmark_is_versioned_bounded_and_data_driven():
    schema = _load(SCHEMA)
    benchmark = _load(BENCHMARK)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(benchmark)
    identifiers = [case["case_id"] for case in benchmark["cases"]]
    assert len(identifiers) == len(set(identifiers))


def test_contextual_follow_up_benchmark_preserves_and_refines_pending_state(tmp_path):
    for case in _load(BENCHMARK)["cases"]:
        catalog = default_home_capability_catalog()
        discovery = CapabilityCandidateDiscovery(catalog=catalog)
        adoption = V2LiveAdoptionPolicy()
        validator = SemanticProposalValidator(
            catalog=catalog,
            specifications=discovery.specifications,
            allowed_operation_ids=adoption.supported_operation_ids,
            date_resolver=HomeCalendarDateResolver(
                TemporalEngine(clock=FixedClock(NOW)),
            ),
        )
        clock = FixedClock(NOW)
        store = PendingResolutionStore(tmp_path / f"{case['case_id']}.json", clock=clock.now_utc)
        proposals = {
            turn["utterance"]: turn["proposal"]
            for turn in case["follow_ups"] if "proposal" in turn
        }
        coordinator = NaturalLanguageResolutionCoordinator(
            discovery=discovery,
            builder=DeterministicClarificationBuilder(catalog=catalog, clock=clock.now_utc),
            engine=FollowUpResolutionEngine(
                semantic_resolver=FixtureResolver(proposals),
                semantic_validator=validator,
                temporal_engine=TemporalEngine(clock=clock),
            ),
            store=store,
            adoption=adoption,
        )
        if "initial_proposal" in case:
            frame = validator.validate(
                case["initial"],
                parse_semantic_interpretation(case["initial_proposal"]),
            )
            _, pending = coordinator.builder.build(frame, conversation_id="benchmark")
            store.save(pending)
        else:
            coordinator.coordinate(case["initial"], conversation_id="benchmark")

        result = None
        for turn in case["follow_ups"]:
            result = coordinator.coordinate(turn["utterance"], conversation_id="benchmark")

        assert result.status.value == case["expected_status"], case["case_id"]
        assert (result.handoff.operation_id if result.handoff else None) == case.get("expected_operation_id"), case["case_id"]
        active = store.active_for_conversation("benchmark")
        assert (active is not None) is case.get("pending_survives", False), case["case_id"]
        frame = result.handoff if result.handoff else (active.interpretation if active else result.diagnostic)
        slots = frame.slots if result.handoff else (active.interpretation.slots if active else result.diagnostic.merged_slots)
        assert {item.name: item.value for item in slots} == case["expected_slots"], case["case_id"]
