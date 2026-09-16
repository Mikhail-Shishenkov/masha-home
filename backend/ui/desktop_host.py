"""PySide6 host for the offline-only Masha Home web renderer."""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Callable

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

from PySide6.QtCore import QObject, QTemporaryFile, QTimer, QUrl, Slot
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
from backend.runtime.runtime_lease import RuntimeLease

from .conversation_bridge import LocalConversationBridge
from .local_origin import HOME_HOST, MashaLocalResourceHandler, SCHEME_NAME, register_masha_scheme


HOME_URL = QUrl("masha://home/index.html")
QWEBCHANNEL_SCRIPT_PATH = "/qtwebchannel/qwebchannel.js"
REMINDER_CUE_HISTORY_LIMIT = 256


class ReminderCuePlayer(QObject):
    """One bounded three-chime sequence per newly projected receipt."""

    def __init__(
        self,
        parent=None,
        *,
        cue: Callable[[], None] | None = None,
        history_limit: int = REMINDER_CUE_HISTORY_LIMIT,
    ):
        super().__init__(parent)
        self._effect = None
        self._audio_file = None
        self._cue = cue or self._home_cue
        self._history_limit = max(1, history_limit)
        self._played_order: deque[str] = deque()
        self._played_ids: set[str] = set()
        self._active_id: str | None = None
        self._remaining = 0
        self._repeat = QTimer(self)
        self._repeat.setInterval(4_000)
        self._repeat.timeout.connect(self._pulse)

    @Slot(str)
    def play_once(self, interaction_id: str) -> bool:
        """Return whether this receipt caused a cue; failures never replay it."""
        if not interaction_id or interaction_id in self._played_ids:
            return False
        self._remember(interaction_id)
        self.stop()
        self._active_id = interaction_id
        self._remaining = 3
        self._pulse()
        if self._remaining:
            self._repeat.start()
        return True

    def _pulse(self) -> None:
        if self._remaining <= 0:
            return
        self._remaining -= 1
        try:
            self._cue()
        except Exception:
            # A missing/disabled audio device must not break Home delivery.
            pass
        if not self._remaining:
            self._repeat.stop()

    @Slot(str)
    def stop(self, interaction_id: str = "") -> None:
        if interaction_id and interaction_id != self._active_id:
            return
        self._repeat.stop()
        self._remaining = 0
        self._active_id = None
        if self._effect is not None:
            self._effect.stop()

    def _home_cue(self) -> None:
        try:
            from PySide6.QtMultimedia import QSoundEffect
            from .reminder_audio import home_chime_wav
            if self._effect is None:
                audio_file = QTemporaryFile(self)
                if not audio_file.open():
                    raise OSError("temporary audio unavailable")
                audio_file.write(home_chime_wav())
                audio_file.flush()
                audio_file.close()
                self._audio_file = audio_file
                self._effect = QSoundEffect(self)
                self._effect.setVolume(0.65)
                self._effect.setLoopCount(1)
                self._effect.setSource(QUrl.fromLocalFile(audio_file.fileName()))
            if self._effect.status() == QSoundEffect.Status.Error:
                self._qt_system_cue()
            else:
                self._effect.play()
        except (ImportError, OSError, RuntimeError):
            self._qt_system_cue()

    def _remember(self, interaction_id: str) -> None:
        if len(self._played_order) >= self._history_limit:
            oldest = self._played_order.popleft()
            self._played_ids.discard(oldest)
        self._played_order.append(interaction_id)
        self._played_ids.add(interaction_id)

    @staticmethod
    def _qt_system_cue() -> None:
        application = QApplication.instance()
        if application is not None:
            application.beep()


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
        self._reminder_cue = ReminderCuePlayer(self)
        self._bridge.reminderDelivery.connect(self._reminder_cue.play_once)
        self._bridge.reminderQuiet.connect(self._reminder_cue.stop)
        self._channel = QWebChannel(self._page)
        self._channel.registerObject("mashaHome", self._bridge)
        self._page.setWebChannel(self._channel)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)
        self._view.setUrl(HOME_URL)
        # The proactive runtime persists delivery independently.  This bounded
        # read-only heartbeat lets an already open Home observe it without a
        # refresh or click; event_id deduplication lives in the bridge/store.
        self._proactive_projection_timer = QTimer(self)
        self._proactive_projection_timer.setInterval(2_000)
        self._proactive_projection_timer.timeout.connect(
            self._bridge.refreshProactiveInteractions
        )
        self._proactive_projection_timer.start()
        # Home time has a much slower cadence than proactive delivery.
        # It only keeps the Presentation clock current so day/evening ambience
        # can change while the Home is open and otherwise idle.
        self._home_time_timer = QTimer(self)
        self._home_time_timer.setInterval(30_000)
        self._home_time_timer.timeout.connect(
            self._bridge.refreshHomeTime
        )
        self._home_time_timer.start()

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
        self._reminder_cue.stop()
        self._bridge.close()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    lease = RuntimeLease(Path(__file__).resolve().parents[2])
    lease.acquire()
    try:
        register_masha_scheme()
        app = QApplication(argv if argv is not None else sys.argv)
        window = MashaHomeWindow()
        window.show()
        return app.exec()
    finally:
        lease.release()


if __name__ == "__main__":
    raise SystemExit(main())
