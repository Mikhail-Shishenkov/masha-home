"""Exclusive local lease proving that the desktop Home process is alive."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .process_liveness import ProcessLiveness, default_process_probe, liveness_from_pid_file


class RuntimeLeaseError(RuntimeError):
    pass


class PidLease:
    """Small fail-closed PID-file lease shared by every local writer."""

    def __init__(self, path: Path, *, process_probe: Callable[[int], bool] = default_process_probe):
        self.path = Path(path)
        self._process_probe = process_probe
        self._descriptor: int | None = None

    def liveness(self) -> ProcessLiveness:
        return liveness_from_pid_file(self.path, process_probe=self._process_probe)

    def set_process_probe(self, process_probe: Callable[[int], bool]) -> None:
        self._process_probe = process_probe

    def acquire(self) -> None:
        if self._descriptor is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if self.liveness().state != "stopped":
                raise RuntimeLeaseError("home_runtime_active")
            self.path.unlink(missing_ok=True)
            self._descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(self._descriptor, str(os.getpid()).encode("ascii"))
        except Exception:
            self.release()
            raise

    def release(self) -> None:
        if self._descriptor is None:
            return
        try:
            os.close(self._descriptor)
        finally:
            self._descriptor = None
            self.path.unlink(missing_ok=True)

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
