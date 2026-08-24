import json
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QMetaMethod, QUrl
from PySide6.QtWebEngineCore import QWebEngineUrlScheme

from backend.ui.local_origin import FRONTEND_ROOT, LocalOriginError, build_masha_scheme, resolve_frontend_resource


def test_masha_scheme_is_secure_local_and_has_a_known_host_root():
    scheme = build_masha_scheme()
    assert bytes(scheme.name()) == b"masha"
    assert scheme.syntax() == QWebEngineUrlScheme.Syntax.Host
    assert FRONTEND_ROOT == Path(__file__).resolve().parents[1] / "frontend"
    assert FRONTEND_ROOT.joinpath("index.html").is_file()


def test_local_origin_resolves_only_bundled_frontend_resources():
    assert resolve_frontend_resource("/index.html") == FRONTEND_ROOT / "index.html"
    assert resolve_frontend_resource("assets/presence/day/idle.png").is_file()
    assert resolve_frontend_resource("assets/presence/day/conversation.png").is_file()
    assert resolve_frontend_resource("assets/presence/evening/idle.png").is_file()
    assert resolve_frontend_resource("assets/presence/evening/thinking.png").is_file()
    assert resolve_frontend_resource("assets/presence/evening/special-cozy-wide.png").is_file()
    assert resolve_frontend_resource("assets/presence/context/boundary-calm.png").is_file()


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
    assert "load-more-conversations" in html
    assert "renderer/interaction-safety.js" in html
    assert "operation-surface" in html
    assert "commitments-trigger" in html
    assert "commitments-surface" in html
    assert "load-more-commitments" in html
    assert "activity-trigger" in html
    assert "activity-surface" in html
    assert "proactive-trigger" in html
    assert "proactive-surface" in html
    assert "continuity-trigger" in html
    assert "continuity-surface" in html
    assert "reflections-trigger" in html
    assert "reflections-surface" in html
    assert "workbench-trigger" in html
    assert "Уголок" in html
    assert "Рабочий уголок" in html
    assert "confirm-operation" in html
    assert "reject-operation" in html
    assert "dashboard" not in html.lower()
    assert "sidebar" not in html.lower()
    assert "Дом Маши · локально" not in html
    assert 'class="runtime-truth"' not in html
    assert "@media (max-width: 1280px)" in css
    assert "height: min(72vh, 740px)" in css
    assert ".recent-conversations { position: absolute; top: 52px; right: 0; bottom: 0; left: 0" in css
    assert "max-height: min(52vh, 460px)" not in css
    assert "border-bottom: 1px solid rgba(226,188,126,.2)" in css
    assert "@media (max-width: 1000px)" in css
    assert "@media (max-width: 780px)" in css
    assert "prefers-reduced-motion: reduce" in css
    assert ".safety-overlay" in css and "pointer-events: none" in css
    assert ".operation-surface" in css
    assert ".commitments-surface" in css
    assert ".activity-surface" in css
    assert ".proactive-surface" in css
    assert ".continuity-surface" in css
    assert ".reflections-surface" in css
    assert ".workbench-surface" in css
    assert ".is-surface-leaving" in css
    assert "surface-content-appear" in css
    assert ".conversation-surface:not(.has-conversations) .recent-conversations-toggle" in css
    assert ".conversation-surface:not(.has-conversations) .new-conversation" in css
    assert "html, body { width: 100%; height: 100%; overflow: hidden; }" in css
    assert "max-height: 112px" in css
    assert "resize: none" in css
    assert "textarea::-webkit-resizer { display: none; }" in css
    assert "overflow-y: auto" in css
    assert "scrollbar-width: thin" in css
    assert "overscroll-behavior: contain" in css
    assert ".recent-conversations" in css and "overflow-y: auto" in css
    assert 'event.key !== "Enter" || event.shiftKey || event.isComposing' in FRONTEND_ROOT.joinpath(
        "renderer", "app.js"
    ).read_text(encoding="utf-8")
    app_source = FRONTEND_ROOT.joinpath("renderer", "app.js").read_text(encoding="utf-8")
    assert "sceneTransitionRevision" in app_source
    assert "clearTimeout(sceneTransitionTimer)" in app_source
    assert 'window.addEventListener("blur", closeTemporarySurfaces)' not in app_source
    assert "bridge.loadWorkbench()" in app_source
    assert "bridge.loadMoreConversations(offset)" in app_source
    assert "loadMoreConversations.hidden = !page?.has_more" in app_source
    assert "interactionSafety.preserveComposer" in app_source
    assert "interactionSafety.isBackgroundProactiveProjection" in app_source
    assert app_source.count('input.value = "";') == 1
    assert "bridge.loadMoreCommitments(offset)" in app_source
    assert "bridge.useModelProfile(profile.profile_id)" in app_source
    assert "transitionToSurface" in app_source
    assert "humanizeContinuityText" not in app_source
    assert "memory_schema.json" not in app_source
    assert "add-shared-moment" in html
    assert "add-continuity-thread" in html
    assert "forgotten-search-toggle" in html
    assert "renderer/candidate-presentation.js" in html
    assert "renderer/exclusive-view-transition.js" in html
    assert "continuityTrigger.hidden = false" in app_source
    assert "surface.hidden = true" in app_source
    assert 'bridge.resolveConfirmation(pendingConfirmation.proposal_id, "confirm")' in app_source
    assert 'bridge.resolveConfirmation(pendingConfirmation.proposal_id, "reject")' in app_source
    assert "delayMs: 1200" in app_source
    assert "candidatePresentation.defer()" in app_source
    assert "historyViewTransition.show" in app_source
    assert "view?.confirmed_memories" not in app_source
    assert "bridge.searchInformation(query, historySearchScope, historySearchForgotten)" in app_source
    scene_map = FRONTEND_ROOT.joinpath("scenes", "scene-map.js").read_text(encoding="utf-8")
    assert "TRANSITION_POLICY" in scene_map
    assert 'enterMs: 330' in scene_map
    assert 'enterMs: 220' in scene_map
    assert 'enterMs: 1' in scene_map
    assert "minimumHoldMs" in scene_map
    assert "settleMs" in scene_map


def test_desktop_host_keeps_hardware_compositing_by_default_with_an_explicit_fallback():
    import os
    from backend.ui import desktop_host

    assert "MASHA_HOME_SOFTWARE_COMPOSITING" in desktop_host.__doc__ or "MASHA_HOME_SOFTWARE_COMPOSITING" in open(desktop_host.__file__, encoding="utf-8").read()
    assert os.environ.get("QT_OPENGL") != "software"
    assert "backdrop-filter" not in FRONTEND_ROOT.joinpath("styles", "home.css").read_text(encoding="utf-8")


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
        "loadMoreConversations",
            "loadHomeAttention",
            "resolveHomeAttentionProactive",
        "loadCommitments",
        "loadMoreCommitments",
        "loadAgentRuns",
            "loadProactiveInteractions",
            "refreshProactiveInteractions",
            "recordReminderPresented",
            "resolveProactiveInteraction",
        "loadSharedContinuity",
        "activateContinuityThread",
        "clearContinuityThread",
        "continueContinuityThread",
        "searchInformation",
        "clearInformationSearch",
        "restoreInformation",
        "resolveMemoryCandidate",
        "loadReflectionWorkspace",
        "resolveReflection",
        "resolveHonestHelp",
        "loadWorkbench",
        "useModelProfile",
        "chooseSkillPackage",
        "resolveSkillInstall",
        "engageEmergencyStop",
        "resumeAutonomy",
        "setSpecialEvening",
        "advanceSpecialEveningProximity",
        "settleAssistantPresence",
        "refreshHomeTime",
        "openConversation",
        "openObservationSource",
        "startNewConversation",
        "submitMessage",
        "chooseLocalDocument",
        "clearLocalDocument",
        "submitMessageWithDocument",
        "proposeCommitmentCancellation",
        "proposeCommitmentClearDue",
        "proposeCommitmentCompletion",
        "proposeCommitmentReschedule",
        "resolveConfirmation",
    }
    bridge.close()


def test_human_search_projects_forgotten_memory_and_restores_via_typed_confirmation(
    tmp_path,
    monkeypatch,
):
    from backend.application import RecallMode, build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.memory_models import MemoryDocument
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.human_information_fixture import FORGOTTEN_MAC_ID, human_information_document
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    repository.replace_document(
        MemoryDocument.model_validate(human_information_document()),
        action="test_home_human_search",
    )
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider(response_text="Я рядом.")]),
    )
    turn = application.send_message("Привет", project_id="project_masha_home")
    assert turn.conversation_id is not None
    requested_modes = []
    real_search = application.search_information

    def observed_search(request):
        requested_modes.append(request.mode)
        return real_search(request)

    monkeypatch.setattr(application, "search_information", observed_search)

    bridge = LocalConversationBridge(application)
    emitted: list[dict] = []
    bridge.event.connect(lambda encoded: emitted.append(json.loads(encoded)))
    bridge.loadInitialState()
    bridge.searchInformation("забытая цена MacBook", "history", False)

    normal_search = next(item for item in emitted if item["kind"] == "human_search_loaded")
    assert requested_modes == [RecallMode.RETROSPECTIVE]
    assert all(item["availability"] != "forgotten" for item in normal_search["items"])
    assert all(item["can_restore"] is False for item in normal_search["items"])

    requested_modes.clear()
    bridge.searchInformation("забытая цена MacBook", "history", True)

    search = [item for item in emitted if item["kind"] == "human_search_loaded"][-1]
    assert requested_modes == [RecallMode.FORGOTTEN_REVIEW]
    assert search["forgotten"] is True
    forgotten = next(item for item in search["items"] if item["availability"] == "forgotten")
    assert forgotten["can_restore"] is True
    assert forgotten["reference"].startswith("result-")
    assert FORGOTTEN_MAC_ID not in json.dumps(search, ensure_ascii=False)

    bridge.restoreInformation(forgotten["reference"])
    proposed = next(item for item in emitted if item["kind"] == "memory_restore_proposed")
    pending = proposed["pending_confirmation"]
    assert pending["confirmation_type"] == "memory_restore"
    assert FORGOTTEN_MAC_ID not in json.dumps(proposed, ensure_ascii=False)

    bridge.resolveConfirmation(pending["proposal_id"], "confirm")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "confirmation_result" for item in emitted) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    resolved = next(item for item in emitted if item["kind"] == "confirmation_result")
    assert resolved["result"]["status"] == "confirmed"
    restored = next(item for item in repository.read_document().facts if item.id == FORGOTTEN_MAC_ID)
    assert restored.visibility.value == "visible"
    bridge.close()


def test_ui_search_order_registers_the_existing_presented_entity_truth(
    tmp_path,
    monkeypatch,
):
    from backend.application import build_masha_application
    from backend.application.human_information import (
        HumanSearchRequest,
        HumanSearchResult,
        RecallMode,
    )
    from backend.llm.model_router import ModelRouter
    from backend.memory.memory_models import MemoryDocument
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.human_information_fixture import (
        ACTIVE_MAC_ID,
        COMPLETED_MAC_TASK_ID,
        RESOLVED_THREAD_ID,
        human_information_document,
    )
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    repository.replace_document(
        MemoryDocument.model_validate(human_information_document()),
        action="test_ui_presented_order",
    )
    provider = LocalProfileProvider(response_text="Этот ответ не должен понадобиться.")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )
    initial = application.send_message(
        "Что ты помнишь про MacBook?",
        project_id="project_masha_home",
    )
    conversation_id = initial.conversation_id
    assert conversation_id is not None and provider.last_request is None

    request = HumanSearchRequest(
        query="",
        project_id="project_masha_home",
        mode=RecallMode.RETROSPECTIVE,
        limit=100,
    )
    available = application.search_information(request)
    by_id = {match.item.ref.entity_id: match for match in available.matches}
    expected_ids = (RESOLVED_THREAD_ID, ACTIVE_MAC_ID, COMPLETED_MAC_TASK_ID)
    ordered = HumanSearchResult(
        request=request,
        matches=tuple(by_id[entity_id] for entity_id in expected_ids),
    )
    selected_result = {"value": ordered}
    monkeypatch.setattr(
        application,
        "search_information",
        lambda _request: selected_result["value"],
    )

    bridge = LocalConversationBridge(application)
    emitted: list[dict] = []
    bridge.event.connect(lambda encoded: emitted.append(json.loads(encoded)))
    bridge.loadInitialState()
    bridge.searchInformation("дом", "all", False)

    search = next(item for item in emitted if item["kind"] == "human_search_loaded")
    presented = application.presented_information(conversation_id)
    assert presented is not None
    assert tuple(item.ordinal for item in presented.items) == (1, 2, 3)
    assert tuple(item.entity_id for item in presented.items) == expected_ids
    assert tuple(item["label"] for item in search["items"]) == tuple(
        item.human_label for item in presented.items
    )

    selected_result["value"] = ordered.model_copy(
        update={"matches": tuple(reversed(ordered.matches))},
    )
    bridge.searchInformation("другой запрос", "all", False)
    replaced = application.presented_information(conversation_id)
    assert replaced is not None
    assert tuple(item.entity_id for item in replaced.items) == tuple(reversed(expected_ids))

    selected_result["value"] = ordered
    bridge.searchInformation("дом", "all", False)
    presented = application.presented_information(conversation_id)
    assert presented is not None

    bridge.submitMessage("что было в первой?")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "turn_result" for item in emitted) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    turn = next(item for item in emitted if item["kind"] == "turn_result")
    answer = turn["result"]["assistant_message"]["content"]
    assert presented.items[0].human_label in answer
    assert presented.items[1].human_label not in answer
    assert presented.items[2].human_label not in answer
    assert provider.last_request is None

    bridge.clearInformationSearch()
    assert application.presented_information(conversation_id) is None
    bridge.searchInformation("дом", "all", False)
    assert application.presented_information(conversation_id) is not None
    bridge.startNewConversation()
    assert application.presented_information(conversation_id) is None
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
    assert recent["recent"]["items"][0]["conversation_id"] == result["result"]["conversation_id"]
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
        "commitments_count",
        "overdue_commitments_count",
        "stale_overdue_commitments_count",
        "upcoming_commitments_count",
        "unscheduled_commitments_count",
        "pending_interactions_count",
        "attention_items",
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


def test_static_home_surfaces_keep_attention_actions_and_connection_shelf_human():
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    renderer = (root / "frontend" / "renderer" / "app.js").read_text(encoding="utf-8")
    assert "Что подключено" in html and "workbench-connections" in html
    assert "resolveHomeAttentionProactive" in renderer
    styles = (root / "frontend" / "styles" / "home.css").read_text(encoding="utf-8")
    assert "Понял" in renderer and "Убрать" in renderer
    assert "просроченное дело" in renderer and "свежая просрочка" not in renderer
    assert "showReminderToast" in renderer and "playReminderCueOnce" in renderer
    assert "formatDueAt(reminder.due_at)" in renderer
    assert "recordReminderPresented" in renderer
    assert 'id="reminder-toast"' in html and 'aria-live="polite"' in html
    assert 'data-attention-level="quiet"' in styles and "animation: none" in styles

def test_desktop_bridge_loads_bounded_memory_and_continuity_without_mutation(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))

    bridge.loadInitialState()
    bridge.loadSharedContinuity()

    loaded = next(item for item in events if item["kind"] == "shared_continuity_loaded")
    assert loaded["continuity"]["confirmed_memories"] == []
    assert loaded["continuity"]["moments"] == []
    assert loaded["continuity"]["open_threads"] == []
    encoded = json.dumps(loaded, ensure_ascii=False)
    assert "audit_events" not in encoded
    assert "identity_version" not in encoded
    assert "source_memory_ids" not in encoded
    assert loaded["snapshot"]["composition"]["primary_surface_id"] == "home.continuity"
    assert repository.read_document() == before
    bridge.close()


def test_desktop_bridge_projects_workbench_and_switches_only_available_profile(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))

    bridge.loadInitialState()
    bridge.loadWorkbench()
    loaded = next(item for item in events if item["kind"] == "workbench_loaded")
    fast = next(item for item in loaded["workbench"]["profiles"] if item["profile_id"] == "fast")
    assert [item["connector_id"] for item in loaded["workbench"]["connections"]] == [
        "google-calendar", "google-drive", "yandex-mail", "yandex-disk",
    ]
    assert {item["access"] for item in loaded["workbench"]["connections"]} == {"read_only"}
    assert "grant_id" not in json.dumps(loaded, ensure_ascii=False)
    assert "secret_ref" not in json.dumps(loaded, ensure_ascii=False)
    assert "local-data" not in json.dumps(loaded, ensure_ascii=False)
    assert loaded["snapshot"]["composition"]["primary_surface_id"] == "home.workbench"

    bridge.useModelProfile(fast["profile_id"])

    applied = next(item for item in events if item["kind"] == "model_switch_applied")
    assert applied["result"]["active_profile"]["profile_id"] == "fast"


def test_desktop_bridge_fact_confirmation_and_restart_use_real_application_result(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    root = _isolated_root(tmp_path)
    application = build_masha_application(project_root=root, router=ModelRouter([LocalProfileProvider()]))
    bridge = LocalConversationBridge(application)
    events = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))
    bridge.loadInitialState()
    bridge.submitMessage("Запомни, что bridge-факт — настоящий")
    deadline = time.monotonic() + 2
    while not any(item["kind"] == "turn_result" for item in events) and time.monotonic() < deadline:
        QCoreApplication.processEvents()
    turn = next(item for item in events if item["kind"] == "turn_result")["result"]
    assert turn["pending_confirmation"]["confirmation_type"] == "memory_create"
    bridge.resolveConfirmation(turn["pending_confirmation"]["proposal_id"], "confirm")
    deadline = time.monotonic() + 2
    while not any(item["kind"] == "confirmation_result" for item in events) and time.monotonic() < deadline:
        QCoreApplication.processEvents()
    assert next(item for item in events if item["kind"] == "confirmation_result")["result"]["status"] == "confirmed"

    restarted = build_masha_application(project_root=root, router=ModelRouter([LocalProfileProvider()]))
    read = restarted.send_message("Что ты обо мне помнишь?", project_id="project_masha_home")
    assert "bridge-факт" in read.assistant_message.content
    bridge.close()


def test_desktop_emergency_stop_blocks_reflection_and_honest_help_actions(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.reflection import ReflectionScope
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    provider = LocalProfileProvider(
        response_text=json.dumps(
            {
                "text": "Мы лучше двигаемся, когда спорим честно.",
                "meaning": "Согласие не важнее ясности.",
                "confidence": 0.8,
                "importance": 0.7,
                "help_offer": {
                    "observation": "Задача выглядит слишком широкой.",
                    "offer": "Могу помочь выделить первый проверяемый шаг.",
                    "expected_benefit": "Появится ясная точка начала.",
                    "why_now": "Тема уже находится в разговоре.",
                    "capability": "conversation",
                },
            },
            ensure_ascii=False,
        )
    )
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )
    conversation = application._conversation._conversation.history.create()  # noqa: SLF001
    application._reflections._reflections.reflect(  # noqa: SLF001
        scope=ReflectionScope.SHARED,
        topic="как мы решаем сложные задачи",
        project_id="project_masha_home",
        conversation_id=conversation.id,
        evidence_message_ids=("message-test",),
        conversation_messages=(),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))

    bridge.loadInitialState()
    bridge.loadReflectionWorkspace()
    workspace = next(item for item in events if item["kind"] == "reflection_workspace_loaded")["workspace"]
    reflection_id = workspace["pending"][0]["candidate_id"]

    bridge.engageEmergencyStop()
    bridge.resolveReflection(reflection_id, "adopt")

    # Prepare an already-approved offer through the domain service; the UI action
    # itself remains blocked by the still-engaged persistent Emergency Stop.
    application._reflections._reflections.adopt(reflection_id)  # noqa: SLF001
    help_id = application.reflection_workspace().help_offers[0].candidate_id
    before = repository.read_document()
    bridge.resolveHonestHelp(help_id, "accept")

    rejected = [item for item in events if item["kind"] in {"reflection_resolution_rejected", "honest_help_rejected"}]
    assert {item["kind"] for item in rejected} == {
        "reflection_resolution_rejected",
        "honest_help_rejected",
    }
    assert all(item["reason"] == "safety_stop" for item in rejected)
    assert repository.read_document() == before
    assert application.reflection_workspace().pending == ()
    assert len(application.reflection_workspace().help_offers) == 1
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


def test_desktop_bridge_commitment_confirmation_has_real_activity_and_result(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))

    bridge.loadInitialState()
    bridge.submitMessage("Маша, запомни, что завтра в 18:00 нужно отправить отчёт")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "turn_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    proposal_result = next(item for item in events if item["kind"] == "turn_result")
    pending = proposal_result["result"]["pending_confirmation"]
    assert pending["confirmation_type"] == "commitment_create"
    assert pending["proposal_id"] not in proposal_result["result"]["assistant_message"]["content"]
    assert proposal_result["snapshot"]["presentation"]["presence"]["activity"] == "confirmation"
    assert proposal_result["snapshot"]["composition"]["primary_surface_id"] == "confirmation.commitment"

    bridge.engageEmergencyStop()
    bridge.resolveConfirmation(pending["proposal_id"], "confirm")
    stopped_resolution = [item for item in events if item["kind"] == "confirmation_rejected"][-1]
    assert stopped_resolution["reason"] == "safety_stop"
    assert application.pending_confirmation(proposal_result["result"]["conversation_id"]) is not None
    assert not any(item.text == "отправить отчёт" for item in repository.read_document().commitments)
    bridge.resumeAutonomy()

    bridge.resolveConfirmation(pending["proposal_id"], "confirm")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "confirmation_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    started = next(item for item in events if item["kind"] == "confirmation_started")
    assert started["snapshot"]["presentation"]["presence"]["activity"] == "working"
    resolved = next(item for item in events if item["kind"] == "confirmation_result")
    assert resolved["result"]["status"] == "confirmed"
    assert resolved["snapshot"]["presentation"]["activities"][0]["state"] == "completed"
    assert any(item.text == "отправить отчёт" for item in repository.read_document().commitments)
    bridge.close()


def test_desktop_bridge_projects_commitments_and_requires_confirmation_for_completion(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.memory_models import CommitmentStatus
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    before = repository.read_document()
    commitment = before.commitments[0]
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))

    bridge.loadInitialState()
    bridge.loadCommitments()
    loaded = next(item for item in events if item["kind"] == "commitments_loaded")
    visible = loaded["commitments"]["items"]
    selected = next(item for item in visible if item["commitment_id"] == commitment.id)
    assert selected["can_propose_completion"] is True
    assert loaded["snapshot"]["composition"]["primary_surface_id"] == "home.commitments"
    assert repository.read_document() == before

    bridge.proposeCommitmentCompletion(commitment.id)
    proposed = next(item for item in events if item["kind"] == "commitment_completion_proposed")
    pending = proposed["result"]["pending_confirmation"]
    assert pending["confirmation_type"] == "commitment_complete"
    assert pending["proposal_id"] not in proposed["result"]["assistant_message"]["content"]
    assert repository.read_document() == before

    bridge.resolveConfirmation(pending["proposal_id"], "confirm")
    deadline = time.monotonic() + 3
    while len([item for item in events if item["kind"] == "confirmation_result"]) < 1 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    resolved = next(item for item in events if item["kind"] == "confirmation_result")
    assert resolved["result"]["status"] == "confirmed"
    updated = next(item for item in repository.read_document().commitments if item.id == commitment.id)
    assert updated.status is CommitmentStatus.COMPLETED
    bridge.close()


def test_desktop_bridge_projects_agent_receipts_and_delivered_checkin(tmp_path):
    from datetime import datetime, timedelta, timezone

    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.skills.agent_loop import (
        AgentRunReceipt,
        AgentRunStatus,
        AgentRunStore,
        AgentStepReceipt,
        AgentStepStatus,
    )
    from backend.skills.autonomy import ActionDecision
    from backend.temporal.proactive_events import (
        ProactiveEvent,
        ProactiveEventState,
        ProactiveEventStore,
        ProactiveEventType,
        check_in_event_id,
    )
    from backend.temporal.proactive_interaction import ProactiveInteractionStore
    from backend.temporal.temporal_models import CheckInCandidate
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    memory_before = repository.read_document()
    now = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
    AgentRunStore(root / "local-data" / "runtime" / "agent-runs.json").save(
        AgentRunReceipt(
            plan_id="plan_bridge_activity",
            plan_sha256="b" * 64,
            goal="Проверить локальный документ",
            status=AgentRunStatus.COMPLETED,
            started_at=now,
            updated_at=now,
            finished_at=now,
            steps=(
                AgentStepReceipt(
                    step_id="step_check",
                    title="Проверить результат",
                    tool_id="private_tool",
                    operation="inspect",
                    status=AgentStepStatus.VERIFIED,
                    policy_decision=ActionDecision.ALLOW,
                    policy_reason="private_reason",
                    started_at=now,
                    finished_at=now,
                    result_summary="Проверено локально",
                ),
            ),
        )
    )
    event_id = check_in_event_id("bridge-anchor")
    proactive_events = ProactiveEventStore(repository)
    proactive_events.create(
        ProactiveEvent(
            event_id=event_id,
            event_type=ProactiveEventType.CHECK_IN,
            source_type="absence",
            source_id="bridge-anchor",
            created_at=now,
            detected_at=now,
            payload={
                "absence_seconds": 3_600,
                "anchor_created_at": (now - timedelta(hours=1)).isoformat(),
            },
        )
    )
    proactive_events.update_state(event_id, ProactiveEventState.CANDIDATE, now)
    interactions = ProactiveInteractionStore(repository)
    interactions.ensure_candidate(
        CheckInCandidate(
            event_id=event_id,
            absence_duration_seconds=3_600,
            last_message_at=now - timedelta(hours=1),
            current_local_time=now,
            proactive_level=2,
        )
    )
    interactions.mark_delivered(event_id, "Миша, просто заглянула. Как ты?", now)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    bridge = LocalConversationBridge(application)
    emitted: list[dict] = []
    bridge.event.connect(lambda encoded: emitted.append(json.loads(encoded)))

    bridge.loadInitialState()
    bridge.loadAgentRuns()
    activity = next(item for item in emitted if item["kind"] == "agent_runs_loaded")
    assert activity["runs"]["items"][0]["status"] == "completed"
    assert activity["runs"]["items"][0]["steps"][0]["title"] == "Проверить результат"
    encoded_activity = json.dumps(activity, ensure_ascii=False)
    assert "private_tool" not in encoded_activity
    assert "private_reason" not in encoded_activity

    bridge.loadProactiveInteractions()
    proactive = next(
        item for item in emitted if item["kind"] == "proactive_interactions_loaded"
    )
    assert proactive["interactions"]["items"][0]["message"] == "Миша, просто заглянула. Как ты?"
    bridge.resolveProactiveInteraction(event_id, "dismiss")
    resolved = next(
        item for item in emitted if item["kind"] == "proactive_interaction_resolved"
    )
    assert resolved["interaction"]["state"] == "dismissed"
    assert repository.read_document() == memory_before
    assert ProactiveInteractionStore(repository).get(event_id)["state"] == "dismissed"
    bridge.close()


def test_open_home_refresh_projects_new_live_reminder_once(tmp_path):
    from datetime import datetime, timedelta, timezone

    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.temporal.proactive import ProactivePolicy, ProactivePolicyStore
    from backend.temporal.proactive_interaction import ProactiveInteractionStore
    from backend.temporal.temporal_engine import FixedClock, TemporalEngine
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    provider = LocalProfileProvider(response_text="Миша, пора сказать мяу.")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    now = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    engine = TemporalEngine(clock)
    conversation_service = application._conversation._conversation
    conversation_service.temporal_engine = engine
    conversation_service.memory_intent_handler.temporal_engine = engine
    application._proactive._clock = clock
    application._proactive._runtime.temporal_engine = engine
    application._proactive._runtime.controlled.temporal_engine = engine
    ProactivePolicyStore(root / "local-data" / "config" / "proactive-policy.json").save(
        ProactivePolicy(
            enabled=True,
            proactive_level=1,
            allow_commitment_reminders=True,
            maximum_reminders=2,
            daily_message_limit=2,
            cooldown_seconds=0,
            runtime_mode="background",
            cycle_interval_seconds=10,
        )
    )
    bridge = LocalConversationBridge(application)
    emitted: list[dict] = []
    bridge.event.connect(lambda encoded: emitted.append(json.loads(encoded)))
    bridge.loadInitialState()
    # Home is already open and its fast projection pulse has observed one
    # policy cycle before the new reminder exists.
    bridge.refreshProactiveInteractions()
    deadline = time.monotonic() + 3
    while bridge._proactive_refresh_in_flight and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    proposed = application.send_message(
        "Напомни через две минуты сказать мяу",
        project_id="project_masha_home",
    )
    assert proposed.pending_confirmation is not None
    application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id="project_masha_home",
    )
    commitment = next(item for item in repository.read_document().commitments if "мяу" in item.text)
    assert commitment.due_at == now + timedelta(minutes=2)
    clock.value = now + timedelta(minutes=3)

    bridge.refreshProactiveInteractions()
    deadline = time.monotonic() + 3
    while len([item for item in emitted if item["kind"] == "proactive_interactions_loaded"]) < 1 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    bridge.refreshProactiveInteractions()
    deadline = time.monotonic() + 1
    while bridge._proactive_refresh_in_flight and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    live = [item for item in emitted if item["kind"] == "proactive_interactions_loaded"]
    assert len(live) == 1
    assert live[0]["delivery_origin"] == "local_runtime"
    assert live[0]["interactions"]["items"][0]["message"] == "Миша, пора сказать мяу."
    assert live[0]["interactions"]["items"][0]["due_at"] == (now + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    trace = application._proactive._trace.list()
    assert {row["stage"] for row in trace} >= {
        "runtime_cycle_started", "interaction_delivered", "renderer_delivery_emitted",
    }
    assert all(row["at"].endswith("+00:00") for row in trace)
    assert ProactiveInteractionStore(repository).list()[0]["state"] == "delivered"
    assert len(application._proactive._journal.list()) == 2
    assert application.status().proactive_reason_code == "authorised"
    bridge.close()


def test_desktop_boundary_forgets_relationship_memory_with_preview_audit_and_restart(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.memory_management import MemoryManagementService
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    provider = LocalProfileProvider()
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([provider]),
    )
    saved = application.send_message(
        "Маша, запомни как часть нашей истории, что сегодня мы запустили первый MVP Дома",
        project_id="project_masha_home",
    )
    application.resolve_confirmation(
        conversation_id=saved.conversation_id,
        proposal_id=saved.pending_confirmation.proposal_id,
        decision="confirm",
        project_id="project_masha_home",
    )
    moment_id = application.shared_continuity().moments[0].moment_id

    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))
    bridge.loadInitialState()
    bridge.submitMessage("Забудь, что сегодня мы запустили первый MVP Дома")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "turn_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    turn = next(item for item in events if item["kind"] == "turn_result")["result"]
    pending = turn["pending_confirmation"]
    assert turn["status"] == "completed"
    assert pending["confirmation_type"] == "memory_forget"
    assert pending["subject"] == "сегодня мы запустили первый MVP Дома"
    assert application.shared_continuity().moments[0].moment_id == moment_id

    bridge.resolveConfirmation(pending["proposal_id"], "confirm")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "confirmation_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    resolution = next(
        item for item in events if item["kind"] == "confirmation_result"
    )["result"]
    assert resolution["status"] == "confirmed"
    assert application.shared_continuity().moments == ()

    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    hidden = MemoryManagementService(repository).get(moment_id)
    assert hidden.payload["visibility"] == "hidden"
    assert any(event["action"] == "memory_forget" for event in hidden.audit_events)
    restarted = build_masha_application(project_root=root, router=ModelRouter([provider]))
    assert restarted.shared_continuity().moments == ()
    bridge.close()


def test_desktop_bridge_continues_a_real_confirmed_thread(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider(response_text="Вернулись к нашей теме.")]),
    )
    proposed = application.send_message(
        "Оставь это как открытую нить: выбрать свет для комнаты",
        project_id="masha-home",
    )
    application.resolve_confirmation(
        conversation_id=proposed.conversation_id,
        proposal_id=proposed.pending_confirmation.proposal_id,
        decision="confirm",
        project_id="masha-home",
    )
    thread = application.shared_continuity().open_threads[0]
    before_threads = application.shared_continuity().open_threads

    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))
    bridge.loadInitialState()
    bridge.continueContinuityThread(thread.thread_id)
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "continuity_thread_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    result = next(item for item in events if item["kind"] == "continuity_thread_result")
    assert result["result"]["assistant_message"]["content"] == "Вернулись к нашей теме."
    conversation_id = result["result"]["conversation_id"]
    assert any(
        "выбрать свет для комнаты" in message.content
        for message in application.conversation(conversation_id).messages
    )
    assert result["result"]["pending_confirmation"] is None
    assert application.shared_continuity().open_threads == before_threads
    assert application.pending_confirmation(conversation_id) is None
    restarted = build_masha_application(project_root=root, router=ModelRouter([LocalProfileProvider()]))
    assert restarted.shared_continuity().open_threads == before_threads
    bridge.close()


def test_production_bridge_keeps_one_pending_confirmation_and_plain_yes_resolves_it(tmp_path):
    import re

    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))
    bridge.loadInitialState()

    def submit(text):
        before = len([item for item in events if item["kind"] == "turn_result"])
        bridge.submitMessage(text)
        deadline = time.monotonic() + 3
        while len([item for item in events if item["kind"] == "turn_result"]) == before and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        return [item for item in events if item["kind"] == "turn_result"][-1]["result"]

    first = submit("Добавь дело купить корм собаке")
    pending = first["pending_confirmation"]
    assert pending is not None
    uuid_pattern = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27}", re.IGNORECASE)
    assert uuid_pattern.search(first["assistant_message"]["content"]) is None
    assert uuid_pattern.search(pending["title"]) is None
    assert uuid_pattern.search(pending["subject"]) is None

    second = submit("Добавь дело заказать корм кошке")
    assert "Сначала решим текущее предложение" in second["assistant_message"]["content"]
    assert second["pending_confirmation"]["proposal_id"] == pending["proposal_id"]
    handler = application._conversation._conversation.memory_intent_handler
    assert len(handler.proposal_store.pending_for_conversation(first["conversation_id"])) == 1

    confirmed = submit("да")
    assert confirmed["pending_confirmation"] is None
    assert confirmed["assistant_message"]["content"] == "Готово, сохранила."
    texts = [item.text for item in application.commitments(limit=None).items]
    assert "купить корм собаке" in texts
    assert "заказать корм кошке" not in texts
    bridge.close()


def test_memory_proposal_bridge_preserves_valid_presentation_lifecycle(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    application = build_masha_application(
        project_root=_isolated_root(tmp_path),
        router=ModelRouter([LocalProfileProvider(response_text="Я здесь.")]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))
    bridge.loadInitialState()

    bridge.submitMessage("Маша, запомни наш разговор про звёзды")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "turn_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    started = next(item for item in events if item["kind"] == "turn_started")
    thinking = next(item for item in events if item["kind"] == "turn_thinking")
    proposed = next(item for item in events if item["kind"] == "turn_result")
    assert started["snapshot"]["presentation"]["presence"]["activity"] == "waiting"
    assert thinking["snapshot"]["presentation"]["presence"]["activity"] == "processing"
    assert proposed["snapshot"]["presentation"]["presence"]["activity"] == "confirmation"
    assert proposed["result"]["pending_confirmation"]["confirmation_type"] == "memory_create"
    proposal_id = proposed["result"]["pending_confirmation"]["proposal_id"]

    bridge.resolveConfirmation(proposal_id, "reject")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "confirmation_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    resolved = next(item for item in events if item["kind"] == "confirmation_result")
    assert resolved["result"]["status"] == "rejected"
    assert resolved["snapshot"]["presentation"]["presence"]["activity"] == "completed"

    before = len([item for item in events if item["kind"] == "turn_result"])
    bridge.submitMessage("Ты здесь?")
    deadline = time.monotonic() + 3
    while len([item for item in events if item["kind"] == "turn_result"]) == before and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    follow_up = [item for item in events if item["kind"] == "turn_result"][-1]
    assert follow_up["result"]["assistant_message"]["content"] == "Я здесь."
    bridge.close()


def test_commitment_pagination_keeps_old_records_actionable_by_id(tmp_path):
    from datetime import datetime, timedelta, timezone

    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    root = _isolated_root(tmp_path)
    application = build_masha_application(project_root=root, router=ModelRouter([LocalProfileProvider()]))
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    document = repository.read_document()
    template = document.commitments[0]
    now = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    commitments = [
        template.model_copy(update={
            "id": template.id if index == 0 else f"commitment_page_{index:02d}",
            "text": f"Дело {index:02d}",
            "due_at": None,
            "created_at": now - timedelta(days=index),
            "updated_at": now - timedelta(days=index),
        })
        for index in range(15)
    ]
    repository.replace_document(document.model_copy(update={"commitments": commitments}))

    bridge = LocalConversationBridge(application)
    emitted: list[dict] = []
    bridge.event.connect(lambda encoded: emitted.append(json.loads(encoded)))
    bridge.loadInitialState()
    bridge.loadCommitments()
    first = [item for item in emitted if item["kind"] == "commitments_loaded"][-1]
    assert len(first["commitments"]["items"]) == 10
    assert first["commitments"]["has_more"] is True
    bridge.loadMoreCommitments(first["commitments"]["next_offset"])
    second = [item for item in emitted if item["kind"] == "commitments_loaded"][-1]
    assert len(second["commitments"]["items"]) == 5
    oldest = second["commitments"]["items"][-1]

    bridge.proposeCommitmentCompletion(oldest["commitment_id"])
    proposed = [item for item in emitted if item["kind"] == "commitment_completion_proposed"][-1]
    assert proposed["result"]["pending_confirmation"]["subject"] == oldest["text"]
    bridge.resolveConfirmation(proposed["result"]["pending_confirmation"]["proposal_id"], "confirm")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "confirmation_result" for item in emitted) and time.monotonic() < deadline:
        (QCoreApplication.instance() or QCoreApplication([])).processEvents()
        time.sleep(0.01)
    stored = next(item for item in repository.read_document().commitments if item.id == oldest["commitment_id"])
    assert stored.status.value == "completed"
    bridge.close()


def test_conversation_pagination_reaches_every_summary_and_preserves_selected_transcript(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    root = _isolated_root(tmp_path)
    application = build_masha_application(project_root=root, router=ModelRouter([LocalProfileProvider()]))
    turns = [application.send_message(f"Разговор {index}", project_id="project_masha_home") for index in range(15)]
    selected_id = turns[0].conversation_id
    for index in range(12):
        application.send_message(f"Продолжение {index}", project_id="project_masha_home", conversation_id=selected_id)

    bridge = LocalConversationBridge(application)
    emitted: list[dict] = []
    bridge.event.connect(lambda encoded: emitted.append(json.loads(encoded)))
    bridge.loadInitialState()
    bridge.loadRecentConversations()
    first = [item for item in emitted if item["kind"] == "recent_conversations"][-1]["recent"]
    assert len(first["items"]) == 10
    assert first["items"][0]["conversation_id"] == selected_id
    bridge.loadMoreConversations(first["next_offset"])
    second = [item for item in emitted if item["kind"] == "recent_conversations"][-1]["recent"]
    assert len(second["items"]) == 5
    all_ids = {item["conversation_id"] for item in first["items"] + second["items"]}
    assert len(all_ids) == 15
    bridge.openConversation(selected_id)
    opened = [item for item in emitted if item["kind"] == "conversation_opened"][-1]
    assert len(opened["conversation"]["messages"]) == 26
    bridge.close()


def test_conversation_pagination_resets_after_new_conversation_lifecycle(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    application = build_masha_application(
        project_root=root, router=ModelRouter([LocalProfileProvider()])
    )
    original = [
        application.send_message(f"Старый разговор {index}", project_id="project_masha_home")
        for index in range(25)
    ]
    bridge = LocalConversationBridge(application)
    emitted: list[dict] = []
    bridge.event.connect(lambda encoded: emitted.append(json.loads(encoded)))
    bridge.loadInitialState()
    bridge.loadRecentConversations()
    first = [item for item in emitted if item["kind"] == "recent_conversations"][-1]["recent"]
    assert first["total"] == 25
    assert first["has_more"] is True
    assert first["next_offset"] == 10
    bridge.loadMoreConversations(first["next_offset"])
    second = [item for item in emitted if item["kind"] == "recent_conversations"][-1]["recent"]
    assert second["offset"] == 10
    assert second["next_offset"] == 20

    bridge.startNewConversation()
    bridge.submitMessage("Первый ответ в новом разговоре")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "turn_result" for item in emitted) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    new_conversation_id = [item for item in emitted if item["kind"] == "turn_result"][-1]["result"]["conversation_id"]

    # This mirrors the renderer's fresh shelf snapshot after a turn.  Its
    # next offset, not the page from the old shelf, is the only valid cursor.
    bridge.loadRecentConversations()
    reset = [item for item in emitted if item["kind"] == "recent_conversations"][-1]["recent"]
    assert reset["offset"] == 0
    assert reset["items"][0]["conversation_id"] == new_conversation_id
    assert reset["total"] == 26
    assert reset["next_offset"] == 10
    pages = [reset]
    while pages[-1]["has_more"]:
        bridge.loadMoreConversations(pages[-1]["next_offset"])
        pages.append([item for item in emitted if item["kind"] == "recent_conversations"][-1]["recent"])
    all_items = [item for page in pages for item in page["items"]]
    all_ids = [item["conversation_id"] for item in all_items]
    assert [page["offset"] for page in pages] == [0, 10, 20]
    assert pages[-1]["next_offset"] is None
    assert len(all_ids) == len(set(all_ids)) == 26
    assert {item.conversation_id for item in original}.issubset(all_ids)

    old_conversation_id = original[0].conversation_id
    bridge.openConversation(old_conversation_id)
    opened = [item for item in emitted if item["kind"] == "conversation_opened"][-1]
    assert opened["conversation"]["conversation_id"] == old_conversation_id
    bridge.loadRecentConversations()
    reopened = [item for item in emitted if item["kind"] == "recent_conversations"][-1]["recent"]
    reopened_pages = [reopened]
    while reopened_pages[-1]["has_more"]:
        bridge.loadMoreConversations(reopened_pages[-1]["next_offset"])
        reopened_pages.append(
            [item for item in emitted if item["kind"] == "recent_conversations"][-1]["recent"]
        )
    reopened_ids = [
        item["conversation_id"] for page in reopened_pages for item in page["items"]
    ]
    assert len(reopened_ids) == len(set(reopened_ids)) == 26
    assert old_conversation_id in reopened_ids
    assert len(opened["conversation"]["messages"]) == 2
    assert reopened["revision"] > reset["revision"]
    bridge.close()


def test_desktop_bridge_installs_a_valid_local_skill_and_restart_sees_it(tmp_path, monkeypatch):
    import shutil

    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge, QFileDialog
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    root = _isolated_root(tmp_path)
    bundled = root / "skills" / "project_observer"
    package = tmp_path / "selected-skill-package"
    shutil.copytree(bundled, package)
    shutil.rmtree(bundled)
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(package), ""))

    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))
    bridge.chooseSkillPackage()
    preview = next(item for item in events if item["kind"] == "skill_install_preview")["preview"]
    assert preview["skill_id"] == "project_observer"
    bridge.resolveSkillInstall(preview["proposal_id"], "confirm")
    result = next(item for item in events if item["kind"] == "skill_install_result")["result"]
    assert result["status"] == "confirmed"
    assert any(item["skill_id"] == "project_observer" for item in result["workbench"]["skills"])
    bridge.close()

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    assert any(item.skill_id == "project_observer" for item in restarted.workbench().skills)


def test_desktop_bridge_local_pdf_picker_projects_no_path_and_can_clear(tmp_path, monkeypatch):
    from backend.application import build_masha_application
    from backend.document_read import LocalDocumentInputError
    from backend.llm.model_router import ModelRouter
    from backend.ui.conversation_bridge import LocalConversationBridge, QFileDialog
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root
    from tests.test_local_document_input import _write_pdf

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    selected = _write_pdf(tmp_path, "bridge-report.pdf")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider(response_text="Я рядом.")]),
    )
    bridge = LocalConversationBridge(application)
    emitted: list[dict] = []
    bridge.event.connect(lambda encoded: emitted.append(json.loads(encoded)))
    bridge.loadInitialState()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(selected), ""))

    bridge.chooseLocalDocument()

    selected_event = next(item for item in emitted if item["kind"] == "local_document_selected")
    document = selected_event["document"]
    assert set(document) == {"token", "display_name", "byte_size"}
    assert document["display_name"] == "bridge-report.pdf"
    assert str(selected) not in json.dumps(selected_event)
    assert str(selected.parent) not in json.dumps(selected_event)

    bridge.clearLocalDocument(document["token"])
    assert emitted[-1]["kind"] == "local_document_cleared"
    bridge._turn_in_flight = True
    bridge.chooseLocalDocument()
    assert emitted[-1] == {"kind": "local_document_rejected", "reason": "turn_in_flight"}
    bridge._turn_in_flight = False
    bridge.chooseLocalDocument()
    replacement = [item for item in emitted if item["kind"] == "local_document_selected"][-1]["document"]
    bridge.startNewConversation()
    with pytest.raises(LocalDocumentInputError, match="local_document_token_invalid"):
        application.send_message_with_document(
            "Прочитай PDF",
            token=replacement["token"],
            project_id="project_masha_home",
        )
    bridge.close()


def test_production_bridge_natural_commitment_flow_persists_and_reloads(tmp_path):
    from backend.application import build_masha_application
    from backend.llm.model_router import ModelRouter
    from backend.memory.sqlite_repository import MemorySqliteRepository
    from backend.ui.conversation_bridge import LocalConversationBridge
    from tests.test_application_boundary import LocalProfileProvider, _isolated_root

    app = QCoreApplication.instance() or QCoreApplication([])
    root = _isolated_root(tmp_path)
    repository = MemorySqliteRepository(root / "local-data" / "memory" / "masha.sqlite3")
    application = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    bridge = LocalConversationBridge(application)
    events: list[dict] = []
    bridge.event.connect(lambda encoded: events.append(json.loads(encoded)))
    bridge.loadInitialState()
    before = len(repository.read_document().commitments)

    bridge.submitMessage("Надо не забыть проверить Персеиды")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "turn_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    proposed = next(item for item in events if item["kind"] == "turn_result")
    pending = proposed["result"]["pending_confirmation"]
    assert pending["confirmation_type"] == "commitment_create"
    assert len(repository.read_document().commitments) == before

    bridge.resolveConfirmation(pending["proposal_id"], "confirm")
    deadline = time.monotonic() + 3
    while not any(item["kind"] == "confirmation_result" for item in events) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert any("персеиды" in item.text.casefold() for item in repository.read_document().commitments)
    bridge.close()

    restarted = build_masha_application(
        project_root=root,
        router=ModelRouter([LocalProfileProvider()]),
    )
    assert any("персеиды" in item.text.casefold() for item in restarted.commitments().items)
