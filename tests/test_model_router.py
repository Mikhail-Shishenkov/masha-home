from pathlib import Path

import pytest

from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_store import IdentityStore
from backend.llm.fake_provider import FakeProvider
from backend.llm.model_models import (
    ModelCapabilities,
    ModelMessage,
    ModelRequest,
    PrivacyScope,
)
from backend.llm.model_provider import ModelProviderUnavailableError, ModelTimeoutError
from backend.llm.model_router import (
    ExternalContextDeniedError,
    ModelCapabilityUnavailableError,
    ModelRouter,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "identity" / "masha.identity.json"


def _request(**overrides) -> ModelRequest:
    fields = {
        "messages": (ModelMessage(role="user", content="Привет, Маша."),),
        "identity_context": IdentityKernel(IdentityStore(MANIFEST_PATH)).build_context(),
    }
    fields.update(overrides)
    return ModelRequest(**fields)


def test_fake_provider_receives_unchanged_identity_context():
    provider = FakeProvider(response_text="Я здесь.")
    request = _request()

    response = ModelRouter([provider]).generate(request)

    assert response.text == "Я здесь."
    assert provider.last_request is not None
    assert provider.last_request.identity_context == request.identity_context


def test_router_prefers_local_provider_even_when_external_is_available():
    local = FakeProvider(provider_id="local", is_local=True)
    external = FakeProvider(provider_id="external", is_local=False)

    response = ModelRouter([local, external]).generate(_request())

    assert response.provider_id == "local"
    assert external.last_request is None


def test_router_requires_capabilities():
    provider = FakeProvider(capabilities=ModelCapabilities(vision=False))
    request = _request(required_capabilities=ModelCapabilities(vision=True))

    with pytest.raises(ModelCapabilityUnavailableError):
        ModelRouter([provider]).generate(request)


def test_external_provider_needs_explicit_permission_and_no_private_context():
    external = FakeProvider(provider_id="external", is_local=False)
    router = ModelRouter([external])

    with pytest.raises(ExternalContextDeniedError):
        router.generate(_request(preferred_provider_id="external"))

    with pytest.raises(ExternalContextDeniedError):
        router.generate(
            _request(
                privacy_scope=PrivacyScope.EXTERNAL_ALLOWED,
                preferred_provider_id="external",
                private_context={"memory": "не отправлять"},
            )
        )

    response = router.generate(
        _request(
            privacy_scope=PrivacyScope.EXTERNAL_ALLOWED,
            preferred_provider_id="external",
        )
    )
    assert response.provider_id == "external"


def test_local_provider_still_works_when_private_context_blocks_external():
    local = FakeProvider(provider_id="local", is_local=True)
    external = FakeProvider(provider_id="external", is_local=False)

    response = ModelRouter([local, external]).generate(
        _request(
            privacy_scope=PrivacyScope.EXTERNAL_ALLOWED,
            private_context={"memory": "локальная запись"},
        )
    )

    assert response.provider_id == "local"


def test_router_reports_unavailable_and_timeout_providers():
    unavailable = FakeProvider(available=False)
    with pytest.raises(ModelProviderUnavailableError):
        ModelRouter([unavailable]).generate(_request())

    timeout = FakeProvider(simulate_timeout=True)
    with pytest.raises(ModelTimeoutError):
        ModelRouter([timeout]).generate(_request())
