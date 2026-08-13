"""Human projection and explicit lifecycle actions for delivered initiative."""

from datetime import datetime, timedelta

from backend.temporal.proactive_interaction import ProactiveInteractionStore

from .contracts import ProactiveInteractionListView, ProactiveInteractionView


class ProactiveApplicationService:
    """Expose only already-delivered local messages and their existing actions."""

    def __init__(self, *, store: ProactiveInteractionStore, clock, runtime=None, policy_store=None, journal=None, daemon=None):
        self._store = store
        self._clock = clock
        self._runtime = runtime
        self._policy_store = policy_store
        self._journal = journal
        self._daemon = daemon
        self._next_runtime_cycle_at = None
        self._runtime_interval_seconds = None

    def refresh(self, *, limit: int = 6) -> ProactiveInteractionListView:
        """Project deliveries; run the existing runtime only at policy cadence."""
        if self._runtime is not None and self._policy_store is not None:
            policy = self._policy_store.load()
            if policy.runtime_mode == "background" and (
                self._daemon is None or not self._daemon.is_running()
            ):
                now = self._clock.now_utc()
                if self._runtime_interval_seconds != policy.cycle_interval_seconds:
                    self._runtime_interval_seconds = policy.cycle_interval_seconds
                    self._next_runtime_cycle_at = None
                if self._next_runtime_cycle_at is None:
                    latest = None if self._journal is None else self._journal.latest()
                    self._next_runtime_cycle_at = (
                        now
                        if latest is None
                        else latest.finished_at + timedelta(seconds=policy.cycle_interval_seconds)
                    )
                if now >= self._next_runtime_cycle_at:
                    # Reserve the cadence before model work so a fast UI
                    # heartbeat cannot enqueue overlapping heavy cycles.
                    self._next_runtime_cycle_at = now + timedelta(
                        seconds=policy.cycle_interval_seconds
                    )
                    receipt = self._runtime.run_cycle(policy)
                    if self._journal is not None:
                        self._journal.append(receipt)
        return self.list(limit=limit)

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
            allowed_actions=("acknowledge", "dismiss") if row["state"] == "delivered" else (),
        )
