"""Strict declarative contracts for locally installed Masha skills."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictSkillModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SkillCapability(str, Enum):
    LOCAL_READ = "local_read"
    LOCAL_WRITE = "local_write"
    PROCESS_EXECUTION = "process_execution"
    NETWORK_ACCESS = "network_access"
    EXTERNAL_COMMUNICATION = "external_communication"
    DESTRUCTIVE_OPERATION = "destructive_operation"
    MEMORY_WRITE = "memory_write"
    IDENTITY_WRITE = "identity_write"


class SkillRisk(str, Enum):
    OBSERVE = "observe"
    REVERSIBLE = "reversible"
    CONSEQUENTIAL = "consequential"
    RESTRICTED = "restricted"


class SkillIntegrity(str, Enum):
    UNREGISTERED = "unregistered"
    VERIFIED = "verified"
    MODIFIED = "modified"
    MISSING = "missing"
    INVALID = "invalid"


class SkillManifest(StrictSkillModel):
    """What a package requests; none of these declarations grant permission."""

    schema_version: Literal["1.0"] = "1.0"
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    name: str = Field(min_length=3, max_length=100)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][a-zA-Z0-9.-]+)?$")
    description: str = Field(min_length=10, max_length=500)
    entrypoint: str | None = Field(
        default=None,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$",
    )
    instructions_file: str = "SKILL.md"
    capabilities: tuple[SkillCapability, ...] = ()
    requested_scopes: tuple[str, ...] = ()
    risk_level: SkillRisk = SkillRisk.OBSERVE
    maximum_autonomy_level: int = Field(default=0, ge=0, le=4)
    supports_dry_run: bool = False
    supports_rollback: bool = False
    verification: str = Field(min_length=5, max_length=400)

    @field_validator("capabilities", "requested_scopes")
    @classmethod
    def unique_values(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("skill manifest lists duplicate values")
        return value

    @field_validator("requested_scopes")
    @classmethod
    def non_empty_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 200 for item in value):
            raise ValueError("requested scopes must be non-empty and bounded")
        return value

    @field_validator("instructions_file")
    @classmethod
    def safe_relative_instructions_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if not normalized or normalized.startswith("/") or ":" in normalized:
            raise ValueError("instructions_file must be a relative package path")
        if any(part in {"", ".", ".."} for part in normalized.split("/")):
            raise ValueError("instructions_file cannot escape the skill package")
        return normalized

    @model_validator(mode="after")
    def validate_declared_risk(self):
        capabilities = set(self.capabilities)
        restricted = {
            SkillCapability.DESTRUCTIVE_OPERATION,
            SkillCapability.IDENTITY_WRITE,
        }
        consequential = {
            SkillCapability.NETWORK_ACCESS,
            SkillCapability.EXTERNAL_COMMUNICATION,
            SkillCapability.MEMORY_WRITE,
        }
        risk_order = {
            SkillRisk.OBSERVE: 0,
            SkillRisk.REVERSIBLE: 1,
            SkillRisk.CONSEQUENTIAL: 2,
            SkillRisk.RESTRICTED: 3,
        }
        if capabilities & restricted and self.risk_level is not SkillRisk.RESTRICTED:
            raise ValueError("destructive and identity-write skills must declare restricted risk")
        if capabilities & consequential and risk_order[self.risk_level] < 2:
            raise ValueError("network, communication and memory-write skills are consequential")
        if SkillCapability.LOCAL_WRITE in capabilities and self.risk_level is SkillRisk.OBSERVE:
            raise ValueError("a local-write skill cannot declare observe-only risk")
        return self


class RegisteredSkill(StrictSkillModel):
    skill_id: str
    version: str
    manifest_path: str
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at: AwareDatetime
    registered_by: Literal["misha"] = "misha"


class SkillRegistryState(StrictSkillModel):
    schema_version: Literal["1.0"] = "1.0"
    skills: tuple[RegisteredSkill, ...] = ()


class SkillDescriptor(StrictSkillModel):
    skill_id: str
    manifest: SkillManifest | None
    registered: RegisteredSkill | None
    integrity: SkillIntegrity
    current_package_sha256: str | None = None
    error: str | None = None


def utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)
