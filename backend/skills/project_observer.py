"""Application-wired, bounded and strictly read-only project observation skill."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from pydantic import JsonValue

from .tools import ToolAdapter, ToolExecutionResult, ToolVerification


PROJECT_OBSERVER_SKILL_ID: Final = "project_observer"
PROJECT_OBSERVER_TOOL_ID: Final = "project_observer"
PROJECT_SCOPE: Final = "workspace:masha-home"

MAX_TREE_DEPTH: Final = 4
MAX_TREE_ENTRIES: Final = 500
MAX_TEXT_CHARS: Final = 20_000
MAX_READ_BYTES: Final = 1_048_576
MAX_HASH_BYTES: Final = 2_097_152

PROTECTED_PARTS: Final = frozenset({
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "local-data",
    "node_modules",
})
PROTECTED_NAMES: Final = frozenset({
    ".env",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "secrets.json",
})
PROTECTED_SUFFIXES: Final = frozenset({".key", ".pem", ".p12", ".pfx"})
TEXT_SUFFIXES: Final = frozenset({
    "",
    ".cfg",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".ps1",
    ".py",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
})


class ProjectObserverBoundaryError(ValueError):
    """A requested observation crossed the explicit read-only boundary."""


@dataclass
class ProjectObserverTool(ToolAdapter):
    """Reads only a normalized workspace root; never writes or launches processes."""

    workspace_root: Path
    skill_id: str = PROJECT_OBSERVER_SKILL_ID
    tool_id: str = PROJECT_OBSERVER_TOOL_ID

    def __post_init__(self) -> None:
        root = Path(self.workspace_root)
        if not root.is_dir() or root.is_symlink():
            raise ProjectObserverBoundaryError("workspace root must be an existing real directory")
        self.workspace_root = root.resolve(strict=True)

    def execute(self, operation: str, inputs: dict[str, JsonValue]) -> ToolExecutionResult:
        try:
            output = self._perform(operation, inputs)
        except (OSError, UnicodeError, ProjectObserverBoundaryError, ValueError) as error:
            return ToolExecutionResult(
                success=False,
                summary="Project observation was blocked or could not be completed.",
                evidence_code="project_observer:blocked",
                error=str(error)[:500],
            )
        evidence = self._evidence(operation, output)
        return ToolExecutionResult(
            success=True,
            summary="Project observation completed inside the bounded workspace.",
            output=output,
            evidence_code=evidence,
        )

    def verify(
        self,
        operation: str,
        inputs: dict[str, JsonValue],
        result: ToolExecutionResult,
    ) -> ToolVerification:
        if not result.success:
            return ToolVerification(verified=False, code="execution_failed")
        try:
            current = self._perform(operation, inputs)
        except (OSError, UnicodeError, ProjectObserverBoundaryError, ValueError):
            return ToolVerification(verified=False, code="project_state_unavailable")
        expected = self._evidence(operation, current)
        return ToolVerification(
            verified=(result.output == current and result.evidence_code == expected),
            code=(
                "project_observation_verified"
                if result.output == current and result.evidence_code == expected
                else "project_changed_before_verification"
            ),
        )

    def _perform(self, operation: str, inputs: dict[str, JsonValue]) -> JsonValue:
        if operation == "list_tree":
            self._only_keys(inputs, {"path", "max_depth", "max_entries"})
            return self._list_tree(
                self._string(inputs, "path", default="."),
                self._integer(inputs, "max_depth", default=2, minimum=0, maximum=MAX_TREE_DEPTH),
                self._integer(
                    inputs,
                    "max_entries",
                    default=200,
                    minimum=1,
                    maximum=MAX_TREE_ENTRIES,
                ),
            )
        if operation == "read_text":
            self._only_keys(inputs, {"path", "max_chars"})
            return self._read_text(
                self._string(inputs, "path"),
                self._integer(
                    inputs,
                    "max_chars",
                    default=8_000,
                    minimum=1,
                    maximum=MAX_TEXT_CHARS,
                ),
            )
        if operation == "inspect_path":
            self._only_keys(inputs, {"path"})
            return self._inspect_path(self._string(inputs, "path"))
        raise ProjectObserverBoundaryError("unsupported project observer operation")

    def _list_tree(self, relative: str, max_depth: int, max_entries: int) -> JsonValue:
        start = self._resolve(relative)
        if not start.is_dir():
            raise ProjectObserverBoundaryError("tree path must be a directory")
        rows: list[dict[str, JsonValue]] = []
        stack = [(start, 0)]
        truncated = False
        while stack:
            directory, depth = stack.pop()
            children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
            directories: list[Path] = []
            for child in children:
                if self._blocked(child) or child.is_symlink():
                    continue
                if len(rows) >= max_entries:
                    truncated = True
                    break
                resolved = child.resolve(strict=True)
                if not resolved.is_relative_to(self.workspace_root):
                    raise ProjectObserverBoundaryError("tree entry escapes workspace")
                row: dict[str, JsonValue] = {
                    "path": resolved.relative_to(self.workspace_root).as_posix(),
                    "type": "directory" if resolved.is_dir() else "file",
                }
                if resolved.is_file():
                    row["size_bytes"] = resolved.stat().st_size
                rows.append(row)
                if resolved.is_dir() and depth < max_depth:
                    directories.append(resolved)
            if truncated:
                break
            stack.extend((item, depth + 1) for item in reversed(directories))
        return {
            "root": self._relative_label(start),
            "entries": rows,
            "truncated": truncated,
        }

    def _read_text(self, relative: str, max_chars: int) -> JsonValue:
        path = self._resolve(relative)
        if not path.is_file():
            raise ProjectObserverBoundaryError("text path must be a file")
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            raise ProjectObserverBoundaryError("file type is outside the text allowlist")
        size = path.stat().st_size
        if size > MAX_READ_BYTES:
            raise ProjectObserverBoundaryError("text file exceeds the read limit")
        content = path.read_text(encoding="utf-8")
        return {
            "path": self._relative_label(path),
            "content": content[:max_chars],
            "truncated": len(content) > max_chars,
            "size_bytes": size,
            "sha256": self._hash_file(path),
        }

    def _inspect_path(self, relative: str) -> JsonValue:
        path = self._resolve(relative)
        if not path.exists():
            raise ProjectObserverBoundaryError("path does not exist")
        if path.is_dir():
            return {"path": self._relative_label(path), "type": "directory"}
        if not path.is_file():
            raise ProjectObserverBoundaryError("path type is not supported")
        size = path.stat().st_size
        if size > MAX_HASH_BYTES:
            raise ProjectObserverBoundaryError("file exceeds the inspection hash limit")
        return {
            "path": self._relative_label(path),
            "type": "file",
            "size_bytes": size,
            "sha256": self._hash_file(path),
        }

    def _resolve(self, relative: str) -> Path:
        normalized = relative.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if not normalized or pure.is_absolute() or ":" in normalized:
            raise ProjectObserverBoundaryError("path must be relative to the workspace")
        if any(part in {"", ".."} for part in pure.parts):
            raise ProjectObserverBoundaryError("path cannot escape the workspace")
        candidate = self.workspace_root.joinpath(*pure.parts)
        self._assert_path_boundary(candidate)
        return candidate.resolve(strict=True)

    def _assert_path_boundary(self, candidate: Path) -> None:
        current = self.workspace_root
        for part in candidate.relative_to(self.workspace_root).parts:
            current = current / part
            if self._blocked(current):
                raise ProjectObserverBoundaryError("path is protected from project observation")
            if current.exists() and current.is_symlink():
                raise ProjectObserverBoundaryError("symbolic links are outside the observer boundary")
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(self.workspace_root):
            raise ProjectObserverBoundaryError("path escapes the workspace")

    @staticmethod
    def _blocked(path: Path) -> bool:
        name = path.name.casefold()
        return (
            name in PROTECTED_PARTS
            or name in PROTECTED_NAMES
            or name.startswith(".env.")
            or path.suffix.casefold() in PROTECTED_SUFFIXES
        )

    def _relative_label(self, path: Path) -> str:
        relative = path.relative_to(self.workspace_root).as_posix()
        return relative or "."

    @staticmethod
    def _only_keys(inputs: dict[str, JsonValue], allowed: set[str]) -> None:
        unknown = set(inputs) - allowed
        if unknown:
            raise ProjectObserverBoundaryError("unexpected observer input")

    @staticmethod
    def _string(inputs: dict[str, JsonValue], key: str, *, default: str | None = None) -> str:
        value = inputs.get(key, default)
        if not isinstance(value, str) or not value or len(value) > 500:
            raise ProjectObserverBoundaryError(f"{key} must be a bounded string")
        return value

    @staticmethod
    def _integer(
        inputs: dict[str, JsonValue],
        key: str,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        value = inputs.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ProjectObserverBoundaryError(f"{key} is outside the allowed bounds")
        return value

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65_536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _evidence(operation: str, output: JsonValue) -> str:
        digest = hashlib.sha256(
            json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return f"project_observer:{operation}:{digest}"
