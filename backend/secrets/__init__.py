"""Local-only secret references and Windows Credential Manager storage."""

from .models import ConnectorCredentialMetadata, ConnectorCredentialState, SecretRef
from .store import InMemorySecretStore, SecretStore, SecretStoreError, WindowsCredentialManagerSecretStore

__all__ = [
    "ConnectorCredentialMetadata",
    "ConnectorCredentialState",
    "InMemorySecretStore",
    "SecretRef",
    "SecretStore",
    "SecretStoreError",
    "WindowsCredentialManagerSecretStore",
]
