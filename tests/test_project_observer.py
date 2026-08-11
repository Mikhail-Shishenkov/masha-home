import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from backend.skills.agent_loop import AgentRunStatus, AgentRunStore, BoundedAgentLoop
from backend.skills.autonomy import (
    ActionAutonomyPolicyStore,
    ActionAutonomyService,
)
from backend.skills.models import SkillCapability, SkillRisk
from backend.skills.observe_cli import run_command
from backend.skills.project_observer import ProjectObserverTool
from backend.skills.project_observer_service import ProjectObserverService
from backend.skills.registry import SkillRegistry
from backend.runtime.safety import AutonomySafetyStore


NOW = datetime(2026, 8, 11, 21, 0, tzinfo=timezone.utc)
SOURCE_PACKAGE = Path(__file__).parents[1] / "skills" / "project_observer"


def _stack(tmp_path: Path, *, grant: bool = True):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copytree(SOURCE_PACKAGE, workspace / "skills" / "project_observer")
    registry = SkillRegistry(
        skills_root=workspace / "skills",
        state_path=workspace / "local-data" / "config" / "skills.json",
        clock=lambda: NOW,
    )
    registry.register("project_observer")
    policy_store = ActionAutonomyPolicyStore(
        workspace / "local-data" / "config" / "action-autonomy.json"
    )
    autonomy = ActionAutonomyService(store=policy_store, registry=registry, clock=lambda: NOW)
    autonomy.set_enabled(True)
    autonomy.set_level(1)
    if grant:
        autonomy.grant(
            skill_id="project_observer",
            capability=SkillCapability.LOCAL_READ,
            scope="workspace:masha-home",
            maximum_autonomy_level=1,
            maximum_risk=SkillRisk.OBSERVE,
        )
    run_store = AgentRunStore(workspace / "local-data" / "runtime" / "agent-runs.json")
    tool = ProjectObserverTool(workspace)
    loop = BoundedAgentLoop(
        registry=registry,
        policy_store=policy_store,
        safety_store=AutonomySafetyStore(
            workspace / "local-data" / "config" / "autonomy-safety.json"
        ),
        run_store=run_store,
        tools=(tool,),
        clock=lambda: NOW,
    )
    service = ProjectObserverService(agent_loop=loop, clock=lambda: NOW)
    return workspace, registry, autonomy, run_store, tool, service


def test_real_package_is_declarative_and_read_only():
    manifest = json.loads((SOURCE_PACKAGE / "skill.json").read_text(encoding="utf-8"))

    assert manifest["entrypoint"] is None
    assert manifest["capabilities"] == ["local_read"]
    assert manifest["requested_scopes"] == ["workspace:masha-home"]
    assert manifest["risk_level"] == "observe"
    assert manifest["maximum_autonomy_level"] == 1


def test_bounded_tree_is_sorted_and_hides_protected_paths(tmp_path):
    workspace, _, _, _, _, service = _stack(tmp_path)
    (workspace / "zeta.txt").write_text("z", encoding="utf-8")
    (workspace / "alpha").mkdir()
    (workspace / "alpha" / "visible.py").write_text("pass\n", encoding="utf-8")
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("private", encoding="utf-8")
    (workspace / ".env").write_text("TOKEN=secret", encoding="utf-8")

    result = service.observe(
        "list_tree",
        {"path": ".", "max_depth": 2, "max_entries": 100},
    )
    paths = [item["path"] for item in result.output["entries"]]

    assert result.receipt.status == AgentRunStatus.COMPLETED
    assert "alpha/visible.py" in paths
    assert ".git" not in paths
    assert ".git/config" not in paths
    assert ".env" not in paths
    assert "local-data" not in paths
    assert paths[:3] == ["alpha", "skills", "zeta.txt"]


def test_text_read_returns_verified_ephemeral_output_only(tmp_path):
    workspace, _, _, run_store, _, service = _stack(tmp_path)
    content = "PRIVATE_OBSERVER_CONTENT\nПривет, Маша."
    (workspace / "notes.md").write_text(content, encoding="utf-8")

    result = service.observe("read_text", {"path": "notes.md", "max_chars": 200})
    journal = run_store.path.read_text(encoding="utf-8")

    assert result.receipt.status == AgentRunStatus.COMPLETED
    assert result.output["content"] == content
    assert result.output["truncated"] is False
    assert content not in journal
    assert "notes.md" not in journal


def test_text_read_is_bounded_and_reports_truncation(tmp_path):
    workspace, _, _, _, _, service = _stack(tmp_path)
    (workspace / "long.txt").write_text("abcdefghij", encoding="utf-8")

    result = service.observe("read_text", {"path": "long.txt", "max_chars": 4})

    assert result.output["content"] == "abcd"
    assert result.output["truncated"] is True


def test_inspect_path_returns_size_and_verified_hash(tmp_path):
    workspace, _, _, _, _, service = _stack(tmp_path)
    path = workspace / "module.py"
    path.write_text("print('safe')\n", encoding="utf-8")

    result = service.observe("inspect_path", {"path": "module.py"})

    assert result.output["type"] == "file"
    assert result.output["size_bytes"] == path.stat().st_size
    assert len(result.output["sha256"]) == 64


def test_protected_traversal_absolute_and_secret_paths_are_blocked(tmp_path):
    workspace, _, _, _, tool, _ = _stack(tmp_path)
    (workspace / ".env").write_text("SECRET=yes", encoding="utf-8")

    traversal = tool.execute("read_text", {"path": "../outside.txt"})
    absolute = tool.execute("read_text", {"path": str(workspace / "skills" / "README.md")})
    secret = tool.execute("read_text", {"path": ".env"})

    assert traversal.success is absolute.success is secret.success is False
    assert traversal.evidence_code == "project_observer:blocked"


def test_binary_and_oversized_text_are_blocked(tmp_path):
    workspace, _, _, _, tool, _ = _stack(tmp_path)
    (workspace / "image.png").write_bytes(b"not-an-image")
    (workspace / "huge.txt").write_text("x" * 1_048_577, encoding="utf-8")

    binary = tool.execute("read_text", {"path": "image.png"})
    huge = tool.execute("read_text", {"path": "huge.txt"})

    assert binary.success is huge.success is False


def test_verification_fails_if_file_changes_between_read_and_check(tmp_path):
    workspace, _, _, _, tool, _ = _stack(tmp_path)
    path = workspace / "changing.txt"
    path.write_text("before", encoding="utf-8")
    result = tool.execute("read_text", {"path": "changing.txt"})
    path.write_text("after", encoding="utf-8")

    verification = tool.verify("read_text", {"path": "changing.txt"}, result)

    assert verification.verified is False
    assert verification.code == "project_changed_before_verification"


def test_missing_grant_pauses_before_any_filesystem_read(tmp_path):
    workspace, _, _, run_store, _, service = _stack(tmp_path, grant=False)
    target = workspace / "unread.txt"
    target.write_text("must not be read", encoding="utf-8")

    result = service.observe("read_text", {"path": "unread.txt"})

    assert result.receipt.status == AgentRunStatus.AWAITING_CONFIRMATION
    assert result.output is None
    assert "must not be read" not in run_store.path.read_text(encoding="utf-8")


def test_human_cli_renders_content_without_internal_ids(tmp_path):
    workspace, _, _, _, _, service = _stack(tmp_path)
    (workspace / "README.md").write_text("# Локальный проект\n", encoding="utf-8")
    output: list[str] = []

    code = run_command(
        "read",
        service=service,
        path="README.md",
        max_chars=200,
        output=output.append,
    )

    rendered = output[0]
    assert code == 0
    assert "# Локальный проект" in rendered
    assert "plan_observe_" not in rendered
    assert "workspace:masha-home" not in rendered


def test_project_observation_changes_no_domain_storage(tmp_path):
    workspace, _, _, _, _, service = _stack(tmp_path)
    (workspace / "safe.txt").write_text("safe", encoding="utf-8")

    service.observe("read_text", {"path": "safe.txt"})

    assert not (workspace / "memory.sqlite3").exists()
    assert not (workspace / "local-data" / "conversations" / "history.json").exists()
    assert not (workspace / "local-data" / "memory-proposals.json").exists()
