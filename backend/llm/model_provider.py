from abc import ABC, abstractmethod

from .model_models import ModelCapabilities, ModelRequest, ModelResponse


class ModelProviderUnavailableError(RuntimeError):
    pass


class ModelTimeoutError(TimeoutError):
    pass


class ModelProvider(ABC):
    """Adapter boundary; providers never own Masha's identity or memory."""

    provider_id: str
    model_id: str
    capabilities: ModelCapabilities
    is_local: bool

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether this provider can currently serve a request."""

    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate one response or raise a typed provider error."""

