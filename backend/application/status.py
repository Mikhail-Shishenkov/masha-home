"""Read-only aggregate status for a future thin local UI."""

from __future__ import annotations

from collections.abc import Callable

from backend.runtime.health import RuntimeHealthService
from backend.runtime.safety import AutonomySafetyService
from backend.skills.permissions import PermissionsSnapshot
from backend.temporal.proactive import ProactivePolicyStore
from backend.temporal.proactive_daemon import ProactiveDaemon
from backend.temporal.proactive_interaction import ProactiveInteractionStore

from .catalogs import RUNTIME_STATUS_LABELS, proactive_reason_label
from .contracts import MashaStatusView, SafetyView
from .model_settings import ModelSettingsService


class MashaStatusService:
    def __init__(
        self,
        *,
        health: RuntimeHealthService,
        models: ModelSettingsService,
        proactive_policy: ProactivePolicyStore,
        daemon: ProactiveDaemon,
        safety: AutonomySafetyService,
        permissions: Callable[[], PermissionsSnapshot],
        proactive_interactions: ProactiveInteractionStore,
        proactive_journal,
    ):
        self._health = health
        self._models = models
        self._proactive_policy = proactive_policy
        self._daemon = daemon
        self._safety = safety
        self._permissions = permissions
        self._proactive_interactions = proactive_interactions
        self._proactive_journal = proactive_journal

    def snapshot(self) -> MashaStatusView:
        health = self._health.inspect()
        model = self._models.current()
        policy = self._proactive_policy.load()
        safety = self._safety.status()
        permissions = self._permissions()
        pending_interactions = sum(
            item["state"] in {"candidate", "delivered"}
            for item in self._proactive_interactions.list()
        )
        latest_cycle = self._proactive_journal.latest()
        daemon_status = self._daemon.status()
        if safety.emergency_stop_engaged:
            proactive_reason = "emergency_stop_engaged"
        elif not policy.enabled:
            proactive_reason = "proactive_disabled"
        elif policy.runtime_mode == "manual":
            proactive_reason = "manual_runtime"
        else:
            proactive_reason = (
                latest_cycle.reason
                if latest_cycle is not None
                else daemon_status.get("last_reason")
            )
        return MashaStatusView(
            runtime_status=health.status,
            runtime_label=RUNTIME_STATUS_LABELS[health.status],
            model_available=model.available,
            model_availability_code=model.availability_code,
            model_label=model.availability_label,
            active_profile_id=model.profile_id,
            proactive_enabled=policy.enabled,
            proactive_label="Инициативность включена" if policy.enabled else "Инициативность выключена",
            proactive_level=policy.proactive_level,
            runtime_mode=policy.runtime_mode,
            runtime_mode_label="Фоновый режим" if policy.runtime_mode == "background" else "Ручной режим",
            daemon_running=self._daemon.is_running(),
            emergency_stop_engaged=safety.emergency_stop_engaged,
            safety_label="Аварийная остановка включена" if safety.emergency_stop_engaged else "Аварийная остановка выключена",
            pending_decisions_count=len(permissions.pending),
            pending_interactions_count=pending_interactions,
            proactive_reason_code=proactive_reason,
            proactive_reason_label=(
                None if proactive_reason is None else proactive_reason_label(proactive_reason)
            ),
            proactive_last_cycle_at=(
                None if latest_cycle is None else latest_cycle.finished_at
            ),
        )

    def engage_emergency_stop(self, reason: str = "manual_emergency_stop") -> SafetyView:
        return self._safety_view(self._safety.engage(reason))

    def release_emergency_stop(self) -> SafetyView:
        return self._safety_view(self._safety.release())

    @staticmethod
    def _safety_view(state) -> SafetyView:
        return SafetyView(
            emergency_stop_engaged=state.emergency_stop_engaged,
            reason=state.reason,
            changed_at=state.changed_at,
            revision=state.revision,
            label="Аварийная остановка включена" if state.emergency_stop_engaged else "Аварийная остановка выключена",
        )
