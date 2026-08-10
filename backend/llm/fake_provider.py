from dataclasses import dataclass, field

from .model_models import (
    FinishReason,
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
)
from .model_provider import ModelProvider, ModelProviderUnavailableError, ModelTimeoutError


@dataclass
class FakeProvider(ModelProvider):
    """Deterministic provider for tests; it has no network or model dependency."""

    provider_id: str = "fake-local"
    model_id: str = "fake-model"
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    is_local: bool = True
    available: bool = True
    simulate_timeout: bool = False
    response_text: str = "Тестовый ответ Маши."
    last_request: ModelRequest | None = field(default=None, init=False)

    def is_available(self) -> bool:
        return self.available

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.available:
            raise ModelProviderUnavailableError(f"provider {self.provider_id} is unavailable")
        if self.simulate_timeout:
            raise ModelTimeoutError(f"provider {self.provider_id} timed out")
        self.last_request = request
        return ModelResponse(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=self.response_text,
            finish_reason=FinishReason.COMPLETED,
            capabilities=self.capabilities,
            is_local=self.is_local,
        )

