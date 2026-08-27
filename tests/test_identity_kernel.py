import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.identity.identity_kernel import IdentityKernel
from backend.identity.identity_kernel import IdentityMemoryVersionMismatchError
from backend.identity.identity_models import IdentityManifest
from backend.identity.identity_store import IdentityStore
from backend.memory.sqlite_repository import MemorySqliteRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "identity" / "masha.identity.json"
REGRESSION_PATH = PROJECT_ROOT / "identity" / "masha.regression.json"


def test_approved_manifest_builds_stable_model_independent_context():
    kernel = IdentityKernel(IdentityStore(MANIFEST_PATH))

    first = kernel.build_context()
    second = kernel.build_context()

    assert first == second
    assert first.name == "Маша"
    assert first.manifest_status == "approved"
    assert "честность важнее удобства" in first.core_traits
    assert first.visual_status == "approved"
    assert len(first.canonical_asset_ids) == 1


def test_draft_manifest_cannot_claim_approval_without_traits():
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["persona"]["core_traits"] = []

    with pytest.raises(ValidationError, match="at least one core trait"):
        IdentityManifest.model_validate(raw)


def test_identity_models_forbid_undeclared_fields():
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["persona"]["model_written_trait"] = "not allowed"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        IdentityManifest.model_validate(raw)


def test_identity_store_is_read_only(tmp_path: Path):
    copied_manifest = tmp_path / "masha.identity.json"
    shutil.copy2(MANIFEST_PATH, copied_manifest)
    store = IdentityStore(copied_manifest)
    before = copied_manifest.read_bytes()

    manifest = store.load()

    assert manifest.persona.id == "masha"
    assert copied_manifest.read_bytes() == before
    assert not hasattr(store, "save")


def test_visual_assets_match_their_manifest_hashes():
    manifest = IdentityStore(MANIFEST_PATH).load()

    for asset in manifest.visual_identity.assets:
        asset_path = PROJECT_ROOT / asset.relative_path
        assert asset_path.is_file()
        assert hashlib.sha256(asset_path.read_bytes()).hexdigest().upper() == asset.sha256


def test_regression_suite_matches_approved_identity_version():
    kernel = IdentityKernel(IdentityStore(MANIFEST_PATH))

    suite = kernel.load_regression_suite(str(REGRESSION_PATH))

    assert len(suite.scenarios) == 3
    assert suite.scenarios[0].id == "disagree_without_rejection"


def test_identity_memory_version_mismatch_is_detected_without_mutation(tmp_path, canonical_memory):
    database = MemorySqliteRepository(tmp_path / "memory.sqlite3")
    changed = dict(canonical_memory)
    changed["identity_version"] = "masha-old"
    database.replace_document(changed)
    before = database.read_document().model_dump(mode="json")
    manifest_before = MANIFEST_PATH.read_bytes()
    kernel = IdentityKernel(IdentityStore(MANIFEST_PATH))

    with pytest.raises(IdentityMemoryVersionMismatchError, match="does not match"):
        kernel.validate_memory_identity(database)

    assert database.read_document().model_dump(mode="json") == before
    assert MANIFEST_PATH.read_bytes() == manifest_before
