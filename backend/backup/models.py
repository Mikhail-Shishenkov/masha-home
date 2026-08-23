from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class _BackupModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BackupComponent(_BackupModel):
    component_id: str = Field(pattern=r"^[a-z][a-z0-9_:/.-]{2,180}$")
    archive_path: str = Field(pattern=r"^(?:manifest\.json|payload/[A-Za-z0-9_./-]+)$")
    required: bool
    byte_size: int = Field(ge=0, le=536_870_912)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    format_version: str | None = Field(default=None, max_length=40)


class BackupManifest(_BackupModel):
    backup_format_version: Literal["1.0"] = "1.0"
    backup_id: str = Field(min_length=12, max_length=100)
    created_at: AwareDatetime
    recovery_hold_required: Literal[True] = True
    application_data_version: str = Field(default="0.1", max_length=40)
    secrets_included: Literal[False] = False
    components: tuple[BackupComponent, ...] = Field(min_length=3, max_length=512)


class BackupVerification(_BackupModel):
    backup_id: str
    created_at: AwareDatetime
    verified: Literal[True] = True
    components_verified: int = Field(ge=3, le=512)
