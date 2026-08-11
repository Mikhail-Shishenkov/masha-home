"""Persistent, local-only execution profiles for replaceable local models.

Profiles select an execution engine.  They are intentionally separate from
identity, memory, conversation history, and temporal state.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class LocalModelProfile(BaseModel):
    """A manually selected local model configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    display_name: str
    provider_id: str
    model_id: str
    timeout_seconds: float = Field(default=30.0, gt=0)
    think: bool = False
    capabilities: tuple[str, ...] = ("text",)
    enabled: bool = True
    description: str = ""


DEFAULT_PROFILES: tuple[LocalModelProfile, ...] = (
    LocalModelProfile(
        profile_id="primary",
        display_name="Primary",
        provider_id="ollama-local",
        model_id="qwen3.5:9b",
        capabilities=("text", "structured_output"),
        description="Основной разговор",
    ),
    LocalModelProfile(
        profile_id="fast",
        display_name="Fast",
        provider_id="ollama-local",
        model_id="qwen3.5:4b",
        description="Быстрый ручной режим",
    ),
    LocalModelProfile(
        profile_id="experimental",
        display_name="Experimental",
        provider_id="ollama-local",
        model_id="",
        enabled=False,
        description="Локальные эксперименты",
    ),
    LocalModelProfile(
        profile_id="vision-candidate",
        display_name="Vision candidate",
        provider_id="ollama-local",
        model_id="gemma4:e4b",
        capabilities=("vision",),
        enabled=False,
        description="Конфигурация на будущее; runtime не подключён",
    ),
)


class ModelProfileStore:
    """JSON-backed operating configuration, persisted independently of memory."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(self._default_data())

    def list_profiles(self) -> tuple[LocalModelProfile, ...]:
        return tuple(LocalModelProfile.model_validate(item) for item in self._load()["profiles"])

    def get_profile(self, profile_id: str) -> LocalModelProfile:
        for profile in self.list_profiles():
            if profile.profile_id == profile_id:
                return profile
        raise KeyError(profile_id)

    def get_active_profile(self) -> LocalModelProfile:
        active_profile_id = self._load().get("active_profile_id")
        try:
            return self.get_profile(active_profile_id)
        except KeyError as error:
            raise ValueError("active profile is invalid") from error

    def set_active_profile(self, profile_id: str) -> LocalModelProfile:
        profile = self.get_profile(profile_id)
        if not profile.enabled:
            raise ValueError("profile is disabled")
        data = self._load()
        data["active_profile_id"] = profile_id
        self._write(data)
        return profile

    # Compatibility aliases make the runtime call sites concise.
    def profiles(self) -> tuple[LocalModelProfile, ...]:
        return self.list_profiles()

    def active(self) -> LocalModelProfile:
        return self.get_active_profile()

    def use(self, profile_id: str) -> LocalModelProfile:
        return self.set_active_profile(profile_id)

    @staticmethod
    def _default_data() -> dict:
        return {
            "active_profile_id": "primary",
            "profiles": [profile.model_dump(mode="json") for profile in DEFAULT_PROFILES],
        }

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
