"""Persistent zero-spend policy for application-owned Internet access."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InternetAccessMode(str, Enum):
    OFF = "off"
    EXPLICIT = "explicit"
    AUTO = "auto"


class InternetAccessPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    mode: InternetAccessMode = InternetAccessMode.EXPLICIT
    allow_task_scoped: bool = False
    allow_background: bool = False
    max_provider_calls_per_turn: int = Field(default=2, ge=1, le=2)
    max_sources_per_observation: int = Field(default=5, ge=1, le=5)
    max_external_context_chars: int = Field(default=5_000, ge=500, le=5_000)
    provider_timeout_seconds: float = Field(default=5.0, ge=1.0, le=20.0)
    monthly_brave_request_cap: int = Field(default=900, ge=0, le=900)

    @model_validator(mode="after")
    def w1_future_modes_remain_disabled(self):
        if self.allow_task_scoped or self.allow_background:
            raise ValueError("task-scoped and background Internet access are not implemented in W1")
        return self


class InternetAccessPolicyStore:
    """Atomic policy storage; loading the default has no filesystem or network side effect."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> InternetAccessPolicy:
        if not self.path.exists():
            return InternetAccessPolicy()
        return InternetAccessPolicy.model_validate(
            json.loads(self.path.read_text(encoding="utf-8"))
        )

    def save(self, policy: InternetAccessPolicy) -> InternetAccessPolicy:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(policy.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return policy

