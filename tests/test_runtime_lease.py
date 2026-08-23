from pathlib import Path

import pytest

from backend.runtime.process_liveness import liveness_from_pid_file
from backend.runtime.runtime_lease import RuntimeLease, RuntimeLeaseError


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
