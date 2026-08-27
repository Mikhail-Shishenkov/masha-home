import json
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.interpretation_v2 import (
    CapabilityCandidateDiscovery,
    InterpretationResolutionState,
)


FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = FIXTURES / "misha_natural_language_benchmark.schema.json"
BENCHMARK_PATH = FIXTURES / "misha_natural_language_benchmark.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_benchmark_fixture_conforms_to_versioned_schema():
    schema = _load(SCHEMA_PATH)
    benchmark = _load(BENCHMARK_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(benchmark)
    case_ids = [case["case_id"] for case in benchmark["cases"]]
    assert len(case_ids) == len(set(case_ids))


def test_every_benchmark_case_runs_without_test_code_registration():
    benchmark = _load(BENCHMARK_PATH)
    discovery = CapabilityCandidateDiscovery(catalog=default_home_capability_catalog())

    for case in benchmark["cases"]:
        frame = discovery.interpret(case["utterance"])
        operations = [candidate.operation_id for candidate in frame.candidates]
        accepted_operations = [
            case["expected_candidate_operations"],
            *case["allowed_candidate_alternatives"],
        ]
        assert operations in accepted_operations, case["case_id"]
        assert {slot.name: slot.value for slot in frame.slots} == case["expected_known_slots"], case["case_id"]
        assert (
            frame.resolution_state
            is InterpretationResolutionState.CLARIFICATION_REQUIRED
        ) == case["clarification_required"], case["case_id"]
        assert frame.ambiguity.value == case["ambiguity_kind"], case["case_id"]
        assert (
            frame.resolution_state
            is InterpretationResolutionState.ORDINARY_CONVERSATION
        ) == case["ordinary_conversation"], case["case_id"]
