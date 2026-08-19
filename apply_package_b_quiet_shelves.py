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


def write_stage(path: str, text: str) -> None:
    STAGED[ROOT / path] = text


def replace_once(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise PatchError(
            f"{path}: {label}: expected 1 exact match, found {count}"
        )
    write_stage(path, text.replace(old, new, 1))
    print(f"[CHECK] {path}: {label}")


def insert_after(path: str, anchor: str, addition: str, label: str) -> None:
    text = read(path)
    count = text.count(anchor)
    if count != 1:
        raise PatchError(
            f"{path}: {label}: expected 1 anchor, found {count}"
        )
    write_stage(path, text.replace(anchor, anchor + addition, 1))
    print(f"[CHECK] {path}: {label}")


def replace_between(
    path: str,
    start: str,
    end: str,
    replacement: str,
    label: str,
) -> None:
    text = read(path)
    start_index = text.find(start)
    if start_index < 0:
        raise PatchError(f"{path}: {label}: start marker not found")
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        raise PatchError(f"{path}: {label}: end marker not found")
    new_text = text[:start_index] + replacement + text[end_index:]
    write_stage(path, new_text)
    print(f"[CHECK] {path}: {label}")


def insert_in_section(
    path: str,
    section_start: str,
    section_end: str,
    anchor: str,
    addition: str,
    label: str,
) -> None:
    text = read(path)
    start_index = text.find(section_start)
    end_index = text.find(section_end, start_index + len(section_start))
    if start_index < 0 or end_index < 0:
        raise PatchError(f"{path}: {label}: section not found")
    section = text[start_index:end_index]
    if section.count(anchor) != 1:
        raise PatchError(
            f"{path}: {label}: expected 1 anchor in section, "
            f"found {section.count(anchor)}"
        )
    section = section.replace(anchor, anchor + addition, 1)
    write_stage(path, text[:start_index] + section + text[end_index:])
    print(f"[CHECK] {path}: {label}")


try:
    index_path = "frontend/index.html"

    replace_between(
        index_path,
        '''  <button
    class="continuity-trigger"
''',
        '''  <button
    class="workbench-trigger"
''',
        '''  <button
    class="continuity-trigger"
    id="continuity-trigger"
    type="button"
    aria-expanded="false"
    aria-controls="continuity-surface"
    disabled
  >
    <span>История</span>
    <span
      class="history-count"
      id="history-count"
      aria-label="Сохранённые моменты и открытые нити"
      hidden
    >0</span>
    <span
      class="history-pending-dot"
      id="history-pending-dot"
      aria-label="На полке ждёт предложение памяти"
      hidden
    ></span>
  </button>

''',
        "replace History navigation trigger",
    )

    replace_between(
        index_path,
        '''    <aside class="continuity-surface" id="continuity-surface" aria-label="Наша общая история" hidden>
''',
        '''    <aside class="reflections-surface" id="reflections-surface" aria-label="Мысли Маши и честная помощь" hidden>
''',
        '''    <aside class="continuity-surface" id="continuity-surface" aria-label="Наша общая история" hidden>
      <header class="object-header">
        <div>
          <p class="eyebrow">тихая полка Дома</p>
          <h2>Наша история</h2>
        </div>
        <div class="object-header-actions">
          <button class="surface-action" id="add-shared-moment" type="button">Сохранить момент</button>
          <button class="surface-action" id="add-continuity-thread" type="button">Оставить нить</button>
          <button class="surface-close" id="close-continuity" type="button">Закрыть</button>
        </div>
      </header>

      <p class="object-intro">
        Здесь ничего не перебивает разговор. Мы сами приходим сюда за тем,
        что решили сохранить или не потерять.
      </p>

      <div class="history-glance" id="history-glance" aria-label="Кратко о нашей истории">
        <span><strong id="history-thread-count">0</strong> открытых нитей</span>
        <span><strong id="history-moment-count">0</strong> общих моментов</span>
        <span class="history-glance-memory" id="history-glance-memory" hidden>
          есть предложение памяти
        </span>
      </div>

      <section class="history-inbox" id="history-inbox" aria-live="polite" hidden>
        <span class="continuity-context">на полке ждёт</span>
        <strong id="history-inbox-title">Маша заметила кое-что важное</strong>
        <p id="history-inbox-summary"></p>
        <p class="history-inbox-note" id="history-inbox-note">
          Это ещё не память. Решение остаётся за тобой.
        </p>
        <div class="history-inbox-actions">
          <button id="history-inbox-approve" type="button">Оставить</button>
          <button id="history-inbox-reject" type="button">Не сохранять</button>
        </div>
      </section>

      <div class="continuity-columns" id="continuity-columns">
        <section class="history-column is-threads">
          <h3>К чему вернуться</h3>
          <p class="history-column-hint">Живые незавершённые темы. Только те, что мы оставили явно.</p>
          <ol class="continuity-list" id="continuity-threads"></ol>
        </section>
        <section class="history-column is-moments">
          <h3>Наши моменты</h3>
          <p class="history-column-hint">Подтверждённые общие эпизоды, к которым приятно вернуться.</p>
          <ol class="continuity-list" id="relationship-moments"></ol>
        </section>
      </div>

      <details class="history-search-drawer" id="history-search-drawer">
        <summary>Найти в памяти, истории и делах</summary>
        <div class="history-search">
          <label class="sr-only" for="history-search-input">Найти в нашей истории и делах</label>
          <input
            id="history-search-input"
            type="search"
            maxlength="240"
            autocomplete="off"
            placeholder="Что ищем?"
          >
          <div class="history-search-controls">
            <div class="history-search-scopes" role="group" aria-label="Где искать">
              <button class="is-active" type="button" data-search-scope="all">Всё</button>
              <button type="button" data-search-scope="history">История</button>
              <button type="button" data-search-scope="tasks">Дела</button>
            </div>
            <button
              class="forgotten-search-toggle"
              id="forgotten-search-toggle"
              type="button"
              aria-pressed="false"
            >Забытое</button>
          </div>
          <p class="history-search-hint" id="history-search-hint">
            Поиск открывается только здесь и ничего сам не вытаскивает в разговор.
          </p>
          <ol
            class="history-search-results"
            id="history-search-results"
            aria-live="polite"
            hidden
          ></ol>
        </div>
      </details>
    </aside>
''',
        "replace History shelf",
    )

    app_path = "frontend/renderer/app.js"

    insert_after(
        app_path,
        '''const continuitySurface = document.getElementById("continuity-surface");
''',
        '''const historyCount = document.getElementById("history-count");
const historyPendingDot = document.getElementById("history-pending-dot");
const historyThreadCount = document.getElementById("history-thread-count");
const historyMomentCount = document.getElementById("history-moment-count");
const historyGlanceMemory = document.getElementById("history-glance-memory");
const historyInbox = document.getElementById("history-inbox");
const historyInboxTitle = document.getElementById("history-inbox-title");
const historyInboxSummary = document.getElementById("history-inbox-summary");
const historyInboxNote = document.getElementById("history-inbox-note");
const historyInboxApprove = document.getElementById("history-inbox-approve");
const historyInboxReject = document.getElementById("history-inbox-reject");
''',
        "bind History shelf elements",
    )

    insert_after(
        app_path,
        '''let pendingMemoryCandidate = null;
''',
        '''let continuityItemCount = 0;
''',
        "add History shelf state",
    )

    replace_between(
        app_path,
        '''function renderMemoryCandidate(candidate) {
''',
        '''function revealMemoryCandidate(candidate) {
''',
        '''function updateHistoryShelfState() {
  const total = Math.max(0, Number(continuityItemCount) || 0);
  const waiting = Boolean(pendingMemoryCandidate);

  historyCount.textContent = String(total);
  historyCount.hidden = total <= 0;

  historyPendingDot.hidden = !waiting;
  historyGlanceMemory.hidden = !waiting;
  continuityTrigger.classList.toggle("has-pending-memory", waiting);
}

function renderHistoryInbox() {
  const candidate = pendingMemoryCandidate;

  if (!candidate) {
    historyInbox.hidden = true;
    historyInboxSummary.textContent = "";
    historyInboxApprove.disabled = false;
    historyInboxReject.disabled = false;
    return;
  }

  const isUpdate = candidate.relation === "possible_update";
  historyInbox.hidden = false;
  historyInboxTitle.textContent = isUpdate
    ? "Похоже, что-то изменилось"
    : "Маша заметила кое-что важное";
  historyInboxSummary.textContent = candidate.summary;
  historyInboxNote.textContent = candidate.requires_explicit_supersession
    ? "Есть похожая подтверждённая запись. Новое не заменит её без отдельного решения."
    : "Это ещё не память. Решение остаётся за тобой.";

  historyInboxApprove.disabled = inFlight || Boolean(pendingConfirmation);
  historyInboxReject.disabled = inFlight || Boolean(pendingConfirmation);
}

function renderMemoryCandidate(candidate) {
  /*
   * Passive memory is shelf-owned. It may light a quiet dot on History,
   * but it never takes over the conversation surface on its own.
   */
  pendingMemoryCandidate = candidate || null;
  candidatePresentation.clear();
  memoryCandidateSurface.hidden = true;

  if (document.documentElement.dataset.operation === "candidate") {
    document.documentElement.dataset.operation = "none";
  }

  updateHistoryShelfState();
  renderHistoryInbox();
}

''',
        "make passive memory shelf-owned",
    )

    replace_between(
        app_path,
        '''function renderContinuity(view) {
''',
        '''function renderHumanSearch(items, query) {
''',
        '''function renderContinuity(view) {
  const moments = view?.moments || [];
  const threads = view?.open_threads || [];

  continuityItemCount = moments.length + threads.length;
  historyThreadCount.textContent = String(threads.length);
  historyMomentCount.textContent = String(moments.length);
  updateHistoryShelfState();
  renderHistoryInbox();

  relationshipMoments.replaceChildren();
  continuityThreads.replaceChildren();

  for (const thread of threads) {
    const item = document.createElement("li");
    item.className = "continuity-item is-thread";

    const context = document.createElement("span");
    context.className = "continuity-context";
    context.textContent = "открытая нить";

    const title = document.createElement("strong");
    title.textContent = thread.summary;

    const reason = document.createElement("p");
    reason.textContent = thread.reason_to_return;

    const action = document.createElement("button");
    action.type = "button";
    action.textContent = "Вернуться к этой теме";
    action.addEventListener("click", () => {
      if (!ready || inFlight) return;
      setComposerState({ enabled: true, waiting: true });
      bridge.continueContinuityThread(thread.thread_id);
    });

    item.append(context, title, reason, action);
    continuityThreads.append(item);
  }

  for (const moment of moments) {
    const item = document.createElement("li");
    item.className = "continuity-item is-moment";

    const context = document.createElement("span");
    context.className = "continuity-context";
    context.textContent = "наш момент";

    const title = document.createElement("strong");
    title.textContent = moment.title;

    const text = document.createElement("p");
    text.textContent = moment.text;

    item.append(context, title, text);
    relationshipMoments.append(item);
  }

  if (!continuityThreads.children.length) {
    continuityThreads.append(
      objectEmpty("Открытых нитей сейчас нет. Дом ничего не держит насильно.")
    );
  }

  if (!relationshipMoments.children.length) {
    relationshipMoments.append(
      objectEmpty("Сохранённых общих моментов пока нет.")
    );
  }
}

''',
        "make threads primary and add shelf counts",
    )

    replace_once(
        app_path,
        '''    continuityTrigger.hidden = false;
''',
        '''    continuityTrigger.hidden = false;
    continuityItemCount = Number(payload.continuity_count || 0);
    updateHistoryShelfState();
''',
        "initialize History count",
    )

    replace_once(
        app_path,
        '''    renderConfirmationResult(result);
    commitmentsCount.textContent = String(payload.commitments_count || 0);
    bridge.loadRecentConversations();
''',
        '''    renderConfirmationResult(result);
    commitmentsCount.textContent = String(payload.commitments_count || 0);
    if (payload.continuity_count !== undefined) {
      continuityItemCount = Number(payload.continuity_count || 0);
      updateHistoryShelfState();
    }
    bridge.loadRecentConversations();
''',
        "refresh History count after confirmation",
    )

    replace_between(
        app_path,
        '''  if (payload.kind === "memory_candidate_resolved") {
''',
        '''  if (payload.kind === "reflection_workspace_loaded") {
''',
        '''  if (payload.kind === "memory_candidate_resolved") {
    pendingMemoryCandidate = null;
    memoryCandidateSurface.hidden = true;
    document.documentElement.dataset.operation = "none";
    surfaceStatus.textContent = payload.message;
    renderMemoryCandidate(payload.memory_candidate);

    if (!continuitySurface.hidden) {
      renderHistoryInbox();
    } else {
      surface.hidden = false;
      surface.classList.remove("is-surface-concealed");
    }
    return;
  }

''',
        "keep memory decisions on the shelf",
    )

    insert_after(
        app_path,
        '''rejectMemoryCandidate.addEventListener("click", () => {
  if (!ready || inFlight || !pendingMemoryCandidate) return;
  approveMemoryCandidate.disabled = true;
  rejectMemoryCandidate.disabled = true;
  bridge.resolveMemoryCandidate(pendingMemoryCandidate.candidate_id, "reject");
});
''',
        '''
historyInboxApprove.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation || !pendingMemoryCandidate) return;
  historyInboxApprove.disabled = true;
  historyInboxReject.disabled = true;
  bridge.resolveMemoryCandidate(
    pendingMemoryCandidate.candidate_id,
    "approve"
  );
});

historyInboxReject.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation || !pendingMemoryCandidate) return;
  historyInboxApprove.disabled = true;
  historyInboxReject.disabled = true;
  bridge.resolveMemoryCandidate(
    pendingMemoryCandidate.candidate_id,
    "reject"
  );
});
''',
        "wire shelf memory decisions",
    )

    bridge_path = "backend/ui/conversation_bridge.py"

    insert_in_section(
        bridge_path,
        '''    def _finish_confirmation(self, future) -> None:
''',
        '''    def _finish_honest_help_direct(self, candidate_id: str, decision: str) -> None:
''',
        '''                "snapshot": snapshot.model_dump(mode="json"),
''',
        '''                "continuity_count": (
                    0
                    if self._application is None
                    else self._continuity_count()
                ),
''',
        "include quiet History count in confirmation result",
    )

    css_path = "frontend/styles/home.css"
    css_marker = "/* Package B — quiet shelves */"
    css = read(css_path)
    if css_marker in css:
        raise PatchError(f"{css_path}: Package B styles already present")

    write_stage(
        css_path,
        css
        + r'''

/* Package B — quiet shelves */

.home-nav .history-count {
  display: grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border: 1px solid rgba(226, 188, 126, .2);
  border-radius: 999px;
  color: rgba(244, 218, 180, .72);
  background: rgba(82, 53, 28, .2);
  font: 600 10px/1 system-ui, sans-serif;
  letter-spacing: 0;
  font-variant-numeric: tabular-nums;
}

.home-nav .history-count[hidden],
.home-nav .history-pending-dot[hidden] {
  display: none;
}

.history-pending-dot {
  width: 6px;
  height: 6px;
  margin-left: -3px;
  border-radius: 50%;
  background: rgba(242, 185, 104, .88);
  box-shadow: 0 0 10px rgba(224, 145, 64, .38);
}

.continuity-trigger.has-pending-memory {
  color: rgba(247, 218, 176, .94);
}

html[data-home-moment="special_evening"] .history-pending-dot {
  opacity: .48;
  box-shadow: 0 0 7px rgba(224, 145, 64, .2);
}

.history-glance {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin: -8px 0 24px;
  color: rgba(239, 218, 191, .5);
  font: 500 11px/1.35 system-ui, sans-serif;
}

.history-glance strong {
  color: rgba(249, 230, 204, .86);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.history-glance-memory {
  color: rgba(238, 190, 126, .76);
}

.history-glance-memory[hidden],
.history-inbox[hidden] {
  display: none;
}

.history-inbox {
  margin: 0 0 26px;
  padding: 17px 18px 16px;
  border: 1px solid rgba(226, 188, 126, .13);
  border-left-color: rgba(226, 188, 126, .42);
  background:
    linear-gradient(145deg, rgba(119, 75, 34, .13), rgba(255, 245, 228, .025));
}

.history-inbox > strong {
  display: block;
  margin: 0 0 7px;
  color: rgba(252, 240, 223, .94);
  font: 500 16px/1.35 system-ui, sans-serif;
}

.history-inbox > p {
  margin: 0;
  color: rgba(244, 229, 209, .68);
  font: 400 13px/1.5 system-ui, sans-serif;
}

.history-inbox .history-inbox-note {
  margin-top: 8px;
  color: rgba(236, 223, 207, .44);
  font-size: 11px;
}

.history-inbox-actions {
  display: flex;
  gap: 15px;
  margin-top: 13px;
}

.history-inbox-actions button {
  padding: 5px 0;
  border: 0;
  border-bottom: 1px solid rgba(226, 188, 126, .28);
  color: rgba(239, 202, 147, .84);
  background: transparent;
  font: 600 11px/1.2 system-ui, sans-serif;
  cursor: pointer;
}

.history-inbox-actions button:hover:not(:disabled) {
  color: #ffe5bd;
  border-bottom-color: rgba(239, 202, 147, .64);
}

.history-inbox-actions button:disabled {
  opacity: .38;
  cursor: not-allowed;
}

.history-column {
  min-width: 0;
}

.history-column-hint {
  min-height: 34px;
  margin: -5px 0 12px;
  color: rgba(236, 223, 207, .4);
  font: 400 11px/1.45 system-ui, sans-serif;
}

.continuity-item.is-thread {
  border-left-color: rgba(226, 188, 126, .38);
  background:
    linear-gradient(145deg, rgba(111, 71, 34, .11), rgba(255, 245, 228, .025));
}

.continuity-item.is-moment {
  border-left-color: rgba(226, 188, 126, .16);
  background: rgba(255, 245, 228, .022);
}

.history-search-drawer {
  margin-top: 28px;
  padding-top: 15px;
  border-top: 1px solid rgba(226, 188, 126, .13);
}

.history-search-drawer > summary {
  width: fit-content;
  color: rgba(239, 202, 147, .66);
  font: 600 11px/1.3 system-ui, sans-serif;
  cursor: pointer;
  list-style: none;
}

.history-search-drawer > summary::-webkit-details-marker {
  display: none;
}

.history-search-drawer > summary::after {
  content: "  +";
  color: rgba(239, 202, 147, .42);
}

.history-search-drawer[open] > summary::after {
  content: "  —";
}

.history-search-drawer .history-search {
  margin-top: 17px;
}

html[data-home-moment="special_evening"] .continuity-surface {
  background:
    linear-gradient(145deg, rgba(32, 22, 16, .96), rgba(16, 13, 11, .92));
}

@media (max-width: 1280px) {
  .history-column-hint {
    min-height: 0;
  }
}
''',
    )
    print(f"[CHECK] {css_path}: add quiet shelf styles")

    test_path = ROOT / "frontend/renderer/quiet-shelves.test.cjs"
    if test_path.exists():
        raise PatchError("frontend/renderer/quiet-shelves.test.cjs already exists")

    test_content = r'''"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "styles", "home.css"), "utf8");

assert.match(html, /id="history-count"/);
assert.match(html, /id="history-pending-dot"/);
assert.match(html, /id="history-inbox"/);
assert.match(html, /id="history-search-drawer"/);

assert.match(app, /function updateHistoryShelfState\(\)/);
assert.match(app, /function renderHistoryInbox\(\)/);
assert.match(app, /continuityItemCount/);
assert.doesNotMatch(app, /candidatePresentation\.offer\(candidate\)/);

const threadsAt = html.indexOf('class="history-column is-threads"');
const momentsAt = html.indexOf('class="history-column is-moments"');
assert.ok(threadsAt >= 0 && momentsAt > threadsAt);

assert.match(css, /Package B — quiet shelves/);
assert.match(css, /\.history-pending-dot/);
assert.match(css, /\.history-inbox/);

console.log("quiet shelves tests passed");
'''
    STAGED[test_path] = test_content
    print("[CHECK] frontend/renderer/quiet-shelves.test.cjs: create test")

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
print("Package B applied: quiet shelves.")
print("Review: git diff")
print(
    r"Python smoke: .\.venv\Scripts\python.exe -m pytest "
    r"tests/test_application_boundary.py -q"
)
print(
    r"Frontend smoke: node frontend\renderer\quiet-shelves.test.cjs"
)
