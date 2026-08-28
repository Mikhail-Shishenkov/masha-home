import json
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.application.home_capabilities import default_home_capability_catalog
from backend.conversation.interpretation_v2 import (
    InterpretationSpecificationRegistry,
    default_interpretation_specifications,
)
from backend.conversation.run_semantic_resolver_benchmark import score_observations


FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = FIXTURES / "misha_semantic_resolver_benchmark.schema.json"
BENCHMARK_PATH = FIXTURES / "misha_semantic_resolver_benchmark.json"
REQUIRED_CATEGORIES = {
    "scheduling", "ordinary", "docs_content", "mail", "files", "memory",
    "continuity", "web", "referent", "typo_colloquial",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_semantic_benchmark_is_versioned_bounded_and_data_driven():
    schema = _load(SCHEMA_PATH)
    benchmark = _load(BENCHMARK_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(benchmark)
    assert len(benchmark["cases"]) >= 50
    assert {case["category"] for case in benchmark["cases"]} == REQUIRED_CATEGORIES
    case_ids = [case["case_id"] for case in benchmark["cases"]]
    assert len(case_ids) == len(set(case_ids))


def test_benchmark_operations_are_catalogued_and_have_interpretation_specs():
    benchmark = _load(BENCHMARK_PATH)
    catalog = default_home_capability_catalog()
    specifications = InterpretationSpecificationRegistry(
        catalog=catalog,
        specifications=default_interpretation_specifications(),
    )
    operation_ids = {
        operation_id
        for case in benchmark["cases"]
        for field in ("expected_candidate_operations", "forbidden_operations")
        for operation_id in case[field]
    }

    for operation_id in operation_ids:
        assert catalog.get(operation_id).operation_id == operation_id
        assert specifications.get(operation_id).operation_id == operation_id


def test_benchmark_metrics_have_stable_documented_meaning():
    observations = [
        {
            "expected_candidate_operations": ["home.timed_commitments"],
            "actual_candidate_operations": ["home.timed_commitments"],
            "clarification_required": False,
            "actual_clarification_required": False,
            "expected_known_slots": {"time": "11:00", "date": "завтра"},
            "actual_known_slots": {"time": "11:00", "date": "сегодня"},
            "ordinary_conversation": False,
            "forbidden_operations": ["google_calendar.event.create"],
            "failure": None,
            "latency_ms": 10.0,
        },
        {
            "expected_candidate_operations": [],
            "actual_candidate_operations": ["google_calendar.event.create"],
            "clarification_required": False,
            "actual_clarification_required": True,
            "expected_known_slots": {},
            "actual_known_slots": {},
            "ordinary_conversation": True,
            "forbidden_operations": ["google_calendar.event.create"],
            "failure": "malformed_output",
            "latency_ms": 30.0,
        },
    ]

    assert score_observations(observations) == {
        "cases": 2,
        "exact_candidate_accuracy_percent": 50.0,
        "forbidden_action_false_positive_rate_percent": 50.0,
        "clarification_accuracy_percent": 50.0,
        "slot_extraction_accuracy_percent": 50.0,
        "ordinary_conversation_false_positive_rate_percent": 100.0,
        "malformed_output_rate_percent": 50.0,
        "median_latency_ms": 20.0,
        "p95_latency_ms": 30.0,
    }
