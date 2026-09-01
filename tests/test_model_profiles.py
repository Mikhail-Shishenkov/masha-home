from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.conversation.cli import _run_model_command
from backend.conversation.conversation_service import ConversationService
from backend.conversation.conversation_store import ConversationStore
from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_profiles import ModelProfileStore
from backend.llm.model_router import ModelRouter
from backend.memory.memory_retriever import MemoryRetriever
from backend.memory.memory_store import MemoryStore
from backend.memory.working_memory import WorkingMemory


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LocalProfileProvider(FakeProvider):
    def __init__(self, *, available: bool = True, available_models: set[str] | None = None):
        super().__init__(provider_id="ollama-local", available=available, response_text="ok")
        self.available_models = available_models or {"qwen3.5:9b", "masha-fast:4b"}

    def is_model_available(self, model_id: str) -> bool:
        return model_id in self.available_models


def _service(tmp_path, provider: LocalProfileProvider, profiles: ModelProfileStore) -> ConversationService:
    return ConversationService(
        identity_kernel=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")),
        memory_retriever=MemoryRetriever(MemoryStore(PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json")),
        working_memory=WorkingMemory(),
        router=ModelRouter([provider]),
        history=ConversationStore(tmp_path / "history.json"),
        model_profiles=profiles,
    )


def test_default_profiles_and_active_profile_survive_restart(tmp_path):
    path = tmp_path / "config" / "models.json"
    profiles = ModelProfileStore(path)

    assert [profile.profile_id for profile in profiles.list_profiles()] == ["primary", "fast", "experimental", "vision-candidate"]
    assert profiles.get_active_profile().profile_id == "fast"
    assert profiles.get_active_profile().model_id == "masha-fast:4b"
    profiles.set_active_profile("primary")

    restarted = ModelProfileStore(path)
    assert restarted.get_active_profile().profile_id == "primary"
    assert restarted.get_active_profile().model_id == "qwen3.5:9b"
    assert restarted.get_active_profile().think is False


def test_disabled_or_unknown_profile_does_not_change_active_profile(tmp_path):
    profiles = ModelProfileStore(tmp_path / "models.json")

    with pytest.raises(KeyError):
        profiles.set_active_profile("missing")
    with pytest.raises(ValueError, match="disabled"):
        profiles.set_active_profile("experimental")

    assert profiles.get_active_profile().profile_id == "fast"


def test_cli_lists_current_and_switches_only_after_availability_checks(tmp_path):
    profiles = ModelProfileStore(tmp_path / "models.json")
    provider = LocalProfileProvider()
    service = _service(tmp_path, provider, profiles)
    output: list[str] = []
    active = profiles.get_active_profile()
    target = profiles.get_profile("primary")

    _run_model_command("list", service=service, output_fn=output.append)
    _run_model_command("current", service=service, output_fn=output.append)
    _run_model_command(f"use {target.profile_id}", service=service, output_fn=output.append)

    assert "primary" in output[0] and "fast" in output[0]
    assert active.model_id in output[1]
    assert f"Переключено на {target.profile_id}" in output[2]
    assert profiles.get_active_profile().profile_id == target.profile_id


@pytest.mark.parametrize(
    ("command", "provider", "expected"),
    [
        ("use missing", LocalProfileProvider(), "Не удалось"),
        ("use experimental", LocalProfileProvider(), "Не удалось"),
        ("use primary", LocalProfileProvider(available=False), "Ollama недоступен"),
        ("use primary", LocalProfileProvider(available_models={"masha-fast:4b"}), "qwen3.5:9b недоступна"),
    ],
)
def test_failed_cli_switch_preserves_previous_profile(tmp_path, command, provider, expected):
    profiles = ModelProfileStore(tmp_path / "models.json")
    service = _service(tmp_path, provider, profiles)
    output: list[str] = []

    _run_model_command(command, service=service, output_fn=output.append)

    assert expected in output[0]
    assert profiles.get_active_profile().profile_id == "fast"


def test_failed_profile_persistence_preserves_file_and_active_profile(tmp_path, monkeypatch):
    profiles = ModelProfileStore(tmp_path / "models.json")
    original = profiles.path.read_bytes()
    monkeypatch.setattr(profiles, "_write", lambda _data: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        profiles.set_active_profile("primary")

    assert profiles.path.read_bytes() == original
    assert profiles.get_active_profile().profile_id == "fast"


def test_selected_profile_is_the_only_execution_target_and_preserves_context_state(tmp_path):
    profiles = ModelProfileStore(tmp_path / "models.json")
    provider = LocalProfileProvider()
    service = _service(tmp_path, provider, profiles)
    active = profiles.get_active_profile()
    identity_before = service.identity_kernel.build_context().model_dump(mode="json")
    memory_before = (PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json").read_bytes()

    conversation_id, _ = service.send("привет", project_id="project_masha_home")

    assert provider.last_request.execution_model_id == active.model_id
    assert provider.last_request.execution_think is active.think
    assert provider.last_request.timeout_seconds == active.timeout_seconds
    assert service.router.select_provider(provider.last_request) is provider
    assert service.identity_kernel.build_context().model_dump(mode="json") == identity_before
    assert (PROJECT_ROOT / "tests" / "fixtures" / "test_memory.json").read_bytes() == memory_before
    assert service.history.get(conversation_id).id == conversation_id
    assert "current_local_time" in provider.last_request.private_context


def test_switch_does_not_write_conversation_or_memory_proposal_files(tmp_path):
    profiles = ModelProfileStore(tmp_path / "models.json")
    history_path = tmp_path / "history.json"
    proposal_path = tmp_path / "proposals.json"
    history_path.write_text(json.dumps({"conversations": []}), encoding="utf-8")
    proposal_path.write_text(json.dumps({"proposals": []}), encoding="utf-8")
    history_before, proposals_before = history_path.read_bytes(), proposal_path.read_bytes()

    profiles.set_active_profile("primary")

    assert history_path.read_bytes() == history_before
    assert proposal_path.read_bytes() == proposals_before
