"""Human projection and explicit lifecycle actions for delivered initiative."""

from datetime import datetime, timedelta

from backend.temporal.proactive_interaction import ProactiveInteractionStore
from backend.temporal.temporal_runtime import due_aware_cycle_delay

from .contracts import ProactiveInteractionListView, ProactiveInteractionView


class ProactiveApplicationService:
    """Expose only already-delivered local messages and their existing actions."""

    def __init__(self, *, store: ProactiveInteractionStore, clock, runtime=None, policy_store=None, journal=None, daemon=None, hold_checker=None, wake_path=None, trace=None):
        self._store = store
        self._clock = clock
        self._runtime = runtime
        self._policy_store = policy_store
        self._journal = journal
        self._daemon = daemon
        self._hold_checker = hold_checker or (lambda: False)
        self._next_runtime_cycle_at = None
        self._runtime_interval_seconds = None
        self._wake_path = wake_path
        self._trace = trace
        self._wake_revision = self._current_wake_revision()

    def refresh(self, *, limit: int = 6) -> ProactiveInteractionListView:
        """Project deliveries; run the existing runtime only at policy cadence."""
        if self._hold_checker():
            self._record("runtime_suppressed", decision="suppress", reason="recovery_hold")
            return self.list(limit=limit)
        if self._runtime is not None and self._policy_store is not None:
            wake_revision = self._current_wake_revision()
            if wake_revision != self._wake_revision:
                self._wake_revision = wake_revision
                self._next_runtime_cycle_at = None
            policy = self._policy_store.load()
            if policy.runtime_mode == "background" and (
                self._daemon is None or not self._daemon.is_operational_or_starting()
            ):
                now = self._clock.now_utc()
                if self._runtime_interval_seconds != policy.cycle_interval_seconds:
                    self._runtime_interval_seconds = policy.cycle_interval_seconds
                    self._next_runtime_cycle_at = None
                if self._next_runtime_cycle_at is None:
                    latest = None if self._journal is None else self._journal.latest()
                    cadence_at = (
                        now
                        if latest is None
                        else latest.finished_at + timedelta(seconds=policy.cycle_interval_seconds)
                    )
                    delay = due_aware_cycle_delay(
                        self._runtime.repository,
                        now=now,
                        cadence_seconds=max(0.0, (cadence_at - now).total_seconds()),
                    )
                    self._next_runtime_cycle_at = now + timedelta(seconds=delay)
                if now >= self._next_runtime_cycle_at:
                    # Reserve the cadence before model work so a fast UI
                    # heartbeat cannot enqueue overlapping heavy cycles.
                    self._next_runtime_cycle_at = now + timedelta(
                        seconds=policy.cycle_interval_seconds
                    )
                    delivered_before = {
                        row["event_id"] for row in self._store.list() if row["state"] == "delivered"
                    }
                    self._record("runtime_cycle_started")
                    receipt = self._runtime.run_cycle(policy)
                    if self._journal is not None:
                        self._journal.append(receipt)
                    next_delay = due_aware_cycle_delay(
                        self._runtime.repository,
                        now=self._clock.now_utc(),
                        cadence_seconds=policy.cycle_interval_seconds,
                    )
                    self._next_runtime_cycle_at = self._clock.now_utc() + timedelta(seconds=next_delay)
                    for row in self._store.list():
                        if row["state"] == "delivered" and row["event_id"] not in delivered_before:
                            self._record(
                                "interaction_delivered",
                                interaction_id=row["event_id"],
                                at=datetime.fromisoformat(row["delivered_at"]),
                            )
        return self.list(limit=limit)

    def record_renderer_delivery(self, interaction_id: str, rendered_at: datetime) -> None:
        self._record("renderer_banner_presented", interaction_id=interaction_id, at=rendered_at)

    def record_renderer_handoff(self, interaction_id: str, emitted_at: datetime) -> None:
        self._record("renderer_delivery_emitted", interaction_id=interaction_id, at=emitted_at)

    def _record(
        self,
        stage: str,
        *,
        interaction_id: str | None = None,
        at: datetime | None = None,
        decision: str | None = None,
        reason: str | None = None,
    ) -> None:
        if self._trace is not None:
            self._trace.record(
                stage, interaction_id=interaction_id, at=at,
                decision=decision, reason=reason,
            )

    def _current_wake_revision(self):
        if self._wake_path is None:
            return None
        try:
            return self._wake_path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def list(self, *, limit: int = 6) -> ProactiveInteractionListView:
        rows = [row for row in self._store.list() if row["state"] == "delivered"]
        return ProactiveInteractionListView(
            items=tuple(self._view(row) for row in rows[:limit])
        )

    def resolve(self, interaction_id: str, decision: str) -> ProactiveInteractionView:
        row = self._store.get(interaction_id)
        if row is None or row["state"] != "delivered":
            raise ValueError("proactive interaction is stale or unavailable")
        now = self._clock.now_utc()
        if decision == "acknowledge":
            updated = self._store.acknowledge(interaction_id, now)
        elif decision == "dismiss":
            updated = self._store.dismiss(interaction_id, now)
        else:
            raise ValueError("unsupported proactive interaction decision")
        return self._view(updated)

    @staticmethod
    def _view(row) -> ProactiveInteractionView:
        check_in = row.get("proactive_event_id") is not None or row["decision"] == "check_in"
        return ProactiveInteractionView(
            interaction_id=row["event_id"],
            interaction_type="check_in" if check_in else "reminder",
            state=row["state"],
            title="Просто заглянула" if check_in else "Напоминание",
            message=row["message_text"],
            created_at=datetime.fromisoformat(row["created_at"]),
            delivered_at=datetime.fromisoformat(row["delivered_at"]),
            due_at=None if row.get("due_at") is None else datetime.fromisoformat(row["due_at"]),
            allowed_actions=("acknowledge", "dismiss") if row["state"] == "delivered" else (),
        )
