"""Minimal local polling process for the controlled proactive runtime."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.runtime.daily_runtime import DailyCycleReceipt, DailyRuntime, DailyRuntimeJournal

from .proactive import ProactivePolicyStore


class ProactiveDaemon:
    def __init__(self, project_root: Path, *, sleep=time.sleep):
        self.project_root = Path(project_root)
        self.runtime_dir = self.project_root / "local-data" / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.runtime_dir / "proactive-daemon.lock"
        self.stop_path = self.runtime_dir / "proactive-daemon.stop"
        self.status_path = self.runtime_dir / "proactive-daemon-status.json"
        self.journal = DailyRuntimeJournal(self.runtime_dir / "daily-runtime-receipts.json")
        self.sleep = sleep

    def run(self, *, max_cycles: int | None = None):
        descriptor = None
        try:
            descriptor = self._acquire_lock()
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            cycles = 0
            while not self.stop_path.exists() and (max_cycles is None or cycles < max_cycles):
                interval = 300
                try:
                    from backend.conversation.cli import build_service
                    service = build_service(project_root=self.project_root)
                    policy = ProactivePolicyStore(service.model_profiles.path.parent / "proactive-policy.json").load()
                    interval = policy.cycle_interval_seconds
                    if policy.runtime_mode == "background":
                        receipt = DailyRuntime(history=service.history, temporal_engine=service.temporal_engine, repository=service.memory_retriever.memory_store, identity_kernel=service.identity_kernel, router=service.router, model_profiles=service.model_profiles).run_cycle(policy)
                        self.journal.append(receipt)
                        self._status("running", result=receipt.result, reason=receipt.reason, error=None, interval=interval)
                    else:
                        self._status("running", result="manual_mode", reason="background_disabled", error=None, interval=interval)
                except Exception as error:
                    now = datetime.now(timezone.utc)
                    self.journal.append(DailyCycleReceipt(cycle_id=f"error_{time.time_ns()}", started_at=now, finished_at=now, model_profile="unavailable", error=str(error)))
                    self._status("running", result="error", reason="cycle_error", error=str(error), interval=interval)
                cycles += 1
                if max_cycles is None or cycles < max_cycles:
                    self._wait(interval)
        finally:
            if descriptor is not None:
                os.close(descriptor)
                self.lock_path.unlink(missing_ok=True)
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
        if not self.lock_path.exists():
            return False
        try:
            pid = int(self.lock_path.read_text(encoding="ascii"))
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            return False

    def _acquire_lock(self):
        try:
            return os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if self.is_running():
                raise
            self.lock_path.unlink(missing_ok=True)
            return os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)

    def _wait(self, seconds):
        remaining = seconds
        while remaining > 0 and not self.stop_path.exists():
            step = min(1, remaining)
            self.sleep(step)
            remaining -= step

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
