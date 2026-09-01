import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.contract
SCENARIOS = Path(__file__).resolve().parents[1] / "release" / "scenarios.json"


def test_release_scenario_catalog_has_exactly_96_unique_owned_journeys():
    payload = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]

    assert payload["target_count"] == 96
    assert len(scenarios) == 96
    assert [item["id"] for item in scenarios] == [
        f"REL-{index:03d}" for index in range(1, 97)
    ]
    assert len({item["id"] for item in scenarios}) == 96
    assert all(item["journey"].strip() for item in scenarios)
    assert all(item["invariant"].strip() for item in scenarios)
    assert all(item["legacy_owners"] for item in scenarios)
    assert all(item["status"] in {"planned", "implemented"} for item in scenarios)
    assert all(
        item.get("owner", "").strip()
        for item in scenarios
        if item["status"] == "implemented"
    )
