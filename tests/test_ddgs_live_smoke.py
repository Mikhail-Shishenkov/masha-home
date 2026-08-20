"""Manual only: MASHA_RUN_DDGS_SMOKE=1 pytest -s tests/test_ddgs_live_smoke.py"""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

import pytest

from backend.external_observation import (
    DDGSWebSearchProvider,
    FreshnessRequirement,
    ProviderSearchRequest,
    WebSearchProviderFailedError,
    WebSearchProviderTimeoutError,
    WebSearchProviderUnavailableError,
)


@pytest.mark.skipif(
    os.environ.get("MASHA_RUN_DDGS_SMOKE") != "1",
    reason="manual live DDGS smoke only",
)
def test_manual_ddgs_auto_live_smoke():
    provider = DDGSWebSearchProvider(timeout_seconds=8)
    queries = (
        ("python programming", "us-en", FreshnessRequirement.TIMELESS),
        ("Ollama latest release", "us-en", FreshnessRequirement.CURRENT),
        ("последняя версия Python", "ru-ru", FreshnessRequirement.CURRENT),
    )
    successful = []
    failures = []
    for query, region, freshness in queries:
        try:
            results = provider.search(ProviderSearchRequest(
                query=query,
                max_results=5,
                region=region,
                freshness=freshness,
                timeout_seconds=8,
            ))
        except (
            WebSearchProviderFailedError,
            WebSearchProviderTimeoutError,
            WebSearchProviderUnavailableError,
        ) as error:
            failures.append(f"{query}: {type(error).__name__}: {error}")
            continue
        assert 0 < len(results) <= 5
        for item in results:
            parsed = urlsplit(item.url)
            assert parsed.scheme in {"http", "https"} and parsed.netloc
            assert item.title
            assert item.snippet
            assert item.retrieved_at
            assert item.provider_id == "ddgs"
            assert item.search_backend == "auto"
        successful.append({
            "query": query,
            "results": [item.model_dump(mode="json") for item in results],
        })
    assert successful, "All bounded DDGS auto queries failed: " + "; ".join(failures)
    print(json.dumps(successful, ensure_ascii=False, indent=2))
