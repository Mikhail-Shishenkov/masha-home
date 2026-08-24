"""Minimal local polling process for the controlled proactive runtime."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from backend.runtime.daily_runtime import DailyCycleReceipt, DailyRuntime, DailyRuntimeJournal
from backend.runtime.process_liveness import ProcessLiveness, default_process_probe
from backend.runtime.runtime_lease import PidLease, RuntimeLeaseError
from backend.runtime.safety import AutonomySafetyStore
from backend.backup.recovery_journal import RecoveryJournal

from .proactive import ProactivePolicyStore
from .proactive_interaction import ProactiveInteractionStore
from .reminder_trace import ReminderDeliveryTrace
from .temporal_runtime import due_aware_cycle_delay


_WAKE_REVISION_UNSET = object()


def request_proactive_wakeup(project_root: Path, *, trace=None) -> None:
    """Notify the existing runtime that deadline state changed; no domain data lives here."""
    runtime_dir = Path(project_root) / "local-data" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    wake_path = runtime_dir / "proactive-daemon.wake"
    wake_path.touch()
    if trace is not None:
        trace.record("wake_signalled")


class ProactiveDaemon:
    def __init__(
        self,
        project_root: Path,
        *,
        sleep=time.sleep,
        process_probe: Callable[[int], bool] | None = None,
    ):
        self.project_root = Path(project_root)
        self.runtime_dir = self.project_root / "local-data" / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.runtime_dir / "proactive-daemon.lock"
        self._lease = PidLease(self.lock_path, process_probe=process_probe or default_process_probe)
        self.stop_path = self.runtime_dir / "proactive-daemon.stop"
        self.status_path = self.runtime_dir / "proactive-daemon-status.json"
        self.wake_path = self.runtime_dir / "proactive-daemon.wake"
        self.journal = DailyRuntimeJournal(self.runtime_dir / "daily-runtime-receipts.json")
        self.trace = ReminderDeliveryTrace(self.runtime_dir / "reminder-delivery-trace.json")
        self.safety_store = AutonomySafetyStore(
            self.project_root / "local-data" / "config" / "autonomy-safety.json"
        )
        self.sleep = sleep
        self._process_probe = process_probe or default_process_probe

    def run(self, *, max_cycles: int | None = None):
        descriptor = None
        try:
            self._lease.set_process_probe(self._process_probe)
            try:
                self._lease.acquire()
            except RuntimeLeaseError as error:
                raise FileExistsError(self.lock_path) from error
            descriptor = self._lease.descriptor
            cycles = 0
            while not self.stop_path.exists() and (max_cycles is None or cycles < max_cycles):
                cycle_wake_revision = self._wake_revision()
                journal = RecoveryJournal(self.project_root)
                if not journal.background_activity_allowed():
                    reason = "recovery_hold_active" if journal.is_hold() else "recovery_active"
                    self._status("stopped", result="suppress", reason=reason, error=None, interval=None)
                    break
                if self.safety_store.is_engaged():
                    self._status("stopped", result="suppress", reason="emergency_stop_engaged", error=None, interval=None)
                    break
                interval = 300
                wait_seconds = float(interval)
                try:
                    from backend.conversation.cli import build_service
                    service = build_service(project_root=self.project_root)
                    policy = ProactivePolicyStore(service.model_profiles.path.parent / "proactive-policy.json").load()
                    interval = policy.cycle_interval_seconds
                    if policy.runtime_mode == "background":
                        repository = service.memory_retriever.memory_store
                        interaction_store = (
                            ProactiveInteractionStore(repository)
                            if hasattr(repository, "_connection") else None
                        )
                        delivered_before = set() if interaction_store is None else {
                            row["event_id"] for row in interaction_store.list() if row["state"] == "delivered"
                        }
                        self.trace.record("daemon_runtime_cycle_started")
                        receipt = DailyRuntime(history=service.history, temporal_engine=service.temporal_engine, repository=service.memory_retriever.memory_store, identity_kernel=service.identity_kernel, router=service.router, model_profiles=service.model_profiles, safety_store=self.safety_store).run_cycle(policy)
                        self.journal.append(receipt)
                        if interaction_store is not None:
                            for row in interaction_store.list():
                                if row["state"] == "delivered" and row["event_id"] not in delivered_before:
                                    self.trace.record(
                                        "interaction_delivered", interaction_id=row["event_id"],
                                        at=datetime.fromisoformat(row["delivered_at"]),
                                    )
                        wait_seconds = due_aware_cycle_delay(
                            service.memory_retriever.memory_store,
                            now=datetime.now(timezone.utc),
                            cadence_seconds=interval,
                        )
                        self._status("running", result=receipt.result, reason=receipt.reason, error=None, interval=wait_seconds)
                    else:
                        self._status("running", result="manual_mode", reason="background_disabled", error=None, interval=interval)
                except Exception as error:
                    now = datetime.now(timezone.utc)
                    self.journal.append(DailyCycleReceipt(cycle_id=f"error_{time.time_ns()}", started_at=now, finished_at=now, model_profile="unavailable", error=str(error)))
                    self._status("running", result="error", reason="cycle_error", error=str(error), interval=interval)
                cycles += 1
                if max_cycles is None or cycles < max_cycles:
                    self._wait(wait_seconds, since_revision=cycle_wake_revision)
        finally:
            if descriptor is not None:
                self._lease.release()
            self.stop_path.unlink(missing_ok=True)
            previous = self.status()
            previous["daemon"] = "stopped"
            previous["next_cycle"] = None
            self.status_path.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def request_stop(self):
        self.stop_path.write_text("stop\n", encoding="utf-8")

    def status(self):
        if not self.status_path.exists():
            return {"daemon": "stopped"}
        return json.loads(self.status_path.read_text(encoding="utf-8"))

    def is_running(self) -> bool:
        """Return a safe boolean; process-probe failures never escape."""
        try:
            return self.liveness().state == "running"
        except Exception:
            return False

    def liveness(self) -> ProcessLiveness:
        # Tests and host adapters may replace the probe after construction;
        # keep the shared lease as the single liveness implementation.
        self._lease.set_process_probe(self._process_probe)
        return self._lease.liveness()

    def _acquire_lock(self):
        self._lease.acquire()
        return self._lease.descriptor

    def _wait(self, seconds, *, since_revision=_WAKE_REVISION_UNSET):
        wake_revision = (
            self._wake_revision()
            if since_revision is _WAKE_REVISION_UNSET
            else since_revision
        )
        remaining = seconds
        while remaining > 0 and not self.stop_path.exists() and not self.safety_store.is_engaged():
            if self._wake_revision() != wake_revision:
                self.trace.record("wake_received")
                return
            step = min(1, remaining)
            self.sleep(step)
            remaining -= step
            if self._wake_revision() != wake_revision:
                self.trace.record("wake_received")
                return

    def _wake_revision(self):
        try:
            return self.wake_path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def _status(self, daemon, *, result, reason, error, interval):
        now = datetime.now(timezone.utc)
        self.status_path.write_text(json.dumps({"daemon": daemon, "last_cycle": now.isoformat(), "last_result": result, "last_reason": reason, "last_error": error, "next_cycle": None if interval is None else (now + timedelta(seconds=interval)).isoformat()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    ProactiveDaemon(args.project_root).run()


if __name__ == "__main__":
    main()
