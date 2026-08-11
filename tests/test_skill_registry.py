import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.skills.cli import run_command
from backend.skills.models import SkillIntegrity, SkillManifest
from backend.skills.registry import SkillIntegrityError, SkillRegistry


NOW = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)


def _manifest(**updates) -> dict:
    payload = {
        "schema_version": "1.0",
        "skill_id": "project_observer",
        "name": "Project Observer",
        "version": "1.0.0",
        "description": "Reads a bounded local project without modifying it.",
        "entrypoint": "local_skill:ProjectObserver",
        "instructions_file": "SKILL.md",
        "capabilities": ["local_read"],
        "requested_scopes": ["workspace:masha-home"],
        "risk_level": "observe",
        "maximum_autonomy_level": 1,
        "supports_dry_run": True,
        "supports_rollback": False,
        "verification": "Return the inspected paths and prove their hashes did not change.",
    }
    payload.update(updates)
    return payload


def _package(root: Path, **manifest_updates) -> Path:
    directory = root / "skills" / manifest_updates.get("skill_id", "project_observer")
    directory.mkdir(parents=True)
    (directory / "skill.json").write_text(
        json.dumps(_manifest(**manifest_updates), ensure_ascii=False),
        encoding="utf-8",
    )
    (directory / "SKILL.md").write_text("# Read-only project observer\n", encoding="utf-8")
    return directory


def _registry(root: Path) -> SkillRegistry:
    return SkillRegistry(
        skills_root=root / "skills",
        state_path=root / "local-data" / "config" / "skills.json",
        clock=lambda: NOW,
    )


def test_discovery_is_read_only_and_never_imports_skill_code(tmp_path):
    directory = _package(tmp_path)
    marker = tmp_path / "IMPORTED"
    (directory / "local_skill.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
        encoding="utf-8",
    )
    registry = _registry(tmp_path)

    rows = registry.list()

    assert len(rows) == 1
    assert rows[0].integrity == SkillIntegrity.UNREGISTERED
    assert marker.exists() is False
    assert registry.state_path.exists() is False


def test_registration_persists_digest_and_survives_restart(tmp_path):
    _package(tmp_path)
    registry = _registry(tmp_path)

    registered = registry.register("project_observer")
    restarted = _registry(tmp_path)
    descriptor = restarted.inspect("project_observer")

    assert registered.package_sha256 == descriptor.current_package_sha256
    assert registered.registered_at == NOW
    assert descriptor.integrity == SkillIntegrity.VERIFIED
    assert descriptor.registered.registered_by == "misha"
    assert not registry.state_path.with_suffix(".json.tmp").exists()


def test_registration_is_idempotent_for_unchanged_package(tmp_path):
    _package(tmp_path)
    registry = _registry(tmp_path)

    first = registry.register("project_observer")
    second = registry.register("project_observer")

    assert second == first
    state = json.loads(registry.state_path.read_text(encoding="utf-8"))
    assert len(state["skills"]) == 1


def test_changed_package_is_detected_and_cannot_be_verified(tmp_path):
    directory = _package(tmp_path)
    registry = _registry(tmp_path)
    registry.register("project_observer")

    (directory / "SKILL.md").write_text("# silently changed instructions\n", encoding="utf-8")
    descriptor = registry.inspect("project_observer")

    assert descriptor.integrity == SkillIntegrity.MODIFIED
    with pytest.raises(SkillIntegrityError, match="changed after registration"):
        registry.verify("project_observer")


def test_manifest_rejects_unsafe_instruction_path_and_duplicate_capability():
    with pytest.raises(ValidationError, match="instructions_file"):
        SkillManifest.model_validate(_manifest(instructions_file="../outside.md"))
    with pytest.raises(ValidationError, match="duplicate"):
        SkillManifest.model_validate(_manifest(capabilities=["local_read", "local_read"]))


@pytest.mark.parametrize(
    ("capability", "risk"),
    [
        ("local_write", "observe"),
        ("network_access", "reversible"),
        ("external_communication", "observe"),
        ("memory_write", "reversible"),
        ("destructive_operation", "consequential"),
        ("identity_write", "consequential"),
    ],
)
def test_manifest_cannot_understate_capability_risk(capability, risk):
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(_manifest(capabilities=[capability], risk_level=risk))


def test_directory_and_manifest_identity_must_match(tmp_path):
    directory = tmp_path / "skills" / "different_name"
    directory.mkdir(parents=True)
    (directory / "skill.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    (directory / "SKILL.md").write_text("instructions", encoding="utf-8")

    descriptor = _registry(tmp_path).inspect("different_name")

    assert descriptor.integrity == SkillIntegrity.INVALID
    assert "match its directory" in descriptor.error


def test_cli_is_human_readable_and_registration_grants_no_execution_permission(tmp_path):
    _package(tmp_path)
    registry = _registry(tmp_path)
    output: list[str] = []

    assert run_command("register", skill_id="project_observer", registry=registry, output=output.append) == 0
    assert run_command("show", skill_id="project_observer", registry=registry, output=output.append) == 0

    rendered = "\n".join(output)
    digest = registry.inspect("project_observer").current_package_sha256
    assert "не разрешение на выполнение" in rendered
    assert "Максимальная автономность: 1 (декларация, не разрешение)" in rendered
    assert digest not in rendered


def test_raw_cli_keeps_technical_integrity_details_available(tmp_path):
    _package(tmp_path)
    registry = _registry(tmp_path)
    registry.register("project_observer")
    output: list[str] = []

    result = run_command(
        "show",
        skill_id="project_observer",
        registry=registry,
        raw=True,
        output=output.append,
    )

    assert result == 0
    payload = json.loads(output[0])
    assert payload["integrity"] == "verified"
    assert len(payload["current_package_sha256"]) == 64


def test_missing_registered_package_is_visible_after_restart(tmp_path):
    directory = _package(tmp_path)
    registry = _registry(tmp_path)
    registry.register("project_observer")
    for path in directory.iterdir():
        path.unlink()
    directory.rmdir()

    rows = _registry(tmp_path).list()

    assert len(rows) == 1
    assert rows[0].integrity == SkillIntegrity.MISSING

