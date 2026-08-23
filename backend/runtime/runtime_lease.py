"""Exclusive local lease proving that the desktop Home process is alive."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from .process_liveness import ProcessLiveness, default_process_probe, liveness_from_pid_file


class RuntimeLeaseError(RuntimeError):
    pass


_PROCESS_GUARD_LOCK = threading.Lock()
_PROCESS_HELD_GUARDS: set[Path] = set()


class PidLease:
    """OS-owned writer lease with a separate diagnostic PID file.

    The ``.guard`` sidecar is never deleted.  Its advisory lock is the only
    ownership authority and is released by the OS if the owning process dies.
    The visible PID file is deliberately not used as a mutex.
    """

    def __init__(self, path: Path, *, process_probe: Callable[[int], bool] = default_process_probe):
        self.path = Path(path)
        self.guard_path = self.path.with_name(f"{self.path.name}.guard")
        self._process_probe = process_probe
        self._descriptor: int | None = None
        self._guard_descriptor: int | None = None

    def liveness(self) -> ProcessLiveness:
        return liveness_from_pid_file(self.path, process_probe=self._process_probe)

    def set_process_probe(self, process_probe: Callable[[int], bool]) -> None:
        self._process_probe = process_probe

    def acquire(self) -> None:
        if self._descriptor is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        guard_key = self.guard_path.resolve()
        with _PROCESS_GUARD_LOCK:
            if guard_key in _PROCESS_HELD_GUARDS:
                raise RuntimeLeaseError("home_runtime_active")
            _PROCESS_HELD_GUARDS.add(guard_key)
        try:
            self._guard_descriptor = self._acquire_os_guard()
            if self.path.exists() and self.liveness().state != "stopped":
                raise RuntimeLeaseError("home_runtime_active")
            self._descriptor = os.open(self.path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
            os.write(self._descriptor, str(os.getpid()).encode("ascii"))
            os.fsync(self._descriptor)
        except Exception:
            if self._guard_descriptor is None:
                with _PROCESS_GUARD_LOCK:
                    _PROCESS_HELD_GUARDS.discard(guard_key)
            else:
                self.release()
            raise

    def _acquire_os_guard(self) -> int:
        descriptor = os.open(self.guard_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return descriptor
        except OSError as error:
            os.close(descriptor)
            raise RuntimeLeaseError("home_runtime_active") from error

    def release(self) -> None:
        if self._guard_descriptor is None:
            return
        metadata_descriptor = self._descriptor
        try:
            if metadata_descriptor is not None:
                os.close(metadata_descriptor)
        finally:
            self._descriptor = None
            if metadata_descriptor is not None:
                self.path.unlink(missing_ok=True)
            self._release_os_guard(self._guard_descriptor)
            self._guard_descriptor = None
            with _PROCESS_GUARD_LOCK:
                _PROCESS_HELD_GUARDS.discard(self.guard_path.resolve())

    @staticmethod
    def _release_os_guard(descriptor: int) -> None:
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @property
    def descriptor(self) -> int:
        if self._descriptor is None:
            raise RuntimeLeaseError("lease_not_acquired")
        return self._descriptor


class RuntimeLease(PidLease):
    def __init__(self, project_root: Path, *, process_probe: Callable[[int], bool] = default_process_probe):
        super().__init__(
            Path(project_root) / "local-data" / "runtime" / "home-runtime.lock",
            process_probe=process_probe,
        )
