"""Deterministic standing permissions for future skill actions; no execution."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import SkillCapability, SkillIntegrity, SkillRisk, utc_now
from .registry import SkillRegistry, SkillRegistryError


class StrictAutonomyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActionDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    DENY = "deny"


RISK_ORDER = {
    SkillRisk.OBSERVE: 0,
    SkillRisk.REVERSIBLE: 1,
    SkillRisk.CONSEQUENTIAL: 2,
    SkillRisk.RESTRICTED: 3,
}

CAPABILITY_MINIMUM_RISK = {
    SkillCapability.LOCAL_READ: SkillRisk.OBSERVE,
    SkillCapability.LOCAL_WRITE: SkillRisk.REVERSIBLE,
    SkillCapability.PROCESS_EXECUTION: SkillRisk.REVERSIBLE,
    SkillCapability.NETWORK_ACCESS: SkillRisk.CONSEQUENTIAL,
    SkillCapability.EXTERNAL_COMMUNICATION: SkillRisk.CONSEQUENTIAL,
    SkillCapability.DESTRUCTIVE_OPERATION: SkillRisk.RESTRICTED,
    SkillCapability.MEMORY_WRITE: SkillRisk.CONSEQUENTIAL,
    SkillCapability.IDENTITY_WRITE: SkillRisk.RESTRICTED,
}


class ActionRequest(StrictAutonomyModel):
    """Application-owned description of one future action, never LLM authority."""

    skill_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    capability: SkillCapability
    scope: str = Field(min_length=1, max_length=200)
    risk_level: SkillRisk
    required_autonomy_level: int = Field(ge=1, le=4)

    @field_validator("scope")
    @classmethod
    def normalized_scope(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("action scope cannot contain surrounding whitespace")
        return value

    @model_validator(mode="after")
    def risk_cannot_be_understated(self):
        minimum = CAPABILITY_MINIMUM_RISK[self.capability]
        if RISK_ORDER[self.risk_level] < RISK_ORDER[minimum]:
            raise ValueError("action request understates capability risk")
        return self


class ActionGrant(StrictAutonomyModel):
    grant_id: str = Field(pattern=r"^grant_[0-9a-f-]{36}$")
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    capability: SkillCapability
    scope: str = Field(min_length=1, max_length=200)
    maximum_risk: SkillRisk
    maximum_autonomy_level: int = Field(ge=0, le=4)
    created_at: AwareDatetime
    created_by: Literal["misha"] = "misha"

    @field_validator("scope")
    @classmethod
    def normalized_scope(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("grant scope cannot contain surrounding whitespace")
        return value


class ActionAutonomyPolicy(StrictAutonomyModel):
    schema_version: Literal["1.0"] = "1.0"
    enabled: bool = False
    maximum_autonomy_level: int = Field(default=0, ge=0, le=4)
    grants: tuple[ActionGrant, ...] = ()
    updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def unique_grants(self):
        ids = [item.grant_id for item in self.grants]
        keys = [
            (item.skill_id, item.capability, item.scope)
            for item in self.grants
        ]
        if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
            raise ValueError("action autonomy policy contains duplicate grants")
        return self


class ActionEvaluation(StrictAutonomyModel):
    decision: ActionDecision
    reason: str
    matched_grant_id: str | None = None


class ActionPolicyError(RuntimeError):
    pass


NON_DELEGABLE_CAPABILITIES = {
    SkillCapability.IDENTITY_WRITE,
    SkillCapability.MEMORY_WRITE,
    SkillCapability.DESTRUCTIVE_OPERATION,
    SkillCapability.EXTERNAL_COMMUNICATION,
}


class ActionAutonomyPolicyStore:
    """Atomic local JSON configuration, separate from proactive policy and Memory."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> ActionAutonomyPolicy:
        if not self.path.exists():
            return ActionAutonomyPolicy()
        return ActionAutonomyPolicy.model_validate(
            json.loads(self.path.read_text(encoding="utf-8"))
        )

    def save(self, policy: ActionAutonomyPolicy) -> ActionAutonomyPolicy:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(policy.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return policy


class ActionAutonomyEngine:
    """Pure policy gate. It cannot run a skill, call an LLM, or mutate a domain."""

    def evaluate(
        self,
        request: ActionRequest,
        *,
        policy: ActionAutonomyPolicy,
        registry: SkillRegistry,
    ) -> ActionEvaluation:
        try:
            descriptor = registry.inspect(request.skill_id)
        except SkillRegistryError:
            return ActionEvaluation(decision=ActionDecision.DENY, reason="skill_not_found")
        if descriptor.integrity is not SkillIntegrity.VERIFIED:
            return ActionEvaluation(
                decision=ActionDecision.DENY,
                reason=f"skill_{descriptor.integrity.value}",
            )
        assert descriptor.manifest is not None
        manifest = descriptor.manifest
        if request.capability not in manifest.capabilities:
            return ActionEvaluation(decision=ActionDecision.DENY, reason="capability_not_declared")
        if request.scope not in manifest.requested_scopes:
            return ActionEvaluation(decision=ActionDecision.DENY, reason="scope_not_declared")
        if RISK_ORDER[request.risk_level] > RISK_ORDER[manifest.risk_level]:
            return ActionEvaluation(decision=ActionDecision.DENY, reason="risk_exceeds_manifest")
        if request.required_autonomy_level > manifest.maximum_autonomy_level:
            return ActionEvaluation(decision=ActionDecision.DENY, reason="autonomy_exceeds_manifest")
        if not policy.enabled:
            return ActionEvaluation(decision=ActionDecision.DENY, reason="action_autonomy_disabled")
        if request.capability is SkillCapability.IDENTITY_WRITE:
            return ActionEvaluation(decision=ActionDecision.DENY, reason="identity_write_not_delegable")
        if request.capability is SkillCapability.MEMORY_WRITE:
            return ActionEvaluation(
                decision=ActionDecision.REQUIRE_CONFIRMATION,
                reason="memory_write_uses_confirmation_flow",
            )
        if request.capability is SkillCapability.DESTRUCTIVE_OPERATION:
            return ActionEvaluation(
                decision=ActionDecision.REQUIRE_CONFIRMATION,
                reason="destructive_action_requires_confirmation",
            )
        if request.capability is SkillCapability.EXTERNAL_COMMUNICATION:
            return ActionEvaluation(
                decision=ActionDecision.REQUIRE_CONFIRMATION,
                reason="external_communication_requires_confirmation",
            )
        if request.required_autonomy_level > policy.maximum_autonomy_level:
            return ActionEvaluation(
                decision=ActionDecision.REQUIRE_CONFIRMATION,
                reason="above_global_autonomy_level",
            )
        grant = next(
            (
                item
                for item in policy.grants
                if item.skill_id == request.skill_id
                and item.capability is request.capability
                and item.scope == request.scope
            ),
            None,
        )
        if grant is None:
            return ActionEvaluation(
                decision=ActionDecision.REQUIRE_CONFIRMATION,
                reason="no_standing_grant",
            )
        if RISK_ORDER[request.risk_level] > RISK_ORDER[grant.maximum_risk]:
            return ActionEvaluation(
                decision=ActionDecision.REQUIRE_CONFIRMATION,
                reason="risk_exceeds_grant",
                matched_grant_id=grant.grant_id,
            )
        if request.required_autonomy_level > grant.maximum_autonomy_level:
            return ActionEvaluation(
                decision=ActionDecision.REQUIRE_CONFIRMATION,
                reason="above_grant_autonomy_level",
                matched_grant_id=grant.grant_id,
            )
        return ActionEvaluation(
            decision=ActionDecision.ALLOW,
            reason="standing_grant",
            matched_grant_id=grant.grant_id,
        )


class ActionAutonomyService:
    """Explicit user-control surface for policy and grants; still no executor."""

    def __init__(
        self,
        *,
        store: ActionAutonomyPolicyStore,
        registry: SkillRegistry,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.store = store
        self.registry = registry
        self._clock = clock

    def policy(self) -> ActionAutonomyPolicy:
        return self.store.load()

    def set_enabled(self, enabled: bool) -> ActionAutonomyPolicy:
        return self._save(self.policy().model_copy(update={"enabled": enabled}))

    def set_level(self, level: int) -> ActionAutonomyPolicy:
        if not 0 <= level <= 4:
            raise ActionPolicyError("autonomy level must be between 0 and 4")
        return self._save(
            self.policy().model_copy(update={"maximum_autonomy_level": level})
        )

    def grants(self) -> tuple[ActionGrant, ...]:
        return self.policy().grants

    def grant(
        self,
        *,
        skill_id: str,
        capability: SkillCapability,
        scope: str,
        maximum_autonomy_level: int,
        maximum_risk: SkillRisk | None = None,
    ) -> ActionGrant:
        descriptor = self.registry.inspect(skill_id)
        if descriptor.integrity is not SkillIntegrity.VERIFIED or descriptor.manifest is None:
            raise ActionPolicyError("skill must be registered and verified before granting permission")
        manifest = descriptor.manifest
        if capability not in manifest.capabilities:
            raise ActionPolicyError("skill did not declare this capability")
        if scope not in manifest.requested_scopes:
            raise ActionPolicyError("scope is outside the skill manifest")
        if maximum_autonomy_level > manifest.maximum_autonomy_level or maximum_autonomy_level < 1:
            raise ActionPolicyError("grant exceeds the skill autonomy ceiling")
        maximum_risk = maximum_risk or manifest.risk_level
        if RISK_ORDER[maximum_risk] > RISK_ORDER[manifest.risk_level]:
            raise ActionPolicyError("grant risk exceeds the skill manifest")
        if RISK_ORDER[maximum_risk] < RISK_ORDER[CAPABILITY_MINIMUM_RISK[capability]]:
            raise ActionPolicyError("grant risk understates the capability")
        if capability in NON_DELEGABLE_CAPABILITIES or manifest.risk_level is SkillRisk.RESTRICTED:
            raise ActionPolicyError("this capability cannot receive a standing grant")
        policy = self.policy()
        existing = next(
            (
                item
                for item in policy.grants
                if item.skill_id == skill_id
                and item.capability is capability
                and item.scope == scope
            ),
            None,
        )
        if existing is not None:
            if (
                existing.maximum_autonomy_level == maximum_autonomy_level
                and existing.maximum_risk is maximum_risk
            ):
                return existing
            raise ActionPolicyError("permission already exists; revoke it before changing limits")
        grant = ActionGrant(
            grant_id=f"grant_{uuid4()}",
            skill_id=skill_id,
            capability=capability,
            scope=scope,
            maximum_risk=maximum_risk,
            maximum_autonomy_level=maximum_autonomy_level,
            created_at=self._aware_now(),
        )
        self._save(policy.model_copy(update={"grants": (*policy.grants, grant)}))
        return grant

    def revoke(self, grant_id: str) -> ActionAutonomyPolicy:
        policy = self.policy()
        remaining = tuple(item for item in policy.grants if item.grant_id != grant_id)
        if len(remaining) == len(policy.grants):
            raise ActionPolicyError("permission grant not found")
        return self._save(policy.model_copy(update={"grants": remaining}))

    def revoke_skill(self, skill_id: str) -> tuple[ActionAutonomyPolicy, int]:
        """Revoke every standing grant for one upgraded skill, without widening policy."""

        policy = self.policy()
        remaining = tuple(item for item in policy.grants if item.skill_id != skill_id)
        revoked = len(policy.grants) - len(remaining)
        if revoked == 0:
            return policy, 0
        return self._save(policy.model_copy(update={"grants": remaining})), revoked

    def _save(self, policy: ActionAutonomyPolicy) -> ActionAutonomyPolicy:
        return self.store.save(
            policy.model_copy(update={"updated_at": self._aware_now()})
        )

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("action autonomy clock must return aware datetime")
        return value
