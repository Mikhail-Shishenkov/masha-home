import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.clarification import (
    DeterministicClarificationBuilder,
    FollowUpResolutionEngine,
)
from backend.conversation.interpretation_v2 import CapabilityCandidateDiscovery


FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = FIXTURES / "misha_natural_language_multiturn.schema.json"
BENCHMARK_PATH = FIXTURES / "misha_natural_language_multiturn.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_multiturn_fixture_conforms_to_versioned_schema():
    schema = _load(SCHEMA_PATH)
    benchmark = _load(BENCHMARK_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(benchmark)
    case_ids = [case["case_id"] for case in benchmark["cases"]]
    assert len(case_ids) == len(set(case_ids))


def test_every_multiturn_case_runs_without_test_code_registration():
    benchmark = _load(BENCHMARK_PATH)
    catalog = default_home_capability_catalog()
    discovery = CapabilityCandidateDiscovery(catalog=catalog)
    builder = DeterministicClarificationBuilder(
        catalog=catalog,
        clock=lambda: datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
        resolution_id_factory=lambda: "00000000-0000-0000-0000-000000000051",
    )
    engine = FollowUpResolutionEngine()

    for case in benchmark["cases"]:
        frame = discovery.interpret(case["turn1"])
        request, pending = builder.build(frame, conversation_id="benchmark-conversation")
        result = engine.resolve(pending, case["turn2"])

        assert request.clarification_kind.value == case["clarification_kind"], case["case_id"]
        assert result.outcome.value == case["expected_outcome"], case["case_id"]
        assert result.selected_operation_id == case["expected_operation_id"], case["case_id"]
        assert {
            slot.name: slot.value for slot in result.interpretation.slots
        } == case["expected_known_slots"], case["case_id"]
