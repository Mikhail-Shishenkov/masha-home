"""Pinned-IP, explicit-boundary HTTPS GET transport for W2.

This module deliberately does not use urllib/requests/httpx so it cannot
silently honor proxy environment variables or follow redirects on its own.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit


class SafeFetchError(RuntimeError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class SafeFetchResponse:
    requested_url: str
    final_url: str
    headers: dict[str, str]
    body: bytes
    redirects: int


Resolver = Callable[[str, int], tuple[str, ...]]


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
    """One bounded GET with per-hop SSRF validation and no proxy support."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        max_bytes: int = 2 * 1024 * 1024,
        max_redirects: int = 3,
        resolver: Resolver = _system_resolver,
        connection_factory: Callable[..., _PinnedHTTPSConnection] = _PinnedHTTPSConnection,
    ):
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 8.0))
        self.max_bytes = max(1, min(int(max_bytes), 2 * 1024 * 1024))
        self.max_redirects = max(0, min(int(max_redirects), 3))
        self._resolver = resolver
        self._connection_factory = connection_factory

    def fetch(self, requested_url: str) -> SafeFetchResponse:
        current_url = self._validate_url(requested_url)
        for redirects in range(self.max_redirects + 1):
            host = urlsplit(current_url).hostname
            assert host is not None
            addresses = self._validated_addresses(host)
            try:
                connection = self._connection_factory(
                    host=host,
                    ip=addresses[0],
                    timeout=self.timeout_seconds,
                )
                target = self._request_target(current_url)
                connection.request("GET", target, headers={
                    "Accept": "text/html, text/plain, application/json, application/*+json;q=0.9",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "User-Agent": "MashaHome/0.1 safe-web-fetch",
                })
                response = connection.getresponse()
                headers = {key.casefold(): value for key, value in response.getheaders()}
                status = response.status
                if 300 <= status < 400:
                    location = headers.get("location")
                    response.close()
                    connection.close()
                    if not location:
                        raise SafeFetchError("redirect_missing_location")
                    if redirects >= self.max_redirects:
                        raise SafeFetchError("too_many_redirects")
                    current_url = self._validate_url(urljoin(current_url, location))
                    continue
                if status < 200 or status >= 300:
                    raise SafeFetchError("http_status_failed", f"HTTP {status}")
                content_length = headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > self.max_bytes:
                            raise SafeFetchError("response_too_large")
                    except ValueError:
                        pass
                if headers.get("content-encoding", "identity").casefold() not in {"", "identity"}:
                    raise SafeFetchError("unsupported_content_encoding")
                body = response.read(self.max_bytes + 1)
                response.close()
                connection.close()
            except SafeFetchError:
                raise
            except socket.timeout as error:
                raise SafeFetchError("fetch_timeout") from error
            except (ssl.SSLError, OSError, http.client.HTTPException) as error:
                raise SafeFetchError("fetch_transport_failed") from error
            if len(body) > self.max_bytes:
                raise SafeFetchError("response_too_large")
            return SafeFetchResponse(
                requested_url=requested_url,
                final_url=current_url,
                headers=headers,
                body=body,
                redirects=redirects,
            )
        raise SafeFetchError("too_many_redirects")

    def _validated_addresses(self, host: str) -> tuple[str, ...]:
        addresses = self._resolver(host, 443)
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
