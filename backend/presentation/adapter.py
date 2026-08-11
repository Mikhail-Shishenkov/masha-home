"""Read-only projection from the UI-01 application boundary."""

from __future__ import annotations

from datetime import datetime

from backend.application.contracts import (
    MashaStatusView,
    ModelAvailabilityCode,
    ModelProfileView,
    VisualAssetView,
)

from .models import (
    AmbientState,
    BasePose,
    DaemonOverlay,
    HomePresentationModel,
    HomeState,
    MashaPresence,
    ModelOverlay,
    OperatingOverlays,
    PresentationTier,
    ProactiveOverlay,
    RuntimeMode,
    SafetyOverlay,
    VisualIdentity,
)


def presentation_model_from_application_state(
    *,
    status: MashaStatusView,
    active_model: ModelProfileView,
    visual_assets: tuple[VisualAssetView, ...],
    observed_at: datetime,
) -> HomePresentationModel:
    """Project UI-safe facts only; never query a domain store or provider."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("presentation timestamps must be timezone-aware")
    if active_model.profile_id != status.active_profile_id:
        raise ValueError("application status and active model profile disagree")

    model = (
        ModelOverlay.AVAILABLE
        if status.model_availability_code is ModelAvailabilityCode.AVAILABLE
        else ModelOverlay.UNAVAILABLE
    )
    runtime_mode = (
        RuntimeMode.BACKGROUND
        if status.runtime_mode == "background"
        else RuntimeMode.MANUAL
    )
    daemon = (
        DaemonOverlay.NOT_REQUIRED
        if runtime_mode is RuntimeMode.MANUAL
        else DaemonOverlay.RUNNING
        if status.daemon_running
        else DaemonOverlay.STOPPED
    )
    home_state = HomeState(status.runtime_status)
    return HomePresentationModel(
        observed_at=observed_at,
        home_state=home_state,
        presence=MashaPresence(
            visual_identity=VisualIdentity(
                visual_identity_id="masha",
                avatar_variant_id="canonical",
                asset_ids=tuple(asset.asset_id for asset in visual_assets),
                tier=PresentationTier.TIER_0,
            ),
            pose=BasePose.UNAVAILABLE
            if home_state is HomeState.UNAVAILABLE
            else BasePose.IDLE,
            ambient=AmbientState.ACTIVE,
        ),
        overlays=OperatingOverlays(
            safety=SafetyOverlay.AUTONOMY_STOPPED
            if status.emergency_stop_engaged
            else SafetyOverlay.AUTONOMY_ACTIVE,
            proactive=ProactiveOverlay.ON
            if status.proactive_enabled
            else ProactiveOverlay.OFF,
            proactive_level=status.proactive_level,
            model=model,
            active_profile_id=active_model.profile_id,
            model_display_name=active_model.display_name,
            runtime_mode=runtime_mode,
            daemon=daemon,
        ),
    )
