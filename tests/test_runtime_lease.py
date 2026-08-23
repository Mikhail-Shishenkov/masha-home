import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import pytest

from backend.runtime.process_liveness import liveness_from_pid_file
from backend.runtime.runtime_lease import RuntimeLease, RuntimeLeaseError


def _contend_for_lease(root_text: str, ready, start, release, results) -> None:
    lease = RuntimeLease(Path(root_text))
    ready.put(True)
    start.wait(10)
    try:
        lease.acquire()
    except RuntimeLeaseError:
        results.put(False)
        return
    try:
        results.put(True)
        release.wait(10)
    finally:
        lease.release()


def _race_two_contenders(tmp_path: Path, *, stale_pid: bool) -> list[bool]:
    root = tmp_path / ("stale" if stale_pid else "free")
    path = root / "local-data/runtime/home-runtime.lock"
    path.parent.mkdir(parents=True)
    if stale_pid:
        path.write_text("999999999", encoding="ascii")
    context = multiprocessing.get_context("spawn")
    ready, start, release, results = (context.Queue(), context.Event(), context.Event(), context.Queue())
    processes = [
        context.Process(target=_contend_for_lease, args=(str(root), ready, start, release, results))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    try:
        assert ready.get(timeout=10) is True
        assert ready.get(timeout=10) is True
        start.set()
        outcome = [results.get(timeout=10), results.get(timeout=10)]
        assert outcome.count(True) == 1
        assert outcome.count(False) == 1
        return outcome
    finally:
        release.set()
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0


def test_empty_and_malformed_locks_are_unknown_and_not_reclaimed(tmp_path: Path):
    lease = RuntimeLease(tmp_path, process_probe=lambda _pid: False)
    lease.path.parent.mkdir(parents=True)
    for content in ("", "not-a-pid", "0"):
        lease.path.write_text(content, encoding="ascii")
        assert lease.liveness().state == "unknown"
        with pytest.raises(RuntimeLeaseError):
            lease.acquire()
        assert lease.path.exists()


def test_only_positively_dead_pid_is_reclaimed(tmp_path: Path):
    lease = RuntimeLease(tmp_path, process_probe=lambda _pid: False)
    lease.path.parent.mkdir(parents=True)
    lease.path.write_text("12345", encoding="ascii")
    lease.acquire()
    try:
        assert lease.liveness().state == "running"
    finally:
        lease.release()


def test_probe_failure_is_unknown_and_not_reclaimed(tmp_path: Path):
    lease = RuntimeLease(tmp_path, process_probe=lambda _pid: (_ for _ in ()).throw(PermissionError("denied")))
    lease.path.parent.mkdir(parents=True)
    lease.path.write_text("12345", encoding="ascii")
    assert lease.liveness().state == "unknown"
    with pytest.raises(RuntimeLeaseError):
        lease.acquire()


def test_two_processes_race_for_free_lease_and_only_one_wins(tmp_path: Path):
    _race_two_contenders(tmp_path, stale_pid=False)


def test_two_processes_race_to_reclaim_stale_pid_and_only_one_wins(tmp_path: Path):
    _race_two_contenders(tmp_path, stale_pid=True)


def test_crashed_owner_releases_os_guard_for_next_process(tmp_path: Path):
    root = tmp_path / "crash"
    code = (
        "from pathlib import Path; from backend.runtime.runtime_lease import RuntimeLease; "
        f"lease=RuntimeLease(Path({str(root)!r})); lease.acquire(); os._exit(0)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", "import os; " + code],
        cwd=Path(__file__).resolve().parents[1], check=False, timeout=20,
    )
    assert completed.returncode == 0
    successor = RuntimeLease(root)
    successor.acquire()
    successor.release()


def test_active_owner_rejects_second_acquire(tmp_path: Path):
    owner = RuntimeLease(tmp_path)
    owner.acquire()
    try:
        with pytest.raises(RuntimeLeaseError):
            RuntimeLease(tmp_path).acquire()
    finally:
        owner.release()
