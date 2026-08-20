"""Explicit local skill package preview, confirmation, installation and upgrade."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import zipfile
from datetime import datetime
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Callable, Final, Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .autonomy import ActionAutonomyService
from .models import SkillCapability, SkillIntegrity, SkillManifest, SkillRisk, utc_now
from .registry import SkillIntegrityError, SkillNotFoundError, SkillRegistry


MAX_PACKAGE_FILES: Final = 200
MAX_PACKAGE_FILE_BYTES: Final = 2_097_152
MAX_PACKAGE_BYTES: Final = 10_485_760
MAX_PACKAGE_PATH_LENGTH: Final = 500
MAX_PACKAGE_DEPTH: Final = 20
IGNORED_PACKAGE_PARTS: Final = frozenset({"__pycache__"})
IGNORED_PACKAGE_SUFFIXES: Final = frozenset({".pyc", ".pyo"})


class StrictInstallModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SkillInstallAction(str, Enum):
    INSTALL = "install"
    UPGRADE = "upgrade"


class SkillInstallStatus(str, Enum):
    PENDING = "pending"
    APPLYING = "applying"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SkillInstallProposal(StrictInstallModel):
    proposal_id: str = Field(pattern=r"^skill_install_[0-9a-f-]{36}$")
    action: SkillInstallAction
    status: SkillInstallStatus = SkillInstallStatus.PENDING
    skill_id: str
    name: str
    source_label: str = Field(min_length=1, max_length=200)
    current_version: str | None = None
    proposed_version: str
    current_package_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    proposed_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capabilities: tuple[SkillCapability, ...] = ()
    requested_scopes: tuple[str, ...] = ()
    risk_level: SkillRisk
    maximum_autonomy_level: int = Field(ge=0, le=4)
    files_added: tuple[str, ...] = ()
    files_changed: tuple[str, ...] = ()
    files_removed: tuple[str, ...] = ()
    permissions_to_revoke: int = Field(default=0, ge=0)
    runtime_supported: bool
    staged_relative_path: str | None = None
    created_at: AwareDatetime
    confirmed_at: AwareDatetime | None = None
    confirmed_by: Literal["misha"] | None = None
    rejected_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def consistent_lifecycle(self):
        if self.action is SkillInstallAction.INSTALL:
            if self.current_version is not None or self.current_package_sha256 is not None:
                raise ValueError("new install cannot have a current package")
        if self.action is SkillInstallAction.UPGRADE:
            if self.current_version is None or self.current_package_sha256 is None:
                raise ValueError("upgrade requires a current package")
        if (self.confirmed_at is None) != (self.confirmed_by is None):
            raise ValueError("confirmation requires timestamp and actor")
        if self.status is SkillInstallStatus.CONFIRMED and self.confirmed_at is None:
            raise ValueError("confirmed install requires confirmation provenance")
        if self.status is SkillInstallStatus.REJECTED and self.rejected_at is None:
            raise ValueError("rejected install requires timestamp")
        groups = self.files_added + self.files_changed + self.files_removed
        if len(groups) != len(set(groups)):
            raise ValueError("package diff contains duplicate paths")
        return self


class SkillInstallState(StrictInstallModel):
    schema_version: Literal["1.0"] = "1.0"
    proposals: tuple[SkillInstallProposal, ...] = ()


class SkillInstallError(RuntimeError):
    pass


class SkillInstallProposalStore:
    """Bounded local operating state suitable for a future UI confirmation flow."""

    def __init__(self, path: Path, *, limit: int = 100):
        self.path = Path(path)
        self.limit = limit

    def list(self) -> tuple[SkillInstallProposal, ...]:
        if not self.path.exists():
            return ()
        return SkillInstallState.model_validate(
            json.loads(self.path.read_text(encoding="utf-8"))
        ).proposals

    def get(self, proposal_id: str) -> SkillInstallProposal | None:
        return next((item for item in self.list() if item.proposal_id == proposal_id), None)

    def latest_open(self) -> SkillInstallProposal | None:
        rows = [
            item
            for item in self.list()
            if item.status in {SkillInstallStatus.PENDING, SkillInstallStatus.APPLYING}
        ]
        return rows[-1] if rows else None

    def save(self, proposal: SkillInstallProposal) -> SkillInstallProposal:
        rows = list(self.list())
        index = next(
            (index for index, item in enumerate(rows) if item.proposal_id == proposal.proposal_id),
            None,
        )
        if index is None:
            rows.append(proposal)
        else:
            rows[index] = proposal
        pending = [
            item
            for item in rows
            if item.status in {SkillInstallStatus.PENDING, SkillInstallStatus.APPLYING}
        ]
        terminal = [item for item in rows if item not in pending]
        bounded = (*terminal[-self.limit :], *pending)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                SkillInstallState(proposals=bounded).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return proposal


class SkillInstallerService:
    """Installs only confirmed local snapshots; it never downloads or imports code."""

    def __init__(
        self,
        *,
        registry: SkillRegistry,
        autonomy: ActionAutonomyService,
        proposal_store: SkillInstallProposalStore,
        runtime_root: Path,
        supported_skill_ids: frozenset[str] = frozenset({"project_observer", "web_search", "web_fetch"}),
        clock: Callable[[], datetime] = utc_now,
    ):
        self.registry = registry
        self.autonomy = autonomy
        self.proposal_store = proposal_store
        self.runtime_root = Path(runtime_root)
        self.supported_skill_ids = supported_skill_ids
        self._clock = clock

    def proposals(self) -> tuple[SkillInstallProposal, ...]:
        return self.proposal_store.list()

    def propose(self, source_path: Path) -> SkillInstallProposal:
        selected_source = Path(source_path).expanduser()
        if selected_source.is_symlink():
            raise SkillInstallError("skill source cannot be a symbolic link")
        source = selected_source.resolve(strict=True)
        proposal_id = f"skill_install_{uuid4()}"
        stage = self._stage_path(proposal_id)
        try:
            self._stage_source(source, stage)
            self._validate_staged_snapshot(stage)
            manifest, digest = SkillRegistry.inspect_package_path(stage)
            existing = self._current_descriptor(manifest.skill_id)
            if existing is None:
                action = SkillInstallAction.INSTALL
                current_version = None
                current_digest = None
                current_files: dict[str, str] = {}
            else:
                if existing.registered is None:
                    raise SkillInstallError(
                        "target package is present but not registered; register or resolve it explicitly"
                    )
                if existing.integrity is not SkillIntegrity.VERIFIED:
                    raise SkillInstallError(
                        "current package is not verified; installation recovery is required"
                    )
                assert existing.manifest is not None
                assert existing.current_package_sha256 is not None
                action = SkillInstallAction.UPGRADE
                current_version = existing.manifest.version
                current_digest = existing.current_package_sha256
                if digest == current_digest:
                    raise SkillInstallError("selected package is already installed")
                if self._version_key(manifest.version) <= self._version_key(current_version):
                    raise SkillInstallError("upgrade version must be newer than the installed version")
                current_files = self._file_hashes(
                    self.registry.package_directory(manifest.skill_id)
                )
            if any(
                item.skill_id == manifest.skill_id
                and item.status in {SkillInstallStatus.PENDING, SkillInstallStatus.APPLYING}
                for item in self.proposal_store.list()
            ):
                raise SkillInstallError("this skill already has an open installation proposal")
            proposed_files = self._file_hashes(stage)
            added, changed, removed = self._diff(current_files, proposed_files)
            proposal = SkillInstallProposal(
                proposal_id=proposal_id,
                action=action,
                skill_id=manifest.skill_id,
                name=manifest.name,
                source_label=source.name,
                current_version=current_version,
                proposed_version=manifest.version,
                current_package_sha256=current_digest,
                proposed_package_sha256=digest,
                capabilities=manifest.capabilities,
                requested_scopes=manifest.requested_scopes,
                risk_level=manifest.risk_level,
                maximum_autonomy_level=manifest.maximum_autonomy_level,
                files_added=added,
                files_changed=changed,
                files_removed=removed,
                permissions_to_revoke=sum(
                    item.skill_id == manifest.skill_id for item in self.autonomy.grants()
                ),
                runtime_supported=manifest.skill_id in self.supported_skill_ids,
                staged_relative_path=self._relative_runtime(stage),
                created_at=self._now(),
            )
            return self.proposal_store.save(proposal)
        except Exception:
            self._remove_tree(stage.parent)
            raise

    def confirm(self, proposal_id: str) -> SkillInstallProposal:
        proposal = self._require_proposal(proposal_id)
        if proposal.status is SkillInstallStatus.CONFIRMED:
            return proposal
        if proposal.status is SkillInstallStatus.REJECTED:
            raise SkillInstallError("rejected installation cannot be confirmed")
        if not proposal.runtime_supported:
            raise SkillInstallError(
                "package has no application-wired safe runtime adapter"
            )
        stage = self._proposal_stage(proposal)
        manifest, digest = SkillRegistry.inspect_package_path(stage)
        if manifest.skill_id != proposal.skill_id or digest != proposal.proposed_package_sha256:
            raise SkillInstallError("staged package changed after preview")
        applying = proposal.model_copy(update={"status": SkillInstallStatus.APPLYING})
        applying = self.proposal_store.save(applying)
        self._apply_confirmed(applying, stage)
        confirmed = applying.model_copy(
            update={
                "status": SkillInstallStatus.CONFIRMED,
                "confirmed_at": self._now(),
                "confirmed_by": "misha",
                "staged_relative_path": None,
            }
        )
        confirmed = self.proposal_store.save(confirmed)
        self._remove_tree(stage.parent)
        self._remove_tree(self._backup_path(proposal_id).parent)
        return confirmed

    def reject(self, proposal_id: str) -> SkillInstallProposal:
        proposal = self._require_proposal(proposal_id)
        if proposal.status is SkillInstallStatus.REJECTED:
            return proposal
        if proposal.status is SkillInstallStatus.CONFIRMED:
            raise SkillInstallError("confirmed installation cannot be rejected")
        if proposal.status is SkillInstallStatus.APPLYING:
            raise SkillInstallError("applying installation must be recovered before rejection")
        rejected = proposal.model_copy(
            update={
                "status": SkillInstallStatus.REJECTED,
                "rejected_at": self._now(),
                "staged_relative_path": None,
            }
        )
        rejected = self.proposal_store.save(rejected)
        self._remove_tree(self._stage_path(proposal_id).parent)
        return rejected

    def _apply_confirmed(self, proposal: SkillInstallProposal, stage: Path) -> None:
        skills_root = self.registry.skills_root.resolve()
        skills_root.mkdir(parents=True, exist_ok=True)
        target = (skills_root / proposal.skill_id).resolve(strict=False)
        if target.parent != skills_root or target.is_symlink():
            raise SkillInstallError("unsafe skill installation target")
        temporary = skills_root / f".{proposal.skill_id}.install-{proposal.proposal_id[14:]}"
        backup = self._backup_path(proposal.proposal_id)
        target_digest = self._digest_if_package(target)
        registration = self.registry.registration(proposal.skill_id)

        if target_digest == proposal.proposed_package_sha256:
            self.autonomy.revoke_skill(proposal.skill_id)
            if registration is None or registration.package_sha256 != proposal.proposed_package_sha256:
                self.registry.pin_installed_package(
                    proposal.skill_id,
                    expected_previous_sha256=proposal.current_package_sha256,
                    expected_package_sha256=proposal.proposed_package_sha256,
                )
            return

        expected_current = proposal.current_package_sha256
        if proposal.action is SkillInstallAction.INSTALL:
            if target.exists():
                raise SkillInstallError("installation target appeared after preview")
        elif target_digest != expected_current:
            active_current = self.registry.package_directory(proposal.skill_id)
            active_digest = self._digest_if_package(active_current)
            if not target.exists() and active_digest == expected_current:
                pass
            elif not target.exists() and self._digest_if_package(backup) == expected_current:
                pass
            else:
                raise SkillInstallError("installed package changed after preview")

        self.autonomy.revoke_skill(proposal.skill_id)
        if temporary.exists():
            if self._digest_if_package(temporary) != proposal.proposed_package_sha256:
                raise SkillInstallError("temporary installation package is inconsistent")
        else:
            shutil.copytree(stage, temporary)
        _, temporary_digest = SkillRegistry.inspect_package_path(temporary)
        if temporary_digest != proposal.proposed_package_sha256:
            raise SkillInstallError("temporary package does not match preview")

        moved_current = False
        installed_new = False
        try:
            if proposal.action is SkillInstallAction.UPGRADE and target.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                target.replace(backup)
                moved_current = True
            temporary.replace(target)
            installed_new = True
            self.registry.pin_installed_package(
                proposal.skill_id,
                expected_previous_sha256=proposal.current_package_sha256,
                expected_package_sha256=proposal.proposed_package_sha256,
            )
        except Exception:
            if installed_new and target.exists():
                self._remove_tree(target)
            if moved_current and backup.exists() and not target.exists():
                backup.replace(target)
            if temporary.exists():
                self._remove_tree(temporary)
            raise

    def _stage_source(self, source: Path, destination: Path) -> None:
        if destination.exists():
            raise SkillInstallError("installation staging path already exists")
        destination.parent.mkdir(parents=True, exist_ok=False)
        if source.is_dir():
            if source.is_symlink():
                raise SkillInstallError("skill source directory cannot be a symbolic link")
            files = self._directory_files(source)
            self._copy_files(files, destination)
            return
        if source.is_file() and source.suffix.casefold() == ".zip":
            self._extract_zip(source, destination)
            return
        raise SkillInstallError("skill source must be a local package directory or ZIP file")

    def _directory_files(self, source: Path) -> tuple[tuple[PurePosixPath, Path, int], ...]:
        rows = []
        for item in source.rglob("*"):
            if item.is_symlink():
                raise SkillInstallError("skill package cannot contain symbolic links")
            if item.is_dir():
                continue
            if not item.is_file():
                raise SkillInstallError("skill package contains an unsupported path type")
            relative = PurePosixPath(item.relative_to(source).as_posix())
            self._validate_relative(relative)
            if self._ignored(relative):
                raise SkillInstallError("compiled Python artifacts are not accepted")
            rows.append((relative, item, item.stat().st_size))
        self._validate_limits([(relative, size) for relative, _, size in rows])
        return tuple(rows)

    def _copy_files(
        self,
        rows: tuple[tuple[PurePosixPath, Path, int], ...],
        destination: Path,
    ) -> None:
        destination.mkdir(parents=True)
        for relative, source, _ in rows:
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def _extract_zip(self, source: Path, destination: Path) -> None:
        with zipfile.ZipFile(source) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            raw_paths = []
            for info in infos:
                if info.flag_bits & 0x1:
                    raise SkillInstallError("encrypted ZIP entries are not supported")
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise SkillInstallError("ZIP package cannot contain symbolic links")
                relative = PurePosixPath(info.filename.replace("\\", "/"))
                self._validate_relative(relative)
                raw_paths.append((relative, info))
            prefix = self._zip_prefix(tuple(path for path, _ in raw_paths))
            rows = []
            seen = set()
            for raw, info in raw_paths:
                relative = PurePosixPath(*raw.parts[len(prefix) :])
                self._validate_relative(relative)
                if self._ignored(relative):
                    raise SkillInstallError("compiled Python artifacts are not accepted")
                key = relative.as_posix().casefold()
                if key in seen:
                    raise SkillInstallError("ZIP package contains duplicate paths")
                seen.add(key)
                rows.append((relative, info))
            self._validate_limits([(relative, info.file_size) for relative, info in rows])
            destination.mkdir(parents=True)
            for relative, info in rows:
                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as input_stream, target.open("wb") as output_stream:
                    written = 0
                    while True:
                        chunk = input_stream.read(65_536)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > info.file_size or written > MAX_PACKAGE_FILE_BYTES:
                            raise SkillInstallError("ZIP entry exceeds its declared safe size")
                        output_stream.write(chunk)
                    if written != info.file_size:
                        raise SkillInstallError("ZIP entry size does not match its metadata")

    def _validate_staged_snapshot(self, directory: Path) -> None:
        rows = []
        root = directory.resolve(strict=True)
        for path in directory.rglob("*"):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise SkillInstallError("staged package contains an unsafe link")
            if path.is_dir():
                continue
            if not path.is_file():
                raise SkillInstallError("staged package contains an unsupported path type")
            relative = PurePosixPath(path.relative_to(directory).as_posix())
            self._validate_relative(relative)
            rows.append((relative, path.stat().st_size))
        self._validate_limits(rows)

    @staticmethod
    def _zip_prefix(paths: tuple[PurePosixPath, ...]) -> tuple[str, ...]:
        if any(path.as_posix() == "skill.json" for path in paths):
            return ()
        top = {path.parts[0] for path in paths if path.parts}
        if len(top) == 1:
            prefix = (next(iter(top)),)
            if any(path.parts[len(prefix) :] == ("skill.json",) for path in paths):
                return prefix
        raise SkillInstallError("ZIP must contain one skill package root")

    @staticmethod
    def _validate_relative(relative: PurePosixPath) -> None:
        rendered = relative.as_posix()
        if (
            not rendered
            or rendered == "."
            or relative.is_absolute()
            or len(rendered) > MAX_PACKAGE_PATH_LENGTH
            or len(relative.parts) > MAX_PACKAGE_DEPTH
            or any(part in {"", ".", ".."} or ":" in part for part in relative.parts)
        ):
            raise SkillInstallError("skill package contains an unsafe path")

    @staticmethod
    def _ignored(relative: PurePosixPath) -> bool:
        return bool(
            set(relative.parts) & IGNORED_PACKAGE_PARTS
            or relative.suffix.casefold() in IGNORED_PACKAGE_SUFFIXES
        )

    @staticmethod
    def _validate_limits(rows: list[tuple[PurePosixPath, int]]) -> None:
        if not rows:
            raise SkillInstallError("skill package is empty")
        if len(rows) > MAX_PACKAGE_FILES:
            raise SkillInstallError("skill package contains too many files")
        if any(size < 0 or size > MAX_PACKAGE_FILE_BYTES for _, size in rows):
            raise SkillInstallError("skill package file exceeds the size limit")
        if sum(size for _, size in rows) > MAX_PACKAGE_BYTES:
            raise SkillInstallError("skill package exceeds the total size limit")
        keys = [relative.as_posix().casefold() for relative, _ in rows]
        if len(keys) != len(set(keys)):
            raise SkillInstallError("skill package contains duplicate paths")

    def _current_descriptor(self, skill_id: str):
        try:
            return self.registry.inspect(skill_id)
        except SkillNotFoundError:
            return None

    @staticmethod
    def _file_hashes(directory: Path) -> dict[str, str]:
        rows = {}
        for path in sorted(Path(directory).rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(directory).as_posix()
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65_536), b""):
                    digest.update(chunk)
            rows[relative] = digest.hexdigest()
        return rows

    @staticmethod
    def _diff(current: dict[str, str], proposed: dict[str, str]):
        current_paths = set(current)
        proposed_paths = set(proposed)
        return (
            tuple(sorted(proposed_paths - current_paths)),
            tuple(sorted(path for path in current_paths & proposed_paths if current[path] != proposed[path])),
            tuple(sorted(current_paths - proposed_paths)),
        )

    @staticmethod
    def _version_key(version: str):
        match = re.fullmatch(
            r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([a-zA-Z0-9.-]+))?(?:\+[a-zA-Z0-9.-]+)?",
            version,
        )
        if match is None:
            raise SkillInstallError("skill version is not valid semantic versioning")
        prerelease = match.group(4)
        prerelease_key = () if prerelease is None else tuple(
            (0, int(part)) if part.isdigit() else (1, part.casefold())
            for part in prerelease.split(".")
        )
        return (
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            1 if prerelease is None else 0,
            prerelease_key,
        )

    def _require_proposal(self, proposal_id: str) -> SkillInstallProposal:
        proposal = self.proposal_store.get(proposal_id)
        if proposal is None:
            raise SkillInstallError("skill installation proposal not found")
        return proposal

    def _proposal_stage(self, proposal: SkillInstallProposal) -> Path:
        if proposal.staged_relative_path is None:
            raise SkillInstallError("installation proposal has no staged package")
        relative = PurePosixPath(proposal.staged_relative_path)
        self._validate_relative(relative)
        candidate = self.runtime_root.joinpath(*relative.parts).resolve(strict=False)
        root = self.runtime_root.resolve(strict=False)
        if not candidate.is_relative_to(root):
            raise SkillInstallError("staged package path escapes runtime root")
        return candidate

    def _stage_path(self, proposal_id: str) -> Path:
        return self.runtime_root / "staging" / proposal_id / "package"

    def _backup_path(self, proposal_id: str) -> Path:
        return self.runtime_root / "backups" / proposal_id / "package"

    def _relative_runtime(self, path: Path) -> str:
        return path.relative_to(self.runtime_root).as_posix()

    @staticmethod
    def _digest_if_package(path: Path) -> str | None:
        if not path.is_dir() or path.is_symlink():
            return None
        try:
            _, digest = SkillRegistry.inspect_package_path(path)
            return digest
        except (OSError, SkillIntegrityError):
            return None

    @staticmethod
    def _remove_tree(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("skill installer clock must return aware datetime")
        return value
