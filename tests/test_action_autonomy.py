import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.skills.autonomy import (
    ActionAutonomyEngine,
    ActionAutonomyPolicyStore,
    ActionAutonomyService,
    ActionDecision,
    ActionPolicyError,
    ActionRequest,
)
from backend.skills.cli import run_command
from backend.skills.models import SkillCapability, SkillRisk
from backend.skills.registry import SkillRegistry


NOW = datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc)


def _package(
    root: Path,
    *,
    skill_id: str = "project_observer",
    capabilities: tuple[str, ...] = ("local_read",),
    scopes: tuple[str, ...] = ("workspace:masha-home",),
    risk: str = "observe",
    ceiling: int = 3,
) -> None:
    directory = root / "skills" / skill_id
    directory.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "skill_id": skill_id,
        "name": skill_id.replace("_", " ").title(),
        "version": "1.0.0",
        "description": "A deterministic test skill with explicitly bounded capabilities.",
        "entrypoint": None,
        "instructions_file": "SKILL.md",
        "capabilities": list(capabilities),
        "requested_scopes": list(scopes),
        "risk_level": risk,
        "maximum_autonomy_level": ceiling,
        "supports_dry_run": True,
        "supports_rollback": False,
        "verification": "Return deterministic evidence without claiming an unverified result.",
    }
    (directory / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "SKILL.md").write_text("# Test skill\n", encoding="utf-8")


def _stack(tmp_path: Path, **package):
    _package(tmp_path, **package)
    registry = SkillRegistry(
        skills_root=tmp_path / "skills",
        state_path=tmp_path / "local-data" / "config" / "skills.json",
        clock=lambda: NOW,
    )
    store = ActionAutonomyPolicyStore(
        tmp_path / "local-data" / "config" / "action-autonomy.json"
    )
    service = ActionAutonomyService(store=store, registry=registry, clock=lambda: NOW)
    return registry, store, service


def _request(
    *,
    skill_id="project_observer",
    capability=SkillCapability.LOCAL_READ,
    scope="workspace:masha-home",
    risk=SkillRisk.OBSERVE,
    level=1,
) -> ActionRequest:
    return ActionRequest(
        skill_id=skill_id,
        capability=capability,
        scope=scope,
        risk_level=risk,
        required_autonomy_level=level,
    )


def _evaluate(registry, service, request=None):
    return ActionAutonomyEngine().evaluate(
        request or _request(),
        policy=service.policy(),
        registry=registry,
    )


def test_default_policy_is_read_only_and_denies_autonomous_actions(tmp_path):
    registry, store, service = _stack(tmp_path)
    registry.register("project_observer")

    result = _evaluate(registry, service)

    assert result.decision == ActionDecision.DENY
    assert result.reason == "action_autonomy_disabled"
    assert store.path.exists() is False


def test_no_standing_grant_requires_confirmation_instead_of_silent_denial(tmp_path):
    registry, _, service = _stack(tmp_path)
    registry.register("project_observer")
    service.set_enabled(True)
    service.set_level(2)

    result = _evaluate(registry, service)

    assert result.decision == ActionDecision.REQUIRE_CONFIRMATION
    assert result.reason == "no_standing_grant"


def test_exact_standing_grant_allows_action_and_survives_restart(tmp_path):
    registry, store, service = _stack(tmp_path)
    registry.register("project_observer")
    service.set_enabled(True)
    service.set_level(2)
    grant = service.grant(
        skill_id="project_observer",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=2,
        maximum_risk=SkillRisk.OBSERVE,
    )

    restarted = ActionAutonomyService(store=ActionAutonomyPolicyStore(store.path), registry=registry)
    result = _evaluate(registry, restarted)

    assert result.decision == ActionDecision.ALLOW
    assert result.reason == "standing_grant"
    assert result.matched_grant_id == grant.grant_id
    assert restarted.policy().updated_at == NOW


def test_grant_is_idempotent_and_changed_limits_require_revoke(tmp_path):
    registry, _, service = _stack(tmp_path)
    registry.register("project_observer")
    first = service.grant(
        skill_id="project_observer",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=1,
    )

    assert service.grant(
        skill_id="project_observer",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=1,
    ) == first
    with pytest.raises(ActionPolicyError, match="revoke"):
        service.grant(
            skill_id="project_observer",
            capability=SkillCapability.LOCAL_READ,
            scope="workspace:masha-home",
            maximum_autonomy_level=2,
        )


def test_revoke_removes_allow_and_requires_confirmation_after_restart(tmp_path):
    registry, store, service = _stack(tmp_path)
    registry.register("project_observer")
    service.set_enabled(True)
    service.set_level(2)
    grant = service.grant(
        skill_id="project_observer",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=2,
    )

    service.revoke(grant.grant_id)
    restarted = ActionAutonomyService(store=ActionAutonomyPolicyStore(store.path), registry=registry)

    assert restarted.grants() == ()
    assert _evaluate(registry, restarted).decision == ActionDecision.REQUIRE_CONFIRMATION


@pytest.mark.parametrize(
    ("action_request", "reason"),
    [
        (_request(capability=SkillCapability.LOCAL_WRITE, risk=SkillRisk.REVERSIBLE), "capability_not_declared"),
        (_request(scope="workspace:other"), "scope_not_declared"),
        (_request(risk=SkillRisk.REVERSIBLE), "risk_exceeds_manifest"),
        (_request(level=4), "autonomy_exceeds_manifest"),
    ],
)
def test_request_cannot_cross_manifest_boundary(tmp_path, action_request, reason):
    registry, _, service = _stack(tmp_path)
    registry.register("project_observer")
    service.set_enabled(True)
    service.set_level(4)

    result = _evaluate(registry, service, action_request)

    assert result.decision == ActionDecision.DENY
    assert result.reason == reason


def test_global_and_grant_levels_bound_standing_permission(tmp_path):
    registry, _, service = _stack(tmp_path)
    registry.register("project_observer")
    service.set_enabled(True)
    service.set_level(1)
    service.grant(
        skill_id="project_observer",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=1,
    )

    above_global = _evaluate(registry, service, _request(level=2))
    service.set_level(3)
    above_grant = _evaluate(registry, service, _request(level=2))

    assert above_global.reason == "above_global_autonomy_level"
    assert above_grant.reason == "above_grant_autonomy_level"
    assert above_global.decision == above_grant.decision == ActionDecision.REQUIRE_CONFIRMATION


def test_grant_risk_can_be_narrower_than_manifest(tmp_path):
    registry, _, service = _stack(
        tmp_path,
        capabilities=("local_read", "network_access"),
        risk="consequential",
    )
    registry.register("project_observer")
    service.set_enabled(True)
    service.set_level(3)
    service.grant(
        skill_id="project_observer",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=2,
        maximum_risk=SkillRisk.OBSERVE,
    )

    result = _evaluate(registry, service, _request(risk=SkillRisk.REVERSIBLE))

    assert result.decision == ActionDecision.REQUIRE_CONFIRMATION
    assert result.reason == "risk_exceeds_grant"


@pytest.mark.parametrize(
    ("capability", "risk", "expected", "reason"),
    [
        (SkillCapability.IDENTITY_WRITE, SkillRisk.RESTRICTED, ActionDecision.DENY, "identity_write_not_delegable"),
        (SkillCapability.MEMORY_WRITE, SkillRisk.CONSEQUENTIAL, ActionDecision.REQUIRE_CONFIRMATION, "memory_write_uses_confirmation_flow"),
        (SkillCapability.DESTRUCTIVE_OPERATION, SkillRisk.RESTRICTED, ActionDecision.REQUIRE_CONFIRMATION, "destructive_action_requires_confirmation"),
        (SkillCapability.EXTERNAL_COMMUNICATION, SkillRisk.CONSEQUENTIAL, ActionDecision.REQUIRE_CONFIRMATION, "external_communication_requires_confirmation"),
    ],
)
def test_non_delegable_boundaries_cannot_receive_silent_allow(tmp_path, capability, risk, expected, reason):
    registry, _, service = _stack(
        tmp_path,
        capabilities=(capability.value,),
        risk=risk.value,
        ceiling=4,
    )
    registry.register("project_observer")
    service.set_enabled(True)
    service.set_level(4)

    result = _evaluate(
        registry,
        service,
        _request(capability=capability, risk=risk, level=4),
    )

    assert result.decision == expected
    assert result.reason == reason
    with pytest.raises(ActionPolicyError, match="cannot receive"):
        service.grant(
            skill_id="project_observer",
            capability=capability,
            scope="workspace:masha-home",
            maximum_autonomy_level=4,
        )


def test_unregistered_or_modified_skill_is_denied_before_grants(tmp_path):
    registry, _, service = _stack(tmp_path)
    service.set_enabled(True)
    service.set_level(3)
    assert _evaluate(registry, service).reason == "skill_unregistered"

    registry.register("project_observer")
    service.grant(
        skill_id="project_observer",
        capability=SkillCapability.LOCAL_READ,
        scope="workspace:masha-home",
        maximum_autonomy_level=2,
    )
    (tmp_path / "skills" / "project_observer" / "SKILL.md").write_text("changed", encoding="utf-8")

    result = _evaluate(registry, service)
    assert result.decision == ActionDecision.DENY
    assert result.reason == "skill_modified"


def test_action_request_cannot_understate_capability_risk():
    with pytest.raises(ValidationError, match="understates"):
        _request(capability=SkillCapability.LOCAL_WRITE, risk=SkillRisk.OBSERVE)


def test_cli_policy_grant_check_and_revoke_hide_internal_ids(tmp_path):
    registry, _, service = _stack(tmp_path)
    registry.register("project_observer")
    output: list[str] = []

    assert run_command("policy", arguments=("on",), registry=registry, autonomy=service, output=output.append) == 0
    assert run_command("policy", arguments=("level", "2"), registry=registry, autonomy=service, output=output.append) == 0
    assert run_command(
        "grant",
        arguments=("project_observer", "local_read", "workspace:masha-home", "2", "observe"),
        registry=registry,
        autonomy=service,
        output=output.append,
    ) == 0
    assert run_command("permissions", registry=registry, autonomy=service, output=output.append) == 0
    assert run_command(
        "check",
        arguments=("project_observer", "local_read", "workspace:masha-home", "1"),
        registry=registry,
        autonomy=service,
        output=output.append,
    ) == 0
    grant_id = service.grants()[0].grant_id
    assert run_command("revoke", arguments=("1",), registry=registry, autonomy=service, output=output.append) == 0

    rendered = "\n".join(output)
    assert "Разрешено текущими постоянными границами" in rendered
    assert "Само действие ещё не запускалось" in rendered
    assert grant_id not in rendered


def test_action_policy_is_separate_from_proactive_policy_and_skill_registry(tmp_path):
    registry, store, service = _stack(tmp_path)
    registry.register("project_observer")
    service.set_enabled(True)

    assert store.path.name == "action-autonomy.json"
    assert registry.state_path.name == "skills.json"
    assert not (store.path.parent / "proactive-policy.json").exists()
