"""Manual only: MASHA_RUN_DDGS_SMOKE=1 pytest -s tests/test_ddgs_live_smoke.py"""

from __future__ import annotations

import json
import os

import pytest

from backend.external_observation import DDGSWebSearchProvider, FreshnessRequirement, ProviderSearchRequest


@pytest.mark.skipif(
    os.environ.get("MASHA_RUN_DDGS_SMOKE") != "1",
    reason="manual live DDGS smoke only",
)
def test_manual_ddgs_duckduckgo_live_smoke():
    provider = DDGSWebSearchProvider(timeout_seconds=8)
    results = provider.search(ProviderSearchRequest(
        query="Ollama latest release",
        max_results=5,
        region="us-en",
        freshness=FreshnessRequirement.CURRENT,
    ))

    assert 0 < len(results) <= 5
    for item in results:
        assert item.title
        assert item.url.startswith("https://")
        assert item.snippet
        assert item.retrieved_at
        assert item.provider_id == "ddgs"
        assert item.search_backend == "duckduckgo"
    print(json.dumps([item.model_dump(mode="json") for item in results], ensure_ascii=False, indent=2))
