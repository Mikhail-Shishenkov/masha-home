from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RecoveryPhase(str, Enum):
    PREVIEWED = "previewed"
    CHECKPOINTED = "checkpointed"
    APPLYING = "applying"
    VERIFYING = "verifying"
    HOLD = "hold"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    RELEASED = "released"
    BLOCKED = "blocked"


class RestoreMode(str, Enum):
    REPLACE = "replace"
    FRESH = "fresh"


class _RecoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RecoveryState(_RecoveryModel):
    schema_version: Literal["1.0"] = "1.0"
    recovery_id: str = Field(min_length=12, max_length=100)
    backup_id: str = Field(min_length=12, max_length=100)
    restore_mode: RestoreMode
    phase: RecoveryPhase
    created_at: AwareDatetime
    updated_at: AwareDatetime
    checkpoint_filename: str | None = Field(default=None, max_length=180)
    error_code: str | None = Field(default=None, max_length=120)


class RestorePreview(_RecoveryModel):
    backup_id: str
    created_at: AwareDatetime
    application_data_version: str
    component_count: int
    restore_modes: tuple[RestoreMode, ...] = (RestoreMode.REPLACE, RestoreMode.FRESH)
    recovery_hold_required: Literal[True]
    secrets_included: Literal[False]


class RestoreResult(_RecoveryModel):
    recovery_id: str
    backup_id: str
    phase: RecoveryPhase
    restore_mode: RestoreMode
