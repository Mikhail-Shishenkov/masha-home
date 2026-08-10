import json
from pathlib import Path

from .identity_models import IdentityManifest, IdentityRegressionSuite


class IdentityStore:
    """Read-only loader for a manifest that belongs to the user, never an LLM."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def load(self) -> IdentityManifest:
        with self.file_path.open("r", encoding="utf-8") as file:
            raw_manifest = json.load(file)
        return IdentityManifest.model_validate(raw_manifest)

    def load_regression_suite(
        self,
        file_path: str | Path,
    ) -> IdentityRegressionSuite:
        with Path(file_path).open("r", encoding="utf-8") as file:
            raw_suite = json.load(file)
        return IdentityRegressionSuite.model_validate(raw_suite)
