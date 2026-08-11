import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.skills.agent_loop import AgentRunReceipt, AgentRunStatus, AgentRunStore
from backend.skills.autonomy import ActionAutonomyPolicyStore, ActionAutonomyService
from backend.skills.cli import build_registry
from backend.skills.installer import (
    SkillInstallAction,
    SkillInstallProposal,
    SkillInstallProposalStore,
)
from backend.skills.models import SkillCapability, SkillRisk
from backend.skills.permissions_cli import build_service, run_command
from backend.temporal.proactive import ProactivePolicy


NOW = datetime(2026, 8, 11, 21, 30, tzinfo=timezone.utc)
SOURCE_PACKAGE = Path(__file__).parents[1] / "skills" / "project_observer"


def _configured_root(tmp_path: Path) -> Path:
    root = tmp_path / "masha"
    shutil.copytree(SOURCE_PACKAGE, root / "skills" / "project_observer")
    registry = build_registry(root)
    registry.register("project_observer")
    policy_store = ActionAutonomyPolicyStore(
        root / "local-data" / "config" / "action-autonomy.json"
    )
    autonomy = ActionAutonomyService(
        store=policy_store,
        registry=registry,
        clock=lambda: NOW,
    )
    autonomy.set_enabled(True)
    autonomy.set_level(1)
    autonomy.grant(
        skill_id="project_observer",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=1,
        maximum_risk=SkillRisk.OBSERVE,
    )
    config = root / "local-data" / "config"
    (config / "proactive-policy.json").write_text(
        json.dumps(
            ProactivePolicy(
                enabled=True,
                proactive_level=2,
                allow_commitment_reminders=True,
                allow_checkins=True,
            ).model_dump(mode="json")
        ),
        encoding="utf-8",
    )
    return root


def test_permissions_status_is_read_only_with_safe_defaults(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    service = build_service(root)
    outputs = []

    assert run_command("status", service=service, output=outputs.append) == 0

    assert "Аварийная остановка: выключена" in outputs[0]
    assert not (root / "local-data" / "config" / "autonomy-safety.json").exists()
    assert not (root / "local-data" / "config" / "action-autonomy.json").exists()
    assert not (root / "local-data" / "config" / "proactive-policy.json").exists()


def test_emergency_stop_persists_and_overlays_permissions_without_mutating_policies(tmp_path):
    root = _configured_root(tmp_path)
    config = root / "local-data" / "config"
    action_path = config / "action-autonomy.json"
    proactive_path = config / "proactive-policy.json"
    before_action = action_path.read_bytes()
    before_proactive = proactive_path.read_bytes()
    service = build_service(root)

    initial = service.snapshot()
    assert initial.action_autonomy.grants_effective == 1
    assert initial.grants[0].effective_autonomy_level == 1
    assert run_command(
        "stop",
        service=service,
        arguments=("остановлено", "Мишей"),
        output=lambda _: None,
    ) == 0

    restarted = build_service(root)
    stopped = restarted.snapshot()
    assert stopped.safety.emergency_stop_engaged is True
    assert stopped.safety.reason == "остановлено Мишей"
    assert stopped.action_autonomy.grants_effective == 0
    assert stopped.grants[0].reason == "emergency_stop_engaged"
    assert stopped.grants[0].effective_autonomy_level == 0
    assert stopped.proactive_autonomy.enabled is True
    assert action_path.read_bytes() == before_action
    assert proactive_path.read_bytes() == before_proactive

    assert run_command("resume", service=restarted, output=lambda _: None) == 0
    released = build_service(root).snapshot()
    assert released.safety.emergency_stop_engaged is False
    assert released.action_autonomy.grants_effective == 1
    assert released.proactive_autonomy.background_runtime_running is False
    assert action_path.read_bytes() == before_action
    assert proactive_path.read_bytes() == before_proactive


def test_unified_snapshot_collects_pending_work_and_hides_ids_in_human_output(tmp_path):
    root = _configured_root(tmp_path)
    config = root / "local-data" / "config"
    proposal = SkillInstallProposal(
        proposal_id="skill_install_00000000-0000-0000-0000-000000000001",
        action=SkillInstallAction.INSTALL,
        skill_id="project_observer",
        name="Project Observer",
        source_label="observer.zip",
        proposed_version="2.0.0",
        proposed_package_sha256="a" * 64,
        capabilities=(SkillCapability.LOCAL_READ,),
        requested_scopes=("workspace:masha-home",),
        risk_level=SkillRisk.OBSERVE,
        maximum_autonomy_level=1,
        files_added=("skill.json",),
        runtime_supported=True,
        staged_relative_path="skill_install/test/package",
        created_at=NOW,
    )
    SkillInstallProposalStore(config / "skill-installs.json").save(proposal)
    AgentRunStore(root / "local-data" / "runtime" / "agent-runs.json").save(
        AgentRunReceipt(
            plan_id="plan_waiting_permission",
            plan_sha256="b" * 64,
            goal="Проверить локальный проект",
            status=AgentRunStatus.AWAITING_CONFIRMATION,
            started_at=NOW,
            updated_at=NOW,
        )
    )
    service = build_service(root)
    outputs = []

    snapshot = service.snapshot()
    assert {item.kind.value for item in snapshot.pending} == {
        "skill_install",
        "agent_confirmation",
    }
    assert snapshot.active_agent_runs == 1
    assert run_command("pending", service=service, output=outputs.append) == 0
    assert "Project Observer" in outputs[0]
    assert "Проверить локальный проект" in outputs[0]
    assert "skill_install_" not in outputs[0]
    assert "plan_waiting_permission" not in outputs[0]


def test_safety_engage_and_release_are_idempotent(tmp_path):
    store = AutonomySafetyStore(tmp_path / "safety.json")
    service = AutonomySafetyService(store=store, clock=lambda: NOW)

    first = service.engage("manual")
    repeated = service.engage("different text is ignored while engaged")
    released = service.release()
    repeated_release = service.release()

    assert first == repeated
    assert first.revision == 1
    assert released == repeated_release
    assert released.revision == 2
