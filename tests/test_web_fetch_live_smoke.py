"""Manual only: MASHA_RUN_W2_FETCH_SMOKE=1 pytest -s tests/test_web_fetch_live_smoke.py"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from backend.external_observation import (
    DDGSWebSearchProvider,
    ExternalObservationService,
    ExternalObservationStore,
    FakeExternalQueryPlanner,
    FakeSourceSelector,
    InternetAccessPolicyStore,
    SafePublicHttpsFetcher,
)
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.skills.registry import SkillRegistry


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    os.environ.get("MASHA_RUN_W2_FETCH_SMOKE") != "1",
    reason="manual live W2 fetch smoke only",
)
def test_manual_direct_fetch_and_search_then_fetch(tmp_path):
    now = lambda: datetime.now(timezone.utc)
    config = tmp_path / "local-data" / "config"
    store = ExternalObservationStore(tmp_path / "local-data" / "runtime" / "external-observations.json")
    safety = AutonomySafetyService(store=AutonomySafetyStore(config / "autonomy-safety.json"), clock=now)
    service = ExternalObservationService(
        provider=DDGSWebSearchProvider(timeout_seconds=8, clock=now),
        policy_store=InternetAccessPolicyStore(config / "internet-access.json"),
        safety_store=safety.store,
        registry=SkillRegistry(skills_root=tmp_path / "local-data" / "skills", bundled_skills_root=ROOT / "skills", state_path=config / "skills.json", clock=now),
        planner=FakeExternalQueryPlanner("python programming"),
        source_selector=FakeSourceSelector("S1"),
        fetcher=SafePublicHttpsFetcher(timeout_seconds=8),
        store=store,
        clock=now,
    )
    direct = service.observe_fetch_request(
        "прочитай https://www.python.org/",
        origin_message_id="manual-direct",
        conversation_message_ids=("manual-direct",),
    )
    assert direct is not None and direct[-1].status.value == "completed"
    assert direct[-1].fetched_page is not None and direct[-1].fetched_page.extracted_text

    chained = service.observe_fetch_request(
        "найди python programming и прочитай страницу",
        origin_message_id="manual-chain",
        conversation_message_ids=("manual-direct", "manual-chain"),
    )
    assert chained is not None and [item.request.kind.value for item in chained] == ["web_search", "web_fetch"]
    assert chained[-1].status.value == "completed" and chained[-1].fetched_page is not None, chained[-1].error_reason
    assert len(chained[-1].fetched_page.extracted_text) <= 8_000
    assert store.source_url(chained[-1].request.observation_id, "page").startswith("https://")
    journal = store.path.read_text(encoding="utf-8")
    assert "<html" not in journal.casefold()
