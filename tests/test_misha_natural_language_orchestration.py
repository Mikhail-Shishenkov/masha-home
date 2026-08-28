import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import DeterministicClarificationBuilder, FollowUpResolutionEngine
from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery
from backend.conversation.pending_resolution import PendingResolutionStore
from backend.conversation.resolution_coordinator import NaturalLanguageResolutionCoordinator


FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = FIXTURES / "misha_natural_language_orchestration.schema.json"
BENCHMARK_PATH = FIXTURES / "misha_natural_language_orchestration.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_orchestration_benchmark_conforms_to_versioned_schema():
    schema = _load(SCHEMA_PATH)
    benchmark = _load(BENCHMARK_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(benchmark)
    identifiers = [case["case_id"] for case in benchmark["cases"]]
    assert len(identifiers) == len(set(identifiers))


def test_every_orchestration_case_runs_without_test_code_registration(tmp_path):
    benchmark = _load(BENCHMARK_PATH)

    for index, case in enumerate(benchmark["cases"]):
        now = [datetime(2026, 8, 28, 9, tzinfo=timezone.utc)]
        clock = lambda: now[0]
        catalog = default_home_capability_catalog()
        store = PendingResolutionStore(tmp_path / str(index) / "pending.json", clock=clock)
        coordinator = NaturalLanguageResolutionCoordinator(
            discovery=CapabilityCandidateDiscovery(catalog=catalog),
            builder=DeterministicClarificationBuilder(catalog=catalog, clock=clock),
            engine=FollowUpResolutionEngine(),
            store=store,
        )
        first = coordinator.coordinate(case["initial"], conversation_id="benchmark")
        original = store.active_for_conversation("benchmark")
        assert original is not None, case["case_id"]
        outcome = first
        if case["follow_up"] is not None:
            now[0] += timedelta(minutes=case["advance_minutes"])
            outcome = coordinator.coordinate(
                case["follow_up"], conversation_id="benchmark"
            )

        assert outcome.status.value == case["expected_status"], case["case_id"]
        operation_id = None if outcome.handoff is None else outcome.handoff.operation_id
        assert operation_id == case["expected_operation_id"], case["case_id"]
        assert store.get(original.resolution_id).status.value == case["expected_pending_status"], case["case_id"]
