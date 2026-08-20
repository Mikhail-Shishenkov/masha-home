"""Search provider protocol and zero-cost DDGS adapter."""

from __future__ import annotations

import importlib.util
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import (
    FreshnessRequirement,
    FreshnessStatus,
    ProviderSearchRequest,
    SearchEvidence,
    SourceTime,
    SourceTimeKind,
    SourceTimePrecision,
)


class WebSearchProviderUnavailableError(RuntimeError):
    pass


class WebSearchProviderTimeoutError(TimeoutError):
    pass


class WebSearchProviderFailedError(RuntimeError):
    pass


class WebSearchProvider(Protocol):
    provider_id: str
    search_backend: str

    def is_available(self) -> bool: ...
    def search(self, request: ProviderSearchRequest) -> tuple[SearchEvidence, ...]: ...


_TRACKING_KEYS = frozenset({"fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "ref", "ref_src"})


def canonicalize_https_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.casefold().rstrip(".")
    port = f":{parsed.port}" if parsed.port not in {None, 443} else ""
    query = urlencode(sorted(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_KEYS
    ))
    path = parsed.path or "/"
    return urlunsplit(("https", host + port, path, query, ""))


def _source_time(raw: object, *, retrieved_at: datetime) -> SourceTime:
    if raw is None or raw == "":
        return SourceTime()
    text = str(raw).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return SourceTime(value=parsed, kind=SourceTimeKind.PUBLISHED, precision=SourceTimePrecision.EXACT)
    except ValueError:
        pass
    try:
        parsed_date = date.fromisoformat(text[:10])
        return SourceTime(value=parsed_date, kind=SourceTimeKind.PUBLISHED, precision=SourceTimePrecision.DATE)
    except ValueError:
        pass
    relative = re.search(r"(\d+)\s*(minute|hour|day|week|минут|час|дн|недел)", text.casefold())
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        if unit.startswith(("minute", "минут")):
            delta = timedelta(minutes=amount)
        elif unit.startswith(("hour", "час")):
            delta = timedelta(hours=amount)
        elif unit.startswith(("week", "недел")):
            delta = timedelta(weeks=amount)
        else:
            delta = timedelta(days=amount)
        return SourceTime(
            value=retrieved_at - delta,
            kind=SourceTimeKind.PROVIDER_ESTIMATE,
            precision=SourceTimePrecision.RELATIVE,
        )
    return SourceTime()


def freshness_status(
    source_time: SourceTime,
    requirement: FreshnessRequirement,
    *,
    now: datetime,
) -> FreshnessStatus:
    if requirement is FreshnessRequirement.TIMELESS:
        return FreshnessStatus.FRESH
    if source_time.value is None:
        return FreshnessStatus.UNKNOWN
    value = source_time.value
    observed = (
        datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
        if isinstance(value, date) and not isinstance(value, datetime)
        else value
    )
    assert isinstance(observed, datetime)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    age = now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)
    limit = {
        FreshnessRequirement.BREAKING: timedelta(days=2),
        FreshnessRequirement.CURRENT: timedelta(days=45),
        FreshnessRequirement.RECENT: timedelta(days=365),
    }[requirement]
    return FreshnessStatus.FRESH if age <= limit else FreshnessStatus.AGED


class FakeWebSearchProvider:
    provider_id = "fake-web"
    search_backend = "fake"

    def __init__(
        self,
        results: tuple[SearchEvidence, ...] = (),
        *,
        available: bool = True,
        error: Exception | None = None,
    ):
        self.results = results
        self.available = available
        self.error = error
        self.requests: list[ProviderSearchRequest] = []

    def is_available(self) -> bool:
        return self.available

    def search(self, request: ProviderSearchRequest) -> tuple[SearchEvidence, ...]:
        self.requests.append(request)
        if not self.available:
            raise WebSearchProviderUnavailableError("fake provider unavailable")
        if self.error is not None:
            raise self.error
        return self.results[: request.max_results]


class DDGSWebSearchProvider:
    """Lazy community DDGS adapter pinned to the explicit DuckDuckGo backend."""

    provider_id = "ddgs"
    search_backend = "duckduckgo"

    def __init__(
        self,
        *,
        timeout_seconds: float = 5.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 20.0))
        self._clock = clock

    def is_available(self) -> bool:
        return importlib.util.find_spec("ddgs") is not None

    def search(self, request: ProviderSearchRequest) -> tuple[SearchEvidence, ...]:
        if not self.is_available():
            raise WebSearchProviderUnavailableError("ddgs package is unavailable")
        try:
            from ddgs import DDGS
            from ddgs.exceptions import TimeoutException
        except ImportError as error:
            raise WebSearchProviderUnavailableError("ddgs package is unavailable") from error
        started_at = self._aware_now()
        kwargs = {
            "region": request.region,
            "safesearch": "moderate",
            "max_results": min(request.max_results, 5),
            "backend": self.search_backend,
        }
        if request.freshness is FreshnessRequirement.BREAKING:
            kwargs["timelimit"] = "d"
        try:
            client = DDGS(timeout=int(min(self.timeout_seconds, request.timeout_seconds)))
            raw_results = (
                client.news(request.query, **kwargs)
                if request.freshness is FreshnessRequirement.BREAKING
                else client.text(request.query, **kwargs)
            )
        except TimeoutException as error:
            raise WebSearchProviderTimeoutError("ddgs search timed out") from error
        except Exception as error:
            message = str(error).casefold()
            if "timed out" in message or "timeout" in message:
                raise WebSearchProviderTimeoutError("ddgs search timed out") from error
            raise WebSearchProviderFailedError("ddgs search failed") from error
        retrieved_at = self._aware_now()
        normalized: list[SearchEvidence] = []
        for rank, raw in enumerate(raw_results or (), 1):
            url = str(raw.get("href") or raw.get("url") or "").strip()
            canonical = canonicalize_https_url(url)
            title = " ".join(str(raw.get("title") or "").split())[:300]
            snippet = " ".join(str(raw.get("body") or raw.get("snippet") or "").split())[:800]
            if canonical is None or not title or not snippet:
                continue
            source_time = _source_time(raw.get("date") or raw.get("published"), retrieved_at=retrieved_at)
            normalized.append(SearchEvidence(
                source_id=f"S{len(normalized) + 1}",
                provider_id=self.provider_id,
                search_backend=self.search_backend,
                title=title,
                url=url,
                canonical_url=canonical,
                domain=urlsplit(canonical).hostname or "unknown",
                snippet=snippet,
                source_time=source_time,
                retrieved_at=retrieved_at,
                observation_started_at=started_at,
                provider_rank=rank,
                freshness_status=freshness_status(source_time, request.freshness, now=retrieved_at),
            ))
            if len(normalized) >= request.max_results:
                break
        return tuple(normalized)

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("DDGS provider clock must return aware datetime")
        return value.astimezone(timezone.utc)
