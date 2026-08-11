"""Read-only, integrity-checked access to canonical visual identity assets."""

from __future__ import annotations

import hashlib
from pathlib import Path

from backend.identity.identity_kernel import IdentityKernel

from .contracts import (
    ApplicationBoundaryError,
    ApplicationErrorCode,
    ResolvedVisualAsset,
    VisualAssetView,
)


class VisualIdentityResolver:
    def __init__(self, *, project_root: Path, identity_kernel: IdentityKernel):
        self._project_root = Path(project_root).resolve()
        self._identity_kernel = identity_kernel

    def canonical_assets(self) -> tuple[VisualAssetView, ...]:
        manifest = self._identity_kernel.load_manifest().visual_identity
        return tuple(self._metadata(asset_id) for asset_id in manifest.canonical_asset_ids)

    def resolve(self, asset_id: str) -> ResolvedVisualAsset:
        manifest = self._identity_kernel.load_manifest().visual_identity
        asset = next((item for item in manifest.assets if item.id == asset_id), None)
        if asset is None or asset_id not in manifest.canonical_asset_ids:
            raise ApplicationBoundaryError(ApplicationErrorCode.VISUAL_ASSET_NOT_FOUND)
        path = (self._project_root / asset.relative_path).resolve()
        if not path.is_relative_to(self._project_root) or not path.is_file():
            raise ApplicationBoundaryError(ApplicationErrorCode.VISUAL_ASSET_NOT_FOUND)
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest().upper()
        if digest != asset.sha256:
            raise ApplicationBoundaryError(ApplicationErrorCode.VISUAL_ASSET_INTEGRITY_FAILED)
        return ResolvedVisualAsset(
            asset=VisualAssetView(
                asset_id=asset.id,
                purpose=asset.purpose,
                media_type=self._media_type(path),
                byte_size=len(content),
            ),
            content=content,
        )

    def _metadata(self, asset_id: str) -> VisualAssetView:
        resolved = self.resolve(asset_id)
        return resolved.asset

    @staticmethod
    def _media_type(path: Path) -> str:
        if path.suffix.casefold() == ".png":
            return "image/png"
        return "application/octet-stream"
