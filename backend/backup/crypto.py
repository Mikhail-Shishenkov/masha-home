"""Versioned authenticated envelope for Whole-Home backup payloads."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .errors import BackupError


_MAGIC = b"MSHBKUP1"
_HEADER_LENGTH_BYTES = 4
_MAX_HEADER_BYTES = 8 * 1024
_SALT_BYTES = 16
_NONCE_BYTES = 12
_TAG_BYTES = 16
_CHUNK_BYTES = 1024 * 1024
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1


def encrypt_file(source: Path, destination: Path, passphrase: str) -> None:
    """Stream an authenticated encrypted envelope without holding payload in memory."""
    if not isinstance(passphrase, str) or not passphrase:
        raise BackupError("passphrase_required")
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    header = {
        "format_version": "1.0",
        "kdf": {
            "name": "scrypt",
            "n": _SCRYPT_N,
            "r": _SCRYPT_R,
            "p": _SCRYPT_P,
            "length": 32,
            "salt": _b64(salt),
        },
        "cipher": {"name": "aes-256-gcm", "nonce": _b64(nonce)},
    }
    header_bytes = _encode_header(header)
    key = _derive_key(passphrase, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header_bytes)
    try:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            outgoing.write(_MAGIC)
            outgoing.write(len(header_bytes).to_bytes(_HEADER_LENGTH_BYTES, "big"))
            outgoing.write(header_bytes)
            for chunk in iter(lambda: incoming.read(_CHUNK_BYTES), b""):
                outgoing.write(encryptor.update(chunk))
            outgoing.write(encryptor.finalize())
            outgoing.write(encryptor.tag)
    except OSError as error:
        raise BackupError("backup_write_failed") from error


def decrypt_file(source: Path, destination: Path, passphrase: str) -> None:
    """Authenticate then stream a bundle into a caller-owned temporary file."""
    if not isinstance(passphrase, str) or not passphrase:
        raise BackupError("passphrase_required")
    try:
        with source.open("rb") as incoming:
            header_bytes, header = _read_header(incoming)
            remaining = source.stat().st_size - incoming.tell()
            if remaining <= _TAG_BYTES:
                raise BackupError("invalid_backup")
            ciphertext_size = remaining - _TAG_BYTES
            key = _derive_key_from_header(passphrase, header)
            decryptor = Cipher(
                algorithms.AES(key), modes.GCM(_header_nonce(header)),
            ).decryptor()
            decryptor.authenticate_additional_data(header_bytes)
            with destination.open("xb") as outgoing:
                unread = ciphertext_size
                while unread:
                    chunk = incoming.read(min(_CHUNK_BYTES, unread))
                    if not chunk:
                        raise BackupError("invalid_backup")
                    unread -= len(chunk)
                    outgoing.write(decryptor.update(chunk))
                tag = incoming.read(_TAG_BYTES)
                if len(tag) != _TAG_BYTES or incoming.read(1):
                    raise BackupError("invalid_backup")
                outgoing.write(decryptor.finalize_with_tag(tag))
    except BackupError:
        _remove_partial(destination)
        raise
    except (InvalidTag, UnicodeDecodeError, ValueError, TypeError, OSError, json.JSONDecodeError) as error:
        _remove_partial(destination)
        raise BackupError("decryption_failed") from error


def read_public_header(source: Path) -> dict[str, object]:
    """Read only the minimal unencrypted format metadata, with strict bounds."""
    try:
        with source.open("rb") as incoming:
            _, header = _read_header(incoming)
            return header
    except BackupError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise BackupError("invalid_backup") from error


def _read_header(incoming: BinaryIO) -> tuple[bytes, dict[str, object]]:
    if incoming.read(len(_MAGIC)) != _MAGIC:
        raise BackupError("invalid_backup")
    encoded_length = incoming.read(_HEADER_LENGTH_BYTES)
    if len(encoded_length) != _HEADER_LENGTH_BYTES:
        raise BackupError("invalid_backup")
    header_length = int.from_bytes(encoded_length, "big")
    if not 2 <= header_length <= _MAX_HEADER_BYTES:
        raise BackupError("invalid_backup")
    header_bytes = incoming.read(header_length)
    if len(header_bytes) != header_length:
        raise BackupError("invalid_backup")
    header = json.loads(header_bytes)
    if not isinstance(header, dict):
        raise BackupError("invalid_backup")
    _validate_header(header)
    return header_bytes, header


def _validate_header(header: dict[str, object]) -> None:
    if header.get("format_version") != "1.0":
        raise BackupError("invalid_backup")
    kdf = header.get("kdf")
    cipher = header.get("cipher")
    if not isinstance(kdf, dict) or not isinstance(cipher, dict):
        raise BackupError("invalid_backup")
    if (
        kdf.get("name") != "scrypt"
        or kdf.get("n") != _SCRYPT_N
        or kdf.get("r") != _SCRYPT_R
        or kdf.get("p") != _SCRYPT_P
        or kdf.get("length") != 32
        or cipher.get("name") != "aes-256-gcm"
    ):
        raise BackupError("invalid_backup")
    if len(_decode_b64(kdf.get("salt"))) != _SALT_BYTES:
        raise BackupError("invalid_backup")
    if len(_decode_b64(cipher.get("nonce"))) != _NONCE_BYTES:
        raise BackupError("invalid_backup")


def _derive_key_from_header(passphrase: str, header: dict[str, object]) -> bytes:
    kdf = header["kdf"]
    assert isinstance(kdf, dict)  # validated by _read_header
    return _derive_key(passphrase, _decode_b64(kdf["salt"]), _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)


def _header_nonce(header: dict[str, object]) -> bytes:
    cipher = header["cipher"]
    assert isinstance(cipher, dict)  # validated by _read_header
    return _decode_b64(cipher["nonce"])


def _derive_key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(passphrase.encode("utf-8"))


def _encode_header(header: dict[str, object]) -> bytes:
    result = json.dumps(header, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    if len(result) > _MAX_HEADER_BYTES:
        raise BackupError("invalid_backup")
    return result


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode_b64(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise BackupError("invalid_backup")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise BackupError("invalid_backup") from error


def _remove_partial(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
