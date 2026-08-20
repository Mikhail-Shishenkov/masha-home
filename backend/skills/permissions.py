"""Unified read model for skill permissions and local autonomy safety."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from backend.runtime.safety import AutonomySafetyService, AutonomySafetyState
from backend.temporal.proactive import ProactivePolicy

from .agent_loop import AgentRunStatus, AgentRunStore
from .autonomy import ActionAutonomyPolicyStore, ActionGrant, RISK_ORDER
from .installer import SkillInstallProposalStore, SkillInstallStatus
from .models import SkillCapability, SkillIntegrity, SkillRisk
from .registry import SkillRegistry


class StrictPermissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PendingControlKind(str, Enum):
    SKILL_INSTALL = "skill_install"
    AGENT_CONFIRMATION = "agent_confirmation"


class SkillPermissionView(StrictPermissionModel):
    skill_id: str
    name: str
    version: str | None
    integrity: SkillIntegrity
    capabilities: tuple[SkillCapability, ...] = ()
    scopes: tuple[str, ...] = ()
    risk: SkillRisk | None = None
    maximum_autonomy_level: int | None = None
    registered: bool = False
    runtime_supported: bool = False


class EffectiveGrantView(StrictPermissionModel):
    grant_id: str
    skill_id: str
    capability: SkillCapability
    scope: str
    maximum_risk: SkillRisk
    maximum_autonomy_level: int
    effective_autonomy_level: int
    effective: bool
    reason: str


class PendingControlView(StrictPermissionModel):
    kind: PendingControlKind
    title: str
    status: str
    reference_id: str


class ActionAutonomyView(StrictPermissionModel):
    enabled: bool
    maximum_autonomy_level: int
    grants_total: int
    grants_effective: int


class ProactiveAutonomyView(StrictPermissionModel):
    enabled: bool
    proactive_level: int
    runtime_mode: str
    background_runtime_running: bool
    commitment_reminders: bool
    checkins: bool


class PermissionsSnapshot(StrictPermissionModel):
    safety: AutonomySafetyState
    action_autonomy: ActionAutonomyView
    proactive_autonomy: ProactiveAutonomyView
    skills: tuple[SkillPermissionView, ...] = ()
    grants: tuple[EffectiveGrantView, ...] = ()
    pending: tuple[PendingControlView, ...] = ()
    active_agent_runs: int = 0


class PermissionControlService:
    """Aggregates existing stores; only stop/release can write safety state."""

    def __init__(
        self,
        *,
        registry: SkillRegistry,
        action_policy_store: ActionAutonomyPolicyStore,
        safety: AutonomySafetyService,
        run_store: AgentRunStore,
        install_store: SkillInstallProposalStore,
        proactive_policy: ProactivePolicy,
        background_runtime_running: bool,
        supported_skill_ids: frozenset[str] = frozenset({"project_observer", "web_search", "web_fetch"}),
    ):
        self.registry = registry
        self.action_policy_store = action_policy_store
        self.safety = safety
        self.run_store = run_store
        self.install_store = install_store
        self.proactive_policy = proactive_policy
        self.background_runtime_running = background_runtime_running
        self.supported_skill_ids = supported_skill_ids

    def snapshot(self) -> PermissionsSnapshot:
        safety = self.safety.status()
        action_policy = self.action_policy_store.load()
        descriptors = self.registry.list()
        descriptor_map = {item.skill_id: item for item in descriptors}
        skills = tuple(
            SkillPermissionView(
                skill_id=item.skill_id,
                name=item.skill_id if item.manifest is None else item.manifest.name,
                version=None if item.manifest is None else item.manifest.version,
                integrity=item.integrity,
                capabilities=() if item.manifest is None else item.manifest.capabilities,
                scopes=() if item.manifest is None else item.manifest.requested_scopes,
                risk=None if item.manifest is None else item.manifest.risk_level,
                maximum_autonomy_level=None
                if item.manifest is None
                else item.manifest.maximum_autonomy_level,
                registered=item.registered is not None,
                runtime_supported=item.skill_id in self.supported_skill_ids,
            )
            for item in descriptors
        )
        grants = tuple(
            self._grant_view(
                grant,
                safety=safety,
                policy_enabled=action_policy.enabled,
                policy_level=action_policy.maximum_autonomy_level,
                descriptor=descriptor_map.get(grant.skill_id),
            )
            for grant in action_policy.grants
        )
        runs = self.run_store.list()
        pending = [
            PendingControlView(
                kind=PendingControlKind.SKILL_INSTALL,
                title=f"{item.name}: {item.proposed_version}",
                status=item.status.value,
                reference_id=item.proposal_id,
            )
            for item in self.install_store.list()
            if item.status in {SkillInstallStatus.PENDING, SkillInstallStatus.APPLYING}
        ]
        pending.extend(
            PendingControlView(
                kind=PendingControlKind.AGENT_CONFIRMATION,
                title=item.goal,
                status=item.status.value,
                reference_id=item.plan_id,
            )
            for item in runs
            if item.status is AgentRunStatus.AWAITING_CONFIRMATION
        )
        active_runs = sum(
            item.status in {AgentRunStatus.RUNNING, AgentRunStatus.AWAITING_CONFIRMATION}
            for item in runs
        )
        proactive = self.proactive_policy
        return PermissionsSnapshot(
            safety=safety,
            action_autonomy=ActionAutonomyView(
                enabled=action_policy.enabled,
                maximum_autonomy_level=action_policy.maximum_autonomy_level,
                grants_total=len(grants),
                grants_effective=sum(item.effective for item in grants),
            ),
            proactive_autonomy=ProactiveAutonomyView(
                enabled=proactive.enabled,
                proactive_level=proactive.proactive_level,
                runtime_mode=proactive.runtime_mode,
                background_runtime_running=self.background_runtime_running,
                commitment_reminders=proactive.allow_commitment_reminders,
                checkins=proactive.allow_checkins,
            ),
            skills=skills,
            grants=grants,
            pending=tuple(pending),
            active_agent_runs=active_runs,
        )

    @staticmethod
    def _grant_view(
        grant: ActionGrant,
        *,
        safety: AutonomySafetyState,
        policy_enabled: bool,
        policy_level: int,
        descriptor,
    ) -> EffectiveGrantView:
        effective = True
        reason = "effective"
        effective_level = min(grant.maximum_autonomy_level, policy_level)
        if safety.emergency_stop_engaged:
            effective, reason = False, "emergency_stop_engaged"
        elif not policy_enabled:
            effective, reason = False, "action_autonomy_disabled"
        elif effective_level < 1:
            effective, reason = False, "global_autonomy_level_zero"
        elif descriptor is None:
            effective, reason = False, "skill_not_found"
        elif descriptor.integrity is not SkillIntegrity.VERIFIED:
            effective, reason = False, f"skill_{descriptor.integrity.value}"
        elif descriptor.manifest is None:
            effective, reason = False, "skill_manifest_unavailable"
        elif grant.capability not in descriptor.manifest.capabilities:
            effective, reason = False, "capability_not_declared"
        elif grant.scope not in descriptor.manifest.requested_scopes:
            effective, reason = False, "scope_not_declared"
        elif RISK_ORDER[grant.maximum_risk] > RISK_ORDER[descriptor.manifest.risk_level]:
            effective, reason = False, "risk_exceeds_manifest"
        elif effective_level < grant.maximum_autonomy_level:
            reason = "limited_by_global_autonomy_level"
        return EffectiveGrantView(
            grant_id=grant.grant_id,
            skill_id=grant.skill_id,
            capability=grant.capability,
            scope=grant.scope,
            maximum_risk=grant.maximum_risk,
            maximum_autonomy_level=grant.maximum_autonomy_level,
            effective_autonomy_level=effective_level if effective else 0,
            effective=effective,
            reason=reason,
        )
