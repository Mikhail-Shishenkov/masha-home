import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.skills.autonomy import (
    ActionAutonomyPolicyStore,
    ActionAutonomyService,
)
from backend.skills.cli import run_command
from backend.skills.installer import (
    SkillInstallAction,
    SkillInstallError,
    SkillInstallProposalStore,
    SkillInstallStatus,
    SkillInstallerService,
)
from backend.skills.models import SkillCapability, SkillIntegrity, SkillRisk
from backend.skills.registry import SkillRegistry


NOW = datetime(2026, 8, 11, 22, 0, tzinfo=timezone.utc)


def _package(
    root: Path,
    *,
    skill_id: str = "test_skill",
    version: str = "1.0.0",
    instructions: str = "# Safe local skill\n",
    capabilities=("local_read",),
    scopes=("workspace:masha-home",),
    entrypoint=None,
) -> Path:
    root.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "skill_id": skill_id,
        "name": "Test Local Skill",
        "version": version,
        "description": "A bounded local package used to test safe installation and upgrade.",
        "entrypoint": entrypoint,
        "instructions_file": "SKILL.md",
        "capabilities": list(capabilities),
        "requested_scopes": list(scopes),
        "risk_level": "observe",
        "maximum_autonomy_level": 1,
        "supports_dry_run": True,
        "supports_rollback": False,
        "verification": "The application adapter verifies every bounded operation deterministically.",
    }
    (root / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "SKILL.md").write_text(instructions, encoding="utf-8")
    return root


def _stack(tmp_path: Path, *, supported=frozenset({"test_skill"})):
    project = tmp_path / "project"
    (project / "skills").mkdir(parents=True)
    registry = SkillRegistry(
        skills_root=project / "local-data" / "skills",
        bundled_skills_root=project / "skills",
        state_path=project / "local-data" / "config" / "skills.json",
        clock=lambda: NOW,
    )
    policy_store = ActionAutonomyPolicyStore(
        project / "local-data" / "config" / "action-autonomy.json"
    )
    autonomy = ActionAutonomyService(store=policy_store, registry=registry, clock=lambda: NOW)
    proposal_store = SkillInstallProposalStore(
        project / "local-data" / "config" / "skill-installs.json"
    )
    installer = SkillInstallerService(
        registry=registry,
        autonomy=autonomy,
        proposal_store=proposal_store,
        runtime_root=project / "local-data" / "skill-install",
        supported_skill_ids=supported,
        clock=lambda: NOW,
    )
    return project, registry, autonomy, proposal_store, installer


def _restart(project, supported=frozenset({"test_skill"})):
    registry = SkillRegistry(
        skills_root=project / "local-data" / "skills",
        bundled_skills_root=project / "skills",
        state_path=project / "local-data" / "config" / "skills.json",
        clock=lambda: NOW,
    )
    autonomy = ActionAutonomyService(
        store=ActionAutonomyPolicyStore(
            project / "local-data" / "config" / "action-autonomy.json"
        ),
        registry=registry,
        clock=lambda: NOW,
    )
    store = SkillInstallProposalStore(
        project / "local-data" / "config" / "skill-installs.json"
    )
    return SkillInstallerService(
        registry=registry,
        autonomy=autonomy,
        proposal_store=store,
        runtime_root=project / "local-data" / "skill-install",
        supported_skill_ids=supported,
        clock=lambda: NOW,
    )


def _installed(project: Path, skill_id: str = "test_skill") -> Path:
    return project / "local-data" / "skills" / skill_id


def test_install_preview_is_persistent_but_does_not_touch_skills_or_registry(tmp_path):
    project, registry, _, store, installer = _stack(tmp_path)
    source = _package(tmp_path / "source")

    proposal = installer.propose(source)

    assert proposal.action is SkillInstallAction.INSTALL
    assert proposal.status is SkillInstallStatus.PENDING
    assert proposal.files_added == ("SKILL.md", "skill.json")
    assert proposal.runtime_supported is True
    assert not _installed(project).exists()
    assert registry.registration("test_skill") is None
    assert store.get(proposal.proposal_id) == proposal
    raw = store.path.read_text(encoding="utf-8")
    assert str(source.resolve()) not in raw


def test_confirm_installs_registers_and_survives_restart(tmp_path):
    project, registry, _, _, installer = _stack(tmp_path)
    source = _package(tmp_path / "source")
    proposal = installer.propose(source)

    confirmed = _restart(project).confirm(proposal.proposal_id)
    descriptor = registry.inspect("test_skill")
    repeated = _restart(project).confirm(proposal.proposal_id)

    assert confirmed.status is SkillInstallStatus.CONFIRMED
    assert confirmed.confirmed_by == "misha"
    assert descriptor.integrity is SkillIntegrity.VERIFIED
    assert descriptor.manifest.version == "1.0.0"
    assert repeated == confirmed
    assert not (project / "local-data" / "skill-install" / "staging" / proposal.proposal_id).exists()


def test_reject_keeps_target_absent_and_removes_staged_copy(tmp_path):
    project, registry, _, _, installer = _stack(tmp_path)
    proposal = installer.propose(_package(tmp_path / "source"))

    rejected = _restart(project).reject(proposal.proposal_id)

    assert rejected.status is SkillInstallStatus.REJECTED
    assert rejected.rejected_at == NOW
    assert registry.registration("test_skill") is None
    assert not _installed(project).exists()
    assert not (project / "local-data" / "skill-install" / "staging" / proposal.proposal_id).exists()


def test_source_snapshot_is_immutable_after_preview(tmp_path):
    project, _, _, _, installer = _stack(tmp_path)
    source = _package(tmp_path / "source", instructions="original\n")
    proposal = installer.propose(source)
    (source / "SKILL.md").write_text("changed outside staging\n", encoding="utf-8")

    _restart(project).confirm(proposal.proposal_id)

    assert (_installed(project) / "SKILL.md").read_text(encoding="utf-8") == "original\n"


def test_staged_tampering_blocks_confirmation(tmp_path):
    project, registry, _, _, installer = _stack(tmp_path)
    proposal = installer.propose(_package(tmp_path / "source"))
    staged = project / "local-data" / "skill-install" / proposal.staged_relative_path
    (staged / "SKILL.md").write_text("tampered", encoding="utf-8")

    with pytest.raises(SkillInstallError, match="changed after preview"):
        _restart(project).confirm(proposal.proposal_id)

    assert registry.registration("test_skill") is None
    assert not _installed(project).exists()


def test_upgrade_shows_diff_revokes_grants_and_replaces_integrity_pin(tmp_path):
    project, registry, autonomy, _, installer = _stack(tmp_path)
    first = installer.propose(_package(tmp_path / "source-v1"))
    installer.confirm(first.proposal_id)
    autonomy.set_enabled(True)
    autonomy.set_level(1)
    autonomy.grant(
        skill_id="test_skill",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=1,
        maximum_risk=SkillRisk.OBSERVE,
    )
    source_v2 = _package(tmp_path / "source-v2", version="1.1.0", instructions="updated\n")
    (source_v2 / "NEW.md").write_text("new\n", encoding="utf-8")

    proposal = installer.propose(source_v2)

    assert proposal.action is SkillInstallAction.UPGRADE
    assert proposal.current_version == "1.0.0"
    assert proposal.proposed_version == "1.1.0"
    assert proposal.files_added == ("NEW.md",)
    assert proposal.files_changed == ("SKILL.md", "skill.json")
    assert proposal.permissions_to_revoke == 1
    assert len(autonomy.grants()) == 1

    confirmed = installer.confirm(proposal.proposal_id)

    assert confirmed.status is SkillInstallStatus.CONFIRMED
    assert autonomy.grants() == ()
    assert autonomy.policy().enabled is True
    assert autonomy.policy().maximum_autonomy_level == 1
    descriptor = registry.inspect("test_skill")
    assert descriptor.integrity is SkillIntegrity.VERIFIED
    assert descriptor.manifest.version == "1.1.0"
    assert descriptor.current_package_sha256 == proposal.proposed_package_sha256


def test_upgrading_bundled_skill_creates_local_override_without_editing_repository(tmp_path):
    project, registry, autonomy, _, installer = _stack(tmp_path)
    bundled = _package(project / "skills" / "test_skill", instructions="bundled\n")
    registry.register("test_skill")
    autonomy.set_enabled(True)
    autonomy.set_level(1)
    autonomy.grant(
        skill_id="test_skill",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=1,
    )
    source = _package(tmp_path / "source-v2", version="1.1.0", instructions="local override\n")

    proposal = installer.propose(source)
    installer.confirm(proposal.proposal_id)

    assert (bundled / "SKILL.md").read_text(encoding="utf-8") == "bundled\n"
    assert (_installed(project) / "SKILL.md").read_text(encoding="utf-8") == "local override\n"
    assert registry.package_directory("test_skill") == _installed(project).resolve()
    assert registry.inspect("test_skill").integrity is SkillIntegrity.VERIFIED
    assert autonomy.grants() == ()


@pytest.mark.parametrize("version", ["1.0.0", "0.9.0", "1.0.0-alpha"])
def test_same_version_or_downgrade_is_rejected(tmp_path, version):
    _, _, _, _, installer = _stack(tmp_path)
    first = installer.propose(_package(tmp_path / "source-v1"))
    installer.confirm(first.proposal_id)

    with pytest.raises(SkillInstallError, match="already installed|newer"):
        installer.propose(_package(tmp_path / f"source-{version}", version=version, instructions="changed"))


def test_target_change_after_upgrade_preview_blocks_confirmation_and_keeps_grant(tmp_path):
    project, _, autonomy, _, installer = _stack(tmp_path)
    first = installer.propose(_package(tmp_path / "source-v1"))
    installer.confirm(first.proposal_id)
    autonomy.set_enabled(True)
    autonomy.set_level(1)
    autonomy.grant(
        skill_id="test_skill",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=1,
    )
    proposal = installer.propose(_package(tmp_path / "source-v2", version="1.1.0"))
    (_installed(project) / "SKILL.md").write_text("local edit", encoding="utf-8")

    with pytest.raises(SkillInstallError, match="changed after preview"):
        installer.confirm(proposal.proposal_id)

    assert len(autonomy.grants()) == 1


def test_zip_package_with_single_root_folder_installs(tmp_path):
    project, registry, _, _, installer = _stack(tmp_path)
    source = _package(tmp_path / "zip-source")
    archive = tmp_path / "test-skill.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for path in source.iterdir():
            output.write(path, f"test-skill/{path.name}")

    proposal = installer.propose(archive)
    installer.confirm(proposal.proposal_id)

    assert registry.inspect("test_skill").integrity is SkillIntegrity.VERIFIED
    assert (_installed(project) / "SKILL.md").is_file()


def test_zip_traversal_and_case_duplicate_are_rejected_without_escape(tmp_path):
    _, _, _, _, installer = _stack(tmp_path)
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as output:
        output.writestr("../escape.txt", "bad")
        output.writestr("skill.json", "{}")
    duplicate = tmp_path / "duplicate.zip"
    package = _package(tmp_path / "duplicate-source")
    with zipfile.ZipFile(duplicate, "w") as output:
        output.write(package / "skill.json", "skill.json")
        output.write(package / "SKILL.md", "SKILL.md")
        output.write(package / "SKILL.md", "skill.md")

    with pytest.raises(SkillInstallError, match="unsafe path"):
        installer.propose(traversal)
    with pytest.raises(SkillInstallError, match="duplicate paths"):
        installer.propose(duplicate)

    assert not (tmp_path / "escape.txt").exists()


def test_zip_file_size_limit_is_enforced_before_proposal(tmp_path):
    _, _, _, store, installer = _stack(tmp_path)
    archive = tmp_path / "oversized.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("skill.json", "{}")
        output.writestr("large.txt", b"x" * 2_097_153)

    with pytest.raises(SkillInstallError, match="size limit"):
        installer.propose(archive)

    assert store.list() == ()


def test_invalid_package_and_compiled_artifacts_leave_no_proposal(tmp_path):
    project, _, _, store, installer = _stack(tmp_path)
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "module.pyc").write_bytes(b"compiled")

    with pytest.raises(SkillInstallError, match="compiled"):
        installer.propose(invalid)

    assert store.list() == ()
    staging = project / "local-data" / "skill-install" / "staging"
    assert not staging.exists() or list(staging.iterdir()) == []


def test_windows_utf8_bom_manifest_is_accepted(tmp_path):
    _, registry, _, _, installer = _stack(tmp_path)
    source = _package(tmp_path / "source")
    manifest = (source / "skill.json").read_text(encoding="utf-8")
    (source / "skill.json").write_text(manifest, encoding="utf-8-sig")

    proposal = installer.propose(source)
    installer.confirm(proposal.proposal_id)

    assert registry.inspect("test_skill").integrity is SkillIntegrity.VERIFIED


def test_package_code_is_never_imported_during_preview_or_confirmation(tmp_path):
    project, _, _, _, installer = _stack(tmp_path)
    source = _package(tmp_path / "source", entrypoint="malicious:run")
    marker = tmp_path / "IMPORTED"
    (source / "malicious.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
        encoding="utf-8",
    )

    proposal = installer.propose(source)
    installer.confirm(proposal.proposal_id)

    assert marker.exists() is False
    assert (_installed(project) / "malicious.py").is_file()


def test_unsupported_runtime_is_visible_but_cannot_be_installed(tmp_path):
    project, registry, _, _, installer = _stack(tmp_path, supported=frozenset())
    proposal = installer.propose(_package(tmp_path / "source"))

    assert proposal.runtime_supported is False
    with pytest.raises(SkillInstallError, match="runtime adapter"):
        installer.confirm(proposal.proposal_id)
    assert registry.registration("test_skill") is None
    assert not _installed(project).exists()


def test_only_one_open_proposal_per_skill(tmp_path):
    _, _, _, _, installer = _stack(tmp_path)
    installer.propose(_package(tmp_path / "source-one"))

    with pytest.raises(SkillInstallError, match="open installation proposal"):
        installer.propose(_package(tmp_path / "source-two", version="1.1.0"))


def test_cli_preview_confirmation_and_history_hide_internal_details(tmp_path):
    _, registry, autonomy, _, installer = _stack(tmp_path)
    source = _package(tmp_path / "source")
    output = []

    assert run_command(
        "install",
        arguments=(str(source),),
        registry=registry,
        autonomy=autonomy,
        installer=installer,
        output=output.append,
    ) == 0
    proposal = installer.proposal_store.latest_open()
    assert run_command(
        "install",
        arguments=("confirm",),
        registry=registry,
        autonomy=autonomy,
        installer=installer,
        output=output.append,
    ) == 0
    assert run_command(
        "installs",
        registry=registry,
        autonomy=autonomy,
        installer=installer,
        output=output.append,
    ) == 0

    rendered = "\n".join(output)
    assert "ещё не установлен" in rendered
    assert "integrity pin обновлён" in rendered
    assert proposal.proposal_id not in rendered
    assert proposal.proposed_package_sha256 not in rendered
    assert str(source.resolve()) not in rendered


def test_raw_cli_exposes_ui_ready_proposal_contract(tmp_path):
    _, registry, autonomy, _, installer = _stack(tmp_path)
    source = _package(tmp_path / "source")
    output = []

    assert run_command(
        "install",
        arguments=(str(source),),
        registry=registry,
        autonomy=autonomy,
        installer=installer,
        raw=True,
        output=output.append,
    ) == 0

    payload = json.loads(output[0])
    assert payload["status"] == "pending"
    assert payload["runtime_supported"] is True
    assert payload["files_added"] == ["SKILL.md", "skill.json"]
    assert len(payload["proposed_package_sha256"]) == 64
