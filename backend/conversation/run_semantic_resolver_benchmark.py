"""Run the data-driven semantic resolver corpus against local model profiles.

This is an explicit developer command.  Importing the module performs no
network activity and automated tests exercise only its pure scoring helpers.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from backend.application.home_capabilities import default_home_capability_catalog
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_roles import ModelRoleProfileStore
from backend.llm.model_router import ModelRouter
from backend.llm.ollama_provider import OllamaProvider

from .interpretation_v2 import (
    InterpretationResolutionState,
    InterpretationSpecificationRegistry,
    default_interpretation_specifications,
)
from .semantic_resolver import LocalSemanticResolver, SemanticProposalValidator


DEFAULT_CORPUS = Path("tests/fixtures/misha_semantic_resolver_benchmark.json")
DEFAULT_OUTPUT_DIR = Path("local-data/model-benchmarks")


def _percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 3) if denominator else 0.0


def _p95(values: Iterable[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def score_observations(observations: list[dict[str, Any]]) -> dict[str, float | int]:
    """Score normalized observations without invoking a model or provider."""

    total = len(observations)
    exact_candidates = 0
    clarification_correct = 0
    forbidden_cases = 0
    forbidden_false_positives = 0
    ordinary_cases = 0
    ordinary_false_positives = 0
    expected_slots = 0
    correct_slots = 0
    malformed = 0
    latencies = []
    for item in observations:
        expected_operations = item["expected_candidate_operations"]
        actual_operations = item["actual_candidate_operations"]
        exact_candidates += actual_operations == expected_operations
        clarification_correct += (
            item["actual_clarification_required"]
            == item["clarification_required"]
        )
        forbidden = set(item["forbidden_operations"])
        if forbidden:
            forbidden_cases += 1
            forbidden_false_positives += bool(forbidden & set(actual_operations))
        if item["ordinary_conversation"]:
            ordinary_cases += 1
            ordinary_false_positives += bool(actual_operations)
        for name, expected_value in item["expected_known_slots"].items():
            expected_slots += 1
            correct_slots += item["actual_known_slots"].get(name) == expected_value
        malformed += item.get("failure") == "malformed_output"
        latencies.append(float(item["latency_ms"]))
    return {
        "cases": total,
        "exact_candidate_accuracy_percent": _percent(exact_candidates, total),
        "forbidden_action_false_positive_rate_percent": _percent(
            forbidden_false_positives, forbidden_cases,
        ),
        "clarification_accuracy_percent": _percent(clarification_correct, total),
        "slot_extraction_accuracy_percent": _percent(correct_slots, expected_slots),
        "ordinary_conversation_false_positive_rate_percent": _percent(
            ordinary_false_positives, ordinary_cases,
        ),
        "malformed_output_rate_percent": _percent(malformed, total),
        "median_latency_ms": round(median(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(_p95(latencies), 3),
    }


def run_profile(
    *,
    profile_id: str,
    cases: list[dict[str, Any]],
    resolver: LocalSemanticResolver,
    validator: SemanticProposalValidator,
) -> dict[str, Any]:
    vocabulary = validator.vocabulary()
    observations: list[dict[str, Any]] = []
    for case in cases:
        result = resolver.resolve(
            case["utterance"], vocabulary, profile_id=profile_id,
        )
        operations: list[str] = []
        slots: dict[str, str] = {}
        clarification = False
        rejection: str | None = None
        if result.proposal is not None:
            try:
                frame = validator.validate(case["utterance"], result.proposal)
                operations = [item.operation_id for item in frame.candidates]
                slots = {
                    item.name: item.value
                    for item in frame.slots
                    if item.value is not None
                }
                clarification = (
                    frame.resolution_state
                    is InterpretationResolutionState.CLARIFICATION_REQUIRED
                )
            except ValueError as error:
                rejection = str(error)
        observations.append({
            **case,
            "actual_candidate_operations": operations,
            "actual_known_slots": slots,
            "actual_clarification_required": clarification,
            "failure": result.failure.value if result.failure is not None else None,
            "validation_rejection": rejection,
            "latency_ms": round(result.latency_ms, 3),
        })
    return {
        "profile_id": profile_id,
        "metrics": score_observations(observations),
        "observations": observations,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Misha's local semantic-resolver benchmark.",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--profiles", nargs="+", default=("primary", "fast"),
        help="Configured local model profile IDs (default: primary fast).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = args.project_root.resolve()
    corpus_path = (args.corpus or project_root / DEFAULT_CORPUS).resolve()
    output_dir = (args.output_dir or project_root / DEFAULT_OUTPUT_DIR).resolve()
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))

    profiles = ModelProfileStore(project_root / "local-data/config/model-profiles.json")
    roles = ModelRoleProfileStore(
        project_root / "local-data/config/model-roles.json", profiles=profiles,
    )
    resolver = LocalSemanticResolver(
        router=ModelRouter((OllamaProvider(),)), role_profiles=roles,
    )
    catalog = default_home_capability_catalog()
    specifications = InterpretationSpecificationRegistry(
        catalog=catalog,
        specifications=default_interpretation_specifications(),
    )
    benchmark_operations = frozenset(
        operation_id
        for case in corpus["cases"]
        for operation_id in (
            *case["expected_candidate_operations"],
            *case["forbidden_operations"],
        )
    )
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=specifications,
        allowed_operation_ids=benchmark_operations,
    )
    report = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(corpus_path),
        "corpus_cases": len(corpus["cases"]),
        "profiles": [
            run_profile(
                profile_id=profile_id,
                cases=corpus["cases"],
                resolver=resolver,
                validator=validator,
            )
            for profile_id in args.profiles
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"semantic-resolver-{timestamp}.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    for profile in report["profiles"]:
        print(profile["profile_id"], json.dumps(profile["metrics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
