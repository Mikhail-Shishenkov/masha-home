import json

import pytest
from pydantic import ValidationError

from backend.secrets import (
    ConnectorCredentialMetadata,
    ConnectorCredentialState,
    InMemorySecretStore,
    SecretRef,
)


def test_secret_ref_is_small_validated_identifier_only():
    assert SecretRef(value="google-calendar-primary").value == "google-calendar-primary"
    with pytest.raises(ValidationError):
        SecretRef(value="Google calendar primary")


def test_in_memory_secret_store_put_get_exists_delete_and_missing():
    store = InMemorySecretStore()
    reference = SecretRef(value="google-calendar-primary")
    assert store.get(reference) is None
    assert store.exists(reference) is False
    store.put(reference, "credential-value-not-for-metadata")
    assert store.get(reference) == "credential-value-not-for-metadata"
    assert store.exists(reference) is True
    store.delete(reference)
    assert store.get(reference) is None
    assert store.exists(reference) is False


def test_connector_credential_lifecycle_is_secret_free():
    store = InMemorySecretStore()
    reference = SecretRef(value="google-calendar-primary")
    disconnected = ConnectorCredentialMetadata(connector_id="google-calendar")
    pending = ConnectorCredentialMetadata(connector_id="google-calendar", secret_ref=reference)
    assert disconnected.credential_state(store) is ConnectorCredentialState.DISCONNECTED
    assert pending.credential_state(store) is ConnectorCredentialState.NEEDS_RECONNECT
    store.put(reference, "credential-value-not-for-metadata")
    assert pending.credential_state(store) is ConnectorCredentialState.READY


def test_serialized_connector_metadata_never_contains_secret_value():
    secret = "credential-value-not-for-metadata"
    metadata = ConnectorCredentialMetadata(
        connector_id="google-calendar", secret_ref=SecretRef(value="google-calendar-primary"),
    )
    serialized = metadata.model_dump_json()
    assert secret not in serialized
    assert json.loads(serialized) == {
        "connector_id": "google-calendar",
        "secret_ref": {"value": "google-calendar-primary"},
    }
