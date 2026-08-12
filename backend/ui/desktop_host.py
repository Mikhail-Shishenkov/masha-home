"""PySide6 host for the offline-only Masha Home web renderer."""

from __future__ import annotations

import sys
from pathlib import Path

# Hardware compositing is the normal path: the Home scene is 4K bitmap-heavy
# and software Chromium compositing makes interaction visibly sluggish.  A
# user can still opt into the fallback for a known-bad graphics driver by
# setting MASHA_HOME_SOFTWARE_COMPOSITING=1 before launching the application.
import os

if os.environ.get("MASHA_HOME_SOFTWARE_COMPOSITING") == "1":
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--disable-gpu --disable-gpu-compositing",
    )

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import QApplication, QMainWindow

from backend.application import build_masha_application

from .conversation_bridge import LocalConversationBridge
from .local_origin import HOME_HOST, MashaLocalResourceHandler, SCHEME_NAME, register_masha_scheme


HOME_URL = QUrl("masha://home/index.html")
QWEBCHANNEL_SCRIPT_PATH = "/qtwebchannel/qwebchannel.js"


class LocalOnlyInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):  # noqa: N802 - Qt override
        url = info.requestUrl()
        info.block(not is_allowed_renderer_resource(url))


def is_allowed_renderer_resource(url: QUrl) -> bool:
    """Allow our bundled origin plus Qt's bundled WebChannel client only."""
    if url.scheme().encode("ascii") == SCHEME_NAME and url.host() == HOME_HOST:
        return True
    return url.scheme() == "qrc" and url.host() == "" and url.path() == QWEBCHANNEL_SCRIPT_PATH


class LocalOnlyPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):  # noqa: N802 - Qt override
        return url.scheme().encode("ascii") == SCHEME_NAME and url.host() == HOME_HOST

    def createWindow(self, window_type):  # noqa: N802 - Qt override
        return None


def configure_profile(parent) -> QWebEngineProfile:
    profile = QWebEngineProfile(parent)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    profile.setUrlRequestInterceptor(LocalOnlyInterceptor(profile))
    profile.installUrlSchemeHandler(SCHEME_NAME, MashaLocalResourceHandler(profile))
    settings = profile.settings()
    attributes = QWebEngineSettings.WebAttribute
    settings.setAttribute(attributes.LocalContentCanAccessRemoteUrls, False)
    settings.setAttribute(attributes.LocalContentCanAccessFileUrls, False)
    settings.setAttribute(attributes.DnsPrefetchEnabled, False)
    settings.setAttribute(attributes.WebGLEnabled, False)
    settings.setAttribute(attributes.PluginsEnabled, False)
    settings.setAttribute(attributes.LocalStorageEnabled, False)
    settings.setAttribute(attributes.FullScreenSupportEnabled, False)
    return profile


class MashaHomeWindow(QMainWindow):
    """Window/lifecycle owner with a one-way local application projection."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Masha Home")
        self.setMinimumSize(1000, 700)
        self.resize(1600, 960)
        self._profile = configure_profile(self)
        self._page = LocalOnlyPage(self._profile, self)
        self._application = self._build_application()
        self._bridge = LocalConversationBridge(self._application, self)
        self._channel = QWebChannel(self._page)
        self._channel.registerObject("mashaHome", self._bridge)
        self._page.setWebChannel(self._channel)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)
        self._view.setUrl(HOME_URL)

    @staticmethod
    def _build_application():
        """Keep a single local facade for this window's conversation session."""
        try:
            return build_masha_application(project_root=Path(__file__).resolve().parents[2])
        except Exception:
            # The shell still loads; LocalConversationBridge emits a controlled
            # unavailable state without exposing exception details or paths.
            return None

    def closeEvent(self, event):  # noqa: N802 - Qt override
        self._bridge.close()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    register_masha_scheme()
    app = QApplication(argv if argv is not None else sys.argv)
    window = MashaHomeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
