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
from .turn_context import (
    TurnContextEnvelope,
    TurnPresentedEntityHint,
    TurnTemporalContext,
)
from backend.temporal.date_resolution import HomeCalendarDateResolver
from backend.temporal.temporal_engine import FixedClock, TemporalEngine
from backend.connectors.presented_read_sets import (
    PresentedReadSetRegistry,
    parse_presented_entity_reference,
)


DEFAULT_CORPUS = Path("tests/fixtures/misha_semantic_resolver_benchmark.json")
DEFAULT_OUTPUT_DIR = Path("local-data/model-benchmarks")
_STRICT_PRESEMANTIC_OWNERS = frozenset((
    "google_drive.document.create", "web.search", "web.fetch",
))


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
    forbidden_candidate_presences = 0
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
    action_request_cases = 0
    action_request_evidence_present = 0
    action_request_evidence_grounded = 0
    action_request_home_accepted = 0
    ordinary_action_evidence_absent = 0
    scheduling_cases = 0
    selection_present = 0
    selection_grounded = 0
    selection_home_accepted = 0
    explicit_scheduling_cases = 0
    explicit_scheduling_correct = 0
    ambiguous_scheduling_cases = 0
    ambiguous_scheduling_correct = 0
    ambiguous_selection_not_authorized = 0
    ambiguous_final_candidate_set_preserved = 0
    update_cases = 0
    update_create_confusions = 0
    create_cases = 0
    create_update_confusions = 0
    contextual_entity_cases = 0
    contextual_entity_recognized = 0
    contextual_entity_application_resolved = 0
    recognized_action_cases = 0
    recognized_action_fallthroughs = 0
    incorrect_capability_handoffs = 0
    failure_categories: dict[str, int] = {}
    latencies = []
    for item in observations:
        expected_operations = item["expected_candidate_operations"]
        actual_operations = item["actual_candidate_operations"]
        focus = item.get("benchmark_focus")
        if focus == "calendar_update":
            update_cases += 1
            update_create_confusions += "google_calendar.event.create" in actual_operations
        elif focus == "calendar_create":
            create_cases += 1
            create_update_confusions += "google_calendar.event.update" in actual_operations
        elif focus == "contextual_entity":
            contextual_entity_cases += 1
            contextual_entity_recognized += bool(
                expected_operations
                and expected_operations[0] in actual_operations
            )
            contextual_entity_application_resolved += _contextual_entity_resolves(
                item["utterance"],
                expected_operations[0] if expected_operations else "",
            )
        if actual_operations and not set(actual_operations).issubset(
            _STRICT_PRESEMANTIC_OWNERS
        ):
            recognized_action_cases += 1
            recognized_action_fallthroughs += item.get("dialogue_core_status") == "pass_through"
            incorrect_capability_handoffs += bool(
                item.get("dialogue_core_status") == "resolved_handoff"
                and set(actual_operations) != set(expected_operations)
            )
        wire_success += item.get("wire_schema_success", False)
        kind_correct += (
            item.get("actual_kind") is not None
            and item.get("actual_kind") == item.get("expected_kind")
        )
        grounded_evidence += item.get("grounded_evidence_items", 0)
        evidence_items += item.get("slot_evidence_items", 0)
        normalization_accepted += item.get("home_normalization_accepted", False)
        if item["ordinary_conversation"]:
            ordinary_action_evidence_absent += not item.get(
                "action_request_evidence_present", False,
            )
        else:
            action_request_cases += 1
            action_request_evidence_present += item.get(
                "action_request_evidence_present", False,
            )
            action_request_evidence_grounded += item.get(
                "action_request_evidence_grounded", False,
            )
            action_request_home_accepted += item.get(
                "action_request_home_accepted", False,
            )
        if item.get("category") == "scheduling":
            scheduling_cases += 1
            selection_present += item.get("operation_selection_evidence_present", False)
            selection_grounded += item.get("operation_selection_evidence_grounded", False)
            selection_home_accepted += item.get("operation_selection_home_accepted", False)
            expectation = item.get("operation_selection_expectation")
            if expectation == "explicit":
                explicit_scheduling_cases += 1
                explicit_scheduling_correct += (
                    item.get("operation_selection_home_accepted", False)
                    and item.get("operation_selection_operation_id")
                    == (expected_operations[0] if len(expected_operations) == 1 else None)
                    and actual_operations == expected_operations
                )
            elif expectation == "ambiguous":
                ambiguous_scheduling_cases += 1
                ambiguous_scheduling_correct += (
                    not item.get("operation_selection_evidence_present", False)
                    and actual_operations == expected_operations
                )
                ambiguous_selection_not_authorized += not item.get(
                    "operation_selection_home_accepted", False,
                )
                ambiguous_final_candidate_set_preserved += (
                    actual_operations == expected_operations
                    and item.get("actual_clarification_required", False)
                )
        exact_candidates += actual_operations == expected_operations
        clarification_correct += (
            item["actual_clarification_required"]
            == item["clarification_required"]
        )
        forbidden = set(item["forbidden_operations"])
        if forbidden:
            forbidden_cases += 1
            forbidden_candidate_presences += bool(
                forbidden & set(actual_operations)
            )
            # A clarification retains choices but has not authorized an
            # operation.  The action FPR therefore measures only an adopted
            # Dialogue Core handoff; candidate noise remains separately visible.
            forbidden_false_positives += bool(
                forbidden & set(actual_operations)
                and item.get("dialogue_core_status") == "resolved_handoff"
            )
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
        "forbidden_candidate_presence_rate_percent": _percent(
            forbidden_candidate_presences, forbidden_cases,
        ),
        "clarification_accuracy_percent": _percent(clarification_correct, total),
        "slot_extraction_accuracy_percent": _percent(correct_slots, expected_slots),
        "slot_evidence_grounding_percent": _percent(
            grounded_evidence, evidence_items,
        ),
        "home_normalization_acceptance_percent": _percent(
            normalization_accepted, total,
        ),
        "action_request_grounding": {
            "action_cases": action_request_cases,
            "evidence_present_percent": _percent(
                action_request_evidence_present, action_request_cases,
            ),
            "evidence_grounded_percent": _percent(
                action_request_evidence_grounded,
                action_request_evidence_present,
            ),
            "home_accepted_percent": _percent(
                action_request_home_accepted, action_request_cases,
            ),
            "ordinary_evidence_correctly_absent_percent": _percent(
                ordinary_action_evidence_absent, ordinary_cases,
            ),
        },
        "scheduling_operation_selection": {
            "cases": scheduling_cases,
            "evidence_present_percent": _percent(selection_present, scheduling_cases),
            "evidence_grounded_percent": _percent(selection_grounded, selection_present),
            "home_accepted_percent": _percent(selection_home_accepted, selection_present),
            "explicit_selection_correct_percent": _percent(
                explicit_scheduling_correct, explicit_scheduling_cases,
            ),
            "ambiguous_selection_correctly_absent_percent": _percent(
                ambiguous_scheduling_correct, ambiguous_scheduling_cases,
            ),
            "ambiguous_selection_not_authorized_percent": _percent(
                ambiguous_selection_not_authorized, ambiguous_scheduling_cases,
            ),
            "ambiguous_final_candidate_set_preserved_percent": _percent(
                ambiguous_final_candidate_set_preserved,
                ambiguous_scheduling_cases,
            ),
            "explicit_cases": explicit_scheduling_cases,
            "ambiguous_cases": ambiguous_scheduling_cases,
        },
        "action_continuity": {
            "calendar_update_cases": update_cases,
            "calendar_update_to_create_confusion_rate_percent": _percent(
                update_create_confusions, update_cases,
            ),
            "calendar_create_cases": create_cases,
            "calendar_create_to_update_confusion_rate_percent": _percent(
                create_update_confusions, create_cases,
            ),
            "contextual_entity_cases": contextual_entity_cases,
            "contextual_entity_recognition_percent": _percent(
                contextual_entity_recognized, contextual_entity_cases,
            ),
            "contextual_entity_application_resolution_percent": _percent(
                contextual_entity_application_resolved, contextual_entity_cases,
            ),
            "recognized_action_fallthrough_rate_percent": _percent(
                recognized_action_fallthroughs, recognized_action_cases,
            ),
            "incorrect_capability_handoff_rate_percent": _percent(
                incorrect_capability_handoffs, recognized_action_cases,
            ),
        },
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


def _contextual_entity_resolves(
    utterance: str,
    operation_id: str,
) -> bool:
    """Exercise Home-owned contextual resolution without any provider call."""

    class _Mail:
        subject = "Одно новое письмо"

    registry = PresentedReadSetRegistry()
    registry.present(
        "benchmark", "yandex_mail", (_Mail(),),
        entity_kind="письмо", presentation_kind="unread",
    )
    reference = parse_presented_entity_reference(
        utterance,
        entity_kind="письмо",
        visible_labels=("Одно новое письмо",),
        require_read_action=operation_id == "yandex_mail.read",
    )
    if reference is None:
        return False
    required = (
        "unread"
        if operation_id == "yandex_mail.read"
        and reference.kind.value == "contextual_class"
        else None
    )
    resolution = registry.resolve(
        "benchmark",
        owner="yandex_mail",
        entity_kind="письмо",
        reference=reference,
        label_of=lambda item: item.subject,
        required_presentation_kind=required,
    )
    return resolution.status == "resolved" and resolution.item is not None


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
        turn_context = _benchmark_turn_context(case, reference_now)
        result = resolver.resolve(
            case["utterance"],
            vocabulary,
            profile_id=profile_id,
            turn_context=turn_context,
        )
        operations: list[str] = []
        slots: dict[str, str] = {}
        clarification = False
        rejection: str | None = None
        diagnostic_category: str | None = None
        actual_kind = None
        evidence_items = 0
        grounded_items = 0
        selection_present = False
        selection_grounded = False
        selection_operation_id = None
        selection_home_accepted = False
        selection_trace_accepted = False
        selection_validation_reason = None
        action_request_present = False
        action_request_grounded = False
        action_request_home_accepted = False
        action_request_validation_reason = None
        accepted_slot_fields: list[str] = []
        rejected_slot_fields: list[dict[str, str]] = []
        proposed_operation_ids: list[str] = []
        if result.proposal is not None:
            actual_kind = result.proposal.kind
            proposed_operation_ids = list(result.proposal.candidate_operation_ids)
            action_request = result.proposal.action_request_evidence
            action_request_present = action_request.is_present
            action_request_grounded = (
                action_request_present
                and normalize_utterance(action_request.evidence_text or "")
                in normalize_utterance(case["utterance"])
            )
            selection = result.proposal.operation_selection_evidence
            selection_present = selection.is_present
            selection_operation_id = selection.operation_id
            selection_grounded = (
                selection_present
                and normalize_utterance(selection.evidence_text or "")
                in normalize_utterance(case["utterance"])
            )
            if result.proposal.kind is SemanticProposalKind.SUPPORTED_ACTION:
                evidence_items = len(result.proposal.extracted_slots)
                source = normalize_utterance(case["utterance"])
                grounded_items = sum(
                    normalize_utterance(item.evidence_text) in source
                    for item in result.proposal.extracted_slots
                )
            try:
                frame = validator.validate(
                    case["utterance"],
                    result.proposal,
                    turn_context=turn_context,
                )
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
                selection_home_accepted = (
                    selection_present
                    and selection_grounded
                    and operations == [selection_operation_id]
                )
                trace = validator.last_trace
                if trace is not None:
                    if trace.action_request is not None:
                        action_request_home_accepted = trace.action_request.accepted
                        action_request_validation_reason = trace.action_request.reason
                    if trace.operation_selection is not None:
                        selection_trace_accepted = trace.operation_selection.accepted
                        selection_validation_reason = trace.operation_selection.reason
                    accepted_slot_fields = [
                        item.name for item in trace.slots if item.accepted
                    ]
                    rejected_slot_fields = [
                        {"name": item.name, "reason": item.reason or "rejected"}
                        for item in trace.slots if not item.accepted
                    ]
            except ValueError as error:
                rejection = str(error)
                diagnostic_category = _validation_category(rejection)
                trace = validator.last_trace
                if trace is not None and trace.action_request is not None:
                    action_request_home_accepted = trace.action_request.accepted
                    action_request_validation_reason = trace.action_request.reason
        elif result.failure is not None:
            diagnostic_category = (
                "provider_error"
                if result.failure.value in {
                    "provider_error", "provider_unavailable", "timeout",
                    "capability_unavailable", "role_unavailable",
                }
                else result.failure.value
            )
        home_frame, home_rejection = _home_interpretation_result(
            case=case,
            semantic_result=result,
            reference_now=reference_now,
        )
        operations = [item.operation_id for item in home_frame.candidates]
        slots = {
            item.name: item.value
            for item in home_frame.slots
            if item.value is not None
        }
        clarification = (
            home_frame.resolution_state
            is InterpretationResolutionState.CLARIFICATION_REQUIRED
        )
        selection_home_accepted = bool(
            selection_present
            and selection_grounded
            and selection_trace_accepted
            and operations == [selection_operation_id]
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
            "model_proposed_operation_ids": proposed_operation_ids,
            "actual_known_slots": slots,
            "actual_clarification_required": clarification,
            "expected_kind": expected_kind,
            "actual_kind": actual_kind,
            "wire_schema_success": result.proposal is not None,
            "slot_evidence_items": evidence_items,
            "grounded_evidence_items": grounded_items,
            "action_request_evidence_present": action_request_present,
            "action_request_evidence_grounded": action_request_grounded,
            "action_request_home_accepted": action_request_home_accepted,
            "action_request_validation_reason": action_request_validation_reason,
            "operation_selection_evidence_present": selection_present,
            "operation_selection_evidence_grounded": selection_grounded,
            "operation_selection_operation_id": selection_operation_id,
            "operation_selection_home_accepted": selection_home_accepted,
            "operation_selection_validation_reason": selection_validation_reason,
            "accepted_slot_fields": accepted_slot_fields,
            "rejected_slot_fields": rejected_slot_fields,
            "home_normalization_accepted": (
                result.proposal is not None and rejection is None
            ),
            "failure": result.failure.value if result.failure is not None else None,
            "validation_rejection": rejection,
            "home_semantic_rejection": home_rejection,
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


def _home_interpretation_result(
    *,
    case: dict[str, Any],
    semantic_result,
    reference_now: datetime,
):
    """Replay one model result through the exact Home-owned hybrid boundary."""

    catalog = default_home_capability_catalog()
    temporal = TemporalEngine(clock=FixedClock(reference_now))
    deterministic = CapabilityCandidateDiscovery(
        catalog=catalog,
        temporal_engine=temporal,
    )
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=deterministic.specifications,
        known_operation_ids=frozenset(deterministic.specifications.operation_ids),
        date_resolver=HomeCalendarDateResolver(temporal),
    )
    hybrid = HybridCapabilityCandidateDiscovery(
        deterministic=deterministic,
        resolver=_ReplayResolver(semantic_result),
        validator=validator,
    )
    frame = hybrid.interpret(
        case["utterance"],
        turn_context=_benchmark_turn_context(case, reference_now),
    )
    return frame, hybrid.last_rejection


def _benchmark_turn_context(
    case: dict[str, Any],
    reference_now: datetime,
) -> TurnContextEnvelope:
    """Mirror the bounded production context without provider calls or IDs."""

    temporal = TemporalEngine(clock=FixedClock(reference_now)).context(
        None,
        user_message=case["utterance"],
    )
    presented = ()
    if case.get("benchmark_focus") == "contextual_entity":
        presented = (TurnPresentedEntityHint(
            reference="P1",
            position=1,
            owner_operation_id="yandex_mail.read",
            kind="письмо",
            human_label="Одно новое письмо",
            time_text="сегодня",
        ),)
    return TurnContextEnvelope(
        temporal=TurnTemporalContext.from_temporal_context(temporal),
        presented_entities=presented,
    )


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
    expected_operations = set(case["expected_candidate_operations"])
    if expected_operations and expected_operations.issubset(
        _STRICT_PRESEMANTIC_OWNERS
    ):
        # Production never offers these structurally protected requests to
        # DialogueCore. Record the real owner instead of grading a synthetic
        # direct-core call that cannot occur in Home.
        return "protected_presemantic_owner", True

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
        known_operation_ids=frozenset(deterministic.specifications.operation_ids),
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
    outcome = core.coordinate(
        case["utterance"],
        conversation_id="benchmark",
        turn_context=_benchmark_turn_context(case, reference_now),
    )
    if case.get("expected_kind") == "unsupported_action":
        expected_status = CoordinationStatus.UNSUPPORTED_ACTION
    elif not expected_operations:
        expected_status = CoordinationStatus.PASS_THROUGH
    elif not expected_operations.issubset(adoption.supported_operation_ids):
        expected_status = CoordinationStatus.UNSUPPORTED_ACTION
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
        "--profiles", nargs="+", default=("fast",),
        help="Configured local model profile IDs (default: fast).",
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
    validator = SemanticProposalValidator(
        catalog=catalog,
        specifications=specifications,
        known_operation_ids=frozenset(specifications.operation_ids),
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
