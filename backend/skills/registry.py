"""Local package discovery and integrity registry without code execution."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from .models import (
    RegisteredSkill,
    SkillDescriptor,
    SkillIntegrity,
    SkillManifest,
    SkillRegistryState,
    utc_now,
)


class SkillRegistryError(RuntimeError):
    pass


class SkillNotFoundError(SkillRegistryError):
    pass


class SkillIntegrityError(SkillRegistryError):
    pass


class SkillRegistrationConflictError(SkillRegistryError):
    pass


class SkillRegistry:
    """Registers immutable package digests; it never imports an entrypoint."""

    def __init__(
        self,
        *,
        skills_root: Path,
        bundled_skills_root: Path | None = None,
        state_path: Path,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.skills_root = Path(skills_root)
        self.bundled_skills_root = (
            None if bundled_skills_root is None else Path(bundled_skills_root)
        )
        self.state_path = Path(state_path)
        self._clock = clock

    def list(self) -> tuple[SkillDescriptor, ...]:
        state = self._load_state()
        registered = {item.skill_id: item for item in state.skills}
        discovered = set(self._discovered_ids())
        skill_ids = sorted(discovered | set(registered))
        return tuple(self.inspect(skill_id, registration=registered.get(skill_id)) for skill_id in skill_ids)

    def inspect(
        self,
        skill_id: str,
        *,
        registration: RegisteredSkill | None = None,
    ) -> SkillDescriptor:
        self._validate_skill_id(skill_id)
        if registration is None:
            registration = next(
                (item for item in self._load_state().skills if item.skill_id == skill_id),
                None,
            )
        directory = self._skill_directory(skill_id)
        if not directory.is_dir():
            if registration is None:
                raise SkillNotFoundError(f"skill package not found: {skill_id}")
            return SkillDescriptor(
                skill_id=skill_id,
                manifest=None,
                registered=registration,
                integrity=SkillIntegrity.MISSING,
                error="registered package directory is missing",
            )
        try:
            manifest = self._load_manifest(directory)
            if manifest.skill_id != skill_id:
                raise SkillIntegrityError("manifest skill_id must match its directory name")
            digest = self._package_digest(directory)
        except (OSError, json.JSONDecodeError, ValidationError, SkillIntegrityError) as error:
            return SkillDescriptor(
                skill_id=skill_id,
                manifest=None,
                registered=registration,
                integrity=SkillIntegrity.INVALID,
                error=str(error),
            )
        integrity = SkillIntegrity.UNREGISTERED
        if registration is not None:
            integrity = (
                SkillIntegrity.VERIFIED
                if registration.version == manifest.version
                and registration.package_sha256 == digest
                else SkillIntegrity.MODIFIED
            )
        return SkillDescriptor(
            skill_id=skill_id,
            manifest=manifest,
            registered=registration,
            integrity=integrity,
            current_package_sha256=digest,
        )

    def verify(self, skill_id: str) -> SkillDescriptor:
        descriptor = self.inspect(skill_id)
        if descriptor.integrity in {SkillIntegrity.INVALID, SkillIntegrity.MISSING}:
            raise SkillIntegrityError(descriptor.error or "skill package is invalid")
        if descriptor.integrity is SkillIntegrity.MODIFIED:
            raise SkillIntegrityError(
                "skill package changed after registration; execution must remain blocked"
            )
        return descriptor

    def register(self, skill_id: str) -> RegisteredSkill:
        descriptor = self.verify(skill_id)
        assert descriptor.manifest is not None
        assert descriptor.current_package_sha256 is not None
        state = self._load_state()
        existing = next((item for item in state.skills if item.skill_id == skill_id), None)
        if existing is not None:
            if (
                existing.version == descriptor.manifest.version
                and existing.package_sha256 == descriptor.current_package_sha256
            ):
                return existing
            raise SkillRegistrationConflictError(
                "registered package changed; a future explicit upgrade flow is required"
            )
        registered = RegisteredSkill(
            skill_id=skill_id,
            version=descriptor.manifest.version,
            manifest_path=f"{skill_id}/skill.json",
            package_sha256=descriptor.current_package_sha256,
            registered_at=self._aware_now(),
        )
        self._write_state(
            state.model_copy(update={"skills": (*state.skills, registered)})
        )
        return registered

    def registration(self, skill_id: str) -> RegisteredSkill | None:
        """Return the current integrity pin without inspecting or executing a package."""

        self._validate_skill_id(skill_id)
        return next(
            (item for item in self._load_state().skills if item.skill_id == skill_id),
            None,
        )

    def pin_installed_package(
        self,
        skill_id: str,
        *,
        expected_previous_sha256: str | None,
        expected_package_sha256: str,
    ) -> RegisteredSkill:
        """Pin a package installed by an explicit, separately confirmed workflow."""

        self._validate_skill_id(skill_id)
        state = self._load_state()
        existing = next((item for item in state.skills if item.skill_id == skill_id), None)
        current_previous = None if existing is None else existing.package_sha256
        if current_previous != expected_previous_sha256:
            raise SkillRegistrationConflictError(
                "skill registration changed after the installation preview"
            )
        descriptor = self.inspect(skill_id, registration=existing)
        if descriptor.manifest is None or descriptor.current_package_sha256 is None:
            raise SkillIntegrityError("installed skill package is not valid")
        if descriptor.current_package_sha256 != expected_package_sha256:
            raise SkillIntegrityError("installed package digest does not match the confirmed preview")
        registered = RegisteredSkill(
            skill_id=skill_id,
            version=descriptor.manifest.version,
            manifest_path=f"{skill_id}/skill.json",
            package_sha256=expected_package_sha256,
            registered_at=self._aware_now(),
        )
        rows = list(state.skills)
        if existing is None:
            rows.append(registered)
        else:
            index = next(index for index, item in enumerate(rows) if item.skill_id == skill_id)
            rows[index] = registered
        self._write_state(state.model_copy(update={"skills": tuple(rows)}))
        return registered

    @classmethod
    def inspect_package_path(cls, directory: Path) -> tuple[SkillManifest, str]:
        """Validate an inert package snapshot without requiring registry membership."""

        root = Path(directory)
        if not root.is_dir() or root.is_symlink():
            raise SkillIntegrityError("skill package must be an existing real directory")
        manifest = cls._load_manifest(root)
        return manifest, cls._package_digest(root)

    def _discovered_ids(self) -> tuple[str, ...]:
        discovered = set()
        for root in self._package_roots():
            if not root.exists():
                continue
            discovered.update(
                child.name
                for child in root.iterdir()
                if child.is_dir()
                and not child.name.startswith((".", "_"))
                and (child / "skill.json").is_file()
            )
        return tuple(sorted(discovered))

    def _skill_directory(self, skill_id: str) -> Path:
        return self.package_directory(skill_id)

    def package_directory(self, skill_id: str) -> Path:
        """Resolve the active package: local UI install first, bundled fallback second."""

        self._validate_skill_id(skill_id)
        first_candidate = None
        for configured_root in self._package_roots():
            root = configured_root.resolve()
            candidate = root / skill_id
            if first_candidate is None:
                first_candidate = candidate.resolve(strict=False)
            if candidate.is_symlink():
                raise SkillIntegrityError("skill package directory cannot be a symlink")
            directory = candidate.resolve(strict=False)
            if directory.parent != root:
                raise SkillIntegrityError("skill path escapes the configured skills root")
            if directory.is_dir():
                return directory
        assert first_candidate is not None
        return first_candidate

    def _package_roots(self) -> tuple[Path, ...]:
        roots = [self.skills_root]
        if self.bundled_skills_root is not None:
            roots.append(self.bundled_skills_root)
        return tuple(roots)

    @staticmethod
    def _load_manifest(directory: Path) -> SkillManifest:
        manifest_path = directory / "skill.json"
        manifest = SkillManifest.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        )
        declared_instructions = directory / manifest.instructions_file
        if declared_instructions.is_symlink():
            raise SkillIntegrityError("declared instructions file is unsafe")
        instructions = declared_instructions.resolve()
        if not instructions.is_relative_to(directory.resolve()):
            raise SkillIntegrityError("instructions path escapes the package")
        if not instructions.is_file() or instructions.is_symlink():
            raise SkillIntegrityError("declared instructions file is missing or unsafe")
        return manifest

    @staticmethod
    def _package_digest(directory: Path) -> str:
        digest = hashlib.sha256()
        root = directory.resolve()
        files = []
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(directory)
            if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise SkillIntegrityError("skill package contains an unsafe link")
            files.append((relative.as_posix(), path))
        if not files:
            raise SkillIntegrityError("skill package is empty")
        for relative, path in sorted(files):
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65_536), b""):
                    digest.update(chunk)
            digest.update(b"\0")
        return digest.hexdigest()

    def _load_state(self) -> SkillRegistryState:
        if not self.state_path.exists():
            return SkillRegistryState()
        return SkillRegistryState.model_validate(
            json.loads(self.state_path.read_text(encoding="utf-8"))
        )

    def _write_state(self, state: SkillRegistryState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    @staticmethod
    def _validate_skill_id(skill_id: str) -> None:
        import re

        if re.fullmatch(r"[a-z][a-z0-9_]{2,63}", skill_id) is None:
            raise SkillIntegrityError("invalid skill id")

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("skill registry clock must return aware datetime")
        return value
