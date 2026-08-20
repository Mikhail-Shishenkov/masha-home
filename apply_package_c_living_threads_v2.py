from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
STAGED: dict[Path, str] = {}


class PatchError(RuntimeError):
    pass


def read(path: str) -> str:
    file_path = ROOT / path
    if file_path not in STAGED:
        if not file_path.exists():
            raise PatchError(f"{path}: file not found")
        STAGED[file_path] = file_path.read_text(encoding="utf-8")
    return STAGED[file_path]


def stage(path: str, text: str) -> None:
    STAGED[ROOT / path] = text


def insert_before(path: str, marker: str, addition: str, label: str) -> None:
    text = read(path)
    count = text.count(marker)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 marker, found {count}")
    stage(path, text.replace(marker, addition + marker, 1))
    print(f"[CHECK] {path}: {label}")


def insert_after(path: str, marker: str, addition: str, label: str) -> None:
    text = read(path)
    count = text.count(marker)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 marker, found {count}")
    stage(path, text.replace(marker, marker + addition, 1))
    print(f"[CHECK] {path}: {label}")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 match, found {count}")
    stage(path, text.replace(old, new, 1))
    print(f"[CHECK] {path}: {label}")


def edit_section(path: str, start_marker: str, end_marker: str, old: str, new: str, label: str) -> None:
    text = read(path)
    start = text.find(start_marker)
    if start < 0:
        raise PatchError(f"{path}: {label}: section start not found")
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise PatchError(f"{path}: {label}: section end not found")
    section = text[start:end]
    count = section.count(old)
    if count != 1:
        raise PatchError(f"{path}: {label}: expected 1 match in section, found {count}")
    section = section.replace(old, new, 1)
    stage(path, text[:start] + section + text[end:])
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

    insert_before(
        "backend/application/continuity.py",
        "    def thread_prompt(self, thread_id: str) -> str:\n",
        """    def thread(self, thread_id: str) -> ContinuityFollowUpView:\n        \"\"\"Return one still-open UI-safe thread or fail closed.\"\"\"\n        matches = [\n            item\n            for item in self.view().open_threads\n            if item.thread_id == thread_id\n        ]\n        if len(matches) != 1:\n            raise KeyError(\"continuity thread not found\")\n        return matches[0]\n\n\n""",
        "add typed thread lookup",
    )

    insert_before(
        "backend/application/conversation.py",
        "    def _confirmation_copy(self, proposal):\n",
        """    def activate_continuity_thread(\n        self,\n        thread_id: str,\n        *,\n        conversation_id: str,\n    ) -> None:\n        \"\"\"Select a thread for the live conversation without sending a turn.\"\"\"\n        self._conversation.history.get(conversation_id)\n        self._active_continuity_by_conversation[conversation_id] = thread_id\n\n    def clear_continuity_thread(self, *, conversation_id: str) -> None:\n        self._active_continuity_by_conversation.pop(conversation_id, None)\n\n    def active_continuity_thread_id(\n        self,\n        *,\n        conversation_id: str,\n    ) -> str | None:\n        return self._active_continuity_by_conversation.get(conversation_id)\n\n""",
        "add ephemeral active-thread API",
    )

    insert_after(
        "backend/application/application.py",
        "    ConversationTurnResult,\n",
        "    ContinuityFollowUpView,\n",
        "import ContinuityFollowUpView",
    )

    insert_after(
        "backend/application/application.py",
        """    def shared_continuity(self) -> SharedContinuityView:\n        return self._continuity.view()\n\n""",
        """    def continuity_thread(self, thread_id: str) -> ContinuityFollowUpView:\n        return self._continuity.thread(thread_id)\n\n    def activate_continuity_thread(\n        self,\n        thread_id: str,\n        *,\n        conversation_id: str | None,\n    ) -> ContinuityFollowUpView:\n        if conversation_id is None:\n            raise ValueError(\"continuity thread needs an active conversation\")\n        thread = self._continuity.thread(thread_id)\n        self._conversation.activate_continuity_thread(\n            thread_id,\n            conversation_id=conversation_id,\n        )\n        return thread\n\n    def clear_continuity_thread(\n        self,\n        *,\n        conversation_id: str | None,\n    ) -> None:\n        if conversation_id is None:\n            return\n        self._conversation.clear_continuity_thread(conversation_id=conversation_id)\n\n    def active_continuity_thread(\n        self,\n        *,\n        conversation_id: str | None,\n    ) -> ContinuityFollowUpView | None:\n        if conversation_id is None:\n            return None\n        thread_id = self._conversation.active_continuity_thread_id(\n            conversation_id=conversation_id,\n        )\n        if thread_id is None:\n            return None\n        try:\n            return self._continuity.thread(thread_id)\n        except KeyError:\n            self._conversation.clear_continuity_thread(conversation_id=conversation_id)\n            return None\n\n""",
        "add public selected-thread boundary",
    )

    insert_before(
        "backend/conversation/context_compiler.py",
        "BEHAVIORAL_CONTRACT = (\n",
        """ACTIVE_CONTINUITY_CONTRACT = (\n    \"АКТИВНАЯ НИТЬ: если active_continuity не null, Миша сам выбрал эту нить \"\n    \"на полке Истории для текущего разговора. Используй summary и reason_to_return \"\n    \"как тихий фон текущей темы, а не как новую команду пользователя. Не начинай \"\n    \"ответ служебной фразой вроде «возвращаемся к теме» и не пересказывай нить без \"\n    \"необходимости. Отвечай прежде всего на текущую реплику Миши. Не придумывай \"\n    \"детали, которых нет в нити, и не объявляй её закрытой или выполненной без \"\n    \"подтверждённого application-действия. Выбор нити не является записью памяти \"\n    \"и сам по себе ничего не меняет.\"\n)\n\n\n""",
        "add active-thread conversation contract",
    )

    replace_once(
        "backend/conversation/context_compiler.py",
        """        context_lens: str = \"general\",\n        home_moment: str = HOME_MOMENT_ORDINARY,\n    ) -> ModelRequest:\n""",
        """        context_lens: str = \"general\",\n        home_moment: str = HOME_MOMENT_ORDINARY,\n        active_continuity: dict[str, str] | None = None,\n    ) -> ModelRequest:\n""",
        "accept structured active thread",
    )

    insert_after(
        "backend/conversation/context_compiler.py",
        "                \"home_moment_contract\": home_moment_contract,\n",
        "                \"active_continuity\": active_continuity,\n                \"active_continuity_contract\": ACTIVE_CONTINUITY_CONTRACT,\n",
        "publish active thread in private context",
    )

    insert_before(
        "backend/conversation/conversation_service.py",
        "        active_profile = None if self.model_profiles is None else self.model_profiles.get_active_profile()\n",
        """        active_continuity = self._active_continuity_context(\n            active_continuity_thread_id\n        )\n""",
        "resolve selected thread before compiling context",
    )

    insert_after(
        "backend/conversation/conversation_service.py",
        "            home_moment=home_moment,\n",
        "            active_continuity=active_continuity,\n",
        "send selected thread to compiler",
    )

    insert_before(
        "backend/conversation/conversation_service.py",
        "    def resolve_memory_proposal(\n",
        """    def _active_continuity_context(\n        self,\n        thread_id: str | None,\n    ) -> dict[str, str] | None:\n        if thread_id is None or self.shared_continuity is None:\n            return None\n\n        matches = [\n            follow_up\n            for _, follow_up in self.shared_continuity.open_follow_ups()\n            if follow_up.id == thread_id\n        ]\n        if len(matches) != 1:\n            return None\n\n        thread = matches[0]\n        return {\n            \"summary\": thread.summary,\n            \"reason_to_return\": thread.reason_to_return,\n            \"topic\": thread.topic,\n        }\n\n""",
        "add selected-thread context resolver",
    )

    insert_after(
        "backend/application/home_snapshot.py",
        """    def opened(self) -> HomeSnapshotView:\n        return self._dispatch(UserOpenedApplication(occurred_at=self._now()))\n""",
        """\n    def conversation_focused(self) -> HomeSnapshotView:\n        \"\"\"Return Presentation focus to conversation without a model turn.\"\"\"\n        return self._dispatch(\n            SurfaceFocused(\n                occurred_at=self._now(),\n                surface_id=\"home.conversation\",\n            )\n        )\n""",
        "add conversation refocus event",
    )

    insert_before(
        "backend/ui/conversation_bridge.py",
        "    @Slot(str)\n    def continueContinuityThread(self, thread_id: str):  # noqa: N802\n",
        """    @Slot(str)\n    def activateContinuityThread(self, thread_id: str):  # noqa: N802\n        \"\"\"Select one History thread as context; do not call the model.\"\"\"\n        if self._application is None or self._turn_in_flight:\n            self._emit({\"kind\": \"continuity_context_unavailable\"})\n            return\n        if self._conversation_id is None:\n            self._emit({\n                \"kind\": \"continuity_context_unavailable\",\n                \"message\": \"Сначала начнём разговор — и тогда нить сможет быть рядом.\",\n            })\n            return\n        try:\n            thread = self._application.activate_continuity_thread(\n                thread_id,\n                conversation_id=self._conversation_id,\n            )\n        except (KeyError, ValueError):\n            self._emit({\"kind\": \"continuity_context_unavailable\"})\n            return\n\n        snapshot = self._session_snapshot(\"conversation_focused\")\n        self._emit({\n            \"kind\": \"continuity_thread_activated\",\n            \"thread\": thread.model_dump(mode=\"json\"),\n            \"snapshot\": snapshot.model_dump(mode=\"json\"),\n        })\n\n    @Slot()\n    def clearContinuityThread(self):  # noqa: N802\n        if self._application is None or self._turn_in_flight:\n            return\n        self._application.clear_continuity_thread(\n            conversation_id=self._conversation_id,\n        )\n        snapshot = self._session_snapshot(\"conversation_focused\")\n        self._emit({\n            \"kind\": \"continuity_thread_cleared\",\n            \"snapshot\": snapshot.model_dump(mode=\"json\"),\n        })\n\n""",
        "add non-speaking thread selection slots",
    )

    insert_after(
        "backend/ui/conversation_bridge.py",
        "                \"continuity_count\": self._continuity_count(),\n",
        "                \"active_continuity_thread\": self._active_continuity_payload(),\n",
        "publish selected thread on Home load",
    )

    edit_section(
        "backend/ui/conversation_bridge.py",
        "    @Slot(str)\n    def openConversation",
        "    @Slot()\n    def startNewConversation",
        "                \"recent\": self._reset_conversation_page_payload(),\n",
        "                \"recent\": self._reset_conversation_page_payload(),\n                \"active_continuity_thread\": self._active_continuity_payload(),\n",
        "publish selected thread on conversation open",
    )

    edit_section(
        "backend/ui/conversation_bridge.py",
        "    def _finish_confirmation(self, future) -> None:\n",
        "    def _finish_honest_help_direct",
        """                \"continuity_count\": (\n                    0\n                    if self._application is None\n                    else self._continuity_count()\n                ),\n""",
        """                \"continuity_count\": (\n                    0\n                    if self._application is None\n                    else self._continuity_count()\n                ),\n                \"active_continuity_thread\": self._active_continuity_payload(),\n""",
        "refresh selected thread after confirmation",
    )

    insert_after(
        "backend/ui/conversation_bridge.py",
        """    def _current_home_moment(self) -> str:\n        # Read under the same lock used by Presentation mutations.\n        with self._session_lock:\n            if self._session is None:\n                return \"ordinary\"\n            return self._session.home_moment.value\n""",
        """\n    def _active_continuity_payload(self) -> dict | None:\n        if self._application is None or self._conversation_id is None:\n            return None\n        thread = self._application.active_continuity_thread(\n            conversation_id=self._conversation_id,\n        )\n        return None if thread is None else thread.model_dump(mode=\"json\")\n""",
        "add selected-thread payload helper",
    )

    insert_after(
        "frontend/index.html",
        "      <p class=\"surface-status\" id=\"surface-status\">Подключаю локальный разговор…</p>\n",
        """      <div class=\"thread-context\" id=\"thread-context\" hidden>\n        <span class=\"thread-context-label\">нить рядом</span>\n        <strong id=\"thread-context-title\"></strong>\n        <button\n          class=\"thread-context-clear\"\n          id=\"thread-context-clear\"\n          type=\"button\"\n          aria-label=\"Убрать выбранную нить из текущего разговора\"\n        >×</button>\n      </div>\n""",
        "add selected-thread chip",
    )

    insert_after(
        "frontend/renderer/app.js",
        "const historyInboxReject = document.getElementById(\"history-inbox-reject\");\n",
        """const threadContext = document.getElementById(\"thread-context\");\nconst threadContextTitle = document.getElementById(\"thread-context-title\");\nconst threadContextClear = document.getElementById(\"thread-context-clear\");\n""",
        "bind selected-thread chip",
    )

    insert_after(
        "frontend/renderer/app.js",
        "let continuityItemCount = 0;\n",
        "let activeContinuityThread = null;\n",
        "add selected-thread UI state",
    )

    insert_before(
        "frontend/renderer/app.js",
        "function renderContinuity(view) {\n",
        """function renderActiveContinuityThread(thread) {\n  activeContinuityThread = thread || null;\n  threadContext.hidden = !activeContinuityThread;\n  threadContextTitle.textContent = activeContinuityThread?.summary || \"\";\n  threadContextClear.disabled = inFlight || !activeContinuityThread;\n}\n\n""",
        "add selected-thread renderer",
    )

    replace_once(
        "frontend/renderer/app.js",
        """    action.textContent = \"Вернуться к этой теме\";\n    action.addEventListener(\"click\", () => {\n      if (!ready || inFlight) return;\n      setComposerState({ enabled: true, waiting: true });\n      bridge.continueContinuityThread(thread.thread_id);\n    });\n""",
        """    action.textContent = (\n      activeContinuityThread?.thread_id === thread.thread_id\n        ? \"Эта нить уже рядом\"\n        : \"Взять эту нить с собой\"\n    );\n    action.disabled =\n      inFlight\n      || activeContinuityThread?.thread_id === thread.thread_id;\n    action.addEventListener(\"click\", () => {\n      if (!ready || inFlight || action.disabled) return;\n      bridge.activateContinuityThread(thread.thread_id);\n    });\n""",
        "select thread without sending a model turn",
    )

    edit_section(
        "frontend/renderer/app.js",
        "  if (payload.kind === \"home_initial\") {\n",
        "  if (payload.kind === \"workbench_loaded\") {\n",
        "    renderMemoryCandidate(payload.memory_candidate);\n",
        "    renderMemoryCandidate(payload.memory_candidate);\n    renderActiveContinuityThread(payload.active_continuity_thread);\n",
        "restore selected thread on Home load",
    )

    edit_section(
        "frontend/renderer/app.js",
        "  if (payload.kind === \"conversation_opened\") {\n",
        "  if (payload.kind === \"turn_started\") {\n",
        "    renderPendingConfirmation(payload.pending_confirmation);\n",
        "    renderPendingConfirmation(payload.pending_confirmation);\n    renderActiveContinuityThread(payload.active_continuity_thread);\n",
        "restore selected thread on conversation switch",
    )

    edit_section(
        "frontend/renderer/app.js",
        "  if (payload.kind === \"conversation_started\") {\n",
        "  if (payload.kind === \"recent_conversations\") {\n",
        "    activeConversationId = null;\n",
        "    activeConversationId = null;\n    renderActiveContinuityThread(null);\n",
        "clear chip for new conversation",
    )

    insert_after(
        "frontend/renderer/app.js",
        """  if (payload.kind === \"shared_continuity_loaded\") {\n    applySnapshot(payload.snapshot);\n    renderContinuity(payload.continuity);\n    continuitySurface.hidden = false;\n    document.documentElement.dataset.objectSurface = \"continuity\";\n    continuityTrigger.setAttribute(\"aria-expanded\", \"true\");\n    return;\n  }\n""",
        """  if (payload.kind === \"continuity_thread_activated\") {\n    applySnapshot(payload.snapshot);\n    renderActiveContinuityThread(payload.thread);\n    returnToConversation();\n    surfaceStatus.textContent = \"Нить рядом. Продолжай своими словами.\";\n    input.focus();\n    return;\n  }\n\n  if (payload.kind === \"continuity_thread_cleared\") {\n    applySnapshot(payload.snapshot);\n    renderActiveContinuityThread(null);\n    surfaceStatus.textContent = \"\";\n    input.focus();\n    return;\n  }\n""",
        "handle selected-thread lifecycle",
    )

    edit_section(
        "frontend/renderer/app.js",
        "  if (payload.kind === \"confirmation_result\") {\n",
        "  if (payload.kind === \"confirmation_rejected\") {\n",
        "    commitmentsCount.textContent = String(payload.commitments_count || 0);\n",
        "    commitmentsCount.textContent = String(payload.commitments_count || 0);\n    renderActiveContinuityThread(payload.active_continuity_thread);\n",
        "sync chip after thread-resolution confirmation",
    )

    replace_once(
        "frontend/renderer/app.js",
        """  if ([\"activities_unavailable\", \"proactive_unavailable\", \"proactive_resolution_rejected\", \"continuity_unavailable\", \"reflections_unavailable\", \"reflection_resolution_rejected\", \"honest_help_rejected\", \"workbench_unavailable\"].includes(payload.kind)) {\n""",
        """  if ([\"activities_unavailable\", \"proactive_unavailable\", \"proactive_resolution_rejected\", \"continuity_unavailable\", \"continuity_context_unavailable\", \"reflections_unavailable\", \"reflection_resolution_rejected\", \"honest_help_rejected\", \"workbench_unavailable\"].includes(payload.kind)) {\n""",
        "include selected-thread unavailable event",
    )

    insert_after(
        "frontend/renderer/app.js",
        """rejectMemoryCandidate.addEventListener(\"click\", () => {\n  if (!ready || inFlight || !pendingMemoryCandidate) return;\n  approveMemoryCandidate.disabled = true;\n  rejectMemoryCandidate.disabled = true;\n  bridge.resolveMemoryCandidate(pendingMemoryCandidate.candidate_id, \"reject\");\n});\n""",
        """\nthreadContextClear.addEventListener(\"click\", () => {\n  if (!ready || inFlight || !activeContinuityThread) return;\n  threadContextClear.disabled = true;\n  bridge.clearContinuityThread();\n});\n""",
        "wire selected-thread clear action",
    )

    append_once(
        "frontend/styles/home.css",
        "/* Package C — living threads */",
        r'''/* Package C — living threads */

.thread-context {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  margin: -5px 0 13px;
  padding: 7px 9px;
  border-left: 1px solid rgba(226, 188, 126, .28);
  background: rgba(108, 70, 35, .08);
  color: rgba(244, 226, 203, .68);
  font: 500 11px/1.3 system-ui, sans-serif;
}

.thread-context[hidden] { display: none; }
.thread-context-label {
  color: rgba(224, 180, 118, .58);
  text-transform: uppercase;
  letter-spacing: .11em;
  font-size: 8px;
  white-space: nowrap;
}
.thread-context strong {
  min-width: 0;
  overflow: hidden;
  color: rgba(249, 235, 214, .82);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.thread-context-clear {
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  color: rgba(239, 202, 147, .58);
  background: transparent;
  font: 400 17px/1 system-ui, sans-serif;
  cursor: pointer;
}
.thread-context-clear:hover:not(:disabled) {
  color: #ffe5bd;
  background: rgba(226, 188, 126, .07);
}
.thread-context-clear:disabled { opacity: .3; cursor: default; }
html[data-home-moment="special_evening"] .thread-context {
  border-left-color: rgba(226, 188, 126, .18);
  background: rgba(70, 41, 24, .06);
}
html[data-home-moment="special_evening"] .thread-context-label {
  color: rgba(224, 180, 118, .42);
}
html[data-home-moment="special_evening"] .thread-context strong {
  color: rgba(249, 235, 214, .68);
}
''',
        "add living-thread styles",
    )

    append_once(
        "tests/test_context_compiler.py",
        "def test_active_continuity_is_structured_background_not_synthetic_user_text(",
        r'''def test_active_continuity_is_structured_background_not_synthetic_user_text():
    compiler = ConversationContextCompiler(
        lambda: datetime(2026, 8, 20, 1, 30, tzinfo=timezone.utc)
    )
    identity = IdentityKernel(
        IdentityStore(PROJECT_ROOT / "identity" / "masha.identity.json")
    ).build_context()

    request = compiler.compile(
        messages=(ModelMessage(role="user", content="Я бы начал с места у воды."),),
        identity_context=identity,
        working_memory=[],
        active_continuity={
            "summary": "Обсудить нашу будущую поездку к морю",
            "reason_to_return": "Вернуться к выбору места и времени",
            "topic": "поездка к морю",
        },
    )

    assert request.messages[-1].content == "Я бы начал с места у воды."
    assert request.private_context["active_continuity"]["summary"] == (
        "Обсудить нашу будущую поездку к морю"
    )
    assert "тихий фон" in request.private_context["active_continuity_contract"]
''',
        "add compiler selected-thread test",
    )

    append_once(
        "tests/test_application_boundary.py",
        "def test_selected_continuity_thread_is_context_not_synthetic_turn(",
        r'''def test_selected_continuity_thread_is_context_not_synthetic_turn(tmp_path):
    _, provider, application = _application(tmp_path)

    first = application.send_message("Привет, Маш.", project_id=PROJECT_ID)
    conversation_id = first.conversation_id

    handler = application._conversation._conversation.memory_intent_handler
    assert handler is not None
    continuity = handler.shared_continuity
    assert continuity is not None

    proposal = continuity.propose_open_thread(
        handler.proposal_store,
        text="Обсудить нашу будущую поездку к морю",
        conversation_id=conversation_id,
        reason_to_return="Вернуться к выбору места и времени",
    )
    continuity.confirm_proposal(proposal, handler.proposal_store)

    thread = next(
        item
        for item in application.shared_continuity().open_threads
        if item.summary == "Обсудить нашу будущую поездку к морю"
    )

    requests_before = len(provider.requests)
    messages_before = len(application.conversation(conversation_id).messages)

    selected = application.activate_continuity_thread(
        thread.thread_id,
        conversation_id=conversation_id,
    )

    assert selected.thread_id == thread.thread_id
    assert len(provider.requests) == requests_before
    assert len(application.conversation(conversation_id).messages) == messages_before

    result = application.send_message(
        "Я бы начал с места, где вечером можно просто гулять у воды.",
        project_id=PROJECT_ID,
        conversation_id=conversation_id,
    )
    assert result.status is ConversationTurnStatus.COMPLETED

    conversation_requests = [
        request
        for request in provider.requests
        if request.private_context.get("active_continuity")
    ]
    assert conversation_requests
    active = conversation_requests[-1].private_context["active_continuity"]
    assert active["summary"] == "Обсудить нашу будущую поездку к морю"
    assert active["reason_to_return"] == "Вернуться к выбору места и времени"

    application.clear_continuity_thread(conversation_id=conversation_id)
    assert application.active_continuity_thread(conversation_id=conversation_id) is None
''',
        "add selected-thread integration test",
    )

    test_file = ROOT / "frontend/renderer/living-threads.test.cjs"
    if test_file.exists():
        raise PatchError("frontend/renderer/living-threads.test.cjs already exists")
    STAGED[test_file] = r'''"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "styles", "home.css"), "utf8");

assert.match(html, /id="thread-context"/);
assert.match(html, /id="thread-context-title"/);
assert.match(html, /id="thread-context-clear"/);
assert.match(app, /function renderActiveContinuityThread\(thread\)/);
assert.match(app, /bridge\.activateContinuityThread\(thread\.thread_id\)/);
assert.match(app, /bridge\.clearContinuityThread\(\)/);
assert.doesNotMatch(app, /bridge\.continueContinuityThread\(thread\.thread_id\)/);
assert.match(css, /Package C — living threads/);
assert.match(css, /\.thread-context/);
console.log("living threads tests passed");
'''
    print("[CHECK] frontend/renderer/living-threads.test.cjs: create test")

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
print("Package C v2 applied: living threads.")
print("Review: git diff")
print(r"Python: .\.venv\Scripts\python.exe -m pytest tests/test_context_compiler.py tests/test_application_boundary.py -q")
print(r"Frontend: node frontend\renderer\quiet-shelves.test.cjs")
print(r"Frontend: node frontend\renderer\living-threads.test.cjs")
