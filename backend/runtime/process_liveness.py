"""Fail-closed PID liveness checks shared by local runtime owners."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from typing import Callable, Literal


@dataclass(frozen=True)
class ProcessLiveness:
    state: Literal["running", "stopped", "unknown"]
    detail: str


def default_process_probe(pid: int) -> bool:
    return _windows_process_is_running(pid) if os.name == "nt" else _posix_process_is_running(pid)


def liveness_from_pid_file(path, *, process_probe: Callable[[int], bool] = default_process_probe) -> ProcessLiveness:
    if not path.exists():
        return ProcessLiveness("stopped", "lock file is absent")
    try:
        pid = int(path.read_text(encoding="ascii"))
    except (ValueError, OSError, UnicodeError):
        # O_EXCL creates the file before its owner has written the PID.  An
        # empty/corrupt file is therefore an in-progress or unreadable owner,
        # not a stale one.  Only a positively dead *valid* PID is reclaimable.
        return ProcessLiveness("unknown", "lock file is malformed or unreadable")
    if pid <= 0:
        return ProcessLiveness("unknown", "lock PID is invalid")
    if pid == os.getpid():
        return ProcessLiveness("running", f"process {pid} is current")
    try:
        running = process_probe(pid)
    except Exception as error:
        return ProcessLiveness("unknown", f"process {pid} probe failed: {type(error).__name__}: {error}")
    return ProcessLiveness("running" if running else "stopped", f"process {pid} is {'running' if running else 'not running'}")


def _posix_process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_process_is_running(pid: int) -> bool:
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    error_access_denied = 5
    error_invalid_parameter = 87
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    get_exit_code = kernel32.GetExitCodeProcess
    get_exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    get_exit_code.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    handle = open_process(process_query_limited_information, False, pid)
    if not handle:
        error_code = ctypes.get_last_error()
        if error_code == error_invalid_parameter:
            return False
        if error_code == error_access_denied:
            raise PermissionError(error_code, "access denied while probing process")
        raise OSError(error_code, "OpenProcess failed")
    try:
        exit_code = wintypes.DWORD()
        if not get_exit_code(handle, ctypes.byref(exit_code)):
            raise OSError(ctypes.get_last_error(), "GetExitCodeProcess failed")
        return exit_code.value == still_active
    finally:
        close_handle(handle)
