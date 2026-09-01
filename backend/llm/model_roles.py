"""Replaceable local model roles separated from model identities."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .model_profiles import LocalModelProfile, ModelProfileStore


class ModelRole(str, Enum):
    SEMANTIC_RESOLVER = "semantic_resolver"


class ModelRoleAssignments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    assignments: dict[ModelRole, str] = Field(
        default_factory=lambda: {ModelRole.SEMANTIC_RESOLVER: "fast"},
        max_length=16,
    )


class ModelRoleProfileStore:
    """Persist role-to-profile selection without embedding a model ID."""

    def __init__(self, path: str | Path, *, profiles: ModelProfileStore):
        self.path = Path(path)
        self.profiles = profiles
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(ModelRoleAssignments())

    def profile_for(self, role: ModelRole) -> LocalModelProfile:
        assignments = self._load()
        profile_id = assignments.assignments.get(role)
        if not profile_id:
            raise ValueError(f"model role is not configured: {role.value}")
        profile = self.profiles.get_profile(profile_id)
        if not profile.enabled:
            raise ValueError(f"model role profile is disabled: {role.value}")
        return profile

    def assign(self, role: ModelRole, profile_id: str) -> LocalModelProfile:
        profile = self.profiles.get_profile(profile_id)
        if not profile.enabled:
            raise ValueError("model role profile is disabled")
        current = self._load()
        self._write(current.model_copy(update={
            "assignments": {**current.assignments, role: profile_id},
        }))
        return profile

    def _load(self) -> ModelRoleAssignments:
        return ModelRoleAssignments.model_validate(
            json.loads(self.path.read_text(encoding="utf-8"))
        )

    def _write(self, assignments: ModelRoleAssignments) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                assignments.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
