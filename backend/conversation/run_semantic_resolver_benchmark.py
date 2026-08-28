"""Run the data-driven semantic resolver corpus against local model profiles.

This is an explicit developer command.  Importing the module performs no
network activity and automated tests exercise only its pure scoring helpers.
"""

from __future__ import annotations

import argparse
import json
import math
from tempfile import TemporaryDirectory
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
from .semantic_resolver import (
    HybridCapabilityCandidateDiscovery,
    LocalSemanticResolver,
    SemanticProposalValidator,
    SemanticProposalKind,
    SupportedActionProposal,
)
from .capability_router import normalize_utterance
from .clarification import DeterministicClarificationBuilder, FollowUpResolutionEngine
from .interpretation_v2 import CapabilityCandidateDiscovery
from .pending_resolution import PendingResolutionStore
from .resolution_coordinator import CoordinationStatus, DialogueCore, V2LiveAdoptionPolicy
from backend.temporal.date_resolution import HomeCalendarDateResolver
from backend.temporal.temporal_engine import FixedClock, TemporalEngine


DEFAULT_CORPUS = Path("tests/fixtures/misha_semantic_resolver_benchmark.json")
DEFAULT_OUTPUT_DIR = Path("local-data/model-benchmarks")


def _percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 3) if denominator else 0.0


def _p95(values: Iterable[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def score_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
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
    wire_success = 0
    kind_correct = 0
    grounded_evidence = 0
    evidence_items = 0
    normalization_accepted = 0
    end_to_end_success = 0
    failure_categories: dict[str, int] = {}
    latencies = []
    for item in observations:
        expected_operations = item["expected_candidate_operations"]
        actual_operations = item["actual_candidate_operations"]
        wire_success += item.get("wire_schema_success", False)
        kind_correct += (
            item.get("actual_kind") is not None
            and item.get("actual_kind") == item.get("expected_kind")
        )
        grounded_evidence += item.get("grounded_evidence_items", 0)
        evidence_items += item.get("slot_evidence_items", 0)
        normalization_accepted += item.get("home_normalization_accepted", False)
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
        category = item.get("diagnostic_category")
        if category:
            failure_categories[category] = failure_categories.get(category, 0) + 1
        end_to_end_success += item.get("dialogue_core_success", (
            actual_operations == expected_operations
            and item["actual_clarification_required"] == item["clarification_required"]
            and all(
                item["actual_known_slots"].get(name) == value
                for name, value in item["expected_known_slots"].items()
            )
        ))
        latencies.append(float(item["latency_ms"]))
    return {
        "cases": total,
        "wire_schema_success_percent": _percent(wire_success, total),
        "kind_accuracy_percent": _percent(kind_correct, total),
        "exact_candidate_accuracy_percent": _percent(exact_candidates, total),
        "forbidden_action_false_positive_rate_percent": _percent(
            forbidden_false_positives, forbidden_cases,
        ),
        "clarification_accuracy_percent": _percent(clarification_correct, total),
        "slot_extraction_accuracy_percent": _percent(correct_slots, expected_slots),
        "slot_evidence_grounding_percent": _percent(
            grounded_evidence, evidence_items,
        ),
        "home_normalization_acceptance_percent": _percent(
            normalization_accepted, total,
        ),
        "ordinary_conversation_false_positive_rate_percent": _percent(
            ordinary_false_positives, ordinary_cases,
        ),
        "malformed_output_rate_percent": _percent(malformed, total),
        "diagnostic_category_counts": dict(sorted(failure_categories.items())),
        "dialogue_core_resolution_success_percent": _percent(
            end_to_end_success, total,
        ),
        "cold_latency_ms": round(latencies[0], 3) if latencies else 0.0,
        "warm_median_latency_ms": round(median(latencies[1:]), 3) if len(latencies) > 1 else 0.0,
        "warm_p95_latency_ms": round(_p95(latencies[1:]), 3),
        "median_latency_ms": round(median(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(_p95(latencies), 3),
    }


def run_profile(
    *,
    profile_id: str,
    cases: list[dict[str, Any]],
    resolver: LocalSemanticResolver,
    validator: SemanticProposalValidator,
    reference_now: datetime,
) -> dict[str, Any]:
    vocabulary = validator.vocabulary()
    observations: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="masha-semantic-benchmark-") as temporary:
      for index, case in enumerate(cases):
        result = resolver.resolve(
            case["utterance"], vocabulary, profile_id=profile_id,
        )
        operations: list[str] = []
        slots: dict[str, str] = {}
        clarification = False
        rejection: str | None = None
        diagnostic_category: str | None = None
        actual_kind = None
        evidence_items = 0
        grounded_items = 0
        if result.proposal is not None:
            actual_kind = result.proposal.kind
            if result.proposal.kind is SemanticProposalKind.SUPPORTED_ACTION:
                evidence_items = len(result.proposal.extracted_slots)
                source = normalize_utterance(case["utterance"])
                grounded_items = sum(
                    normalize_utterance(item.evidence_text) in source
                    for item in result.proposal.extracted_slots
                )
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
                diagnostic_category = _validation_category(rejection)
        elif result.failure is not None:
            diagnostic_category = (
                "provider_error"
                if result.failure.value in {
                    "provider_error", "provider_unavailable", "timeout",
                    "capability_unavailable", "role_unavailable",
                }
                else result.failure.value
            )
        expected_kind = (
            "ordinary"
            if case["ordinary_conversation"]
            else case.get("expected_kind", "supported_action")
        )
        core_status, core_success = _dialogue_core_result(
            case=case,
            semantic_result=result,
            reference_now=reference_now,
            store_path=Path(temporary) / f"{index}.json",
        )
        observations.append({
            **case,
            "actual_candidate_operations": operations,
            "actual_known_slots": slots,
            "actual_clarification_required": clarification,
            "expected_kind": expected_kind,
            "actual_kind": actual_kind,
            "wire_schema_success": result.proposal is not None,
            "slot_evidence_items": evidence_items,
            "grounded_evidence_items": grounded_items,
            "home_normalization_accepted": (
                result.proposal is not None and rejection is None
            ),
            "failure": result.failure.value if result.failure is not None else None,
            "validation_rejection": rejection,
            "diagnostic_category": diagnostic_category,
            "dialogue_core_status": core_status,
            "dialogue_core_success": core_success,
            "latency_ms": round(result.latency_ms, 3),
        })
    return {
        "profile_id": profile_id,
        "metrics": score_observations(observations),
        "observations": observations,
    }


class _ReplayResolver:
    def __init__(self, result):
        self.result = result

    def resolve(self, *_args, **_kwargs):
        return self.result


def _dialogue_core_result(
    *,
    case: dict[str, Any],
    semantic_result,
    reference_now: datetime,
    store_path: Path,
) -> tuple[str, bool]:
    catalog = default_home_capability_catalog()
    temporal = TemporalEngine(clock=FixedClock(reference_now))
    deterministic = CapabilityCandidateDiscovery(
        catalog=catalog,
        temporal_engine=temporal,
    )
    adoption = V2LiveAdoptionPolicy()
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=deterministic.specifications,
        allowed_operation_ids=adoption.supported_operation_ids,
        date_resolver=HomeCalendarDateResolver(temporal),
    )
    hybrid = HybridCapabilityCandidateDiscovery(
        deterministic=deterministic,
        resolver=_ReplayResolver(semantic_result),
        validator=validator,
    )
    core = DialogueCore(
        discovery=hybrid,
        builder=DeterministicClarificationBuilder(
            catalog=catalog,
            clock=temporal.clock.now_utc,
        ),
        engine=FollowUpResolutionEngine(temporal_engine=temporal),
        store=PendingResolutionStore(store_path, clock=temporal.clock.now_utc),
        adoption=adoption,
    )
    outcome = core.coordinate(case["utterance"], conversation_id="benchmark")
    expected_operations = set(case["expected_candidate_operations"])
    if case.get("expected_kind") == "unsupported_action":
        expected_status = CoordinationStatus.UNSUPPORTED_ACTION
    elif not expected_operations or not expected_operations.issubset(
        adoption.supported_operation_ids
    ):
        expected_status = CoordinationStatus.PASS_THROUGH
    elif case["clarification_required"]:
        expected_status = CoordinationStatus.CLARIFICATION
    else:
        expected_status = CoordinationStatus.RESOLVED_HANDOFF
    return outcome.status.value, outcome.status is expected_status


def _validation_category(rejection: str) -> str:
    if "grounded" in rejection or "invented" in rejection:
        return "grounding_error"
    if "normalization" in rejection or "duration_ambiguous" in rejection:
        return "normalization_error"
    if "operation" in rejection or "slot" in rejection or "candidate" in rejection:
        return "capability_validation_error"
    return "semantic_mismatch"


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
    reference_now = datetime.fromisoformat(
        corpus.get("reference_time", datetime.now(timezone.utc).isoformat())
    )

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
        date_resolver=HomeCalendarDateResolver(
            TemporalEngine(clock=FixedClock(reference_now)),
        ),
    )
    report = {
        "schema_version": "2.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(corpus_path),
        "corpus_cases": len(corpus["cases"]),
        "profiles": [
            run_profile(
                profile_id=profile_id,
                cases=corpus["cases"],
                resolver=resolver,
                validator=validator,
                reference_now=reference_now,
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
