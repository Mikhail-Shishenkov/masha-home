"""Pure deterministic state reduction for Presentation Runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

from .events import (
    ActivityCancelled,
    ActivityCompleted,
    ActivityFailed,
    ActivityProgressed,
    ActivityQueued,
    ActivityStarted,
    ActivityWaiting,
    AssistantResponded,
    AssistantStartedThinking,
    AssistantSettled,
    AutonomyResumed,
    EmergencyStopEngaged,
    ModelChanged,
    ModelSwitchStarted,
    ModelUnavailable,
    PresentationEvent,
    ProactiveAcknowledged,
    ProactiveCandidateAppeared,
    ProactiveDelivered,
    ProactiveDismissed,
    RuntimeModeChanged,
    SurfaceBackgrounded,
    SurfaceClosed,
    SurfaceCompleted,
    SurfaceCreated,
    SurfaceFocused,
    SurfaceMinimized,
    UserOpenedApplication,
    UserSentMessage,
    WindowFocusChanged,
    HomeMomentChanged,
)
from .models import (
    ActivityPresentation,
    ActivityProgress,
    ActivityState,
    AmbientState,
    AttentionState,
    BasePose,
    DaemonOverlay,
    ExpressionCode,
    ExpressionCue,
    ExpressionHold,
    ExpressionSource,
    HomePresentationModel,
    InteractionSurface,
    ModelOverlay,
    OperatingOverlays,
    PresenceActivity,
    ProgressKind,
    ProactiveOverlay,
    RuntimeMode,
    SafetyOverlay,
    SurfaceCapability,
    SurfaceKind,
    SurfaceLifecycle,
    SurfaceRole,
    WindowState,
)


CONVERSATION_SURFACE_ID = "home.conversation"

_RESPONSE_EXPRESSION_CODES = {
    "warm": ExpressionCode.WARM_SMILE,
    "amused": ExpressionCode.AMUSED,
    "thoughtful": ExpressionCode.THOUGHTFUL,
    "supportive": ExpressionCode.SYMPATHETIC,
    "firm": ExpressionCode.SERIOUS,
    "playful": ExpressionCode.PLAYFUL,
}

class PresentationReducer:
    """Maps an event and immutable model to a new model without side effects."""

    def reduce(
        self,
        model: HomePresentationModel,
        event: PresentationEvent,
    ) -> HomePresentationModel:
        next_model = self._reduce(model, event)
        return HomePresentationModel.model_validate(
            next_model.model_copy(
                update={
                    "revision": model.revision + 1,
                    "observed_at": event.occurred_at,
                }
            ).model_dump()
        )

    def _reduce(
        self,
        model: HomePresentationModel,
        event: PresentationEvent,
    ) -> HomePresentationModel:
        if isinstance(event, UserOpenedApplication):
            conversation = InteractionSurface(
                surface_id=CONVERSATION_SURFACE_ID,
                kind=SurfaceKind.CONVERSATION,
                lifecycle=SurfaceLifecycle.ACTIVE,
                role=SurfaceRole.PRIMARY,
                title="Разговор",
                summary="Маша рядом",
                sensitive=True,
                capabilities=(SurfaceCapability.INSPECT, SurfaceCapability.COLLAPSE),
            )
            return model.model_copy(
                update={
                    "opened": True,
                    "surfaces": self._upsert_surface(model.surfaces, conversation),
                    "active_surface_id": conversation.surface_id,
                }
            )

        if isinstance(event, HomeMomentChanged):
            return model.model_copy(
                update={
                    "home_moment": event.moment,
                }
            )

        if isinstance(event, UserSentMessage):
            current = self._ensure_conversation(model)
            current = self._focus(current, CONVERSATION_SURFACE_ID)
            return current.model_copy(
                update={
                    "presence": current.presence.model_copy(
                        update={
                            "pose": BasePose.ATTENTIVE,
                            "expression": self._expression(ExpressionCode.ATTENTIVE, 0.32),
                            "attention": AttentionState.TOWARD_USER,
                            "activity": PresenceActivity.WAITING,
                        }
                    )
                }
            )

        if isinstance(event, AssistantStartedThinking):
            return model.model_copy(
                update={
                    "presence": model.presence.model_copy(
                        update={
                            "pose": BasePose.ATTENTIVE,
                            "expression": self._expression(ExpressionCode.THOUGHTFUL, 0.4),
                            "attention": AttentionState.THINKING_AWAY,
                            "activity": PresenceActivity.PROCESSING,
                        }
                    )
                }
            )

        if isinstance(event, AssistantResponded):
            expression_code = _RESPONSE_EXPRESSION_CODES[
                event.expression_cue
            ]

            return model.model_copy(
                update={
                    "presence": model.presence.model_copy(
                        update={
                            "pose": BasePose.SPEAKING,
                            "expression": self._expression(
                                expression_code,
                                0.34,
                                source=ExpressionSource.APPLICATION_CUE,
                            ),
                            "attention": AttentionState.TOWARD_USER,
                            "activity": PresenceActivity.SPEAKING,
                        }
                    )
                }
            )

        if isinstance(event, AssistantSettled):
            current_expression = model.presence.expression

            settled_expression = (
                current_expression.model_copy(
                    update={
                        "intensity": min(
                            current_expression.intensity,
                            0.18,
                        ),
                        "hold": ExpressionHold.WHILE_STATE_ACTIVE,
                    }
                )
                if current_expression is not None
                else self._expression(
                    ExpressionCode.NEUTRAL,
                    0.12,
                )
            )

            return model.model_copy(
                update={
                    "presence": model.presence.model_copy(
                        update={
                            "pose": BasePose.ATTENTIVE,
                            "expression": settled_expression,
                            "attention": AttentionState.TOWARD_USER,
                            "activity": PresenceActivity.IDLE,
                        }
                    )
                }
            )

        if isinstance(event, SurfaceCreated):
            update = {"surfaces": self._upsert_surface(model.surfaces, event.surface)}
            if event.surface.kind in {SurfaceKind.CONFIRMATION, SurfaceKind.COMMITMENT}:
                update["presence"] = model.presence.model_copy(
                    update={
                        "pose": BasePose.ATTENTIVE,
                        "expression": self._expression(ExpressionCode.ATTENTIVE, 0.38),
                        "attention": AttentionState.TOWARD_SURFACE,
                        "activity": (
                            PresenceActivity.CONFIRMATION
                            if event.surface.kind is SurfaceKind.CONFIRMATION
                            else PresenceActivity.WAITING
                        ),
                    }
                )
            return model.model_copy(update=update)
        if isinstance(event, SurfaceFocused):
            return self._focus(model, event.surface_id)
        if isinstance(event, SurfaceMinimized):
            return self._surface_lifecycle(model, event.surface_id, SurfaceLifecycle.MINIMIZED)
        if isinstance(event, SurfaceBackgrounded):
            return self._surface_lifecycle(model, event.surface_id, SurfaceLifecycle.BACKGROUND)
        if isinstance(event, SurfaceCompleted):
            return self._surface_lifecycle(model, event.surface_id, SurfaceLifecycle.COMPLETED)
        if isinstance(event, SurfaceClosed):
            return self._surface_lifecycle(model, event.surface_id, SurfaceLifecycle.CLOSED)

        if isinstance(event, ActivityQueued):
            activity = ActivityPresentation(
                activity_id=event.activity_id,
                state=ActivityState.QUEUED,
                title=event.title,
                summary=event.summary,
                updated_at=event.occurred_at,
            )
            surface = self._activity_surface(event.surface_id, activity)
            return model.model_copy(
                update={
                    "activities": self._upsert_activity(model.activities, activity),
                    "surfaces": self._upsert_surface(model.surfaces, surface),
                }
            )

        if isinstance(event, ActivityStarted):
            if model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED:
                activity = ActivityPresentation(
                    activity_id=event.activity_id,
                    state=ActivityState.WAITING,
                    title=event.title,
                    summary="Автономность остановлена — задача не запущена",
                    updated_at=event.occurred_at,
                    reason_code="emergency_stop_engaged",
                )
                return model.model_copy(
                    update={
                        "activities": self._upsert_activity(model.activities, activity),
                        "surfaces": self._upsert_surface(
                            model.surfaces,
                            self._activity_surface(event.surface_id, activity),
                        ),
                    }
                )
            activity = ActivityPresentation(
                activity_id=event.activity_id,
                state=ActivityState.RUNNING,
                title=event.title,
                summary=event.summary,
                progress=ActivityProgress(kind=ProgressKind.INDETERMINATE),
                started_at=event.occurred_at,
                updated_at=event.occurred_at,
            )
            return model.model_copy(
                update={
                    "activities": self._upsert_activity(model.activities, activity),
                    "surfaces": self._upsert_surface(
                        model.surfaces,
                        self._activity_surface(event.surface_id, activity, active=True),
                    ),
                    "presence": model.presence.model_copy(
                        update={
                            "pose": BasePose.WORKING,
                            "expression": self._expression(ExpressionCode.ATTENTIVE, 0.28),
                            "attention": AttentionState.TOWARD_SURFACE,
                            "activity": PresenceActivity.WORKING,
                        }
                    ),
                }
            )

        if isinstance(event, ActivityProgressed):
            activity = self._activity(model, event.activity_id)
            if activity is None:
                return model
            progressed = activity.model_copy(
                update={
                    "state": ActivityState.RUNNING,
                    "summary": event.summary,
                    "progress": ActivityProgress(
                        kind=ProgressKind.STEPS,
                        completed_units=event.completed_units,
                        total_units=event.total_units,
                        label=f"{event.completed_units} / {event.total_units}",
                    ),
                    "updated_at": event.occurred_at,
                }
            )
            return self._replace_activity_and_surface(model, progressed, SurfaceLifecycle.ACTIVE)

        if isinstance(event, ActivityWaiting):
            return self._terminal_or_waiting_activity(
                model,
                event.activity_id,
                ActivityState.WAITING,
                event.summary,
                event.occurred_at,
                SurfaceLifecycle.BACKGROUND,
                PresenceActivity.WAITING,
                ExpressionCode.ATTENTIVE,
            )

        if isinstance(event, ActivityCompleted):
            return self._terminal_or_waiting_activity(
                model,
                event.activity_id,
                ActivityState.COMPLETED,
                event.summary,
                event.occurred_at,
                SurfaceLifecycle.COMPLETED,
                PresenceActivity.COMPLETED,
                ExpressionCode.PROUD,
            )

        if isinstance(event, ActivityFailed):
            return self._terminal_or_waiting_activity(
                model,
                event.activity_id,
                ActivityState.FAILED,
                event.summary,
                event.occurred_at,
                SurfaceLifecycle.COMPLETED,
                PresenceActivity.ERROR,
                ExpressionCode.SERIOUS,
                reason_code=event.reason_code,
            )

        if isinstance(event, ActivityCancelled):
            return self._terminal_or_waiting_activity(
                model,
                event.activity_id,
                ActivityState.CANCELLED,
                event.summary,
                event.occurred_at,
                SurfaceLifecycle.COMPLETED,
                PresenceActivity.IDLE,
                ExpressionCode.NEUTRAL,
            )

        if isinstance(event, ProactiveCandidateAppeared):
            surface = InteractionSurface(
                surface_id=self._proactive_surface_id(event.event_id),
                kind=SurfaceKind.PROACTIVE,
                lifecycle=SurfaceLifecycle.CREATED,
                role=SurfaceRole.SUPPORTING,
                title=event.title,
                capabilities=(SurfaceCapability.INSPECT,),
            )
            return model.model_copy(
                update={"surfaces": self._upsert_surface(model.surfaces, surface)}
            )

        if isinstance(event, ProactiveDelivered):
            surface_id = self._proactive_surface_id(event.event_id)
            existing = self._surface(model, surface_id)
            if model.overlays.safety is SafetyOverlay.AUTONOMY_STOPPED:
                blocked = (existing or InteractionSurface(
                    surface_id=surface_id,
                    kind=SurfaceKind.PROACTIVE,
                    title="Инициативное сообщение",
                )).model_copy(
                    update={
                        "lifecycle": SurfaceLifecycle.BACKGROUND,
                        "role": SurfaceRole.SUPPORTING,
                        "summary": "Доставка не показана: автономность остановлена",
                    }
                )
                return model.model_copy(
                    update={"surfaces": self._upsert_surface(model.surfaces, blocked)}
                )
            delivered = (existing or InteractionSurface(
                surface_id=surface_id,
                kind=SurfaceKind.PROACTIVE,
                title="Маша обращается к тебе",
            )).model_copy(
                update={
                    "lifecycle": SurfaceLifecycle.ACTIVE,
                    "role": SurfaceRole.SUPPORTING,
                    "summary": event.text,
                    "sensitive": True,
                    "capabilities": (
                        SurfaceCapability.ACKNOWLEDGE,
                        SurfaceCapability.DISMISS,
                    ),
                }
            )
            busy = model.presence.activity in {
                PresenceActivity.LISTENING,
                PresenceActivity.PROCESSING,
                PresenceActivity.SPEAKING,
            }
            presence = model.presence if busy else model.presence.model_copy(
                update={
                    "pose": BasePose.ATTENTIVE,
                    "expression": self._expression(ExpressionCode.ATTENTIVE, 0.34),
                    "attention": AttentionState.PROACTIVE,
                    "activity": PresenceActivity.WAITING,
                }
            )
            return model.model_copy(
                update={
                    "surfaces": self._upsert_surface(model.surfaces, delivered),
                    "presence": presence,
                    "overlays": model.overlays.model_copy(
                        update={"proactive": ProactiveOverlay.ATTENTION}
                    ),
                }
            )

        if isinstance(event, (ProactiveDismissed, ProactiveAcknowledged)):
            lifecycle = (
                SurfaceLifecycle.CLOSED
                if isinstance(event, ProactiveDismissed)
                else SurfaceLifecycle.COMPLETED
            )
            updated = self._surface_lifecycle(
                model,
                self._proactive_surface_id(event.event_id),
                lifecycle,
            )
            return updated.model_copy(
                update={
                    "overlays": updated.overlays.model_copy(
                        update={
                            "proactive": ProactiveOverlay.ON
                            if updated.overlays.proactive_level > 0
                            else ProactiveOverlay.OFF
                        }
                    ),
                    "presence": updated.presence.model_copy(
                        update={
                            "pose": BasePose.IDLE,
                            "expression": self._expression(ExpressionCode.NEUTRAL, 0.2),
                            "attention": AttentionState.AMBIENT,
                            "activity": PresenceActivity.IDLE,
                        }
                    ),
                }
            )

        if isinstance(event, ModelSwitchStarted):
            return model.model_copy(
                update={
                    "overlays": model.overlays.model_copy(
                        update={"model": ModelOverlay.SWITCHING}
                    )
                }
            )

        if isinstance(event, ModelChanged):
            return model.model_copy(
                update={
                    "overlays": model.overlays.model_copy(
                        update={
                            "model": ModelOverlay.AVAILABLE,
                            "active_profile_id": event.profile_id,
                            "model_display_name": event.display_name,
                        }
                    )
                }
            )

        if isinstance(event, ModelUnavailable):
            return model.model_copy(
                update={
                    "overlays": model.overlays.model_copy(
                        update={
                            "model": ModelOverlay.UNAVAILABLE,
                            "active_profile_id": event.profile_id,
                            "model_display_name": event.display_name,
                        }
                    )
                }
            )

        if isinstance(event, EmergencyStopEngaged):
            return model.model_copy(
                update={
                    "overlays": model.overlays.model_copy(
                        update={"safety": SafetyOverlay.AUTONOMY_STOPPED}
                    ),
                    "presence": model.presence.model_copy(
                        update={"ambient": AmbientState.QUIET}
                    ),
                }
            )

        if isinstance(event, AutonomyResumed):
            return model.model_copy(
                update={
                    "overlays": model.overlays.model_copy(
                        update={"safety": SafetyOverlay.AUTONOMY_ACTIVE}
                    ),
                    "presence": model.presence.model_copy(
                        update={"ambient": self._ambient_for_window(model.window_state)}
                    ),
                }
            )

        if isinstance(event, RuntimeModeChanged):
            daemon = (
                DaemonOverlay.NOT_REQUIRED
                if event.runtime_mode is RuntimeMode.MANUAL
                else DaemonOverlay.RUNNING
                if event.daemon_running
                else DaemonOverlay.STOPPED
            )
            return model.model_copy(
                update={
                    "overlays": model.overlays.model_copy(
                        update={"runtime_mode": event.runtime_mode, "daemon": daemon}
                    )
                }
            )

        if isinstance(event, WindowFocusChanged):
            window = WindowState.FOCUSED if event.focused else WindowState.UNFOCUSED
            return model.model_copy(
                update={
                    "window_state": window,
                    "privacy_masked": not event.focused,
                    "presence": model.presence.model_copy(
                        update={"ambient": self._ambient_for_window(window)}
                    ),
                }
            )

        raise TypeError(f"unsupported presentation event: {type(event).__name__}")

    @staticmethod
    def _expression(
            code: ExpressionCode,
            intensity: float,
            *,
            source: ExpressionSource = ExpressionSource.STATE_RULE,
    ) -> ExpressionCue:
        return ExpressionCue(
            code=code,
            intensity=intensity,
            source=source,
            hold=ExpressionHold.WHILE_STATE_ACTIVE,
        )

    @staticmethod
    def _ambient_for_window(window: WindowState) -> AmbientState:
        return AmbientState.ACTIVE if window is WindowState.FOCUSED else AmbientState.PRIVACY

    @staticmethod
    def _upsert_surface(
        surfaces: tuple[InteractionSurface, ...],
        surface: InteractionSurface,
    ) -> tuple[InteractionSurface, ...]:
        rows = list(surfaces)
        for index, item in enumerate(rows):
            if item.surface_id == surface.surface_id:
                rows[index] = surface
                break
        else:
            rows.append(surface)
        return tuple(rows)

    @staticmethod
    def _upsert_activity(
        activities: tuple[ActivityPresentation, ...],
        activity: ActivityPresentation,
    ) -> tuple[ActivityPresentation, ...]:
        rows = list(activities)
        for index, item in enumerate(rows):
            if item.activity_id == activity.activity_id:
                rows[index] = activity
                break
        else:
            rows.append(activity)
        return tuple(rows)

    @staticmethod
    def _surface(model: HomePresentationModel, surface_id: str) -> InteractionSurface | None:
        return next((item for item in model.surfaces if item.surface_id == surface_id), None)

    @staticmethod
    def _activity(model: HomePresentationModel, activity_id: str) -> ActivityPresentation | None:
        return next((item for item in model.activities if item.activity_id == activity_id), None)

    def _ensure_conversation(self, model: HomePresentationModel) -> HomePresentationModel:
        if self._surface(model, CONVERSATION_SURFACE_ID) is not None:
            return model
        surface = InteractionSurface(
            surface_id=CONVERSATION_SURFACE_ID,
            kind=SurfaceKind.CONVERSATION,
            lifecycle=SurfaceLifecycle.ACTIVE,
            role=SurfaceRole.PRIMARY,
            title="Разговор",
            sensitive=True,
        )
        return model.model_copy(
            update={
                "surfaces": self._upsert_surface(model.surfaces, surface),
                "active_surface_id": surface.surface_id,
            }
        )

    def _focus(self, model: HomePresentationModel, surface_id: str) -> HomePresentationModel:
        target = self._surface(model, surface_id)
        if target is None or target.lifecycle in {SurfaceLifecycle.COMPLETED, SurfaceLifecycle.CLOSED}:
            return model
        rows = []
        for surface in model.surfaces:
            if surface.surface_id == surface_id:
                rows.append(
                    surface.model_copy(
                        update={
                            "lifecycle": SurfaceLifecycle.ACTIVE,
                            "role": (
                                SurfaceRole.DECISION
                                if surface.role is SurfaceRole.DECISION
                                else SurfaceRole.PRIMARY
                            ),
                        }
                    )
                )
            elif surface.role is SurfaceRole.PRIMARY:
                rows.append(
                    surface.model_copy(
                        update={"lifecycle": SurfaceLifecycle.BACKGROUND, "role": SurfaceRole.SUPPORTING}
                    )
                )
            else:
                rows.append(surface)
        return model.model_copy(update={"surfaces": tuple(rows), "active_surface_id": surface_id})

    def _surface_lifecycle(
        self,
        model: HomePresentationModel,
        surface_id: str,
        lifecycle: SurfaceLifecycle,
    ) -> HomePresentationModel:
        target = self._surface(model, surface_id)
        if target is None:
            return model
        role = target.role
        if lifecycle in {
            SurfaceLifecycle.MINIMIZED,
            SurfaceLifecycle.BACKGROUND,
            SurfaceLifecycle.COMPLETED,
            SurfaceLifecycle.CLOSED,
        }:
            role = SurfaceRole.SUPPORTING
        updated = target.model_copy(update={"lifecycle": lifecycle, "role": role})
        active_id = model.active_surface_id
        if surface_id == active_id and lifecycle is not SurfaceLifecycle.ACTIVE:
            active_id = None
        return model.model_copy(
            update={
                "surfaces": self._upsert_surface(model.surfaces, updated),
                "active_surface_id": active_id,
            }
        )

    @staticmethod
    def _activity_surface(
        surface_id: str,
        activity: ActivityPresentation,
        *,
        active: bool = False,
    ) -> InteractionSurface:
        return InteractionSurface(
            surface_id=surface_id,
            kind=SurfaceKind.ACTIVITY,
            lifecycle=SurfaceLifecycle.ACTIVE if active else SurfaceLifecycle.CREATED,
            role=SurfaceRole.SUPPORTING,
            title=activity.title,
            summary=activity.summary,
            capabilities=(SurfaceCapability.INSPECT, SurfaceCapability.COLLAPSE),
            activity_id=activity.activity_id,
        )

    def _replace_activity_and_surface(
        self,
        model: HomePresentationModel,
        activity: ActivityPresentation,
        lifecycle: SurfaceLifecycle,
    ) -> HomePresentationModel:
        surface = next(
            (item for item in model.surfaces if item.activity_id == activity.activity_id),
            None,
        )
        surfaces = model.surfaces
        if surface is not None:
            surfaces = self._upsert_surface(
                surfaces,
                surface.model_copy(
                    update={
                        "lifecycle": lifecycle,
                        "summary": activity.summary,
                        "role": SurfaceRole.SUPPORTING,
                    }
                ),
            )
        return model.model_copy(
            update={
                "activities": self._upsert_activity(model.activities, activity),
                "surfaces": surfaces,
            }
        )

    def _terminal_or_waiting_activity(
        self,
        model: HomePresentationModel,
        activity_id: str,
        state: ActivityState,
        summary: str,
        occurred_at,
        lifecycle: SurfaceLifecycle,
        presence_activity: PresenceActivity,
        expression: ExpressionCode,
        *,
        reason_code: str | None = None,
    ) -> HomePresentationModel:
        current = self._activity(model, activity_id)
        if current is None:
            return model
        activity = current.model_copy(
            update={
                "state": state,
                "summary": summary,
                "updated_at": occurred_at,
                "reason_code": reason_code,
            }
        )
        updated = self._replace_activity_and_surface(model, activity, lifecycle)
        return updated.model_copy(
            update={
                "presence": updated.presence.model_copy(
                    update={
                        "pose": BasePose.WAITING
                        if state is ActivityState.WAITING
                        else BasePose.IDLE,
                        "expression": self._expression(expression, 0.38),
                        "attention": AttentionState.TOWARD_SURFACE,
                        "activity": presence_activity,
                    }
                )
            }
        )

    @staticmethod
    def _proactive_surface_id(event_id: str) -> str:
        normalized = "".join(
            character if character.isalnum() or character in "_.:-" else "_"
            for character in event_id
        )
        return f"proactive:{normalized}"[:128]


@dataclass
class PresentationRuntime:
    """Small state holder around the pure reducer; no callbacks or domain access."""

    model: HomePresentationModel
    reducer: PresentationReducer = field(default_factory=PresentationReducer)

    def dispatch(self, event: PresentationEvent) -> HomePresentationModel:
        self.model = self.reducer.reduce(self.model, event)
        return self.model
