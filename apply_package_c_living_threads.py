from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
STAGED: dict[Path, str] = {}


class PatchError(RuntimeError):
    pass


def read(path: str) -> str:
    p = ROOT / path
    if p not in STAGED:
        if not p.exists():
            raise PatchError(f"{path}: file not found")
        STAGED[p] = p.read_text(encoding="utf-8")
    return STAGED[p]


def stage(path: str, text: str) -> None:
    STAGED[ROOT / path] = text


def replace_once(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 match, found {count}")
    stage(path, text.replace(old, new, 1))
    print(f"[CHECK] {path}: {label}")


def insert_after(path: str, anchor: str, addition: str, label: str) -> None:
    text = read(path)
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 anchor, found {count}")
    stage(path, text.replace(anchor, anchor + addition, 1))
    print(f"[CHECK] {path}: {label}")


def replace_between(path: str, start: str, end: str, replacement: str, label: str) -> None:
    text = read(path)
    a = text.find(start)
    if a < 0:
        raise PatchError(f"{path}: {label}: start marker not found")
    b = text.find(end, a + len(start))
    if b < 0:
        raise PatchError(f"{path}: {label}: end marker not found")
    stage(path, text[:a] + replacement + text[b:])
    print(f"[CHECK] {path}: {label}")


def append_once(path: str, marker: str, block: str, label: str) -> None:
    text = read(path)
    if marker in text:
        raise PatchError(f"{path}: {label}: already present")
    if not text.endswith("\n"):
        text += "\n"
    stage(path, text + "\n" + block.strip() + "\n")
    print(f"[CHECK] {path}: {label}")


try:
    if "function updateHistoryShelfState()" not in read("frontend/renderer/app.js"):
        raise PatchError("Package B is not present in frontend/renderer/app.js")

    replace_once('backend/application/continuity.py', '\ndef thread_prompt(self, thread_id: str) -> str:\n    matches = [item for item in self.view().open_threads if item.thread_id == thread_id]\n    if len(matches) != 1:\n        raise KeyError("continuity thread not found")\n    thread = matches[0]\n    return (\n        "Давай вернёмся к нашей общей истории. "\n        f"Открытая тема: {thread.summary}. Зачем вернуться: {thread.reason_to_return}."\n    )\n', '\ndef thread_prompt(self, thread_id: str) -> str:\n    # Legacy explicit-prompt path. Package C UI no longer calls it.\n    thread = self.thread(thread_id)\n    return (\n        "Давай вернёмся к нашей общей истории. "\n        f"Открытая тема: {thread.summary}. Зачем вернуться: {thread.reason_to_return}."\n    )\n', 'reuse typed thread lookup')

    replace_once('backend/conversation/context_compiler.py', '\n)\n\n\nBEHAVIORAL_CONTRACT = (\n', '\n)\n\nACTIVE_CONTINUITY_CONTRACT = (\n    "АКТИВНАЯ НИТЬ: если active_continuity не null, Миша сам выбрал эту нить "\n    "на полке Истории для текущего разговора. Используй summary и reason_to_return "\n    "как тихий фон текущей темы, а не как новую команду пользователя. Не начинай "\n    "ответ служебной фразой вроде «возвращаемся к теме» и не пересказывай нить без "\n    "необходимости. Отвечай прежде всего на текущую реплику Миши. Не придумывай "\n    "детали, которых нет в нити, и не объявляй её закрытой или выполненной без "\n    "подтверждённого application-действия. Выбор нити не является записью памяти "\n    "и сам по себе ничего не меняет."\n)\n\n\nBEHAVIORAL_CONTRACT = (\n', 'add active-thread conversation contract')

    replace_once('backend/conversation/context_compiler.py', '\n    context_lens: str = "general",\n    home_moment: str = HOME_MOMENT_ORDINARY,\n) -> ModelRequest:\n', '\n    context_lens: str = "general",\n    home_moment: str = HOME_MOMENT_ORDINARY,\n    active_continuity: dict[str, str] | None = None,\n) -> ModelRequest:\n', 'accept structured active thread')

    replace_once('backend/conversation/conversation_service.py', '\n    return conversation.id, user, assistant\n\n@staticmethod\ndef _model_history_message(message) -> ModelMessage:\n', '\n    return conversation.id, user, assistant\n\ndef _active_continuity_context(\n    self,\n    thread_id: str | None,\n) -> dict[str, str] | None:\n    if thread_id is None or self.shared_continuity is None:\n        return None\n\n    matches = [\n        follow_up\n        for _, follow_up in self.shared_continuity.open_follow_ups()\n        if follow_up.id == thread_id\n    ]\n\n    if len(matches) != 1:\n        return None\n\n    thread = matches[0]\n    return {\n        "summary": thread.summary,\n        "reason_to_return": thread.reason_to_return,\n        "topic": thread.topic,\n    }\n\n@staticmethod\ndef _model_history_message(message) -> ModelMessage:\n', 'add selected-thread context resolver')

    replace_once('frontend/renderer/app.js', '\nfunction renderContinuity(view) {\n', '\nfunction renderActiveContinuityThread(thread) {\n  activeContinuityThread = thread || null;\n  threadContext.hidden = !activeContinuityThread;\n  threadContextTitle.textContent =\n    activeContinuityThread?.summary || "";\n  threadContextClear.disabled = inFlight || !activeContinuityThread;\n}\n\nfunction renderContinuity(view) {\n', 'add thread chip renderer')

    replace_once('frontend/renderer/app.js', '\naction.textContent = "Вернуться к этой теме";\naction.addEventListener("click", () => {\n  if (!ready || inFlight) return;\n  setComposerState({ enabled: true, waiting: true });\n  bridge.continueContinuityThread(thread.thread_id);\n});\n', '\naction.textContent = (\n  activeContinuityThread?.thread_id === thread.thread_id\n    ? "Эта нить уже рядом"\n    : "Взять эту нить с собой"\n);\naction.disabled =\n  inFlight\n  || activeContinuityThread?.thread_id === thread.thread_id;\naction.addEventListener("click", () => {\n  if (!ready || inFlight || action.disabled) return;\n  bridge.activateContinuityThread(thread.thread_id);\n});\n', 'select thread without sending a turn')

    replace_once('frontend/renderer/app.js', '\nrenderPendingConfirmation(payload.pending_confirmation);\nrenderMemoryCandidate(payload.memory_candidate);\nreturn;\n', '\nrenderPendingConfirmation(payload.pending_confirmation);\nrenderMemoryCandidate(payload.memory_candidate);\nrenderActiveContinuityThread(payload.active_continuity_thread);\nreturn;\n', 'restore selected thread on Home load')

    replace_once('frontend/renderer/app.js', '\n  setComposerState({ enabled: ready });\n  renderPendingConfirmation(payload.pending_confirmation);\n  return;\n}\nif (payload.kind === "turn_started") {\n', '\n  setComposerState({ enabled: ready });\n  renderPendingConfirmation(payload.pending_confirmation);\n  renderActiveContinuityThread(payload.active_continuity_thread);\n  return;\n}\nif (payload.kind === "turn_started") {\n', 'restore selected thread on conversation open')

    replace_once('frontend/renderer/app.js', '\nif (["activities_unavailable", "proactive_unavailable", "proactive_resolution_rejected", "continuity_unavailable", "reflections_unavailable", "reflection_resolution_rejected", "honest_help_rejected", "workbench_unavailable"].includes(payload.kind)) {\n', '\nif (["activities_unavailable", "proactive_unavailable", "proactive_resolution_rejected", "continuity_unavailable", "continuity_context_unavailable", "reflections_unavailable", "reflection_resolution_rejected", "honest_help_rejected", "workbench_unavailable"].includes(payload.kind)) {\n', 'include thread-context unavailable event')

    insert_after('backend/application/continuity.py', '\nreturn SharedContinuityView(\n    # Ordinary Fact/Decision/Episode belong to Memory, not to "our\n    # history".  Only explicitly confirmed shared moments and threads\n    # are allowed on this surface.\n    confirmed_memories=(),\n    moments=moments,\n    open_threads=threads,\n    quarantined_count=self._continuity.quarantined_count(),\n)\n\n\n', '\ndef thread(self, thread_id: str) -> ContinuityFollowUpView:\n    # Return one still-open UI-safe thread or fail closed.\n    matches = [\n        item\n        for item in self.view().open_threads\n        if item.thread_id == thread_id\n    ]\n    if len(matches) != 1:\n        raise KeyError("continuity thread not found")\n    return matches[0]\n\n\n', 'add typed thread lookup')

    insert_after('backend/application/conversation.py', '\ndef discard_presented_entity_set(self, conversation_id: str) -> None:\n    handler = self._conversation.memory_intent_handler\n    if handler is not None:\n        handler.discard_presented_entity_set(conversation_id)\n', '\n\ndef activate_continuity_thread(\n    self,\n    thread_id: str,\n    *,\n    conversation_id: str,\n) -> None:\n    # Select one thread for this live conversation without sending a turn.\n    self._conversation.history.get(conversation_id)\n    self._active_continuity_by_conversation[conversation_id] = thread_id\n\ndef clear_continuity_thread(self, *, conversation_id: str) -> None:\n    self._active_continuity_by_conversation.pop(conversation_id, None)\n\ndef active_continuity_thread_id(\n    self,\n    *,\n    conversation_id: str,\n) -> str | None:\n    return self._active_continuity_by_conversation.get(conversation_id)\n', 'add ephemeral active-thread API')

    insert_after('backend/application/application.py', '\nConversationTurnResult,\n', '\nContinuityFollowUpView,\n', 'import ContinuityFollowUpView')

    insert_after('backend/application/application.py', '\ndef shared_continuity(self) -> SharedContinuityView:\n    return self._continuity.view()\n\n', '\ndef continuity_thread(self, thread_id: str) -> ContinuityFollowUpView:\n    return self._continuity.thread(thread_id)\n\ndef activate_continuity_thread(\n    self,\n    thread_id: str,\n    *,\n    conversation_id: str | None,\n) -> ContinuityFollowUpView:\n    if conversation_id is None:\n        raise ValueError("continuity thread needs an active conversation")\n    thread = self._continuity.thread(thread_id)\n    self._conversation.activate_continuity_thread(\n        thread_id,\n        conversation_id=conversation_id,\n    )\n    return thread\n\ndef clear_continuity_thread(\n    self,\n    *,\n    conversation_id: str | None,\n) -> None:\n    if conversation_id is None:\n        return\n    self._conversation.clear_continuity_thread(\n        conversation_id=conversation_id,\n    )\n\ndef active_continuity_thread(\n    self,\n    *,\n    conversation_id: str | None,\n) -> ContinuityFollowUpView | None:\n    if conversation_id is None:\n        return None\n    thread_id = self._conversation.active_continuity_thread_id(\n        conversation_id=conversation_id,\n    )\n    if thread_id is None:\n        return None\n    try:\n        return self._continuity.thread(thread_id)\n    except KeyError:\n        self._conversation.clear_continuity_thread(\n            conversation_id=conversation_id,\n        )\n        return None\n\n', 'add public selected-thread boundary')

    insert_after('backend/conversation/context_compiler.py', '\n"home_moment_contract": home_moment_contract,\n', '\n"active_continuity": active_continuity,\n"active_continuity_contract": ACTIVE_CONTINUITY_CONTRACT,\n', 'publish structured active thread')

    insert_after('backend/conversation/conversation_service.py', '\nactive_profile = None if self.model_profiles is None else self.model_profiles.get_active_profile()\n', '\nactive_continuity = self._active_continuity_context(\n    active_continuity_thread_id\n)\n', 'resolve selected thread before model request')

    insert_after('backend/conversation/conversation_service.py', '\nhome_moment=home_moment,\n', '\nactive_continuity=active_continuity,\n', 'send selected thread to compiler')

    insert_after('backend/application/home_snapshot.py', '\ndef opened(self) -> HomeSnapshotView:\n    return self._dispatch(UserOpenedApplication(occurred_at=self._now()))\n', '\n\ndef conversation_focused(self) -> HomeSnapshotView:\n    # Return Presentation focus to conversation without a model turn.\n    return self._dispatch(\n        SurfaceFocused(\n            occurred_at=self._now(),\n            surface_id="home.conversation",\n        )\n    )\n', 'add conversation refocus event')

    insert_after('backend/ui/conversation_bridge.py', '\n"continuity_count": self._continuity_count(),\n', '\n"active_continuity_thread": self._active_continuity_payload(),\n', 'publish selected thread on Home load')

    insert_after('backend/ui/conversation_bridge.py', '\n"pending_confirmation": None if pending is None else pending.model_dump(mode="json"),\n', '\n"active_continuity_thread": self._active_continuity_payload(),\n', 'publish selected thread on conversation open')

    insert_after('backend/ui/conversation_bridge.py', '\n"continuity_count": (\n    0\n    if self._application is None\n    else self._continuity_count()\n),\n', '\n"active_continuity_thread": self._active_continuity_payload(),\n', 'refresh selected thread after confirmation')

    insert_after('backend/ui/conversation_bridge.py', '\ndef _current_home_moment(self) -> str:\n    # Read under the same lock used by Presentation mutations.\n    with self._session_lock:\n        if self._session is None:\n            return "ordinary"\n        return self._session.home_moment.value\n', '\n\ndef _active_continuity_payload(self) -> dict | None:\n    if self._application is None or self._conversation_id is None:\n        return None\n    thread = self._application.active_continuity_thread(\n        conversation_id=self._conversation_id,\n    )\n    return (\n        None\n        if thread is None\n        else thread.model_dump(mode="json")\n    )\n', 'add selected-thread payload helper')

    insert_after('frontend/index.html', '\n<p class="surface-status" id="surface-status">Подключаю локальный разговор…</p>\n', '\n<div class="thread-context" id="thread-context" hidden>\n  <span class="thread-context-label">нить рядом</span>\n  <strong id="thread-context-title"></strong>\n  <button\n    class="thread-context-clear"\n    id="thread-context-clear"\n    type="button"\n    aria-label="Убрать выбранную нить из текущего разговора"\n  >×</button>\n</div>\n', 'add selected-thread chip')

    insert_after('frontend/renderer/app.js', '\nconst historyInboxReject = document.getElementById("history-inbox-reject");\n', '\nconst threadContext = document.getElementById("thread-context");\nconst threadContextTitle = document.getElementById("thread-context-title");\nconst threadContextClear = document.getElementById("thread-context-clear");\n', 'bind thread chip')

    insert_after('frontend/renderer/app.js', '\nlet continuityItemCount = 0;\n', '\nlet activeContinuityThread = null;\n', 'add active thread UI state')

    insert_after('frontend/renderer/app.js', '\nactiveConversationId = null;\n', '\nrenderActiveContinuityThread(null);\n', 'clear thread chip for new conversation')

    insert_after('frontend/renderer/app.js', '\nif (payload.kind === "shared_continuity_loaded") {\n  applySnapshot(payload.snapshot);\n  renderContinuity(payload.continuity);\n  continuitySurface.hidden = false;\n  document.documentElement.dataset.objectSurface = "continuity";\n  continuityTrigger.setAttribute("aria-expanded", "true");\n  return;\n}\n', '\nif (payload.kind === "continuity_thread_activated") {\n  applySnapshot(payload.snapshot);\n  renderActiveContinuityThread(payload.thread);\n  returnToConversation();\n  surfaceStatus.textContent = "Нить рядом. Продолжай своими словами.";\n  input.focus();\n  return;\n}\n\nif (payload.kind === "continuity_thread_cleared") {\n  applySnapshot(payload.snapshot);\n  renderActiveContinuityThread(null);\n  surfaceStatus.textContent = "";\n  input.focus();\n  return;\n}\n', 'handle selected-thread lifecycle')

    insert_after('frontend/renderer/app.js', '\nif (payload.continuity_count !== undefined) {\n  continuityItemCount = Number(payload.continuity_count || 0);\n  updateHistoryShelfState();\n}\n', '\nrenderActiveContinuityThread(payload.active_continuity_thread);\n', 'sync selected thread after confirmation')

    insert_after('frontend/renderer/app.js', '\nrejectMemoryCandidate.addEventListener("click", () => {\n  if (!ready || inFlight || !pendingMemoryCandidate) return;\n  approveMemoryCandidate.disabled = true;\n  rejectMemoryCandidate.disabled = true;\n  bridge.resolveMemoryCandidate(pendingMemoryCandidate.candidate_id, "reject");\n});\n', '\n\nthreadContextClear.addEventListener("click", () => {\n  if (!ready || inFlight || !activeContinuityThread) return;\n  threadContextClear.disabled = true;\n  bridge.clearContinuityThread();\n});\n', 'wire thread chip clear action')

    replace_between('backend/ui/conversation_bridge.py', '\n@Slot(str)\ndef continueContinuityThread(self, thread_id: str):  # noqa: N802\n', '\n@Slot()\ndef loadReflectionWorkspace(self):  # noqa: N802\n', '\n@Slot(str)\ndef activateContinuityThread(self, thread_id: str):  # noqa: N802\n    # Select context only. No synthetic prompt and no model call.\n    if self._application is None or self._turn_in_flight:\n        self._emit({"kind": "continuity_context_unavailable"})\n        return\n    if self._conversation_id is None:\n        self._emit({\n            "kind": "continuity_context_unavailable",\n            "message": "Сначала начнём разговор — и тогда нить сможет быть рядом.",\n        })\n        return\n    try:\n        thread = self._application.activate_continuity_thread(\n            thread_id,\n            conversation_id=self._conversation_id,\n        )\n    except (KeyError, ValueError):\n        self._emit({"kind": "continuity_context_unavailable"})\n        return\n\n    snapshot = self._session_snapshot("conversation_focused")\n    self._emit({\n        "kind": "continuity_thread_activated",\n        "thread": thread.model_dump(mode="json"),\n        "snapshot": snapshot.model_dump(mode="json"),\n    })\n\n@Slot()\ndef clearContinuityThread(self):  # noqa: N802\n    if self._application is None or self._turn_in_flight:\n        return\n    self._application.clear_continuity_thread(\n        conversation_id=self._conversation_id,\n    )\n    snapshot = self._session_snapshot("conversation_focused")\n    self._emit({\n        "kind": "continuity_thread_cleared",\n        "snapshot": snapshot.model_dump(mode="json"),\n    })\n\n', 'replace auto-turn slot with select/clear slots')

    replace_between('backend/ui/conversation_bridge.py', '\ndef _finish_continuity_thread(self, future) -> None:\n', '\ndef _finish_confirmation(self, future) -> None:\n', '\ndef _finish_confirmation(self, future) -> None:\n', 'remove synthetic thread callback')

    append_once('frontend/styles/home.css', '/* Package C — living threads */', '\n/* Package C — living threads */\n\n.thread-context {\n  display: grid;\n  grid-template-columns: auto minmax(0, 1fr) auto;\n  align-items: center;\n  gap: 9px;\n  margin: -5px 0 13px;\n  padding: 7px 9px;\n  border-left: 1px solid rgba(226, 188, 126, .28);\n  background: rgba(108, 70, 35, .08);\n  color: rgba(244, 226, 203, .68);\n  font: 500 11px/1.3 system-ui, sans-serif;\n}\n\n.thread-context[hidden] {\n  display: none;\n}\n\n.thread-context-label {\n  color: rgba(224, 180, 118, .58);\n  text-transform: uppercase;\n  letter-spacing: .11em;\n  font-size: 8px;\n  white-space: nowrap;\n}\n\n.thread-context strong {\n  min-width: 0;\n  overflow: hidden;\n  color: rgba(249, 235, 214, .82);\n  font-weight: 500;\n  text-overflow: ellipsis;\n  white-space: nowrap;\n}\n\n.thread-context-clear {\n  width: 22px;\n  height: 22px;\n  padding: 0;\n  border: 0;\n  border-radius: 50%;\n  color: rgba(239, 202, 147, .58);\n  background: transparent;\n  font: 400 17px/1 system-ui, sans-serif;\n  cursor: pointer;\n}\n\n.thread-context-clear:hover:not(:disabled) {\n  color: #ffe5bd;\n  background: rgba(226, 188, 126, .07);\n}\n\n.thread-context-clear:disabled {\n  opacity: .3;\n  cursor: default;\n}\n\nhtml[data-home-moment="special_evening"] .thread-context {\n  border-left-color: rgba(226, 188, 126, .18);\n  background: rgba(70, 41, 24, .06);\n  color: rgba(244, 226, 203, .5);\n}\n\nhtml[data-home-moment="special_evening"] .thread-context-label {\n  color: rgba(224, 180, 118, .42);\n}\n\nhtml[data-home-moment="special_evening"] .thread-context strong {\n  color: rgba(249, 235, 214, .68);\n}\n', 'add living-thread styles')

    append_once('tests/test_application_boundary.py', 'def test_selected_continuity_thread_is_context_not_synthetic_turn(', '\ndef test_selected_continuity_thread_is_context_not_synthetic_turn(tmp_path):\n    _, provider, application = _application(tmp_path)\n\n    first = application.send_message(\n        "Привет, Маш.",\n        project_id=PROJECT_ID,\n    )\n    conversation_id = first.conversation_id\n\n    handler = application._conversation._conversation.memory_intent_handler\n    assert handler is not None\n    continuity = handler.shared_continuity\n    assert continuity is not None\n\n    proposal = continuity.propose_open_thread(\n        handler.proposal_store,\n        text="Обсудить нашу будущую поездку к морю",\n        conversation_id=conversation_id,\n        reason_to_return="Вернуться к выбору места и времени",\n    )\n    continuity.confirm_proposal(proposal, handler.proposal_store)\n\n    thread = next(\n        item\n        for item in application.shared_continuity().open_threads\n        if item.summary == "Обсудить нашу будущую поездку к морю"\n    )\n\n    requests_before = len(provider.requests)\n    messages_before = len(application.conversation(conversation_id).messages)\n\n    selected = application.activate_continuity_thread(\n        thread.thread_id,\n        conversation_id=conversation_id,\n    )\n\n    assert selected.thread_id == thread.thread_id\n    assert len(provider.requests) == requests_before\n    assert len(application.conversation(conversation_id).messages) == messages_before\n\n    result = application.send_message(\n        "Я бы начал с места, где вечером можно просто гулять у воды.",\n        project_id=PROJECT_ID,\n        conversation_id=conversation_id,\n    )\n\n    assert result.status is ConversationTurnStatus.COMPLETED\n\n    conversation_requests = [\n        request\n        for request in provider.requests\n        if request.private_context.get("active_continuity")\n    ]\n    assert conversation_requests\n    active = conversation_requests[-1].private_context["active_continuity"]\n    assert active["summary"] == "Обсудить нашу будущую поездку к морю"\n    assert active["reason_to_return"] == "Вернуться к выбору места и времени"\n\n    application.clear_continuity_thread(conversation_id=conversation_id)\n    assert application.active_continuity_thread(\n        conversation_id=conversation_id,\n    ) is None\n', 'add selected-thread integration test')

    append_once('tests/test_context_compiler.py', 'def test_active_continuity_is_structured_background_not_synthetic_user_text(', '\ndef test_active_continuity_is_structured_background_not_synthetic_user_text():\n    compiler = ConversationContextCompiler(\n        lambda: datetime(2026, 8, 20, 1, 30, tzinfo=timezone.utc)\n    )\n    identity = IdentityKernel(\n        IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")\n    ).build_context()\n\n    request = compiler.compile(\n        messages=(\n            ModelMessage(\n                role="user",\n                content="Я бы начал с места у воды.",\n            ),\n        ),\n        identity_context=identity,\n        working_memory=[],\n        active_continuity={\n            "summary": "Обсудить нашу будущую поездку к морю",\n            "reason_to_return": "Вернуться к выбору места и времени",\n            "topic": "поездка к морю",\n        },\n    )\n\n    assert request.messages[-1].content == "Я бы начал с места у воды."\n    assert request.private_context["active_continuity"]["summary"] == (\n        "Обсудить нашу будущую поездку к морю"\n    )\n    assert "тихий фон" in request.private_context["active_continuity_contract"]\n', 'add compiler selected-thread test')

    _new = ROOT / 'frontend/renderer/living-threads.test.cjs'
    if _new.exists():
        raise PatchError('frontend/renderer/living-threads.test.cjs: already exists')
    STAGED[_new] = '"use strict";\n\nconst assert = require("node:assert/strict");\nconst fs = require("node:fs");\nconst path = require("node:path");\n\nconst root = path.join(__dirname, "..");\nconst app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");\nconst html = fs.readFileSync(path.join(root, "index.html"), "utf8");\nconst css = fs.readFileSync(path.join(root, "styles", "home.css"), "utf8");\n\nassert.match(html, /id="thread-context"/);\nassert.match(html, /id="thread-context-title"/);\nassert.match(html, /id="thread-context-clear"/);\n\nassert.match(app, /function renderActiveContinuityThread\\(thread\\)/);\nassert.match(app, /bridge\\.activateContinuityThread\\(thread\\.thread_id\\)/);\nassert.match(app, /bridge\\.clearContinuityThread\\(\\)/);\nassert.doesNotMatch(app, /bridge\\.continueContinuityThread\\(thread\\.thread_id\\)/);\n\nassert.match(css, /Package C — living threads/);\nassert.match(css, /\\.thread-context/);\n\nconsole.log("living threads tests passed");\n'
    print("[CHECK] frontend/renderer/living-threads.test.cjs: create")

    for file_path, text in STAGED.items():
        if file_path.suffix == ".py":
            compile(text, str(file_path), "exec")

except (PatchError, SyntaxError) as exc:
    print()
    print(f"[STOP] {exc}")
    print("No files were written.")
    raise SystemExit(1)

for file_path, text in STAGED.items():
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")
    print(f"[WRITE] {file_path.relative_to(ROOT)}")

print()
print("Package C applied: living threads.")
print("Review: git diff")
print(
    r"Python: .\.venv\Scripts\python.exe -m pytest "
    r"tests/test_context_compiler.py tests/test_application_boundary.py -q"
)
print(
    r"Frontend: node frontend\renderer\quiet-shelves.test.cjs "
    r"&& node frontend\renderer\living-threads.test.cjs"
)
