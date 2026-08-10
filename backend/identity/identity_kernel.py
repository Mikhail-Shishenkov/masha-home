from .identity_models import (
    IdentityContext,
    IdentityManifest,
    IdentityRegressionSuite,
)
from .identity_store import IdentityStore


class IdentityKernel:
    """Builds the same identity context independently of the selected LLM."""

    def __init__(self, store: IdentityStore):
        self._store = store

    def load_manifest(self) -> IdentityManifest:
        return self._store.load()

    def build_context(self) -> IdentityContext:
        manifest = self.load_manifest()
        return IdentityContext(
            identity_version=manifest.identity_version,
            manifest_status=manifest.status,
            persona_id=manifest.persona.id,
            name=manifest.persona.name,
            role=manifest.persona.role,
            core_traits=manifest.persona.core_traits,
            communication_principles=manifest.persona.communication_principles,
            relationship_expressions=manifest.persona.relationship_expressions,
            growth_areas=manifest.persona.growth_areas,
            visual_status=manifest.visual_identity.status,
            canonical_asset_ids=manifest.visual_identity.canonical_asset_ids,
        )

    def load_regression_suite(self, file_path: str) -> IdentityRegressionSuite:
        suite = self._store.load_regression_suite(file_path)
        if suite.identity_version != self.load_manifest().identity_version:
            raise ValueError("regression suite must match the loaded identity version")
        return suite
