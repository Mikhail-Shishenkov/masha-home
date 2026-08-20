"""Pinned-IP, explicit-boundary HTTPS GET transport for W2.

This module deliberately does not use urllib/requests/httpx so it cannot
silently honor proxy environment variables or follow redirects on its own.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import threading
import zlib
from dataclasses import dataclass
from queue import Empty, Queue
from time import monotonic
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit


class SafeFetchError(RuntimeError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class SafeFetchResponse:
    """Only the bounded decoded HTTP representation leaves the transport."""

    requested_url: str
    final_url: str
    headers: dict[str, str]
    body: bytes
    redirects: int
    raw_bytes_read: int | None = None


Resolver = Callable[[str, int], tuple[str, ...]]
MonotonicClock = Callable[[], float]


def _system_resolver(host: str, port: int) -> tuple[str, ...]:
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise SafeFetchError("dns_resolution_failed") from error
    addresses = tuple(dict.fromkeys(row[4][0] for row in rows))
    if not addresses:
        raise SafeFetchError("dns_resolution_failed")
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a validated numeric IP while authenticating the DNS hostname."""

    def __init__(self, *, host: str, ip: str, timeout: float):
        super().__init__(host=host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


class SafePublicHttpsFetcher:
    """One deadline-bounded GET with per-hop SSRF validation and no proxy support."""

    _READ_CHUNK_BYTES = 64 * 1024

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        max_bytes: int = 2 * 1024 * 1024,
        max_pdf_bytes: int = 10 * 1024 * 1024,
        max_redirects: int = 3,
        resolver: Resolver = _system_resolver,
        connection_factory: Callable[..., _PinnedHTTPSConnection] = _PinnedHTTPSConnection,
        monotonic_clock: MonotonicClock = monotonic,
    ):
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 8.0))
        self.max_bytes = max(1, min(int(max_bytes), 2 * 1024 * 1024))
        self.max_pdf_bytes = max(self.max_bytes, min(int(max_pdf_bytes), 10 * 1024 * 1024))
        self.max_redirects = max(0, min(int(max_redirects), 3))
        self._resolver = resolver
        self._connection_factory = connection_factory
        self._monotonic = monotonic_clock

    def fetch(self, requested_url: str) -> SafeFetchResponse:
        deadline = self._monotonic() + self.timeout_seconds
        current_url = self._validate_url(requested_url)
        for redirects in range(self.max_redirects + 1):
            self._remaining_timeout(deadline)
            host = urlsplit(current_url).hostname
            assert host is not None
            addresses = self._validated_addresses(host, deadline)
            connection = None
            response = None
            try:
                connection = self._connection_factory(
                    host=host,
                    ip=addresses[0],
                    timeout=self._remaining_timeout(deadline),
                )
                target = self._request_target(current_url)
                connection.request("GET", target, headers={
                    "Accept": "text/html, text/plain, application/json, application/*+json;q=0.9, application/pdf;q=0.9",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "User-Agent": "MashaHome/0.1 safe-web-fetch",
                })
                self._set_remaining_timeout(connection, deadline)
                response = connection.getresponse()
                headers = self._normalized_headers(response)
                status = response.status
                if 300 <= status < 400:
                    location = headers.get("location")
                    if not location:
                        raise SafeFetchError("redirect_missing_location")
                    if redirects >= self.max_redirects:
                        raise SafeFetchError("too_many_redirects")
                    current_url = self._validate_url(urljoin(current_url, location))
                    continue
                if status < 200 or status >= 300:
                    raise SafeFetchError("http_status_failed", f"HTTP {status}")
                body_limit = self.max_pdf_bytes if self._is_pdf(headers) else self.max_bytes
                content_length = headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > body_limit:
                            raise SafeFetchError("response_too_large")
                    except ValueError:
                        pass
                content_encoding = self._content_encoding(headers)
                body, raw_bytes_read = self._read_and_decode_body(
                    response,
                    connection,
                    deadline,
                    content_encoding,
                    body_limit,
                )
            except SafeFetchError:
                raise
            except socket.timeout as error:
                raise SafeFetchError("fetch_timeout") from error
            except (ssl.SSLError, OSError, http.client.HTTPException) as error:
                raise SafeFetchError("fetch_transport_failed") from error
            finally:
                self._close_quietly(response)
                self._close_quietly(connection)
            return SafeFetchResponse(
                requested_url=requested_url,
                final_url=current_url,
                headers=headers,
                body=body,
                redirects=redirects,
                raw_bytes_read=raw_bytes_read,
            )
        raise SafeFetchError("too_many_redirects")

    def _read_and_decode_body(
        self,
        response,
        connection,
        deadline: float,
        encoding: str,
        max_bytes: int,
    ) -> tuple[bytes, int]:
        body = bytearray()
        raw_bytes_read = 0
        decompressor = self._decompressor(encoding)
        while True:
            self._set_remaining_timeout(connection, deadline)
            remaining_bytes = max_bytes + 1 - raw_bytes_read
            chunk = response.read(min(self._READ_CHUNK_BYTES, remaining_bytes))
            # A socket read may have returned only after its per-operation
            # timeout. Check the single wall-clock deadline before accepting it.
            self._remaining_timeout(deadline)
            if not chunk:
                break
            raw_bytes_read += len(chunk)
            if raw_bytes_read > max_bytes:
                raise SafeFetchError("response_too_large")
            self._append_decoded(body, chunk, decompressor, deadline, max_bytes)
        if decompressor is not None:
            try:
                self._append_decoded(
                    body,
                    decompressor.flush(max_bytes + 1 - len(body)),
                    None,
                    deadline,
                    max_bytes,
                )
            except zlib.error as error:
                raise SafeFetchError("content_decoding_failed") from error
            if not decompressor.eof or decompressor.unused_data:
                raise SafeFetchError("content_decoding_failed")
        return bytes(body), raw_bytes_read

    def _append_decoded(self, body: bytearray, chunk: bytes, decompressor, deadline: float, max_bytes: int) -> None:
        self._remaining_timeout(deadline)
        try:
            decoded = chunk if decompressor is None else decompressor.decompress(
                chunk,
                max_bytes + 1 - len(body),
            )
        except zlib.error as error:
            raise SafeFetchError("content_decoding_failed") from error
        self._remaining_timeout(deadline)
        body.extend(decoded)
        if len(body) > max_bytes:
            raise SafeFetchError("decoded_response_too_large")

    @staticmethod
    def _is_pdf(headers: dict[str, str]) -> bool:
        return headers.get("content-type", "").split(";", 1)[0].strip().casefold() == "application/pdf"

    @staticmethod
    def _decompressor(encoding: str):
        if encoding == "gzip":
            return zlib.decompressobj(16 + zlib.MAX_WBITS)
        if encoding == "deflate":
            return zlib.decompressobj()
        return None

    @staticmethod
    def _normalized_headers(response) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in response.getheaders():
            normalized_key = str(key).casefold()
            normalized_value = str(value)
            headers[normalized_key] = (
                normalized_value
                if normalized_key not in headers
                else f"{headers[normalized_key]}, {normalized_value}"
            )
        return headers

    @staticmethod
    def _content_encoding(headers: dict[str, str]) -> str:
        encoding = headers.get("content-encoding", "").strip().casefold()
        if encoding in {"", "identity", "gzip", "deflate"}:
            return encoding
        raise SafeFetchError("unsupported_content_encoding")

    def _remaining_timeout(self, deadline: float) -> float:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise SafeFetchError("fetch_timeout")
        return remaining

    def _set_remaining_timeout(self, connection, deadline: float) -> None:
        remaining = self._remaining_timeout(deadline)
        connection.timeout = remaining
        sock = getattr(connection, "sock", None)
        if sock is not None:
            sock.settimeout(remaining)

    @staticmethod
    def _close_quietly(resource) -> None:
        if resource is None:
            return
        try:
            resource.close()
        except Exception:
            pass

    def _validated_addresses(self, host: str, deadline: float) -> tuple[str, ...]:
        # getaddrinfo has no portable timeout parameter. Run the resolver only
        # after an explicit fetch request and stop waiting at the same deadline.
        result: Queue[tuple[str, object]] = Queue(maxsize=1)

        def resolve() -> None:
            try:
                result.put(("addresses", self._resolver(host, 443)))
            except Exception as error:
                result.put(("error", error))

        threading.Thread(target=resolve, daemon=True).start()
        try:
            kind, value = result.get(timeout=self._remaining_timeout(deadline))
        except Empty as error:
            raise SafeFetchError("fetch_timeout") from error
        if kind == "error":
            if isinstance(value, SafeFetchError):
                raise value
            raise SafeFetchError("dns_resolution_failed") from value
        addresses = value
        assert isinstance(addresses, tuple)
        if not addresses:
            raise SafeFetchError("dns_resolution_failed")
        for raw in addresses:
            try:
                address = ipaddress.ip_address(raw)
            except ValueError as error:
                raise SafeFetchError("dns_resolution_failed") from error
            if not address.is_global:
                raise SafeFetchError("non_public_destination")
        return addresses

    @staticmethod
    def _validate_url(value: str) -> str:
        try:
            parsed = urlsplit(value.strip())
        except ValueError as error:
            raise SafeFetchError("invalid_url") from error
        if parsed.scheme.casefold() != "https":
            raise SafeFetchError("unsupported_scheme")
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise SafeFetchError("invalid_url")
        try:
            port = parsed.port
        except ValueError as error:
            raise SafeFetchError("invalid_url") from error
        if port not in {None, 443}:
            raise SafeFetchError("non_default_port")
        host = parsed.hostname.casefold().rstrip(".")
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise SafeFetchError("local_destination")
        return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))

    @staticmethod
    def _request_target(url: str) -> str:
        parsed = urlsplit(url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
