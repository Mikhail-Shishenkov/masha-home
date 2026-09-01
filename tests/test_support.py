"""Minimal fixtures shared by independent application-boundary contracts."""

from __future__ import annotations

import shutil
from pathlib import Path

from backend.llm.fake_provider import FakeProvider
from backend.memory.sqlite_repository import MemorySqliteRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LocalProfileProvider(FakeProvider):
    def __init__(
        self,
        *,
        available: bool = True,
        available_models: set[str] | None = None,
        simulate_timeout: bool = False,
        response_text: str = "Привет, Миша.",
    ):
        super().__init__(
            provider_id="ollama-local",
            available=available,
            simulate_timeout=simulate_timeout,
            response_text=response_text,
        )
        self.available_models = available_models or {"qwen3.5:9b", "masha-fast:4b"}

    def is_model_available(self, model_id: str) -> bool:
        return model_id in self.available_models


def _isolated_root(tmp_path: Path) -> Path:
    root = tmp_path / "masha-home"
    shutil.copytree(PROJECT_ROOT / "identity", root / "identity")
    shutil.copytree(PROJECT_ROOT / "skills", root / "skills")
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    repository.import_json(PROJECT_ROOT / "memory" / "test_memory.json")
    return root
