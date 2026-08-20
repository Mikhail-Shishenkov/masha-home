"""Manual only: MASHA_RUN_W4_PDF_SMOKE=1 pytest -s tests/test_document_read_live_smoke.py"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from backend.document_read import DocumentReadStore
from backend.external_observation import (
    ExternalObservationService,
    ExternalObservationStore,
    FakeExternalQueryPlanner,
    FakeWebSearchProvider,
    InternetAccessPolicyStore,
    SafePublicHttpsFetcher,
)
from backend.runtime.safety import AutonomySafetyService, AutonomySafetyStore
from backend.skills.registry import SkillRegistry


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
PDF_URL = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"


@pytest.mark.skipif(
    os.environ.get("MASHA_RUN_W4_PDF_SMOKE") != "1",
    reason="manual live W4 PDF smoke only",
)
def test_manual_public_text_pdf_read(tmp_path):
    now = lambda: datetime.now(timezone.utc)
    config = tmp_path / "local-data" / "config"
    document_store = DocumentReadStore(tmp_path / "local-data" / "runtime" / "document-read-receipts.json")
    service = ExternalObservationService(
        provider=FakeWebSearchProvider(()),
        policy_store=InternetAccessPolicyStore(config / "internet-access.json"),
        safety_store=AutonomySafetyService(
            store=AutonomySafetyStore(config / "autonomy-safety.json"), clock=now,
        ).store,
        registry=SkillRegistry(
            skills_root=tmp_path / "local-data" / "skills",
            bundled_skills_root=ROOT / "skills",
            state_path=config / "skills.json",
            clock=now,
        ),
        planner=FakeExternalQueryPlanner(None),
        store=ExternalObservationStore(tmp_path / "local-data" / "runtime" / "external-observations.json"),
        document_store=document_store,
        fetcher=SafePublicHttpsFetcher(timeout_seconds=8),
        clock=now,
    )

    observations = service.observe_fetch_request(
        f"прочитай {PDF_URL}", origin_message_id="manual-w4", conversation_message_ids=("manual-w4",),
    )

    assert observations is not None and observations[-1].status.value == "completed"
    observation = observations[-1]
    receipt = service.document_receipt(observation)
    assert receipt is not None and receipt.evidence.page_count > 0
    assert receipt.evidence.pages and receipt.evidence.extracted_chars > 0
    journal = document_store.path.read_text(encoding="utf-8")
    assert "%PDF-" not in journal
