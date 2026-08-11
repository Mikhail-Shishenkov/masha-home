"""Pure renderer-neutral spatial composition for Masha Home."""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import Field, model_validator

from .models import (
    ActivityState,
    AttentionState,
    BasePose,
    CompositionAnchor,
    CompositionPlacement,
    CompositionPriority,
    CompositionSize,
    ExpressionCue,
    HomePresentationModel,
    InteractionSurface,
    ModelOverlay,
    OcclusionConstraints,
    OPAQUE_ID_PATTERN,
    PresenceActivity,
    PresenceRelation,
    PresentationModel,
    ProactiveOverlay,
    SafetyOverlay,
    SurfaceCompositionIntent,
    SurfaceInteractionMode,
    SurfaceKind,
    SurfaceLifecycle,
    SurfaceRole,
    WindowState,
)


class CompositionVariant(str, Enum):
    PRESENCE_FIRST = "presence_first"
    CONVERSATION_FIRST = "conversation_first"
    ADAPTIVE_CINEMATIC = "adaptive_cinematic"


class ViewportClass(str, Enum):
    WIDE = "wide"
    STANDARD = "standard"
    NARROW = "narrow"
    VERY_NARROW = "very_narrow"


class CompositionRegionKind(str, Enum):
    AMBIENT = "ambient"
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    DECISION = "decision"


class FocusOwner(str, Enum):
    PRESENCE = "presence"
    USER = "user"
    SURFACE = "surface"
    SAFETY = "safety"
    PRIVACY = "privacy"


class OverlayKind(str, Enum):
    PRIVACY = "privacy"
    SAFETY = "safety"
    PROACTIVE = "proactive"
    MODEL = "model"
    RUNTIME = "runtime"


class OverlaySalience(str, Enum):
    SUBTLE = "subtle"
    NORMAL = "normal"
    ELEVATED = "elevated"


class CompositionStability(str, Enum):
    INITIAL = "initial"
    STABLE = "stable"
    RECOMPOSED = "recomposed"
    PRIVACY_OVERRIDE = "privacy_override"
    SAFETY_OVERRIDE = "safety_override"
    VIEWPORT_OVERRIDE = "viewport_override"


class ViewportCharacteristics(PresentationModel):
    size_class: ViewportClass = ViewportClass.WIDE
    reduced_motion: bool = False
    privacy_required: bool = False


class MashaComposition(PresentationModel):
    anchor: CompositionAnchor = CompositionAnchor.ROOM
    placement: CompositionPlacement
    size_class: CompositionSize
    priority: CompositionPriority = CompositionPriority.PRIMARY
    pose: BasePose
    expression: ExpressionCue
    attention: AttentionState
    activity: PresenceActivity
    face_visible: bool = True
    silhouette_visible: bool = True


class CompositionRegion(PresentationModel):
    region_id: str = Field(pattern=OPAQUE_ID_PATTERN)
    kind: CompositionRegionKind
    placement: CompositionPlacement
    size_class: CompositionSize
    priority: CompositionPriority
    anchor: CompositionAnchor
    surface_id: str | None = Field(default=None, pattern=OPAQUE_ID_PATTERN)
    surface_kind: SurfaceKind | None = None
    surface_lifecycle: SurfaceLifecycle | None = None
    activity_state: ActivityState | None = None
    interaction_mode: SurfaceInteractionMode = SurfaceInteractionMode.PASSIVE
    presence_relation: PresenceRelation = PresenceRelation.BACKGROUND
    occlusion: OcclusionConstraints = OcclusionConstraints()
    content_masked: bool = False
    focus_owned: bool = False


class CompositionOverlay(PresentationModel):
    kind: OverlayKind
    state_code: str = Field(min_length=1, max_length=120)
    placement: CompositionPlacement
    priority: CompositionPriority
    salience: OverlaySalience
    masks_sensitive_content: bool = False


class CompositionPlan(PresentationModel):
    schema_version: str = "1.0"
    source_revision: int = Field(ge=0)
    variant: CompositionVariant
    viewport: ViewportCharacteristics
    masha: MashaComposition
    regions: tuple[CompositionRegion, ...]
    overlays: tuple[CompositionOverlay, ...]
    primary_surface_id: str | None = Field(default=None, pattern=OPAQUE_ID_PATTERN)
    focus_owner: FocusOwner
    focus_surface_id: str | None = Field(default=None, pattern=OPAQUE_ID_PATTERN)
    suppressed_surface_ids: tuple[str, ...] = ()
    privacy_masked: bool = False
    stability: CompositionStability = CompositionStability.INITIAL
    stability_key: str = Field(pattern=r"^cmp1_[0-9a-f]{20}$")

    @model_validator(mode="after")
    def coherent_plan(self):
        region_ids = [region.region_id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("composition region IDs must be unique")
        surface_ids = [region.surface_id for region in self.regions if region.surface_id]
        if len(surface_ids) != len(set(surface_ids)):
            raise ValueError("a surface may occupy only one composition region")
        if self.primary_surface_id is not None and self.primary_surface_id not in surface_ids:
            raise ValueError("primary surface must occupy a composition region")
        if self.focus_owner is FocusOwner.SURFACE and self.focus_surface_id is None:
            raise ValueError("surface focus requires a surface ID")
        return self


_PRIORITY_RANK = {
    CompositionPriority.AMBIENT: 0,
    CompositionPriority.SUPPORTING: 1,
    CompositionPriority.PRIMARY: 2,
    CompositionPriority.DECISION: 3,
    CompositionPriority.SAFETY: 4,
}

_TERMINAL_ACTIVITY_STATES = {
    ActivityState.COMPLETED,
    ActivityState.FAILED,
    ActivityState.CANCELLED,
}


class CompositionResolver:
    """Resolve immutable presentation state into a semantic spatial plan."""

    def resolve(
        self,
        model: HomePresentationModel,
        *,
        viewport: ViewportCharacteristics | None = None,
        variant: CompositionVariant = CompositionVariant.PRESENCE_FIRST,
        previous_plan: CompositionPlan | None = None,
    ) -> CompositionPlan:
        viewport = viewport or ViewportCharacteristics()
        privacy = (
            viewport.privacy_required
            or model.privacy_masked
            or model.window_state is WindowState.UNFOCUSED
        )
        stopped = model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED

        candidates, initially_suppressed = self._surface_candidates(model, stopped=stopped)
        primary = self._primary_surface(model, candidates)
        selected, capacity_suppressed = self._bounded_surfaces(candidates, primary, viewport)
        suppressed = tuple(sorted(set(initially_suppressed + capacity_suppressed)))

        regions = (
            self._ambient_region(privacy=privacy),
            *(
                self._surface_region(
                    model,
                    surface,
                    primary=surface.surface_id == (primary.surface_id if primary else None),
                    primary_surface_id=primary.surface_id if primary else None,
                    viewport=viewport,
                    variant=variant,
                    privacy=privacy,
                    previous_plan=previous_plan,
                )
                for surface in selected
            ),
        )
        overlays = self._overlays(model, privacy=privacy)
        focus_owner, focus_surface_id = self._focus(
            model,
            primary=primary,
            privacy=privacy,
            stopped=stopped,
        )
        masha = self._masha(model, viewport=viewport, variant=variant, privacy=privacy)
        stability_key = self._stability_key(
            variant=variant,
            viewport=viewport,
            masha={
                "placement": masha.placement,
                "size_class": masha.size_class,
                "face_visible": masha.face_visible,
                "silhouette_visible": masha.silhouette_visible,
            },
            regions=tuple(
                {
                    "region_id": region.region_id,
                    "kind": region.kind,
                    "placement": region.placement,
                    "size_class": region.size_class,
                    "priority": region.priority,
                    "anchor": region.anchor,
                    "surface_id": region.surface_id,
                    "surface_kind": region.surface_kind,
                    "presence_relation": region.presence_relation,
                    "content_masked": region.content_masked,
                }
                for region in regions
            ),
            overlays=tuple(
                {
                    "kind": overlay.kind,
                    "placement": overlay.placement,
                    "priority": overlay.priority,
                    "salience": overlay.salience,
                    "masks_sensitive_content": overlay.masks_sensitive_content,
                }
                for overlay in overlays
            ),
            primary_surface_id=primary.surface_id if primary else None,
            focus_owner=focus_owner,
            focus_surface_id=focus_surface_id,
            suppressed=suppressed,
            privacy=privacy,
        )
        stability = self._stability(
            previous_plan,
            stability_key=stability_key,
            viewport=viewport,
            privacy=privacy,
            stopped=stopped,
        )
        return CompositionPlan(
            source_revision=model.revision,
            variant=variant,
            viewport=viewport,
            masha=masha,
            regions=regions,
            overlays=overlays,
            primary_surface_id=primary.surface_id if primary else None,
            focus_owner=focus_owner,
            focus_surface_id=focus_surface_id,
            suppressed_surface_ids=suppressed,
            privacy_masked=privacy,
            stability=stability,
            stability_key=stability_key,
        )

    @staticmethod
    def _ambient_region(*, privacy: bool) -> CompositionRegion:
        return CompositionRegion(
            region_id="region:home.ambient",
            kind=CompositionRegionKind.AMBIENT,
            placement=CompositionPlacement.AMBIENT_BACKGROUND,
            size_class=CompositionSize.EXPANDED,
            priority=CompositionPriority.AMBIENT,
            anchor=CompositionAnchor.ROOM,
            presence_relation=PresenceRelation.BACKGROUND,
            content_masked=privacy,
        )

    @staticmethod
    def _surface_candidates(
        model: HomePresentationModel,
        *,
        stopped: bool,
    ) -> tuple[list[InteractionSurface], list[str]]:
        candidates: list[InteractionSurface] = []
        suppressed: list[str] = []
        for surface in model.surfaces:
            if surface.lifecycle in {SurfaceLifecycle.CLOSED, SurfaceLifecycle.MINIMIZED}:
                suppressed.append(surface.surface_id)
                continue
            if surface.kind is SurfaceKind.PROACTIVE and (
                model.overlays.proactive is ProactiveOverlay.OFF or stopped
            ):
                suppressed.append(surface.surface_id)
                continue
            candidates.append(surface)
        return candidates, suppressed

    def _primary_surface(
        self,
        model: HomePresentationModel,
        candidates: list[InteractionSurface],
    ) -> InteractionSurface | None:
        non_terminal = [
            surface
            for surface in candidates
            if surface.lifecycle not in {SurfaceLifecycle.COMPLETED, SurfaceLifecycle.CLOSED}
        ]
        decision = next(
            (
                surface
                for surface in non_terminal
                if surface.role is SurfaceRole.DECISION
                or surface.kind is SurfaceKind.CONFIRMATION
            ),
            None,
        )
        if decision is not None:
            return decision
        if model.active_surface_id is not None:
            active = next(
                (surface for surface in non_terminal if surface.surface_id == model.active_surface_id),
                None,
            )
            if active is not None:
                return active
        primary = next(
            (surface for surface in non_terminal if surface.role is SurfaceRole.PRIMARY),
            None,
        )
        if primary is not None:
            return primary
        active_activity_ids = {
            activity.activity_id
            for activity in model.activities
            if activity.state not in _TERMINAL_ACTIVITY_STATES
        }
        activity = next(
            (surface for surface in non_terminal if surface.activity_id in active_activity_ids),
            None,
        )
        if activity is not None:
            return activity
        return next(
            (surface for surface in non_terminal if surface.kind is SurfaceKind.CONVERSATION),
            non_terminal[0] if non_terminal else None,
        )

    def _bounded_surfaces(
        self,
        candidates: list[InteractionSurface],
        primary: InteractionSurface | None,
        viewport: ViewportCharacteristics,
    ) -> tuple[list[InteractionSurface], list[str]]:
        capacity = {
            ViewportClass.WIDE: 4,
            ViewportClass.STANDARD: 3,
            ViewportClass.NARROW: 3,
            ViewportClass.VERY_NARROW: 2,
        }[viewport.size_class]
        ordered = sorted(
            candidates,
            key=lambda surface: (
                0 if primary and surface.surface_id == primary.surface_id else 1,
                -_PRIORITY_RANK[self._intent(surface).priority],
                0 if surface.kind is SurfaceKind.CONVERSATION else 1,
                surface.surface_id,
            ),
        )
        selected = ordered[:capacity]
        suppressed = [surface.surface_id for surface in ordered[capacity:]]
        return selected, suppressed

    def _surface_region(
        self,
        model: HomePresentationModel,
        surface: InteractionSurface,
        *,
        primary: bool,
        primary_surface_id: str | None,
        viewport: ViewportCharacteristics,
        variant: CompositionVariant,
        privacy: bool,
        previous_plan: CompositionPlan | None,
    ) -> CompositionRegion:
        intent = self._intent(surface)
        decision = surface.role is SurfaceRole.DECISION or surface.kind is SurfaceKind.CONFIRMATION
        priority = (
            CompositionPriority.DECISION
            if decision
            else CompositionPriority.PRIMARY
            if primary
            else intent.priority
        )
        kind = (
            CompositionRegionKind.DECISION
            if decision
            else CompositionRegionKind.PRIMARY
            if primary
            else CompositionRegionKind.SUPPORTING
        )
        placement = self._placement(surface, intent, primary=primary, viewport=viewport)
        placement = self._stable_placement(
            surface,
            intent,
            placement=placement,
            viewport=viewport,
            variant=variant,
            privacy=privacy,
            previous_plan=previous_plan,
            primary_surface_id=primary_surface_id,
        )
        size = self._size(model, surface, intent, primary=primary, viewport=viewport, variant=variant)
        activity = next(
            (item for item in model.activities if item.activity_id == surface.activity_id),
            None,
        )
        return CompositionRegion(
            region_id=f"region:{surface.surface_id}",
            kind=kind,
            placement=placement,
            size_class=size,
            priority=priority,
            anchor=intent.anchor,
            surface_id=surface.surface_id,
            surface_kind=surface.kind,
            surface_lifecycle=surface.lifecycle,
            activity_state=activity.state if activity is not None else None,
            interaction_mode=intent.interaction_mode,
            presence_relation=intent.presence_relation,
            occlusion=intent.occlusion,
            content_masked=privacy and surface.sensitive,
            focus_owned=primary,
        )

    @staticmethod
    def _placement(
        surface: InteractionSurface,
        intent: SurfaceCompositionIntent,
        *,
        primary: bool,
        viewport: ViewportCharacteristics,
    ) -> CompositionPlacement:
        decision = surface.role is SurfaceRole.DECISION or surface.kind is SurfaceKind.CONFIRMATION
        if decision:
            return CompositionPlacement.FOREGROUND
        if viewport.size_class in {ViewportClass.NARROW, ViewportClass.VERY_NARROW}:
            return (
                CompositionPlacement.STACKED_PRIMARY
                if primary
                else CompositionPlacement.STACKED_SECONDARY
            )
        if surface.lifecycle is SurfaceLifecycle.COMPLETED:
            return CompositionPlacement.PERIPHERAL
        if (
            surface.kind is SurfaceKind.CONVERSATION
            and primary
            and surface.composition is None
        ):
            return CompositionPlacement.NEAR_RIGHT
        if surface.kind is SurfaceKind.CONVERSATION and surface.composition is None:
            return CompositionPlacement.LOWER
        if surface.kind is SurfaceKind.ACTIVITY and primary and surface.composition is None:
            return CompositionPlacement.NEAR_RIGHT
        if surface.kind is SurfaceKind.ACTIVITY and not primary:
            return CompositionPlacement.LOWER
        return intent.preferred_position

    @staticmethod
    def _size(
        model: HomePresentationModel,
        surface: InteractionSurface,
        intent: SurfaceCompositionIntent,
        *,
        primary: bool,
        viewport: ViewportCharacteristics,
        variant: CompositionVariant,
    ) -> CompositionSize:
        if surface.lifecycle in {
            SurfaceLifecycle.BACKGROUND,
            SurfaceLifecycle.COMPLETED,
        }:
            return CompositionSize.COMPACT
        activity = next(
            (item for item in model.activities if item.activity_id == surface.activity_id),
            None,
        )
        if activity is not None and activity.state in _TERMINAL_ACTIVITY_STATES:
            return CompositionSize.COMPACT
        if viewport.size_class is ViewportClass.VERY_NARROW:
            return CompositionSize.STANDARD if primary else CompositionSize.COMPACT
        if variant is CompositionVariant.CONVERSATION_FIRST:
            if surface.kind is SurfaceKind.CONVERSATION and primary:
                return CompositionSize.EXPANDED
            return CompositionSize.COMPACT if not primary else intent.size_class
        if variant is CompositionVariant.ADAPTIVE_CINEMATIC and primary:
            if surface.kind in {SurfaceKind.ACTIVITY, SurfaceKind.AGENT_TASK, SurfaceKind.MEDIA}:
                return CompositionSize.EXPANDED
        return intent.size_class

    @staticmethod
    def _stable_placement(
        surface: InteractionSurface,
        intent: SurfaceCompositionIntent,
        *,
        placement: CompositionPlacement,
        viewport: ViewportCharacteristics,
        variant: CompositionVariant,
        privacy: bool,
        previous_plan: CompositionPlan | None,
        primary_surface_id: str | None,
    ) -> CompositionPlacement:
        if previous_plan is None:
            return placement
        if previous_plan.viewport != viewport or previous_plan.variant is not variant:
            return placement
        if previous_plan.privacy_masked != privacy:
            return placement
        if previous_plan.primary_surface_id != primary_surface_id:
            return placement
        previous = next(
            (region for region in previous_plan.regions if region.surface_id == surface.surface_id),
            None,
        )
        if previous is None:
            return placement
        responsive_allowed = {
            CompositionPlacement.STACKED_PRIMARY,
            CompositionPlacement.STACKED_SECONDARY,
        }
        allowed = set(intent.allowed_positions) | responsive_allowed
        if surface.kind is SurfaceKind.CONFIRMATION:
            allowed.add(CompositionPlacement.FOREGROUND)
        if previous.placement in allowed:
            return previous.placement
        return placement

    def _intent(self, surface: InteractionSurface) -> SurfaceCompositionIntent:
        if surface.composition is not None:
            return surface.composition
        if surface.role is SurfaceRole.DECISION or surface.kind is SurfaceKind.CONFIRMATION:
            return SurfaceCompositionIntent(
                anchor=CompositionAnchor.ACTIVE_SURFACE,
                preferred_position=CompositionPlacement.FOREGROUND,
                allowed_positions=(
                    CompositionPlacement.FOREGROUND,
                    CompositionPlacement.STACKED_PRIMARY,
                ),
                size_class=CompositionSize.COMPACT,
                priority=CompositionPriority.DECISION,
                interaction_mode=SurfaceInteractionMode.DECISION,
                presence_relation=PresenceRelation.SHARED_ATTENTION,
            )
        if surface.kind is SurfaceKind.PROACTIVE:
            return SurfaceCompositionIntent(
                preferred_position=CompositionPlacement.NEAR_RIGHT,
                allowed_positions=(
                    CompositionPlacement.NEAR_RIGHT,
                    CompositionPlacement.NEAR_LEFT,
                    CompositionPlacement.STACKED_SECONDARY,
                ),
                size_class=CompositionSize.WHISPER,
                priority=CompositionPriority.SUPPORTING,
                interaction_mode=SurfaceInteractionMode.INSPECT,
                presence_relation=PresenceRelation.SHARED_ATTENTION,
            )
        if surface.kind is SurfaceKind.ACTIVITY:
            return SurfaceCompositionIntent(
                preferred_position=CompositionPlacement.LOWER,
                allowed_positions=(
                    CompositionPlacement.LOWER,
                    CompositionPlacement.NEAR_RIGHT,
                    CompositionPlacement.NEAR_LEFT,
                    CompositionPlacement.STACKED_PRIMARY,
                    CompositionPlacement.STACKED_SECONDARY,
                    CompositionPlacement.PERIPHERAL,
                ),
                size_class=CompositionSize.STANDARD,
                priority=CompositionPriority.SUPPORTING,
                interaction_mode=SurfaceInteractionMode.INSPECT,
                presence_relation=PresenceRelation.SURROUNDING,
            )
        if surface.kind is SurfaceKind.CONVERSATION:
            return SurfaceCompositionIntent(
                preferred_position=CompositionPlacement.NEAR_RIGHT,
                size_class=CompositionSize.STANDARD,
                priority=CompositionPriority.PRIMARY,
                interaction_mode=SurfaceInteractionMode.MIXED,
                presence_relation=PresenceRelation.BESIDE,
            )
        if surface.kind is SurfaceKind.MEDIA:
            return SurfaceCompositionIntent(
                preferred_position=CompositionPlacement.NEAR_RIGHT,
                allowed_positions=(
                    CompositionPlacement.NEAR_RIGHT,
                    CompositionPlacement.NEAR_LEFT,
                    CompositionPlacement.STACKED_PRIMARY,
                    CompositionPlacement.FULL_SPACE,
                ),
                size_class=CompositionSize.EXPANDED,
                priority=CompositionPriority.PRIMARY,
                interaction_mode=SurfaceInteractionMode.DIRECT,
                presence_relation=PresenceRelation.COMPACT_PRESENCE,
            )
        return SurfaceCompositionIntent(
            preferred_position=CompositionPlacement.NEAR_RIGHT,
            size_class=CompositionSize.STANDARD,
            priority=CompositionPriority.SUPPORTING,
            interaction_mode=SurfaceInteractionMode.INSPECT,
            presence_relation=PresenceRelation.BESIDE,
        )

    @staticmethod
    def _masha(
        model: HomePresentationModel,
        *,
        viewport: ViewportCharacteristics,
        variant: CompositionVariant,
        privacy: bool,
    ) -> MashaComposition:
        if viewport.size_class in {ViewportClass.NARROW, ViewportClass.VERY_NARROW}:
            placement = CompositionPlacement.UPPER
            size = (
                CompositionSize.COMPACT
                if viewport.size_class is ViewportClass.VERY_NARROW
                else CompositionSize.STANDARD
            )
        else:
            placement = CompositionPlacement.CENTER_LEFT
            size = (
                CompositionSize.EXPANDED
                if variant is CompositionVariant.PRESENCE_FIRST
                else CompositionSize.STANDARD
            )
        return MashaComposition(
            placement=placement,
            size_class=size,
            pose=model.presence.pose,
            expression=model.presence.expression,
            attention=model.presence.attention,
            activity=model.presence.activity,
            face_visible=not privacy,
            silhouette_visible=True,
        )

    @staticmethod
    def _overlays(
        model: HomePresentationModel,
        *,
        privacy: bool,
    ) -> tuple[CompositionOverlay, ...]:
        overlays: list[CompositionOverlay] = []
        if privacy:
            overlays.append(
                CompositionOverlay(
                    kind=OverlayKind.PRIVACY,
                    state_code="privacy_masked",
                    placement=CompositionPlacement.FULL_SPACE,
                    priority=CompositionPriority.SAFETY,
                    salience=OverlaySalience.ELEVATED,
                    masks_sensitive_content=True,
                )
            )
        if model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED:
            overlays.append(
                CompositionOverlay(
                    kind=OverlayKind.SAFETY,
                    state_code=model.overlays.safety.value,
                    placement=CompositionPlacement.PERIPHERAL,
                    priority=CompositionPriority.SAFETY,
                    salience=OverlaySalience.ELEVATED,
                )
            )
        if model.overlays.proactive is ProactiveOverlay.OFF:
            overlays.append(
                CompositionOverlay(
                    kind=OverlayKind.PROACTIVE,
                    state_code=model.overlays.proactive.value,
                    placement=CompositionPlacement.AMBIENT_BACKGROUND,
                    priority=CompositionPriority.AMBIENT,
                    salience=OverlaySalience.SUBTLE,
                )
            )
        if model.overlays.model is not ModelOverlay.AVAILABLE:
            overlays.append(
                CompositionOverlay(
                    kind=OverlayKind.MODEL,
                    state_code=model.overlays.model.value,
                    placement=CompositionPlacement.PERIPHERAL,
                    priority=CompositionPriority.SUPPORTING,
                    salience=OverlaySalience.NORMAL,
                )
            )
        overlays.append(
            CompositionOverlay(
                kind=OverlayKind.RUNTIME,
                state_code=f"{model.overlays.runtime_mode.value}:{model.overlays.daemon.value}",
                placement=CompositionPlacement.AMBIENT_BACKGROUND,
                priority=CompositionPriority.AMBIENT,
                salience=OverlaySalience.SUBTLE,
            )
        )
        return tuple(overlays)

    @staticmethod
    def _focus(
        model: HomePresentationModel,
        *,
        primary: InteractionSurface | None,
        privacy: bool,
        stopped: bool,
    ) -> tuple[FocusOwner, str | None]:
        if privacy:
            return FocusOwner.PRIVACY, None
        if stopped:
            return FocusOwner.SAFETY, None
        if primary is not None:
            return FocusOwner.SURFACE, primary.surface_id
        if model.presence.attention is AttentionState.TOWARD_USER:
            return FocusOwner.USER, None
        return FocusOwner.PRESENCE, None

    @staticmethod
    def _stability_key(**semantic_state) -> str:
        def normalized(value):
            if hasattr(value, "model_dump"):
                return value.model_dump(mode="json")
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, tuple):
                return [normalized(item) for item in value]
            if isinstance(value, list):
                return [normalized(item) for item in value]
            if isinstance(value, dict):
                return {key: normalized(item) for key, item in value.items()}
            return value

        payload = json.dumps(
            normalized(semantic_state),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"cmp1_{hashlib.sha256(payload).hexdigest()[:20]}"

    @staticmethod
    def _stability(
        previous_plan: CompositionPlan | None,
        *,
        stability_key: str,
        viewport: ViewportCharacteristics,
        privacy: bool,
        stopped: bool,
    ) -> CompositionStability:
        if previous_plan is None:
            return CompositionStability.INITIAL
        if previous_plan.viewport != viewport:
            return CompositionStability.VIEWPORT_OVERRIDE
        if previous_plan.privacy_masked != privacy:
            return CompositionStability.PRIVACY_OVERRIDE
        previous_stopped = any(
            overlay.kind is OverlayKind.SAFETY for overlay in previous_plan.overlays
        )
        if previous_stopped != stopped:
            return CompositionStability.SAFETY_OVERRIDE
        if previous_plan.stability_key == stability_key:
            return CompositionStability.STABLE
        return CompositionStability.RECOMPOSED
