"""Persistent local emergency stop for application-owned autonomous activity."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator



def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutonomySafetyState(BaseModel):
    """A higher-priority latch; it is not Identity, Memory, or a permission grant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    emergency_stop_engaged: bool = False
    changed_at: AwareDatetime | None = None
    changed_by: Literal["misha"] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=200)
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def change_provenance_is_complete(self):
        if (self.changed_at is None) != (self.changed_by is None):
            raise ValueError("safety state change requires timestamp and actor")
        if self.emergency_stop_engaged and self.reason is None:
            raise ValueError("engaged emergency stop requires a reason")
        if not self.emergency_stop_engaged and self.reason is not None:
            raise ValueError("released emergency stop cannot retain an active reason")
        return self


class AutonomySafetyStore:
    """Atomic local configuration with a safe, read-only default."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> AutonomySafetyState:
        if not self.path.exists():
            return AutonomySafetyState()
        return AutonomySafetyState.model_validate(
            json.loads(self.path.read_text(encoding="utf-8"))
        )

    def save(self, state: AutonomySafetyState) -> AutonomySafetyState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return state

    def is_engaged(self) -> bool:
        return self.load().emergency_stop_engaged


class AutonomySafetyService:
    """Explicit human control over the latch; release never starts any activity."""

    def __init__(
        self,
        *,
        store: AutonomySafetyStore,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.store = store
        self._clock = clock

    def status(self) -> AutonomySafetyState:
        return self.store.load()

    def engage(self, reason: str = "manual_emergency_stop") -> AutonomySafetyState:
        normalized = reason.strip()
        if not normalized:
            raise ValueError("emergency stop reason cannot be empty")
        current = self.status()
        if current.emergency_stop_engaged:
            return current
        return self.store.save(
            current.model_copy(
                update={
                    "emergency_stop_engaged": True,
                    "changed_at": self._aware_now(),
                    "changed_by": "misha",
                    "reason": normalized,
                    "revision": current.revision + 1,
                }
            )
        )

    def release(self) -> AutonomySafetyState:
        current = self.status()
        if not current.emergency_stop_engaged:
            return current
        return self.store.save(
            current.model_copy(
                update={
                    "emergency_stop_engaged": False,
                    "changed_at": self._aware_now(),
                    "changed_by": "misha",
                    "reason": None,
                    "revision": current.revision + 1,
                }
            )
        )

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("autonomy safety clock must return aware datetime")
        return value
