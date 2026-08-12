import json
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QMetaMethod, QUrl

from backend.ui.local_origin import FRONTEND_ROOT, LocalOriginError, build_masha_scheme, resolve_frontend_resource


def test_masha_scheme_is_secure_local_and_has_a_known_host_root():
    scheme = build_masha_scheme()
    assert bytes(scheme.name()) == b"masha"
    assert FRONTEND_ROOT == Path(__file__).resolve().parents[1] / "frontend"
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


def test_production_frontend_keeps_desktop_composition_and_accessibility_contracts():
    html = FRONTEND_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    css = FRONTEND_ROOT.joinpath("styles", "home.css").read_text(encoding="utf-8")

    assert "home-attention-trigger" in html
    assert "safety-trigger" in html
    assert "recent-conversations" in html
    assert "dashboard" not in html.lower()
    assert "sidebar" not in html.lower()
    assert "Дом Маши · локально" not in html
    assert 'class="runtime-truth"' not in html
    assert "@media (max-width: 1280px)" in css
    assert "@media (max-width: 1000px)" in css
    assert "@media (max-width: 780px)" in css
    assert "prefers-reduced-motion: reduce" in css
    assert ".safety-overlay" in css and "pointer-events: none" in css
    assert ".conversation-surface:not(.has-conversations) .surface-actions" in css
    assert "html, body { width: 100%; height: 100%; overflow: hidden; }" in css
    assert "max-height: 112px" in css
    assert "resize: none" in css
    assert "textarea::-webkit-resizer { display: none; }" in css
    assert 'event.key !== "Enter" || event.shiftKey || event.isComposing' in FRONTEND_ROOT.joinpath(
        "renderer", "app.js"
    ).read_text(encoding="utf-8")
    app_source = FRONTEND_ROOT.joinpath("renderer", "app.js").read_text(encoding="utf-8")
    assert "sceneTransitionRevision" in app_source
    assert "clearTimeout(sceneTransitionTimer)" in app_source
    assert 'window.addEventListener("blur", closeTemporarySurfaces)' in app_source
    scene_map = FRONTEND_ROOT.joinpath("scenes", "scene-map.js").read_text(encoding="utf-8")
    assert "TRANSITION_POLICY" in scene_map
    assert 'durationMs: 520' in scene_map
    assert 'durationMs: 300' in scene_map
    assert 'durationMs: 1' in scene_map


def test_webchannel_bridge_exposes_only_typed_allowlisted_slots():
    from backend.ui.conversation_bridge import LocalConversationBridge

    bridge = LocalConversationBridge(None)
    meta = bridge.metaObject()
    slots = {
        bytes(meta.method(index).methodSignature()).decode().split("(", 1)[0]
        for index in range(meta.methodOffset(), meta.methodCount())
        if meta.method(index).methodType() is QMetaMethod.MethodType.Slot
    }
    assert slots == {
        "loadInitialState",
        "loadRecentConversations",
        "loadHomeAttention",
        "engageEmergencyStop",
        "resumeAutonomy",
        "openConversation",
        "startNewConversation",
        "submitMessage",
    }
    bridge.close()


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

    bridge.loadHomeAttention()
    attention = next(item for item in events if item["kind"] == "home_attention")
    assert attention["attention"]["active_conversation"]["conversation_id"] == result["result"]["conversation_id"]
    assert set(attention["attention"]) == {
        "observed_at",
        "active_conversation",
        "model_available",
        "model_label",
        "emergency_stop_engaged",
        "safety_label",
    }

    bridge.engageEmergencyStop()
    stopped = [item for item in events if item["kind"] == "safety_changed"][-1]
    assert stopped["safety"]["emergency_stop_engaged"] is True
    assert stopped["snapshot"]["presentation"]["overlays"]["safety"] == "autonomy_stopped"

    bridge.resumeAutonomy()
    resumed = [item for item in events if item["kind"] == "safety_changed"][-1]
    assert resumed["safety"]["emergency_stop_engaged"] is False
    assert resumed["snapshot"]["presentation"]["overlays"]["safety"] == "autonomy_active"
    bridge.close()


def test_unavailable_model_never_emits_a_fake_thinking_state(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    application = build_masha_application(
        project_root=_isolated_root(tmp_path),
        router=ModelRouter([LocalProfileProvider(available=False)]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))

    bridge.loadInitialState()
    bridge.submitMessage("Ты здесь?")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "turn_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert not any(item["kind"] == "turn_thinking" for item in events)
    result = next(item for item in events if item["kind"] == "turn_result")
    assert result["result"]["status"] == "model_unavailable"
    assert result["snapshot"]["presentation"]["presence"]["activity"] not in {
        "processing",
        "speaking",
    }
    assert result["snapshot"]["presentation"]["overlays"]["model"] == "model_unavailable"
    bridge.close()
