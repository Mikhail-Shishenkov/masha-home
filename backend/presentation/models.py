"""Immutable, renderer-neutral presentation models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


OPAQUE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


class PresentationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HomeState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"

class HomeMoment(str, Enum):
    ORDINARY = "ordinary"
    SPECIAL_EVENING = "special_evening"

class HomeProximity(str, Enum):
    WIDE = "wide"
    CLOSE = "close"
    NEAR = "near"


class PresentationTier(str, Enum):
    TIER_0 = "tier_0_static"
    TIER_1 = "tier_1_2d"
    TIER_2 = "tier_2_rich"


class BasePose(str, Enum):
    IDLE = "idle"
    ATTENTIVE = "attentive"
    SPEAKING = "speaking"
    WORKING = "working"
    WAITING = "waiting"
    RESTING = "resting"
    UNAVAILABLE = "unavailable"


class ExpressionCode(str, Enum):
    NEUTRAL = "neutral"
    ATTENTIVE = "attentive"
    CURIOUS = "curious"
    WARM_SMILE = "warm_smile"
    AMUSED = "amused"
    PLAYFUL = "playful"
    LAUGHING = "laughing"
    THOUGHTFUL = "thoughtful"
    SURPRISED = "surprised"
    SKEPTICAL = "skeptical"
    SLIGHTLY_ANNOYED = "slightly_annoyed"
    CONCERNED = "concerned"
    SERIOUS = "serious"
    SYMPATHETIC = "sympathetic"
    HAPPY = "happy"
    PROUD = "proud"
    SLEEPY = "sleepy"


class ExpressionSource(str, Enum):
    STATE_RULE = "state_rule"
    APPLICATION_CUE = "application_cue"
    USER_PREVIEW = "user_preview"


class ExpressionHold(str, Enum):
    TRANSIENT = "transient"
    WHILE_STATE_ACTIVE = "while_state_active"


class AttentionState(str, Enum):
    AMBIENT = "ambient"
    TOWARD_USER = "toward_user"
    TOWARD_SURFACE = "toward_surface"
    THINKING_AWAY = "thinking_away"
    PROACTIVE = "proactive"
    INTERRUPTED = "interrupted"


class PresenceActivity(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    WAITING = "waiting"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    WORKING = "working"
    CONFIRMATION = "confirmation"
    COMPLETED = "completed"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class AmbientState(str, Enum):
    ACTIVE = "active"
    QUIET = "quiet"
    PRIVACY = "privacy"
    LOW_POWER = "low_power"


class SafetyOverlay(str, Enum):
    AUTONOMY_ACTIVE = "autonomy_active"
    AUTONOMY_STOPPED = "autonomy_stopped"


class ProactiveOverlay(str, Enum):
    OFF = "proactive_off"
    ON = "proactive_on"
    ATTENTION = "proactive_attention"


class ModelOverlay(str, Enum):
    AVAILABLE = "model_available"
    SWITCHING = "model_switching"
    UNAVAILABLE = "model_unavailable"


class RuntimeMode(str, Enum):
    MANUAL = "manual_runtime"
    BACKGROUND = "background_runtime"


class DaemonOverlay(str, Enum):
    NOT_REQUIRED = "not_required"
    RUNNING = "running"
    STOPPED = "stopped"
    DEGRADED = "degraded"


class WindowState(str, Enum):
    FOCUSED = "focused"
    UNFOCUSED = "unfocused"


class SurfaceKind(str, Enum):
    CONVERSATION = "conversation"
    ACTIVITY = "activity"
    AGENT_TASK = "agent_task"
    MEMORY = "memory"
    COMMITMENT = "commitment"
    PROACTIVE = "proactive"
    CONFIRMATION = "confirmation"
    MEDIA = "media"
    SKILLS = "skills"
    PERMISSIONS = "permissions"
    MODEL_RUNTIME = "model_runtime"
    VOICE = "voice"
    SETTINGS = "settings"
    GENERIC = "generic"


class SurfaceLifecycle(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    MINIMIZED = "minimized"
    BACKGROUND = "background"
    COMPLETED = "completed"
    CLOSED = "closed"


class SurfaceRole(str, Enum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    DECISION = "decision"
    AMBIENT = "ambient"


class CompositionAnchor(str, Enum):
    MASHA = "masha"
    ROOM = "room"
    VIEWPORT = "viewport"
    ACTIVE_SURFACE = "active_surface"
    SOURCE_SURFACE = "source_surface"


class CompositionPlacement(str, Enum):
    CENTER_LEFT = "center_left"
    CENTER = "center"
    UPPER = "upper"
    NEAR_RIGHT = "near_right"
    NEAR_LEFT = "near_left"
    LOWER = "lower"
    FOREGROUND = "foreground"
    PERIPHERAL = "peripheral"
    STACKED_PRIMARY = "stacked_primary"
    STACKED_SECONDARY = "stacked_secondary"
    FULL_SPACE = "full_space"
    AMBIENT_BACKGROUND = "ambient_background"


class CompositionSize(str, Enum):
    WHISPER = "whisper"
    COMPACT = "compact"
    STANDARD = "standard"
    EXPANDED = "expanded"
    IMMERSIVE = "immersive"


class CompositionPriority(str, Enum):
    AMBIENT = "ambient"
    SUPPORTING = "supporting"
    PRIMARY = "primary"
    DECISION = "decision"
    SAFETY = "safety"


class SurfaceInteractionMode(str, Enum):
    PASSIVE = "passive"
    INSPECT = "inspect"
    INPUT = "input"
    DECISION = "decision"
    DIRECT = "direct"
    MIXED = "mixed"


class PresenceRelation(str, Enum):
    BESIDE = "beside"
    SHARED_ATTENTION = "shared_attention"
    SURROUNDING = "surrounding"
    BACKGROUND = "background"
    COMPACT_PRESENCE = "compact_presence"


class PresenceOcclusion(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    EXPLICIT_IMMERSIVE = "explicit_immersive"


class SurfaceCapability(str, Enum):
    INSPECT = "inspect"
    EXPAND = "expand"
    COLLAPSE = "collapse"
    DISMISS = "dismiss"
    ACKNOWLEDGE = "acknowledge"
    CONFIRM = "confirm"
    REJECT = "reject"
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    RETRY = "retry"


class OcclusionConstraints(PresentationModel):
    max_presence_occlusion: PresenceOcclusion = PresenceOcclusion.NONE
    preserve_face: bool = True
    preserve_silhouette: bool = True


class SurfaceCompositionIntent(PresentationModel):
    anchor: CompositionAnchor = CompositionAnchor.MASHA
    anchor_surface_id: str | None = Field(default=None, pattern=OPAQUE_ID_PATTERN)
    preferred_position: CompositionPlacement = CompositionPlacement.NEAR_RIGHT
    allowed_positions: tuple[CompositionPlacement, ...] = (
        CompositionPlacement.NEAR_RIGHT,
        CompositionPlacement.NEAR_LEFT,
        CompositionPlacement.LOWER,
        CompositionPlacement.STACKED_PRIMARY,
        CompositionPlacement.STACKED_SECONDARY,
    )
    size_class: CompositionSize = CompositionSize.STANDARD
    priority: CompositionPriority = CompositionPriority.SUPPORTING
    interaction_mode: SurfaceInteractionMode = SurfaceInteractionMode.INSPECT
    expandable: bool = True
    collapsible: bool = True
    transform_targets: tuple[SurfaceKind, ...] = ()
    presence_relation: PresenceRelation = PresenceRelation.BESIDE
    occlusion: OcclusionConstraints = OcclusionConstraints()

    @model_validator(mode="after")
    def coherent_intent(self):
        if self.preferred_position not in self.allowed_positions:
            raise ValueError("preferred position must be allowed")
        if len(self.allowed_positions) != len(set(self.allowed_positions)):
            raise ValueError("allowed positions must be unique")
        if self.anchor is CompositionAnchor.SOURCE_SURFACE and self.anchor_surface_id is None:
            raise ValueError("source-surface anchor requires an opaque surface ID")
        if self.anchor is not CompositionAnchor.SOURCE_SURFACE and self.anchor_surface_id is not None:
            raise ValueError("anchor surface ID is only valid for source-surface anchor")
        if self.size_class is CompositionSize.IMMERSIVE:
            if self.occlusion.max_presence_occlusion is not PresenceOcclusion.EXPLICIT_IMMERSIVE:
                raise ValueError("immersive size requires explicit immersive occlusion")
        return self


class ActivityState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProgressKind(str, Enum):
    NONE = "none"
    INDETERMINATE = "indeterminate"
    STEPS = "steps"
    FRACTION = "fraction"


class ExpressionCue(PresentationModel):
    code: ExpressionCode = ExpressionCode.NEUTRAL
    intensity: float = Field(default=0.2, ge=0.0, le=1.0)
    source: ExpressionSource = ExpressionSource.STATE_RULE
    hold: ExpressionHold = ExpressionHold.WHILE_STATE_ACTIVE


class VisualIdentity(PresentationModel):
    visual_identity_id: str = Field(pattern=OPAQUE_ID_PATTERN)
    avatar_variant_id: str = Field(pattern=OPAQUE_ID_PATTERN)
    asset_ids: tuple[str, ...] = ()
    tier: PresentationTier = PresentationTier.TIER_0

    @model_validator(mode="after")
    def opaque_asset_ids(self):
        for asset_id in self.asset_ids:
            if not asset_id or any(character in asset_id for character in ("/", "\\")):
                raise ValueError("visual asset references must be opaque IDs")
        return self


class MashaPresence(PresentationModel):
    visual_identity: VisualIdentity
    pose: BasePose = BasePose.IDLE
    expression: ExpressionCue = ExpressionCue()
    attention: AttentionState = AttentionState.AMBIENT
    activity: PresenceActivity = PresenceActivity.IDLE
    ambient: AmbientState = AmbientState.ACTIVE


class OperatingOverlays(PresentationModel):
    safety: SafetyOverlay = SafetyOverlay.AUTONOMY_ACTIVE
    proactive: ProactiveOverlay = ProactiveOverlay.OFF
    proactive_level: int = Field(default=0, ge=0, le=5)
    model: ModelOverlay = ModelOverlay.AVAILABLE
    active_profile_id: str = Field(default="primary", pattern=OPAQUE_ID_PATTERN)
    model_display_name: str = "Local model"
    runtime_mode: RuntimeMode = RuntimeMode.MANUAL
    daemon: DaemonOverlay = DaemonOverlay.NOT_REQUIRED


class ActivityProgress(PresentationModel):
    kind: ProgressKind = ProgressKind.NONE
    completed_units: int | None = Field(default=None, ge=0)
    total_units: int | None = Field(default=None, gt=0)
    label: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def valid_units(self):
        if self.kind in {ProgressKind.STEPS, ProgressKind.FRACTION}:
            if self.completed_units is None or self.total_units is None:
                raise ValueError("measured progress requires completed and total units")
            if self.completed_units > self.total_units:
                raise ValueError("completed progress cannot exceed total")
        elif self.completed_units is not None or self.total_units is not None:
            raise ValueError("unmeasured progress cannot contain units")
        return self


class ActivityStep(PresentationModel):
    step_id: str = Field(pattern=OPAQUE_ID_PATTERN)
    label: str = Field(min_length=1, max_length=160)
    state: ActivityState


class ActivityPresentation(PresentationModel):
    activity_id: str = Field(pattern=OPAQUE_ID_PATTERN)
    state: ActivityState
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=500)
    progress: ActivityProgress = ActivityProgress()
    steps: tuple[ActivityStep, ...] = ()
    started_at: AwareDatetime | None = None
    updated_at: AwareDatetime
    capabilities: tuple[SurfaceCapability, ...] = ()
    reason_code: str | None = Field(default=None, max_length=120)


class InteractionSurface(PresentationModel):
    surface_id: str = Field(pattern=OPAQUE_ID_PATTERN)
    kind: SurfaceKind
    lifecycle: SurfaceLifecycle = SurfaceLifecycle.CREATED
    role: SurfaceRole = SurfaceRole.SUPPORTING
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=500)
    sensitive: bool = False
    capabilities: tuple[SurfaceCapability, ...] = ()
    activity_id: str | None = Field(default=None, pattern=OPAQUE_ID_PATTERN)
    composition: SurfaceCompositionIntent | None = None


class HomePresentationModel(PresentationModel):
    schema_version: Literal["1.0"] = "1.0"
    revision: int = Field(default=0, ge=0)
    observed_at: AwareDatetime
    opened: bool = False
    home_state: HomeState = HomeState.READY
    home_moment: HomeMoment = HomeMoment.ORDINARY
    home_proximity: HomeProximity = HomeProximity.WIDE
    window_state: WindowState = WindowState.FOCUSED
    privacy_masked: bool = False
    presence: MashaPresence
    overlays: OperatingOverlays = OperatingOverlays()
    surfaces: tuple[InteractionSurface, ...] = ()
    activities: tuple[ActivityPresentation, ...] = ()
    active_surface_id: str | None = Field(default=None, pattern=OPAQUE_ID_PATTERN)


    @model_validator(mode="after")
    def coherent_scene(self):
        surface_ids = [surface.surface_id for surface in self.surfaces]
        if len(surface_ids) != len(set(surface_ids)):
            raise ValueError("surface IDs must be unique")
        activity_ids = [activity.activity_id for activity in self.activities]
        if len(activity_ids) != len(set(activity_ids)):
            raise ValueError("activity IDs must be unique")
        primary = [
            surface.surface_id
            for surface in self.surfaces
            if surface.role is SurfaceRole.PRIMARY
            and surface.lifecycle not in {SurfaceLifecycle.COMPLETED, SurfaceLifecycle.CLOSED}
        ]
        if len(primary) > 1:
            raise ValueError("only one surface may be primary")
        if self.active_surface_id is not None:
            if self.active_surface_id not in surface_ids:
                raise ValueError("active surface must exist")
            active = next(item for item in self.surfaces if item.surface_id == self.active_surface_id)
            if active.lifecycle in {SurfaceLifecycle.COMPLETED, SurfaceLifecycle.CLOSED}:
                raise ValueError("terminal surface cannot be active")
        return self


def default_home_model(*, observed_at: datetime, asset_ids: tuple[str, ...] = ("masha.canonical",)) -> HomePresentationModel:
    """Create a local Tier 0 scene without touching application or persistence."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("presentation timestamps must be timezone-aware")
    return HomePresentationModel(
        observed_at=observed_at,
        presence=MashaPresence(
            visual_identity=VisualIdentity(
                visual_identity_id="masha",
                avatar_variant_id="canonical",
                asset_ids=asset_ids,
            )
        ),
    )
