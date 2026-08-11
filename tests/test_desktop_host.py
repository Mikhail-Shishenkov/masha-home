import json
import time

from PySide6.QtCore import QCoreApplication, QUrl

from backend.ui.local_origin import FRONTEND_ROOT, LocalOriginError, build_masha_scheme, resolve_frontend_resource


def test_masha_scheme_is_secure_local_and_has_a_known_host_root():
    scheme = build_masha_scheme()
    assert bytes(scheme.name()) == b"masha"
    assert FRONTEND_ROOT.joinpath("index.html").is_file()


def test_local_origin_resolves_only_bundled_frontend_resources():
    assert resolve_frontend_resource("/index.html") == FRONTEND_ROOT / "index.html"
    assert resolve_frontend_resource("assets/canonical-master.png").is_file()
    assert resolve_frontend_resource("assets/conversation-candidate.png").is_file()
    assert resolve_frontend_resource("assets/thinking-candidate.png").is_file()
    assert resolve_frontend_resource("assets/activity-candidate.png").is_file()
    assert resolve_frontend_resource("assets/listening-v1.png").is_file()
    assert resolve_frontend_resource("assets/quiet-beside-v1.png").is_file()
    assert resolve_frontend_resource("assets/firm-disagreement-v1.png").is_file()


def test_local_origin_rejects_path_traversal_and_missing_resources():
    import pytest

    with pytest.raises(LocalOriginError):
        resolve_frontend_resource("../../local-data/masha-home.sqlite")
    with pytest.raises(LocalOriginError):
        resolve_frontend_resource("missing.html")


def test_desktop_host_allows_only_its_origin_and_bundled_webchannel_client():
    from backend.ui import desktop_host

    assert desktop_host.is_allowed_renderer_resource(QUrl("masha://home/index.html"))
    assert desktop_host.is_allowed_renderer_resource(QUrl("qrc:///qtwebchannel/qwebchannel.js"))
    assert not desktop_host.is_allowed_renderer_resource(QUrl("https://example.com/app.js"))
    assert not desktop_host.is_allowed_renderer_resource(QUrl("file:///C:/masha-home/local-data/memory/masha.sqlite3"))


def test_local_conversation_bridge_serializes_one_real_isolated_turn(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider(response_text="Привет из локального bridge.")]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))

    bridge.loadInitialState()
    bridge.startNewConversation()
    bridge.submitMessage("Привет")
    bridge.submitMessage("Второе сообщение не должно уйти")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "turn_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    bridge.close()

    assert events[0]["kind"] == "home_initial"
    assert any(item["kind"] == "conversation_started" for item in events)
    assert [item["kind"] for item in events].count("turn_started") == 1
    thinking = next(item for item in events if item["kind"] == "turn_thinking")
    assert thinking["snapshot"]["presentation"]["presence"]["activity"] == "processing"
    assert any(item["kind"] == "turn_rejected" for item in events)
    result = next(item for item in events if item["kind"] == "turn_result")
    assert result["result"]["status"] == "completed"
    assert result["result"]["assistant_message"]["content"] == "Привет из локального bridge."
    assert result["snapshot"]["presentation"]["presence"]["activity"] == "speaking"

    bridge.loadRecentConversations()
    recent = next(item for item in events if item["kind"] == "recent_conversations")
    assert recent["recent"][0]["conversation_id"] == result["result"]["conversation_id"]
    bridge.openConversation(result["result"]["conversation_id"])
    assert any(item["kind"] == "conversation_opened" for item in events)
