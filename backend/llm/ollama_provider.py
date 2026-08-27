"""Local Ollama adapter for the provider-neutral model contract."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .model_models import (
    FinishReason,
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
)
from .model_provider import ModelProvider, ModelProviderUnavailableError, ModelTimeoutError


class OllamaProvider(ModelProvider):
    provider_id = "ollama-local"
    model_id = ""
    capabilities = ModelCapabilities(structured_output=True, tools=True, vision=True)
    is_local = True

    def __init__(
        self,
        *,
        endpoint: str = "http://127.0.0.1:11434",
        model_id: str = "",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model_id = model_id

    def is_available(self) -> bool:
        try:
            with urlopen(f"{self.endpoint}/api/tags", timeout=2.0) as response:
                return 200 <= response.status < 300
        except (OSError, URLError):
            return False

    def is_model_available(self, model_id: str) -> bool:
        try:
            with urlopen(f"{self.endpoint}/api/tags", timeout=2.0) as response:
                body = json.loads(response.read().decode("utf-8"))
            return any(item.get("name") == model_id for item in body.get("models", []))
        except (OSError, URLError, json.JSONDecodeError):
            return False

    def generate(self, request: ModelRequest) -> ModelResponse:
        model_id = request.execution_model_id or self.model_id
        if not model_id:
            raise ModelProviderUnavailableError("no local model selected")
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": self._system_context(request)},
                *[
                    {"role": message.role.value, "content": message.content}
                    for message in request.messages
                ],
            ],
            "think": request.execution_think,
            "stream": False,
        }
        if request.required_capabilities.structured_output:
            payload["format"] = "json"
        http_request = Request(
            f"{self.endpoint}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=request.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except TimeoutError as error:
            raise ModelTimeoutError("local Ollama request timed out") from error
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
            raise ModelProviderUnavailableError("local Ollama is unavailable") from error
        if body.get("error"):
            raise ModelProviderUnavailableError(str(body["error"]))
        text = str((body.get("message") or {}).get("content", "")).strip()
        if not text:
            raise ModelProviderUnavailableError("local Ollama returned an empty response")
        return ModelResponse(
            provider_id=self.provider_id,
            model_id=str(body.get("model", model_id)),
            text=text,
            finish_reason=FinishReason.LENGTH if body.get("done_reason") == "length" else FinishReason.COMPLETED,
            capabilities=self.capabilities,
            is_local=True,
        )

    @staticmethod
    def _system_context(request: ModelRequest) -> str:
        identity = request.identity_context
        private = request.private_context
        return "\n\n".join(
            (
                "Identity Context (application-owned, protected source of identity):\n"
                + json.dumps(identity.model_dump(mode="json"), ensure_ascii=False),
                "Conversation Context (bounded and application-provided):\n"
                + json.dumps(private, ensure_ascii=False),
                "Follow the application-provided behavioural contract exactly. Do not invent operations or capabilities.",
            )
        )
