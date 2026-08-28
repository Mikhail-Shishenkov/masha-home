import json
from pathlib import Path

import pytest

from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.model_models import ModelCapabilities, ModelMessage, ModelRequest
from backend.llm.model_provider import ModelProviderUnavailableError
from backend.llm.model_router import ModelRouter
from backend.llm.ollama_provider import OllamaProvider


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def read(self):
        return json.dumps(self.body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _request():
    return ModelRequest(
        messages=(ModelMessage(role="user", content="Привет"),),
        identity_context=IdentityKernel(IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")).build_context(),
        private_context={"current_local_time": "2026-08-11T00:00:00+03:00", "memory_context": []},
        execution_model_id="qwen3.5:9b",
    )


def test_provider_sends_local_identity_context_and_disables_thinking(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        if isinstance(request, str):
            return _Response({"models": []})
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response({"model": "qwen3.5:9b", "message": {"content": "Привет."}, "done": True})

    monkeypatch.setattr("backend.llm.ollama_provider.urlopen", fake_urlopen)
    response = OllamaProvider().generate(_request())

    assert response.text == "Привет."
    assert captured["payload"]["model"] == "qwen3.5:9b"
    assert captured["payload"]["think"] is False
    assert "format" not in captured["payload"]
    assert "Identity Context" in captured["payload"]["messages"][0]["content"]
    assert "current_local_time" in captured["payload"]["messages"][0]["content"]


def test_provider_sends_json_format_only_for_required_structured_output(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        if isinstance(request, str):
            return _Response({"models": []})
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response({"model": "qwen3.5:9b", "message": {"content": '{"ok":true}'}, "done": True})

    monkeypatch.setattr("backend.llm.ollama_provider.urlopen", fake_urlopen)
    provider = OllamaProvider()
    request = _request().model_copy(update={
        "required_capabilities": ModelCapabilities(structured_output=True),
    })

    response = ModelRouter([provider]).generate(request)

    assert provider.capabilities.structured_output is True
    assert captured["payload"]["format"] == "json"
    assert response.text == '{"ok":true}'


def test_provider_forwards_generic_json_schema_and_temperature(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response({"message": {"content": '{"kind":"ordinary"}'}, "done": True})

    monkeypatch.setattr("backend.llm.ollama_provider.urlopen", fake_urlopen)
    schema = {
        "type": "object",
        "properties": {"kind": {"const": "ordinary"}},
        "required": ["kind"],
        "additionalProperties": False,
    }
    request = _request().model_copy(update={
        "required_capabilities": ModelCapabilities(structured_output=True),
        "structured_output_schema": schema,
        "generation_temperature": 0,
    })

    OllamaProvider().generate(request)

    assert captured["payload"]["format"] == schema
    assert captured["payload"]["options"] == {"temperature": 0.0}


def test_model_request_rejects_schema_without_structured_capability():
    with pytest.raises(ValueError, match="requires structured_output"):
        _request().model_copy(
            update={"structured_output_schema": {"type": "object"}},
        ).model_validate(
            {
                **_request().model_dump(mode="python"),
                "structured_output_schema": {"type": "object"},
            }
        )


def test_provider_uses_selected_execution_model_without_fallback(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response({"message": {"content": "Привет."}, "done": True})

    monkeypatch.setattr("backend.llm.ollama_provider.urlopen", fake_urlopen)
    response = OllamaProvider().generate(_request().model_copy(update={"execution_model_id": "qwen3.5:4b"}))

    assert captured["payload"]["model"] == "qwen3.5:4b"
    assert response.model_id == "qwen3.5:4b"


def test_provider_maps_ollama_errors_to_controlled_provider_error(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr("backend.llm.ollama_provider.urlopen", unavailable)

    with pytest.raises(ModelProviderUnavailableError):
        OllamaProvider().generate(_request())
