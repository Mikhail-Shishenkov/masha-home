"""Read-only Home projection owned by the public application boundary."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.presentation import (
    AssistantResponded,
    AssistantStartedThinking,
    ActivityCompleted,
    ActivityFailed,
    ActivityStarted,
    AutonomyResumed,
    CompositionPlan,
    CompositionResolver,
    CompositionVariant,
    HomePresentationModel,
    EmergencyStopEngaged,
    ModelUnavailable,
    InteractionSurface,
    SurfaceCapability,
    SurfaceCompleted,
    SurfaceCreated,
    SurfaceFocused,
    SurfaceKind,
    SurfaceLifecycle,
    SurfaceRole,
    PresentationRuntime,
    UserOpenedApplication,
    UserSentMessage,
    ViewportCharacteristics,
    presentation_model_from_application_state,
)

from .contracts import MashaStatusView, ModelProfileView, UiContract, VisualAssetView
from .model_settings import ModelSettingsService
from .status import MashaStatusService
from .visual_assets import VisualIdentityResolver


class HomeSnapshotView(UiContract):
    """Bounded renderer-safe data with no service, provider, or storage handles."""

    observed_at: datetime
    status: MashaStatusView
    active_model: ModelProfileView
    visual_assets: tuple[VisualAssetView, ...]
    presentation: HomePresentationModel
    composition: CompositionPlan


class HomeSnapshotService:
    """Build one deterministic UI projection from existing read-only services."""

    def __init__(
        self,
        *,
        status: MashaStatusService,
        models: ModelSettingsService,
        visuals: VisualIdentityResolver,
        composition: CompositionResolver | None = None,
    ):
        self._status = status
        self._models = models
        self._visuals = visuals
        self._composition = composition or CompositionResolver()

    def snapshot(
        self,
        *,
        viewport: ViewportCharacteristics | None = None,
    ) -> HomeSnapshotView:
        """Read local state without mutating persistence or invoking a model."""
        observed_at = datetime.now(timezone.utc)
        status = self._status.snapshot()
        active_model = self._models.current()
        visual_assets = self._visuals.canonical_assets()
        presentation = presentation_model_from_application_state(
            status=status,
            active_model=active_model,
            visual_assets=visual_assets,
            observed_at=observed_at,
        )
        return HomeSnapshotView(
            observed_at=observed_at,
            status=status,
            active_model=active_model,
            visual_assets=visual_assets,
            presentation=presentation,
            composition=self._composition.resolve(
                presentation,
                viewport=viewport,
                variant=CompositionVariant.PRESENCE_FIRST,
            ),
        )

    def open_session(self) -> "HomePresentationSession":
        """Create a local UI-only presentation session from the current snapshot."""
        return HomePresentationSession(self.snapshot(), composition=self._composition)


class HomePresentationSession:
    """Deterministic UI session; it owns no domain data and performs no mutation."""

    def __init__(self, snapshot: HomeSnapshotView, *, composition: CompositionResolver):
        self._status = snapshot.status
        self._active_model = snapshot.active_model
        self._visual_assets = snapshot.visual_assets
        self._composition = composition
        self._runtime = PresentationRuntime(snapshot.presentation)

    def opened(self) -> HomeSnapshotView:
        return self._dispatch(UserOpenedApplication(occurred_at=datetime.now(timezone.utc)))

    def user_sent(self) -> HomeSnapshotView:
        return self._dispatch(UserSentMessage(occurred_at=datetime.now(timezone.utc)))

    def assistant_thinking(self) -> HomeSnapshotView:
        return self._dispatch(AssistantStartedThinking(occurred_at=datetime.now(timezone.utc)))

    def assistant_responded(self) -> HomeSnapshotView:
        return self._dispatch(AssistantResponded(occurred_at=datetime.now(timezone.utc)))

    def confirmation_requested(self, *, title: str, summary: str) -> HomeSnapshotView:
        now = datetime.now(timezone.utc)
        self._dispatch(
            SurfaceCreated(
                occurred_at=now,
                surface=InteractionSurface(
                    surface_id="confirmation.commitment",
                    kind=SurfaceKind.CONFIRMATION,
                    lifecycle=SurfaceLifecycle.ACTIVE,
                    role=SurfaceRole.DECISION,
                    title=title,
                    summary=summary,
                    sensitive=True,
                    capabilities=(SurfaceCapability.CONFIRM, SurfaceCapability.REJECT),
                ),
            )
        )
        return self._dispatch(
            SurfaceFocused(occurred_at=now, surface_id="confirmation.commitment")
        )

    def commitments_opened(self, *, summary: str) -> HomeSnapshotView:
        now = datetime.now(timezone.utc)
        self._dispatch(
            SurfaceCreated(
                occurred_at=now,
                surface=InteractionSurface(
                    surface_id="home.commitments",
                    kind=SurfaceKind.COMMITMENT,
                    lifecycle=SurfaceLifecycle.ACTIVE,
                    role=SurfaceRole.SUPPORTING,
                    title="Наши дела",
                    summary=summary,
                    capabilities=(SurfaceCapability.INSPECT,),
                ),
            )
        )
        return self._dispatch(SurfaceFocused(occurred_at=now, surface_id="home.commitments"))

    def confirmation_resolving(self, *, title: str) -> HomeSnapshotView:
        now = datetime.now(timezone.utc)
        self._dispatch(
            SurfaceCompleted(occurred_at=now, surface_id="confirmation.commitment")
        )
        return self._dispatch(
            ActivityStarted(
                occurred_at=now,
                activity_id="activity.confirmation",
                surface_id="activity.confirmation",
                title=title,
                summary="Применяю только подтверждённое изменение локально",
            )
        )

    def confirmation_resolved(self, *, summary: str) -> HomeSnapshotView:
        return self._dispatch(
            ActivityCompleted(
                occurred_at=datetime.now(timezone.utc),
                activity_id="activity.confirmation",
                summary=summary,
            )
        )

    def confirmation_failed(self, *, summary: str) -> HomeSnapshotView:
        return self._dispatch(
            ActivityFailed(
                occurred_at=datetime.now(timezone.utc),
                activity_id="activity.confirmation",
                summary=summary,
                reason_code="confirmation_failed",
            )
        )

    def model_unavailable(self, *, profile_id: str, display_name: str) -> HomeSnapshotView:
        return self._dispatch(
            ModelUnavailable(
                occurred_at=datetime.now(timezone.utc),
                profile_id=profile_id,
                display_name=display_name,
            )
        )

    def emergency_stop(self, *, reason: str) -> HomeSnapshotView:
        self._status = self._status.model_copy(
            update={
                "emergency_stop_engaged": True,
                "safety_label": "Аварийная остановка включена",
            }
        )
        return self._dispatch(
            EmergencyStopEngaged(
                occurred_at=datetime.now(timezone.utc),
                reason=reason,
            )
        )

    def autonomy_resumed(self) -> HomeSnapshotView:
        self._status = self._status.model_copy(
            update={
                "emergency_stop_engaged": False,
                "safety_label": "Аварийная остановка выключена",
            }
        )
        return self._dispatch(AutonomyResumed(occurred_at=datetime.now(timezone.utc)))

    @property
    def active_model_display_name(self) -> str:
        return self._active_model.display_name

    def _dispatch(self, event) -> HomeSnapshotView:
        presentation = self._runtime.dispatch(event)
        return HomeSnapshotView(
            observed_at=presentation.observed_at,
            status=self._status,
            active_model=self._active_model,
            visual_assets=self._visual_assets,
            presentation=presentation,
            composition=self._composition.resolve(
                presentation,
                variant=CompositionVariant.PRESENCE_FIRST,
            ),
        )
