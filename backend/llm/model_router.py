from collections.abc import Iterable

from .model_models import ModelRequest, ModelResponse, PrivacyScope
from .model_provider import ModelProvider, ModelProviderUnavailableError


class ModelCapabilityUnavailableError(RuntimeError):
    pass


class ExternalContextDeniedError(PermissionError):
    pass


class ModelRouter:
    """Selects a capable provider while keeping local data local by default."""

    def __init__(self, providers: Iterable[ModelProvider] = ()):
        self._providers: dict[str, ModelProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ModelProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"duplicate provider id: {provider.provider_id}")
        self._providers[provider.provider_id] = provider

    def get_provider(self, provider_id: str) -> ModelProvider | None:
        """Return a registered provider without selecting or falling back."""
        return self._providers.get(provider_id)

    def generate(self, request: ModelRequest) -> ModelResponse:
        provider = self.select_provider(request)
        return provider.generate(request)

    def select_provider(self, request: ModelRequest) -> ModelProvider:
        candidates = self._candidates(request)
        if not candidates:
            raise ModelProviderUnavailableError("no available model provider")

        capable = [
            provider
            for provider in candidates
            if provider.capabilities.supports(request.required_capabilities)
        ]
        if not capable:
            raise ModelCapabilityUnavailableError(
                "no available provider supports the required capabilities"
            )
        return capable[0]

    def _candidates(self, request: ModelRequest) -> list[ModelProvider]:
        if request.preferred_provider_id is not None:
            provider = self._providers.get(request.preferred_provider_id)
            if provider is None or not provider.is_available():
                return []
            self._check_privacy(provider, request)
            return [provider]

        local = [
            provider
            for provider in self._providers.values()
            if provider.is_local and provider.is_available()
        ]
        external = [
            provider
            for provider in self._providers.values()
            if not provider.is_local and provider.is_available()
        ]
        if request.privacy_scope == PrivacyScope.LOCAL_ONLY:
            return local
        if request.private_context:
            return local
        return local + external

    @staticmethod
    def _check_privacy(provider: ModelProvider, request: ModelRequest) -> None:
        if provider.is_local:
            return
        if request.privacy_scope != PrivacyScope.EXTERNAL_ALLOWED:
            raise ExternalContextDeniedError("external provider is not allowed for this request")
        if request.private_context:
            raise ExternalContextDeniedError(
                "private context cannot be sent to an external provider"
            )
