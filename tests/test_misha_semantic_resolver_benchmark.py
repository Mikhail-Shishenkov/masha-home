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
            "dialogue_core_status": "resolved_handoff",
            "latency_ms": 30.0,
        },
    ]

    assert score_observations(observations) == {
        "cases": 2,
        "wire_schema_success_percent": 0.0,
        "kind_accuracy_percent": 0.0,
        "exact_candidate_accuracy_percent": 50.0,
        "forbidden_action_false_positive_rate_percent": 50.0,
        "forbidden_candidate_presence_rate_percent": 50.0,
        "clarification_accuracy_percent": 50.0,
        "slot_extraction_accuracy_percent": 50.0,
        "slot_evidence_grounding_percent": 0.0,
        "home_normalization_acceptance_percent": 0.0,
        "action_request_grounding": {
            "action_cases": 1,
            "evidence_present_percent": 0.0,
            "evidence_grounded_percent": 0.0,
            "home_accepted_percent": 0.0,
            "ordinary_evidence_correctly_absent_percent": 100.0,
        },
        "scheduling_operation_selection": {
            "cases": 0,
            "evidence_present_percent": 0.0,
            "evidence_grounded_percent": 0.0,
            "home_accepted_percent": 0.0,
            "explicit_selection_correct_percent": 0.0,
            "ambiguous_selection_correctly_absent_percent": 0.0,
            "ambiguous_selection_not_authorized_percent": 0.0,
            "ambiguous_final_candidate_set_preserved_percent": 0.0,
            "explicit_cases": 0,
            "ambiguous_cases": 0,
        },
        "action_continuity": {
            "calendar_update_cases": 0,
            "calendar_update_to_create_confusion_rate_percent": 0.0,
            "calendar_create_cases": 0,
            "calendar_create_to_update_confusion_rate_percent": 0.0,
            "contextual_entity_cases": 0,
            "contextual_entity_recognition_percent": 0.0,
            "contextual_entity_application_resolution_percent": 0.0,
            "recognized_action_fallthrough_rate_percent": 0.0,
            "incorrect_capability_handoff_rate_percent": 50.0,
        },
        "ordinary_conversation_false_positive_rate_percent": 100.0,
        "malformed_output_rate_percent": 50.0,
        "diagnostic_category_counts": {},
        "dialogue_core_resolution_success_percent": 0.0,
        "cold_latency_ms": 10.0,
        "warm_median_latency_ms": 30.0,
        "warm_p95_latency_ms": 30.0,
        "median_latency_ms": 20.0,
        "p95_latency_ms": 30.0,
    }


def test_scheduling_selection_metrics_distinguish_grounded_choice_from_ambiguity():
    observations = [
        {
            "category": "scheduling",
            "operation_selection_expectation": "explicit",
            "expected_candidate_operations": ["home.timed_commitments"],
            "actual_candidate_operations": ["home.timed_commitments"],
            "clarification_required": False,
            "actual_clarification_required": False,
            "expected_known_slots": {},
            "actual_known_slots": {},
            "ordinary_conversation": False,
            "forbidden_operations": [],
            "operation_selection_evidence_present": True,
            "operation_selection_evidence_grounded": True,
            "operation_selection_operation_id": "home.timed_commitments",
            "operation_selection_home_accepted": True,
            "latency_ms": 10.0,
        },
        {
            "category": "scheduling",
            "operation_selection_expectation": "ambiguous",
            "expected_candidate_operations": [
                "google_calendar.event.create", "home.timed_commitments",
            ],
            "actual_candidate_operations": [
                "google_calendar.event.create", "home.timed_commitments",
            ],
            "clarification_required": True,
            "actual_clarification_required": True,
            "expected_known_slots": {},
            "actual_known_slots": {},
            "ordinary_conversation": False,
            "forbidden_operations": [],
            "operation_selection_evidence_present": False,
            "operation_selection_evidence_grounded": False,
            "operation_selection_operation_id": None,
            "operation_selection_home_accepted": False,
            "latency_ms": 20.0,
        },
    ]

    assert score_observations(observations)["scheduling_operation_selection"] == {
        "cases": 2,
        "evidence_present_percent": 50.0,
        "evidence_grounded_percent": 100.0,
        "home_accepted_percent": 100.0,
        "explicit_selection_correct_percent": 100.0,
        "ambiguous_selection_correctly_absent_percent": 100.0,
        "ambiguous_selection_not_authorized_percent": 100.0,
        "ambiguous_final_candidate_set_preserved_percent": 100.0,
        "explicit_cases": 1,
        "ambiguous_cases": 1,
    }
