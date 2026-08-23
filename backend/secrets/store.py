"""Secret storage adapters. Production values live only in Windows Credential Manager."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Protocol

from .models import SecretRef


class SecretStoreError(RuntimeError):
    """Controlled storage failure; messages never contain a credential value."""


class SecretStore(Protocol):
    def put(self, ref: SecretRef, value: str) -> None: ...
    def get(self, ref: SecretRef) -> str | None: ...
    def exists(self, ref: SecretRef) -> bool: ...
    def delete(self, ref: SecretRef) -> None: ...


class InMemorySecretStore:
    """Test-only adapter. It must never be selected by production composition."""

    def __init__(self):
        self._values: dict[str, str] = {}

    def put(self, ref: SecretRef, value: str) -> None:
        _validate_value(value)
        self._values[ref.value] = value

    def get(self, ref: SecretRef) -> str | None:
        return self._values.get(ref.value)

    def exists(self, ref: SecretRef) -> bool:
        return ref.value in self._values

    def delete(self, ref: SecretRef) -> None:
        self._values.pop(ref.value, None)


class WindowsCredentialManagerSecretStore:
    """Windows-only generic credentials, scoped to the current local machine."""

    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2
    _ERROR_NOT_FOUND = 1168
    _MAX_BLOB_BYTES = 2560
    _TARGET_PREFIX = "MashaHome/secret/"

    def __init__(self):
        if os.name != "nt":
            raise SecretStoreError("windows_credential_manager_unavailable")
        self._advapi32 = ctypes.WinDLL("Advapi32", use_last_error=True)
        self._credential_type = _credential_type()
        self._configure_functions()

    def put(self, ref: SecretRef, value: str) -> None:
        encoded = _validate_value(value, maximum_bytes=self._MAX_BLOB_BYTES)
        blob = (ctypes.c_byte * len(encoded)).from_buffer_copy(encoded)
        credential = self._credential_type()
        credential.Type = self._CRED_TYPE_GENERIC
        credential.TargetName = self._target(ref)
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte))
        credential.Persist = self._CRED_PERSIST_LOCAL_MACHINE
        if not self._advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise SecretStoreError("credential_write_failed")

    def get(self, ref: SecretRef) -> str | None:
        pointer = ctypes.POINTER(self._credential_type)()
        if not self._advapi32.CredReadW(self._target(ref), self._CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == self._ERROR_NOT_FOUND:
                return None
            raise SecretStoreError("credential_read_failed")
        try:
            credential = pointer.contents
            raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise SecretStoreError("credential_value_invalid") from error
        finally:
            self._advapi32.CredFree(pointer)

    def exists(self, ref: SecretRef) -> bool:
        return self.get(ref) is not None

    def delete(self, ref: SecretRef) -> None:
        if self._advapi32.CredDeleteW(self._target(ref), self._CRED_TYPE_GENERIC, 0):
            return
        if ctypes.get_last_error() != self._ERROR_NOT_FOUND:
            raise SecretStoreError("credential_delete_failed")

    def _target(self, ref: SecretRef) -> str:
        return f"{self._TARGET_PREFIX}{ref.value}"

    def _configure_functions(self) -> None:
        self._advapi32.CredWriteW.argtypes = (ctypes.POINTER(self._credential_type), wintypes.DWORD)
        self._advapi32.CredWriteW.restype = wintypes.BOOL
        self._advapi32.CredReadW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(self._credential_type)),
        )
        self._advapi32.CredReadW.restype = wintypes.BOOL
        self._advapi32.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
        self._advapi32.CredDeleteW.restype = wintypes.BOOL
        self._advapi32.CredFree.argtypes = (ctypes.c_void_p,)
        self._advapi32.CredFree.restype = None


def _credential_type():
    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", _FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    return _CREDENTIALW


def _validate_value(value: str, *, maximum_bytes: int = 16_384) -> bytes:
    if not isinstance(value, str) or not value:
        raise SecretStoreError("secret_value_invalid")
    encoded = value.encode("utf-8")
    if len(encoded) > maximum_bytes:
        raise SecretStoreError("secret_value_too_large")
    return encoded
