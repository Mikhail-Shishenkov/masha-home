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

ResponseExpressionCue = Literal[
    "warm",
    "amused",
    "thoughtful",
    "supportive",
    "firm",
    "playful",
]

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


class ExternalSourceView(UiContract):
    source_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    title: str = Field(min_length=1, max_length=300)
    domain: str = Field(min_length=1, max_length=253)
    retrieved_at: datetime
    source_time: str | None = None
    freshness_status: Literal["fresh", "aged", "unknown"]


class ExternalObservationView(UiContract):
    observation_id: str = Field(min_length=8, max_length=100)
    kind: Literal["web_search", "web_fetch"] = "web_search"
    sources: tuple[ExternalSourceView, ...] = Field(default=(), max_length=5)
    page: "FetchedPageView | None" = None
    document: "DocumentReadView | None" = None


class FetchedPageView(UiContract):
    title: str | None = Field(default=None, max_length=300)
    domain: str = Field(min_length=1, max_length=253)
    content_type: str = Field(min_length=1, max_length=120)
    fetched_at: datetime
    truncated: bool
    extractor: str = Field(min_length=1, max_length=80)


class DocumentReadView(UiContract):
    format: Literal["pdf"] = "pdf"
    title: str | None = Field(default=None, max_length=300)
    source_kind: Literal["web", "local", "connector"] = "web"
    display_name: str | None = Field(default=None, max_length=300)
    domain: str | None = Field(default=None, min_length=1, max_length=253)
    page_count: int = Field(ge=1, le=100)
    pages_read: int = Field(ge=1, le=100)
    extracted_chars: int = Field(ge=1, le=16_000)
    truncated: bool
    extractor: str = Field(min_length=1, max_length=80)


class MessageView(UiContract):
    message_id: str | None
    conversation_id: str | None
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    created_at: datetime | None
    persisted: bool
    external_observation: ExternalObservationView | None = None
    external_observations: tuple[ExternalObservationView, ...] = Field(default=(), max_length=2)
    local_documents: tuple[DocumentReadView, ...] = Field(default=(), max_length=1)


class ConversationView(UiContract):
    conversation_id: str
    created_at: datetime
    messages: tuple[MessageView, ...]


class ConversationSummaryView(UiContract):
    conversation_id: str
    created_at: datetime
    last_interaction_at: datetime
    preview: str = Field(min_length=1, max_length=160)


class ConversationPageView(UiContract):
    items: tuple[ConversationSummaryView, ...]
    offset: int = Field(ge=0)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    has_more: bool
    next_offset: int | None = Field(default=None, ge=0)
    query: str | None = None


class CommitmentView(UiContract):
    commitment_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=500)
    status: Literal["open", "upcoming", "overdue", "completed", "cancelled"]
    time_bucket: Literal[
        "fresh_overdue",
        "upcoming",
        "unscheduled",
        "stale_overdue",
    ]
    due_at: datetime | None
    completed_at: datetime | None
    can_propose_completion: bool


class CommitmentListView(UiContract):
    observed_at: datetime
    items: tuple[CommitmentView, ...]
    offset: int = Field(default=0, ge=0)
    page_size: int = Field(default=10, ge=1)
    total: int = Field(default=0, ge=0)
    actionable_total: int = Field(default=0, ge=0)

    fresh_overdue_total: int = Field(default=0, ge=0)
    upcoming_total: int = Field(default=0, ge=0)
    unscheduled_total: int = Field(default=0, ge=0)
    stale_overdue_total: int = Field(default=0, ge=0)

    has_more: bool = False
    next_offset: int | None = Field(default=None, ge=0)


class AgentStepView(UiContract):
    title: str = Field(min_length=1, max_length=200)
    status: Literal["awaiting_confirmation", "denied", "executing", "verified", "failed"]
    result_summary: str | None = Field(default=None, max_length=500)


class AgentRunView(UiContract):
    run_id: str = Field(min_length=1)
    goal: str = Field(min_length=1, max_length=500)
    status: Literal["running", "awaiting_confirmation", "completed", "denied", "failed", "budget_exhausted"]
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    completed_steps: int = Field(ge=0)
    total_steps: int = Field(ge=0)
    steps: tuple[AgentStepView, ...]
    status_label: str = Field(min_length=1, max_length=120)


class AgentRunListView(UiContract):
    items: tuple[AgentRunView, ...]


class ProactiveInteractionView(UiContract):
    interaction_id: str = Field(min_length=1)
    interaction_type: Literal["reminder", "check_in"]
    state: Literal["delivered", "acknowledged", "dismissed"]
    title: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=500)
    created_at: datetime
    delivered_at: datetime
    due_at: datetime | None = None
    allowed_actions: tuple[Literal["acknowledge", "dismiss"], ...]


class ProactiveInteractionListView(UiContract):
    items: tuple[ProactiveInteractionView, ...]


class ProactiveDiagnosticView(UiContract):
    kind: Literal["reminder", "check_in"]
    decision: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    reason_code: str = Field(min_length=1, max_length=120)
    reason_label: str = Field(min_length=1, max_length=200)


class RelationshipMomentView(UiContract):
    moment_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=240)
    text: str = Field(min_length=1, max_length=1_000)
    created_at: datetime


class ConfirmedMemoryItemView(UiContract):
    memory_id: str = Field(min_length=1)
    memory_type: Literal["fact", "decision", "episode"]
    text: str = Field(min_length=1, max_length=1_000)
    created_at: datetime | None


class ContinuityFollowUpView(UiContract):
    thread_id: str = Field(min_length=1)
    topic: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=1_000)
    reason_to_return: str = Field(min_length=1, max_length=1_000)
    priority: float = Field(ge=0.0, le=1.0)
    revisit_after: datetime | None


class SharedContinuityView(UiContract):
    confirmed_memories: tuple[ConfirmedMemoryItemView, ...]
    moments: tuple[RelationshipMomentView, ...]
    open_threads: tuple[ContinuityFollowUpView, ...]
    quarantined_count: int = Field(ge=0)


class AdoptedReflectionView(UiContract):
    reflection_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=700)
    meaning: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    scope: Literal["self", "shared", "help_learning"]
    created_at: datetime
    reconsiders_previous: bool


class PendingReflectionView(UiContract):
    candidate_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=700)
    meaning: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    scope: Literal["self", "shared", "help_learning"]
    created_at: datetime
    allowed_actions: tuple[Literal["adopt", "reject"], ...] = ("adopt", "reject")


class HonestHelpOfferView(UiContract):
    candidate_id: str = Field(min_length=1)
    observation: str = Field(min_length=1, max_length=400)
    offer: str = Field(min_length=1, max_length=400)
    expected_benefit: str = Field(min_length=1, max_length=300)
    why_now: str = Field(min_length=1, max_length=300)
    allowed_actions: tuple[Literal["accept", "dismiss"], ...] = ("accept", "dismiss")


class ReflectionWorkspaceView(UiContract):
    adopted: tuple[AdoptedReflectionView, ...]
    pending: tuple[PendingReflectionView, ...]
    help_offers: tuple[HonestHelpOfferView, ...]


class ReflectionResolutionView(UiContract):
    candidate_id: str
    status: Literal["adopted", "rejected"]
    message: str


class PassiveMemoryCandidateView(UiContract):
    candidate_id: str = Field(min_length=1)
    candidate_type: Literal["fact", "decision", "commitment", "relationship_memory"]
    summary: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0.0, le=1.0)
    detected_at: datetime
    expires_at: datetime
    relation: Literal["new", "possible_update"]
    related_memory_id: str | None
    requires_explicit_supersession: bool
    allowed_actions: tuple[Literal["approve", "reject"], ...] = (
        "approve",
        "reject",
    )


class PassiveMemoryCandidateResolutionView(UiContract):
    candidate_id: str = Field(min_length=1)
    status: Literal["approved", "rejected"]
    result_memory_id: str | None


class MemoryProvenanceView(UiContract):
    record_id: str = Field(min_length=1)
    source: Literal["conversation"]
    candidate_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    evidence_message_ids: tuple[str, ...]
    detector_version: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0.0, le=1.0)
    detected_at: datetime
    reviewed_by: Literal["misha"]
    reviewed_at: datetime
    relation: Literal["new", "possible_update"]
    related_memory_id: str | None


class HonestHelpResolutionView(UiContract):
    candidate_id: str
    status: Literal["delivered", "dismissed", "model_unavailable"]
    conversation_id: str | None
    message: str
    user_message_id: str | None = None


class PendingConfirmationView(UiContract):
    """Bounded human-facing projection of one existing memory proposal."""

    proposal_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    confirmation_type: Literal[
        "memory_create",
        "memory_update",
        "memory_forget",
        "memory_restore",
        "commitment_create",
        "commitment_complete",
        "commitment_cancel",
        "commitment_reschedule",
        "commitment_clear_due",
        "shared_moment_create",
        "continuity_update",
        "google_calendar_create",
    ]
    title: str = Field(min_length=1, max_length=160)
    subject: str = Field(min_length=1, max_length=500)
    due_at: datetime | None
    created_at: datetime
    allowed_actions: tuple[Literal["confirm", "reject"], ...] = ("confirm", "reject")


class CommitmentProposalResult(UiContract):
    conversation_id: str
    user_message: MessageView
    assistant_message: MessageView
    pending_confirmation: PendingConfirmationView


class ConfirmationResolutionStatus(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FAILED = "failed"


class ConfirmationResolutionResult(UiContract):
    proposal_id: str
    conversation_id: str
    status: ConfirmationResolutionStatus
    user_message: MessageView
    assistant_message: MessageView
    pending_confirmation: PendingConfirmationView | None = None

class HomeAttentionItemView(UiContract):
    kind: Literal[
        "overdue_commitment",
        "upcoming_commitment",
        "proactive_interaction",
        "pending_confirmation",
        "model_unavailable",
        "safety_stop",
    ]
    title: str = Field(min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=500)
    urgency: Literal["quiet", "notice", "important"]
    interaction_id: str | None = Field(default=None, min_length=1)
    allowed_actions: tuple[Literal["acknowledge", "dismiss"], ...] = ()
class HomeAttentionView(UiContract):
    """Bounded truth for what currently deserves attention in Home."""

    observed_at: datetime
    active_conversation: ConversationSummaryView | None
    model_available: bool
    model_label: str
    emergency_stop_engaged: bool
    safety_label: str
    commitments_count: int = Field(ge=0)
    overdue_commitments_count: int = Field(default=0, ge=0)
    stale_overdue_commitments_count: int = Field(default=0, ge=0)
    upcoming_commitments_count: int = Field(default=0, ge=0)
    unscheduled_commitments_count: int = Field(default=0, ge=0)
    pending_interactions_count: int = Field(default=0, ge=0)
    attention_items: tuple[HomeAttentionItemView, ...] = ()


class ConversationTurnResult(UiContract):
    conversation_id: str | None
    user_message: MessageView
    assistant_message: MessageView | None
    status: ConversationTurnStatus
    active_profile_id: str
    expression_cue: ResponseExpressionCue = "warm"
    error_code: ApplicationErrorCode | None = None
    error_label: str | None = None
    pending_confirmation: PendingConfirmationView | None = None


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


class SkillWorkbenchView(UiContract):
    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=160)
    version: str | None
    integrity: str = Field(min_length=1, max_length=80)
    capabilities: tuple[str, ...]
    runtime_supported: bool
    summary: str | None = Field(default=None, max_length=300)
    usage: str | None = Field(default=None, max_length=160)
    can: tuple[str, ...] = Field(default=(), max_length=5)
    cannot: tuple[str, ...] = Field(default=(), max_length=6)
    scopes: tuple[str, ...] = ()
    risk: str | None = Field(default=None, max_length=80)


class PermissionGrantView(UiContract):
    skill_id: str = Field(min_length=1)
    capability: str = Field(min_length=1, max_length=100)
    scope: str = Field(min_length=1, max_length=200)
    effective: bool
    label: str = Field(min_length=1, max_length=100)
    mode: Literal["self", "ask", "forbidden"]


class PermissionPendingView(UiContract):
    kind: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    status: str = Field(min_length=1, max_length=80)


class ExternalConnectionView(UiContract):
    """Local, renderer-safe state of one independent read connection."""

    connector_id: Literal["google-calendar", "google-drive", "yandex-mail", "yandex-disk"]
    display_name: str = Field(min_length=1, max_length=80)
    state: Literal["ready", "needs_reconnect", "disconnected"]
    access: Literal["read_only", "read_with_create_setup", "read_and_create"] = "read_only"


class WorkbenchView(UiContract):
    profiles: tuple[ModelProfileView, ...]
    skills: tuple[SkillWorkbenchView, ...]
    grants: tuple[PermissionGrantView, ...]
    pending: tuple[PermissionPendingView, ...]
    emergency_stop_engaged: bool
    action_autonomy_enabled: bool
    action_autonomy_level: int = Field(ge=0, le=4)
    active_agent_runs: int = Field(ge=0)
    connections: tuple[ExternalConnectionView, ...] = ()


class SkillInstallPreviewView(UiContract):
    proposal_id: str = Field(min_length=1)
    action: Literal["install", "upgrade"]
    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=160)
    proposed_version: str = Field(min_length=1, max_length=80)
    capabilities: tuple[str, ...]
    requested_scopes: tuple[str, ...]
    risk_level: str = Field(min_length=1, max_length=80)
    maximum_autonomy_level: int = Field(ge=0, le=4)
    permissions_to_revoke: int = Field(ge=0)
    runtime_supported: bool
    files_added: int = Field(ge=0)
    files_changed: int = Field(ge=0)
    files_removed: int = Field(ge=0)


class SkillInstallResultView(UiContract):
    status: Literal["confirmed", "rejected"]
    skill_id: str
    message: str = Field(min_length=1, max_length=300)
    workbench: WorkbenchView


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
    commitment_reminders_allowed: bool = False
    runtime_mode: Literal["manual", "background"]
    runtime_mode_label: str
    daemon_running: bool
    emergency_stop_engaged: bool
    safety_label: str
    pending_decisions_count: int = Field(ge=0)
    pending_interactions_count: int = Field(ge=0)
    proactive_reason_code: str | None = None
    proactive_reason_label: str | None = None
    proactive_last_cycle_at: datetime | None = None
    proactive_diagnostics: tuple[ProactiveDiagnosticView, ...] = ()
