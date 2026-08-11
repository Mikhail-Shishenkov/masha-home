import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.skills.agent_cli import run_command as run_agent_command
from backend.skills.agent_loop import (
    AgentPlan,
    AgentRunError,
    AgentRunReceipt,
    AgentRunStatus,
    AgentRunStore,
    AgentStep,
    AgentStepReceipt,
    AgentStepStatus,
    BoundedAgentLoop,
)
from backend.skills.autonomy import (
    ActionAutonomyPolicyStore,
    ActionAutonomyService,
    ActionDecision,
    ActionRequest,
)
from backend.skills.models import SkillCapability, SkillRisk
from backend.skills.registry import SkillRegistry
from backend.skills.tools import FakeTool, ToolAdapter


NOW = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)


def _package(root: Path) -> Path:
    directory = root / "skills" / "project_observer"
    directory.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "skill_id": "project_observer",
        "name": "Project Observer",
        "version": "1.0.0",
        "description": "A fake-only project skill used by the bounded Agent Loop tests.",
        "entrypoint": None,
        "instructions_file": "SKILL.md",
        "capabilities": ["local_read"],
        "requested_scopes": ["workspace:masha-home"],
        "risk_level": "observe",
        "maximum_autonomy_level": 3,
        "supports_dry_run": True,
        "supports_rollback": False,
        "verification": "Fake Tool returns deterministic evidence for exact input equality.",
    }
    (directory / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "SKILL.md").write_text("# Fake-only test skill\n", encoding="utf-8")
    return directory


def _stack(tmp_path: Path, *, grant: bool = True, tool=None, clock=lambda: NOW):
    package = _package(tmp_path)
    registry = SkillRegistry(
        skills_root=tmp_path / "skills",
        state_path=tmp_path / "local-data" / "config" / "skills.json",
        clock=lambda: NOW,
    )
    registry.register("project_observer")
    policy_store = ActionAutonomyPolicyStore(
        tmp_path / "local-data" / "config" / "action-autonomy.json"
    )
    autonomy = ActionAutonomyService(store=policy_store, registry=registry, clock=lambda: NOW)
    autonomy.set_enabled(True)
    autonomy.set_level(3)
    active_grant = None
    if grant:
        active_grant = autonomy.grant(
            skill_id="project_observer",
            capability=SkillCapability.LOCAL_READ,
            scope="workspace:masha-home",
            maximum_autonomy_level=3,
            maximum_risk=SkillRisk.OBSERVE,
        )
    run_store = AgentRunStore(tmp_path / "local-data" / "runtime" / "agent-runs.json")
    fake = tool or FakeTool()
    loop = BoundedAgentLoop(
        registry=registry,
        policy_store=policy_store,
        run_store=run_store,
        tools=(fake,),
        clock=clock,
    )
    return package, registry, autonomy, active_grant, run_store, fake, loop


def _step(step_id: str, *, operation="echo", value="safe") -> AgentStep:
    return AgentStep(
        step_id=step_id,
        title=f"Проверить шаг {step_id}",
        tool_id="fake",
        operation=operation,
        action=ActionRequest(
            skill_id="project_observer",
            capability=SkillCapability.LOCAL_READ,
            scope="workspace:masha-home",
            risk_level=SkillRisk.OBSERVE,
            required_autonomy_level=1,
        ),
        inputs={"value": value},
    )


def _plan(*steps, plan_id="plan_test_run", max_steps=10, max_duration_seconds=300):
    return AgentPlan(
        plan_id=plan_id,
        goal="Проверить bounded Agent Loop без реального воздействия",
        steps=steps or (_step("step_one"),),
        max_steps=max_steps,
        max_duration_seconds=max_duration_seconds,
        created_at=NOW,
    )


def test_plan_rejects_duplicate_steps_and_unbounded_inputs():
    with pytest.raises(ValidationError, match="duplicate"):
        _plan(_step("step_same"), _step("step_same"))
    with pytest.raises(ValidationError, match="16 KiB"):
        _step("step_large", value="x" * 17_000)


def test_allowed_multistep_plan_executes_verifies_and_persists_receipt(tmp_path):
    _, _, _, _, store, fake, loop = _stack(tmp_path)
    plan = _plan(_step("step_one"), _step("step_two"))

    receipt = loop.run(plan)
    restarted = AgentRunStore(store.path).get(plan.plan_id)

    assert receipt.status == AgentRunStatus.COMPLETED
    assert receipt.terminal_reason == "all_steps_verified"
    assert [item.status for item in receipt.steps] == [AgentStepStatus.VERIFIED] * 2
    assert fake.calls == ["echo", "echo"]
    assert restarted == receipt


def test_completed_plan_is_idempotent_after_restart(tmp_path):
    _, registry, _, _, store, fake, loop = _stack(tmp_path)
    plan = _plan()
    first = loop.run(plan)
    restarted_tool = FakeTool()
    restarted_loop = BoundedAgentLoop(
        registry=registry,
        policy_store=loop.policy_store,
        run_store=AgentRunStore(store.path),
        tools=(restarted_tool,),
        clock=lambda: NOW,
    )

    second = restarted_loop.run(plan)

    assert second == first
    assert fake.calls == ["echo"]
    assert restarted_tool.calls == []


def test_confirmation_pauses_without_execution_and_resume_is_explicit(tmp_path):
    _, _, _, _, _, fake, loop = _stack(tmp_path, grant=False)
    plan = _plan()

    waiting = loop.run(plan)
    confirmed = loop.confirm(plan.plan_id, "step_one")

    assert waiting.status == confirmed.status == AgentRunStatus.AWAITING_CONFIRMATION
    assert confirmed.steps[0].confirmed_at == NOW
    assert confirmed.steps[0].confirmed_by == "misha"
    assert fake.calls == []

    completed = loop.run(plan)
    assert completed.status == AgentRunStatus.COMPLETED
    assert fake.calls == ["echo"]


def test_confirmation_cannot_override_a_denied_run(tmp_path):
    _, registry, autonomy, _, _, fake, loop = _stack(tmp_path)
    autonomy.set_enabled(False)

    receipt = loop.run(_plan())

    assert receipt.status == AgentRunStatus.DENIED
    assert receipt.terminal_reason == "action_autonomy_disabled"
    assert fake.calls == []
    with pytest.raises(AgentRunError, match="not awaiting"):
        loop.confirm(receipt.plan_id, "step_one")


def test_step_budget_stops_before_extra_execution(tmp_path):
    _, _, _, _, _, fake, loop = _stack(tmp_path)

    receipt = loop.run(
        _plan(_step("step_one"), _step("step_two"), max_steps=1)
    )

    assert receipt.status == AgentRunStatus.BUDGET_EXHAUSTED
    assert receipt.terminal_reason == "step_budget_exhausted"
    assert fake.calls == ["echo"]


def test_exact_time_budget_boundary_stops_without_execution(tmp_path):
    _, _, _, _, store, fake, loop = _stack(
        tmp_path,
        clock=lambda: NOW + timedelta(seconds=10),
    )
    plan = _plan(max_duration_seconds=10)
    store.save(
        AgentRunReceipt(
            plan_id=plan.plan_id,
            plan_sha256=plan.digest(),
            goal=plan.goal,
            status=AgentRunStatus.RUNNING,
            started_at=NOW,
            updated_at=NOW,
        )
    )

    receipt = loop.run(plan)

    assert receipt.status == AgentRunStatus.BUDGET_EXHAUSTED
    assert receipt.terminal_reason == "time_budget_exhausted"
    assert fake.calls == []


@pytest.mark.parametrize(
    ("operation", "reason", "verification"),
    [
        ("fail", "simulated_failure", "fake-failed"),
        ("unverified", "verification_failed", "simulated_unverified_result"),
    ],
)
def test_failed_or_unverified_result_is_never_called_completed(tmp_path, operation, reason, verification):
    _, _, _, _, _, fake, loop = _stack(tmp_path)

    receipt = loop.run(_plan(_step("step_one", operation=operation)))
    repeated = loop.run(_plan(_step("step_one", operation=operation)))

    assert receipt.status == AgentRunStatus.FAILED
    assert receipt.terminal_reason == reason
    assert receipt.steps[0].status == AgentStepStatus.FAILED
    assert verification in receipt.steps[0].verification_code
    assert repeated == receipt
    assert fake.calls == [operation]


def test_missing_tool_fails_without_execution(tmp_path):
    package = _package(tmp_path)
    registry = SkillRegistry(
        skills_root=tmp_path / "skills",
        state_path=tmp_path / "skills.json",
        clock=lambda: NOW,
    )
    registry.register("project_observer")
    policy = ActionAutonomyPolicyStore(tmp_path / "policy.json")
    autonomy = ActionAutonomyService(store=policy, registry=registry, clock=lambda: NOW)
    autonomy.set_enabled(True)
    autonomy.set_level(3)
    loop = BoundedAgentLoop(
        registry=registry,
        policy_store=policy,
        run_store=AgentRunStore(tmp_path / "runs.json"),
        tools=(),
        clock=lambda: NOW,
    )

    receipt = loop.run(_plan())

    assert package.exists()
    assert receipt.status == AgentRunStatus.FAILED
    assert receipt.terminal_reason == "tool_not_injected"


def test_injected_tool_must_belong_to_authorized_skill(tmp_path):
    wrong_tool = FakeTool(skill_id="different_skill")
    _, _, _, _, _, _, loop = _stack(tmp_path, tool=wrong_tool)

    receipt = loop.run(_plan())

    assert receipt.status == AgentRunStatus.FAILED
    assert receipt.terminal_reason == "tool_skill_mismatch"
    assert wrong_tool.calls == []


def test_policy_is_re_evaluated_before_every_step(tmp_path):
    holder = {}

    def revoke_after_first(_operation):
        if holder["grant"] is not None:
            holder["autonomy"].revoke(holder["grant"].grant_id)
            holder["grant"] = None

    fake = FakeTool(on_execute=revoke_after_first)
    _, _, autonomy, grant, _, _, loop = _stack(tmp_path, tool=fake)
    holder.update(autonomy=autonomy, grant=grant)

    receipt = loop.run(_plan(_step("step_one"), _step("step_two")))

    assert receipt.status == AgentRunStatus.AWAITING_CONFIRMATION
    assert [item.status for item in receipt.steps] == [
        AgentStepStatus.VERIFIED,
        AgentStepStatus.AWAITING_CONFIRMATION,
    ]
    assert fake.calls == ["echo"]


def test_skill_integrity_is_rechecked_before_every_step(tmp_path):
    holder = {}

    def tamper_after_first(_operation):
        holder["instructions"].write_text("tampered", encoding="utf-8")

    fake = FakeTool(on_execute=tamper_after_first)
    package, _, _, _, _, _, loop = _stack(tmp_path, tool=fake)
    holder["instructions"] = package / "SKILL.md"

    receipt = loop.run(_plan(_step("step_one"), _step("step_two")))

    assert receipt.status == AgentRunStatus.DENIED
    assert receipt.terminal_reason == "skill_modified"
    assert fake.calls == ["echo"]


class ExplodingTool(FakeTool):
    def execute(self, operation, inputs):
        self.calls.append(operation)
        raise RuntimeError("boom")


def test_tool_exception_is_controlled_and_not_retried(tmp_path):
    exploding = ExplodingTool()
    _, _, _, _, _, _, loop = _stack(tmp_path, tool=exploding)
    plan = _plan()

    receipt = loop.run(plan)
    repeated = loop.run(plan)

    assert receipt.status == AgentRunStatus.FAILED
    assert receipt.terminal_reason == "tool_exception"
    assert receipt.steps[0].verification_code == "tool_exception:RuntimeError"
    assert repeated == receipt
    assert exploding.calls == ["echo"]


def test_interrupted_executing_receipt_is_not_replayed_after_restart(tmp_path):
    _, _, _, _, store, fake, loop = _stack(tmp_path)
    plan = _plan()
    store.save(
        AgentRunReceipt(
            plan_id=plan.plan_id,
            plan_sha256=plan.digest(),
            goal=plan.goal,
            status=AgentRunStatus.RUNNING,
            started_at=NOW,
            updated_at=NOW,
            steps=(
                AgentStepReceipt(
                    step_id="step_one",
                    title="Проверить шаг step_one",
                    tool_id="fake",
                    operation="echo",
                    status=AgentStepStatus.EXECUTING,
                    policy_decision=ActionDecision.ALLOW,
                    policy_reason="standing_grant",
                    started_at=NOW,
                ),
            ),
        )
    )

    receipt = loop.run(plan)

    assert receipt.status == AgentRunStatus.FAILED
    assert receipt.terminal_reason == "interrupted_execution_requires_review"
    assert fake.calls == []


def test_receipt_excludes_raw_inputs_and_tool_outputs(tmp_path):
    _, _, _, _, store, _, loop = _stack(tmp_path)
    secret = "PRIVATE_STEP_INPUT_123"

    loop.run(_plan(_step("step_one", value=secret)))
    raw = store.path.read_text(encoding="utf-8")

    assert secret not in raw
    assert "result_summary" in raw
    assert "verification_code" in raw


def test_verified_output_can_be_consumed_without_persistence(tmp_path):
    _, _, _, _, store, _, loop = _stack(tmp_path)
    secret = "EPHEMERAL_OUTPUT_456"
    captured = []

    receipt = loop.run(
        _plan(_step("step_one", value=secret)),
        on_verified_result=lambda _step, result: captured.append(result.output),
    )

    assert receipt.status == AgentRunStatus.COMPLETED
    assert captured == [{"value": secret}]
    assert secret not in store.path.read_text(encoding="utf-8")


def test_same_plan_id_with_changed_content_is_rejected(tmp_path):
    _, _, _, _, _, fake, loop = _stack(tmp_path)
    loop.run(_plan(_step("step_one", value="first")))

    with pytest.raises(AgentRunError, match="different plan"):
        loop.run(_plan(_step("step_one", value="changed")))
    assert fake.calls == ["echo"]


def test_agent_cli_is_read_only_human_facing_and_hides_plan_hash(tmp_path):
    _, _, _, _, store, _, loop = _stack(tmp_path)
    receipt = loop.run(_plan())
    output: list[str] = []

    assert run_agent_command("runs", store=store, output=output.append) == 0
    assert run_agent_command("show", store=store, number="1", output=output.append) == 0

    rendered = "\n".join(output)
    assert receipt.goal in rendered
    assert "завершено и проверено" in rendered
    assert receipt.plan_id not in rendered
    assert receipt.plan_sha256 not in rendered


def test_empty_agent_cli_is_read_only(tmp_path):
    store = AgentRunStore(tmp_path / "agent-runs.json")
    output: list[str] = []

    assert run_agent_command("runs", store=store, output=output.append) == 0

    assert output == ["Агентных запусков пока нет."]
    assert store.path.exists() is False


def test_run_store_is_bounded(tmp_path):
    store = AgentRunStore(tmp_path / "agent-runs.json", limit=2)
    for index in range(3):
        store.save(
            AgentRunReceipt(
                plan_id=f"plan_test_{index}",
                plan_sha256="a" * 64,
                goal=f"Тестовая задача номер {index}",
                status=AgentRunStatus.COMPLETED,
                started_at=NOW,
                updated_at=NOW,
                finished_at=NOW,
                terminal_reason="all_steps_verified",
            )
        )

    assert [item.plan_id for item in store.list()] == ["plan_test_1", "plan_test_2"]
