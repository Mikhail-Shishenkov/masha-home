import json
import shutil
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


@pytest.fixture
def memory_path(tmp_path: Path) -> str:
    """Return an isolated writable copy of the memory fixture."""
    target = tmp_path / "test_memory.json"
    shutil.copy2(FIXTURES_DIR / "test_memory.json", target)
    return str(target)


@pytest.fixture
def persona_path(tmp_path: Path) -> str:
    """Return an isolated copy of the persona fixture."""
    target = tmp_path / "test_persona.json"
    shutil.copy2(FIXTURES_DIR / "test_persona.json", target)
    return str(target)


@pytest.fixture
def canonical_memory() -> dict:
    with open(
        PROJECT_ROOT / "memory" / "test_memory.json",
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)

@pytest.fixture
def memory_schema() -> dict:
    with open(
        PROJECT_ROOT / "memory" / "memory_schema.json",
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)
