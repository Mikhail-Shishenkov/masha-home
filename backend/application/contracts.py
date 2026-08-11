"""Stable UI-safe contracts for the local Masha Home application boundary."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UiContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, ser_json_bytes="base64")


class ConversationTurnStatus(str, Enum):
    COMPLETED = "completed"
    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"
    FAILED = "failed"


class ApplicationErrorCode(str, Enum):
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    CONVERSATION_FAILED = "CONVERSATION_FAILED"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    PROFILE_DISABLED = "PROFILE_DISABLED"
    PROVIDER_NOT_FOUND = "PROVIDER_NOT_FOUND"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    MODEL_CHECK_UNAVAILABLE = "MODEL_CHECK_UNAVAILABLE"
    VISUAL_ASSET_NOT_FOUND = "VISUAL_ASSET_NOT_FOUND"
    VISUAL_ASSET_INTEGRITY_FAILED = "VISUAL_ASSET_INTEGRITY_FAILED"


class ApplicationBoundaryError(RuntimeError):
    """Controlled application error with a stable machine-readable code."""

    def __init__(self, code: ApplicationErrorCode):
        super().__init__(code.value)
        self.code = code


class MessageView(UiContract):
    message_id: str | None
    conversation_id: str | None
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    created_at: datetime | None
    persisted: bool


class ConversationView(UiContract):
    conversation_id: str
    created_at: datetime
    messages: tuple[MessageView, ...]


class ConversationSummaryView(UiContract):
    conversation_id: str
    created_at: datetime
    last_interaction_at: datetime
    preview: str = Field(min_length=1, max_length=160)


class ConversationTurnResult(UiContract):
    conversation_id: str | None
    user_message: MessageView
    assistant_message: MessageView | None
    status: ConversationTurnStatus
    active_profile_id: str
    error_code: ApplicationErrorCode | None = None
    error_label: str | None = None


class ModelAvailabilityCode(str, Enum):
    AVAILABLE = "available"
    DISABLED = "disabled"
    PROVIDER_NOT_FOUND = "provider_not_found"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MODEL_NOT_CONFIGURED = "model_not_configured"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_CHECK_UNAVAILABLE = "model_check_unavailable"


class ModelProfileView(UiContract):
    profile_id: str
    display_name: str
    model_id: str
    capabilities: tuple[str, ...]
    description: str
    enabled: bool
    active: bool
    available: bool
    availability_code: ModelAvailabilityCode
    availability_label: str


class ModelSwitchStatus(str, Enum):
    APPLIED = "applied"
    REJECTED = "rejected"


class ModelSwitchResult(UiContract):
    status: ModelSwitchStatus
    requested_profile_id: str
    active_profile: ModelProfileView
    error_code: ApplicationErrorCode | None = None
    error_label: str | None = None


class VisualAssetView(UiContract):
    asset_id: str
    purpose: str
    media_type: str
    byte_size: int = Field(ge=1)


class ResolvedVisualAsset(UiContract):
    asset: VisualAssetView
    content: bytes


class SafetyView(UiContract):
    emergency_stop_engaged: bool
    reason: str | None
    changed_at: datetime | None
    revision: int
    label: str


class MashaStatusView(UiContract):
    runtime_status: Literal["ready", "degraded", "unavailable"]
    runtime_label: str
    model_available: bool
    model_availability_code: ModelAvailabilityCode
    model_label: str
    active_profile_id: str
    proactive_enabled: bool
    proactive_label: str
    proactive_level: int = Field(ge=0, le=5)
    runtime_mode: Literal["manual", "background"]
    runtime_mode_label: str
    daemon_running: bool
    emergency_stop_engaged: bool
    safety_label: str
    pending_decisions_count: int = Field(ge=0)
    pending_interactions_count: int = Field(ge=0)
