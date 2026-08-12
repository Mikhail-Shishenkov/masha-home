"""Closed ``masha://`` resource origin for the local desktop renderer."""

from __future__ import annotations

import mimetypes
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWebEngineCore import QWebEngineUrlScheme, QWebEngineUrlSchemeHandler


SOURCE_FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
INSTALLED_FRONTEND_ROOT = Path(sys.prefix) / "share" / "masha-home" / "frontend"


def _frontend_root() -> Path:
    """Resolve the production renderer without making it a backend package detail."""
    for candidate in (SOURCE_FRONTEND_ROOT, INSTALLED_FRONTEND_ROOT):
        resolved = candidate.resolve()
        if resolved.joinpath("index.html").is_file():
            return resolved
    return SOURCE_FRONTEND_ROOT.resolve()


FRONTEND_ROOT = _frontend_root()
SCHEME_NAME = b"masha"
HOME_HOST = "home"


class LocalOriginError(ValueError):
    """A request is not a safe bundled frontend resource."""


def build_masha_scheme() -> QWebEngineUrlScheme:
    scheme = QWebEngineUrlScheme(SCHEME_NAME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
    )
    return scheme


def register_masha_scheme() -> None:
    """Register before QApplication/QWebEngine construction; safe to call once per process."""
    if QWebEngineUrlScheme.schemeByName(SCHEME_NAME).name():
        return
    QWebEngineUrlScheme.registerScheme(build_masha_scheme())


def resolve_frontend_resource(path: str) -> Path:
    relative = path.lstrip("/") or "index.html"
    candidate = (FRONTEND_ROOT / relative).resolve()
    try:
        candidate.relative_to(FRONTEND_ROOT)
    except ValueError as error:
        raise LocalOriginError("resource escapes bundled frontend root") from error
    if not candidate.is_file():
        raise LocalOriginError("bundled frontend resource does not exist")
    return candidate


class MashaLocalResourceHandler(QWebEngineUrlSchemeHandler):
    """Serve only bundled renderer files; no filesystem passthrough."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._open_buffers: list[QBuffer] = []

    def requestStarted(self, job):  # noqa: N802 - Qt override
        url = job.requestUrl()
        if url.host() != HOME_HOST:
            job.fail(job.Error.UrlNotFound)
            return
        try:
            resource = resolve_frontend_resource(url.path())
        except LocalOriginError:
            job.fail(job.Error.UrlNotFound)
            return
        mime_type = (mimetypes.guess_type(resource.name)[0] or "application/octet-stream").encode("ascii")
        buffer = QBuffer(self)
        buffer.setData(resource.read_bytes())
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._open_buffers.append(buffer)
        job.reply(mime_type, buffer)
