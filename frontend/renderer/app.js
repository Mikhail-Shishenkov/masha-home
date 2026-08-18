"use strict";

// UI-05D talks only to the closed `mashaHome` WebChannel object. It has no
// browser network access and no references to Python/domain services.
document.documentElement.dataset.renderer = "local-shell";
const interactionSafety = window.MashaInteractionSafety;

const surface = document.getElementById("conversation-surface");
const transcript = document.getElementById("transcript");
const composer = document.getElementById("composer");
const input = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const newConversationButton = document.getElementById("new-conversation");
const recentToggle = document.getElementById("recent-conversations-toggle");
const recentPanel = document.getElementById("recent-conversations");
const recentList = document.getElementById("recent-list");
const loadMoreConversations = document.getElementById("load-more-conversations");
const title = document.getElementById("conversation-title");
const surfaceStatus = document.getElementById("surface-status");
const runtimeTruth = document.getElementById("runtime-truth");
const homeAttentionTrigger = document.getElementById("home-attention-trigger");
const homeAttention = document.getElementById("home-attention");
const homeAttentionTitle =
  document.getElementById("home-attention-title");
const attentionLines = document.getElementById("attention-lines");
const safetyTrigger = document.getElementById("safety-trigger");
const safetyOverlay = document.getElementById("safety-overlay");
const resumeAction = document.getElementById("resume-action");
const sceneLayers = [...document.querySelectorAll(".scene")];
const operationSurface = document.getElementById("operation-surface");
const operationEyebrow = document.getElementById("operation-eyebrow");
const operationTitle = document.getElementById("operation-title");
const operationSubject = document.getElementById("operation-subject");
const operationDue = document.getElementById("operation-due");
const operationSteps = document.getElementById("operation-steps");
const operationActions = document.getElementById("operation-actions");
const confirmOperation = document.getElementById("confirm-operation");
const rejectOperation = document.getElementById("reject-operation");
const closeOperation = document.getElementById("close-operation");
const commitmentsTrigger = document.getElementById("commitments-trigger");
const commitmentsCount = document.getElementById("commitments-count");
const commitmentsSurface = document.getElementById("commitments-surface");
const commitmentsList = document.getElementById("commitments-list");
const loadMoreCommitments = document.getElementById("load-more-commitments");
const closeCommitments = document.getElementById("close-commitments");
const activityTrigger = document.getElementById("activity-trigger");
const activitySurface = document.getElementById("activity-surface");
const agentRunList = document.getElementById("agent-run-list");
const closeActivity = document.getElementById("close-activity");
const proactiveTrigger = document.getElementById("proactive-trigger");
const proactiveSurface = document.getElementById("proactive-surface");
const proactiveList = document.getElementById("proactive-list");
const closeProactive = document.getElementById("close-proactive");
const continuityTrigger = document.getElementById("continuity-trigger");
const continuitySurface = document.getElementById("continuity-surface");
const relationshipMoments = document.getElementById("relationship-moments");
const continuityThreads = document.getElementById("continuity-threads");
const closeContinuity = document.getElementById("close-continuity");
const reflectionsTrigger = document.getElementById("reflections-trigger");
const reflectionsSurface = document.getElementById("reflections-surface");
const reflectionList = document.getElementById("reflection-list");
const closeReflections = document.getElementById("close-reflections");
const workbenchTrigger = document.getElementById("workbench-trigger");
const workbenchSurface = document.getElementById("workbench-surface");
const workbenchModels = document.getElementById("workbench-models");
const workbenchSkills = document.getElementById("workbench-skills");
const workbenchPermissions = document.getElementById("workbench-permissions");
const closeWorkbench = document.getElementById("close-workbench");
const addCommitment = document.getElementById("add-commitment");
const commitmentCreateSurface = document.getElementById("commitment-create-surface");
const commitmentTitle = document.getElementById("commitment-title");
const commitmentDue = document.getElementById("commitment-due");
const submitCommitment = document.getElementById("submit-commitment");
const cancelCommitment = document.getElementById("cancel-commitment");
const addSkill = document.getElementById("add-skill");
const skillInstallSurface = document.getElementById("skill-install-surface");
const skillInstallTitle = document.getElementById("skill-install-title");
const skillInstallCopy = document.getElementById("skill-install-copy");
const confirmSkillInstall = document.getElementById("confirm-skill-install");
const rejectSkillInstall = document.getElementById("reject-skill-install");
const addSharedMoment = document.getElementById("add-shared-moment");
const addContinuityThread = document.getElementById("add-continuity-thread");
const continuityCreateSurface = document.getElementById("continuity-create-surface");
const continuityCreateEyebrow = document.getElementById("continuity-create-eyebrow");
const continuityCreateTitle = document.getElementById("continuity-create-title");
const continuityCreateText = document.getElementById("continuity-create-text");
const submitContinuity = document.getElementById("submit-continuity");
const cancelContinuity = document.getElementById("cancel-continuity");
const historySearchInput = document.getElementById("history-search-input");
const historySearchResults = document.getElementById("history-search-results");
const historySearchHint = document.getElementById("history-search-hint");
const continuityColumns = document.getElementById("continuity-columns");
const historySearchScopes = [...document.querySelectorAll("[data-search-scope]")];
const forgottenSearchToggle = document.getElementById("forgotten-search-toggle");
const memoryCandidateSurface = document.getElementById("memory-candidate-surface");
const memoryCandidateEyebrow = document.getElementById("memory-candidate-eyebrow");
const memoryCandidateTitle = document.getElementById("memory-candidate-title");
const memoryCandidateSummary = document.getElementById("memory-candidate-summary");
const memoryCandidateNote = document.getElementById("memory-candidate-note");
const approveMemoryCandidate = document.getElementById("approve-memory-candidate");
const rejectMemoryCandidate = document.getElementById("reject-memory-candidate");

let bridge = null;
let ready = false;
let inFlight = false;
let provisionalUser = null;
let activeSceneId = "scene.home.idle";
let activeSceneLayer = 0;
let activeConversationId = null;
let recentPageState = { revision: -1, nextOffset: null, ids: new Set() };
let sceneTransitionRevision = 0;
let sceneTransitionTimer = null;
let sceneSettleTimer = null;
let activeSceneChangedAt = performance.now();
let pendingConfirmation = null;
let pendingMemoryCandidate = null;
let historySearchScope = "all";
let historySearchForgotten = false;
let historySearchTimer = null;
let pendingSkillInstall = null;
let continuityCreateKind = null;
const attentionMagicState = {
  commitments: 0,
  freshOverdueCommitments: 0,
  proactive: 0,
  pendingConfirmation: false,
  modelAvailable: true,
  safetyEngaged: false,
};

function resolveAttentionMagicLevel(state) {
    if (state.safetyEngaged) {
    return "quiet";
  }

  if (state.freshOverdueCommitments > 0) {
    return "urgent";
  }

  if (!state.modelAvailable) {
    return "urgent";
  }

  const reasons =
    state.commitments
    + state.proactive
    + (state.pendingConfirmation ? 1 : 0);

  if (state.pendingConfirmation) {
    return reasons >= 4 ? "center" : "whisper";
  }

  if (reasons <= 0) return "quiet";
  if (reasons === 1) return "glance";
  if (reasons <= 3) return "whisper";

  return "center";
}

function resolveAttentionMagicSource(state) {
  if (state.proactive > 0 && state.commitments > 0) {
    return "mixed";
  }

  if (state.proactive > 0) {
    return "initiative";
  }

  if (state.pendingConfirmation) {
    return "decision";
  }

  if (state.commitments > 0) {
    return "commitments";
  }

  return "quiet";
}

function attentionReasonCount(state) {
  return (
    state.commitments
    + state.proactive
    + (state.pendingConfirmation ? 1 : 0)
  );
}

function triggerAttentionNoveltyIfNeeded(state) {
  const nextCount = attentionReasonCount(state);

  if (lastAttentionReasonCount === null) {
    lastAttentionReasonCount = nextCount;
    return;
  }

  if (nextCount > lastAttentionReasonCount) {
    clearTimeout(attentionNoveltyTimer);

    homeAttentionTrigger.classList.remove("is-new-attention");

    void homeAttentionTrigger.offsetWidth;

    homeAttentionTrigger.classList.add("is-new-attention");

    attentionNoveltyTimer = window.setTimeout(() => {
      homeAttentionTrigger.classList.remove("is-new-attention");
      attentionNoveltyTimer = null;
    }, 1100);
  }

  lastAttentionReasonCount = nextCount;
}

function acknowledgeAttentionNovelty() {
  clearTimeout(attentionNoveltyTimer);
  attentionNoveltyTimer = null;

  homeAttentionTrigger.classList.remove("is-new-attention");

  lastAttentionReasonCount =
    attentionReasonCount(attentionMagicState);
}

function updateAttentionMagic() {
  homeAttentionTrigger.dataset.attentionLevel =
    resolveAttentionMagicLevel(attentionMagicState);

  homeAttentionTrigger.dataset.attentionSource =
    resolveAttentionMagicSource(attentionMagicState);

  triggerAttentionNoveltyIfNeeded(attentionMagicState);
}
let lastAttentionReasonCount = null;
let attentionNoveltyTimer = null;
const COMPOSER_MIN_HEIGHT = 44;
const COMPOSER_MAX_HEIGHT = 112;
const SURFACE_EXIT_MS = 200;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let surfaceTransitionTimer = null;
const candidatePresentation = window.MashaCandidatePresentation.create({
  delayMs: 1200,
  isQuiet: isCandidatePresentationQuiet,
  onReveal: revealMemoryCandidate,
  setTimer: window.setTimeout.bind(window),
  clearTimer: window.clearTimeout.bind(window),
});
const historyViewTransition = window.MashaExclusiveViewTransition.create({
  history: continuityColumns,
  search: historySearchResults,
  exitMs: reducedMotion.matches ? 0 : 110,
  setTimer: window.setTimeout.bind(window),
  clearTimer: window.clearTimeout.bind(window),
  requestFrame: window.requestAnimationFrame.bind(window),
});

function fitComposer() {
  input.style.height = `${COMPOSER_MIN_HEIGHT}px`;
  input.style.height = `${Math.min(input.scrollHeight, COMPOSER_MAX_HEIGHT)}px`;
  input.classList.toggle("is-scrollable", input.scrollHeight > COMPOSER_MAX_HEIGHT);
}

function applyScene(presentation) {
  const next = window.MashaSceneMap.resolveScene(presentation);
  document.documentElement.dataset.scene = next.id;
  const revision = ++sceneTransitionRevision;
  const transition = window.MashaSceneMap.resolveTransition({
    presentation,
    reducedMotion: reducedMotion.matches,
  });
  clearTimeout(sceneSettleTimer);
  if (next.id === activeSceneId) {
    clearTimeout(sceneTransitionTimer);
    sceneTransitionTimer = null;
    window.MashaSceneTransitionSafety.restoreActiveLayer(
      sceneLayers,
      activeSceneLayer,
    );
    return;
  }
  const heldFor = performance.now() - activeSceneChangedAt;
  const holdDelay = Math.max(0, transition.minimumHoldMs - heldFor);
  const delay = Math.max(transition.settleMs, holdDelay);
  sceneSettleTimer = window.setTimeout(
    () => commitScene(next, transition, revision),
    delay,
  );
}

function commitScene(next, transition, revision) {
  if (revision !== sceneTransitionRevision || next.id === activeSceneId) return;

  const current = sceneLayers[activeSceneLayer];
  const incoming = sceneLayers[1 - activeSceneLayer];

  document.documentElement.dataset.sceneTransition = transition.kind;
  document.documentElement.style.setProperty(
    "--scene-exit-ms",
    `${transition.exitMs}ms`
  );
  document.documentElement.style.setProperty(
    "--scene-enter-ms",
    `${transition.enterMs}ms`
  );

  clearTimeout(sceneTransitionTimer);

  let transitionStarted = false;

  /*
   * Always begin from a known two-layer state.
   * The current scene stays fully visible underneath the incoming scene.
   */
  for (const layer of sceneLayers) {
    layer.onload = null;
    layer.onerror = null;
    layer.classList.remove(
      "is-incoming",
      "is-revealed",
      "is-leaving"
    );
  }

  current.classList.add("is-active");
  incoming.classList.remove("is-active");

  const completeTransition = () => {
    if (revision !== sceneTransitionRevision) return;

    current.classList.remove(
      "is-active",
      "is-leaving"
    );

    incoming.classList.remove(
      "is-incoming",
      "is-revealed"
    );
    incoming.classList.add("is-active");

    activeSceneLayer = sceneLayers.indexOf(incoming);
    activeSceneId = next.id;
    activeSceneChangedAt = performance.now();

    sceneTransitionTimer = null;
  };

  const showIncoming = () => {
    if (
      revision !== sceneTransitionRevision
      || transitionStarted
    ) return;

    transitionStarted = true;

    incoming.alt = next.alt;
    incoming.classList.add("is-incoming");

    /*
     * Important:
     * give Chromium one rendered frame with the incoming layer at opacity 0.
     * Only on the following frame do we reveal it.
     *
     * The outgoing scene never fades to black first. The incoming scene
     * dissolves directly over the still-visible room.
     */
    void incoming.offsetWidth;

    window.requestAnimationFrame(() => {
      if (revision !== sceneTransitionRevision) return;

      incoming.classList.add("is-revealed");

      sceneTransitionTimer = window.setTimeout(
        completeTransition,
        transition.enterMs + 40
      );
    });
  };

  incoming.onload = showIncoming;

  incoming.onerror = () => {
    if (revision !== sceneTransitionRevision) return;

    incoming.src = "assets/presence/evening/idle.png";
    incoming.alt = "Маша дома, в своей гостиной";
  };

  incoming.src = next.source;

  /*
   * Preloaded/cached images may already be complete.
   */
  if (incoming.complete) {
    showIncoming();
  }
}

function nearLatest() {
  return transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 72;
}

function scrollToLatestIfAppropriate(force = false) {
  if (force || nearLatest()) transcript.scrollTop = transcript.scrollHeight;
}

function setComposerState({ enabled, waiting = false }) {
  inFlight = waiting;
  input.disabled = !enabled || waiting;
  sendButton.disabled = !enabled || waiting || !input.value.trim();
  newConversationButton.disabled = !enabled || waiting;
  recentToggle.disabled = !enabled || waiting;
  homeAttentionTrigger.disabled = !enabled || waiting;
  commitmentsTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  activityTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  proactiveTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  continuityTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  reflectionsTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  workbenchTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  safetyTrigger.disabled = !enabled;
}

function closeTemporarySurfaces() {
  recentPanel.hidden = true;
  homeAttention.hidden = true;
  commitmentsSurface.hidden = true;
  activitySurface.hidden = true;
  proactiveSurface.hidden = true;
  continuitySurface.hidden = true;
  reflectionsSurface.hidden = true;
  workbenchSurface.hidden = true;
  commitmentCreateSurface.hidden = true;
  skillInstallSurface.hidden = true;
  continuityCreateSurface.hidden = true;
  memoryCandidateSurface.hidden = true;
  document.documentElement.dataset.commitments = "closed";
  document.documentElement.dataset.homeAttention = "closed";
  document.documentElement.dataset.objectSurface = "closed";
  recentToggle.setAttribute("aria-expanded", "false");
  homeAttentionTrigger.setAttribute("aria-expanded", "false");
  commitmentsTrigger.setAttribute("aria-expanded", "false");
  activityTrigger.setAttribute("aria-expanded", "false");
  proactiveTrigger.setAttribute("aria-expanded", "false");
  continuityTrigger.setAttribute("aria-expanded", "false");
  reflectionsTrigger.setAttribute("aria-expanded", "false");
  workbenchTrigger.setAttribute("aria-expanded", "false");
}

function transitionToSurface(open, { preserveCandidate = false } = {}) {
  if (!preserveCandidate) candidatePresentation.defer();
  clearTimeout(surfaceTransitionTimer);
  const visible = [
    surface,
    recentPanel,
    homeAttention,
    commitmentsSurface,
    activitySurface,
    proactiveSurface,
    continuitySurface,
    reflectionsSurface,
    workbenchSurface,
    operationSurface, memoryCandidateSurface, commitmentCreateSurface, skillInstallSurface, continuityCreateSurface,
  ].filter((element) => !element.hidden);
  for (const element of visible) element.classList.add("is-surface-leaving");
  surfaceTransitionTimer = window.setTimeout(() => {
    closeTemporarySurfaces();
    hideOperationSurface();
    surface.classList.remove("is-surface-leaving");
    surface.classList.add("is-surface-concealed");
    surface.hidden = true;
    for (const element of visible) element.classList.remove("is-surface-leaving");
    open();
  }, reducedMotion.matches ? 0 : SURFACE_EXIT_MS);
}

function returnToConversation() {
  candidatePresentation.defer();
  clearTimeout(surfaceTransitionTimer);
  const visible = [commitmentsSurface, activitySurface, proactiveSurface, continuitySurface, reflectionsSurface, workbenchSurface, operationSurface]
    .filter((element) => !element.hidden);
  for (const element of visible) element.classList.add("is-surface-leaving");
  surfaceTransitionTimer = window.setTimeout(() => {
    closeTemporarySurfaces();
    hideOperationSurface();
    for (const element of visible) element.classList.remove("is-surface-leaving");
    surface.hidden = false;
    // Force the hidden shell to become a distinct rendered frame before its
    // normal opacity transition begins.  The conversation is absolutely
    // positioned, so this does not reflow the room or the active surface.
    void surface.offsetWidth;
    surface.classList.remove("is-surface-concealed");
    input.focus();
    candidatePresentation.reconsider();
  }, reducedMotion.matches ? 0 : SURFACE_EXIT_MS);
}

function workbenchItem(title, detail) {
  const item = document.createElement("li");
  item.className = "workbench-item";
  item.append(
    Object.assign(document.createElement("h4"), { textContent: title }),
    Object.assign(document.createElement("p"), { textContent: detail }),
  );
  return item;
}

function humanCapability(capability) {
  return {
    text: "разговор и тексты",
    thinking: "рассуждение",
    vision: "работа с изображениями",
    tools: "инструменты",
    structured_output: "структурированные ответы",
  }[capability] || "локальная возможность";
}

function humanProfileTitle(profile) {
  if (profile.profile_id === "primary") return "Основная";
  if (profile.profile_id === "fast") return "Быстрая";
  return profile.display_name;
}

function modelItem(profile) {
  const status = profile.active ? "сейчас" : profile.available ? "доступна локально" : "сейчас недоступна";
  const item = workbenchItem(
    `${humanProfileTitle(profile)}${profile.active ? " · сейчас" : ""}`,
    `${profile.model_id || "Модель ещё не настроена"} · ${status}`,
  );
  if (!profile.active) {
    const action = document.createElement("button");
    action.type = "button";
    action.textContent = "Использовать";
    action.disabled = !profile.available || !profile.enabled || inFlight;
    action.addEventListener("click", () => bridge.useModelProfile(profile.profile_id));
    item.append(action);
  }
  return item;
}

function renderWorkbench(view) {
  workbenchModels.replaceChildren();
  workbenchSkills.replaceChildren();
  workbenchPermissions.replaceChildren();
  const profiles = view?.profiles || [];
  const familiarProfiles = profiles.filter((profile) => profile.profile_id === "primary" || profile.profile_id === "fast");
  const otherProfiles = profiles.filter((profile) => !familiarProfiles.includes(profile));
  for (const profile of familiarProfiles) {
    workbenchModels.append(modelItem(profile));
  }
  if (otherProfiles.length) {
    const details = document.createElement("details");
    details.className = "workbench-other-options";
    const summary = document.createElement("summary");
    summary.textContent = "Другие варианты";
    const list = document.createElement("ol");
    list.className = "workbench-list";
    for (const profile of otherProfiles) list.append(modelItem(profile));
    details.append(summary, list);
    const item = document.createElement("li");
    item.className = "workbench-other";
    item.append(details);
    workbenchModels.append(item);
  }
  for (const skill of view?.skills || []) {
    const capabilityText = skill.capabilities.length
      ? skill.capabilities.map(humanCapability).join(", ")
      : "пока без доступных действий";
    workbenchSkills.append(workbenchItem(
      skill.name,
      skill.runtime_supported ? `Могу использовать для: ${capabilityText}.` : "Пока просто хранится здесь и ничего не запускает.",
    ));
  }
  const skillNames = new Map((view?.skills || []).map((skill) => [skill.skill_id, skill.name]));
  for (const grant of view?.grants || []) {
    workbenchPermissions.append(workbenchItem(
      grant.mode === "self" ? "Могу сама" : grant.mode === "forbidden" ? "Запрещено" : "Сначала спрошу тебя",
      `${skillNames.get(grant.skill_id) || "Этот навык"} · ${humanCapability(grant.capability)}`,
    ));
  }
  for (const pending of view?.pending || []) {
    workbenchPermissions.append(workbenchItem(
      "Сначала спрошу тебя",
      pending.title,
    ));
  }
  if (!workbenchModels.children.length) workbenchModels.append(objectEmpty("Профили моделей пока не настроены."));
  if (!workbenchSkills.children.length) workbenchSkills.append(objectEmpty("Навыков в локальном реестре пока нет."));
  if (!workbenchPermissions.children.length) workbenchPermissions.append(objectEmpty("Постоянных разрешений и ожидающих решений нет."));
}

function renderContinuity(view) {
  relationshipMoments.replaceChildren();
  continuityThreads.replaceChildren();
  for (const moment of view?.moments || []) {
    const item = document.createElement("li");
    item.className = "continuity-item";
    const title = document.createElement("strong");
    title.textContent = moment.title;
    const text = document.createElement("p");
    text.textContent = moment.text;
    item.append(title, text);
    relationshipMoments.append(item);
  }
  for (const thread of view?.open_threads || []) {
    const item = document.createElement("li");
    item.className = "continuity-item is-thread";
    const title = document.createElement("strong");
    title.textContent = thread.summary;
    const reason = document.createElement("p");
    reason.textContent = thread.reason_to_return;
    const context = document.createElement("span");
    context.className = "continuity-context";
    context.textContent = "открытая нить";
    const action = document.createElement("button");
    action.type = "button";
    action.textContent = "Продолжить в разговоре";
    action.addEventListener("click", () => {
      if (!ready || inFlight) return;
      setComposerState({ enabled: true, waiting: true });
      bridge.continueContinuityThread(thread.thread_id);
    });
    item.append(context, title, reason, action);
    continuityThreads.append(item);
  }
  if (!relationshipMoments.children.length) relationshipMoments.append(objectEmpty("Наших сохранённых моментов пока нет."));
  if (!continuityThreads.children.length) continuityThreads.append(objectEmpty("Открытых нитей сейчас нет."));
}

function renderHumanSearch(items, query) {
  historySearchResults.replaceChildren();
  if (!query) {
    historySearchHint.textContent = "Здесь находятся и нынешние дела, и то, что уже осталось в прошлом.";
    historyViewTransition.show("history");
    return;
  }
  historySearchHint.textContent = historySearchForgotten
    ? "Это то, что ты просил меня не использовать. Вернуть можно только с твоего подтверждения."
    : "Текущее остаётся ближе, а завершённое и прошлое отмечены тише.";
  if (!items.length) {
    historySearchResults.append(objectEmpty(
      historySearchForgotten
        ? "Среди забытого ничего похожего не нашла."
        : "Пока ничего похожего не нашла.",
    ));
    historyViewTransition.show("search");
    return;
  }
  for (const result of items) {
    const presentation = window.MashaHumanInformation.describe(result);
    const row = document.createElement("li");
    row.className = `continuity-item search-result is-${presentation.tone}`;
    row.append(
      Object.assign(document.createElement("span"), { className: "search-result-context", textContent: presentation.context }),
      Object.assign(document.createElement("p"), { className: "search-result-label", textContent: result.label }),
    );
    if (result.can_restore) {
      const restore = document.createElement("button");
      restore.type = "button";
      restore.textContent = "Вернуть в память";
      restore.addEventListener("click", () => {
        if (!ready || inFlight || pendingConfirmation) return;
        restore.disabled = true;
        bridge.restoreInformation(result.reference);
      });
      row.append(restore);
    }
    historySearchResults.append(row);
  }
  historyViewTransition.show("search");
}

function showHumanSearchPending(query) {
  if (!query) return;
  historySearchResults.replaceChildren(objectEmpty("Ищу в нашем доме…"));
  historySearchHint.textContent = historySearchForgotten
    ? "Это то, что ты просил меня не использовать."
    : "Ищу среди нынешнего и того, что осталось в прошлом.";
  historyViewTransition.show("search");
}

function resetHumanSearchUi() {
  clearTimeout(historySearchTimer);
  historySearchInput.value = "";
  historySearchInput.placeholder = "Найти в нашем доме";
  historySearchScope = "all";
  historySearchForgotten = false;
  forgottenSearchToggle.classList.remove("is-active");
  forgottenSearchToggle.setAttribute("aria-pressed", "false");
  for (const choice of historySearchScopes) {
    choice.classList.toggle("is-active", choice.dataset.searchScope === "all");
  }
  renderHumanSearch([], "");
}

function isCandidatePresentationQuiet() {
  const objectSurface = document.documentElement.dataset.objectSurface;
  return Boolean(
    ready
    && pendingMemoryCandidate
    && !inFlight
    && !pendingConfirmation
    && !input.value.trim()
    && safetyOverlay.hidden
    && !surface.hidden
    && recentPanel.hidden
    && [undefined, "", "closed"].includes(objectSurface)
    && operationSurface.hidden
    && memoryCandidateSurface.hidden
  );
}

function renderMemoryCandidate(candidate) {
  pendingMemoryCandidate = candidate || null;
  if (!candidate) {
    candidatePresentation.clear();
    memoryCandidateSurface.hidden = true;
    return;
  }
  candidatePresentation.offer(candidate);
}

function revealMemoryCandidate(candidate) {
  if (
    !candidate
    || candidate !== pendingMemoryCandidate
    || !isCandidatePresentationQuiet()
  ) return;
  const isUpdate = candidate.relation === "possible_update";
  memoryCandidateEyebrow.textContent = isUpdate ? "похоже, это изменилось" : "мне кажется, это стоит помнить";
  memoryCandidateTitle.textContent = isUpdate ? "Оставить новое?" : "Может быть, это стоит помнить?";
  memoryCandidateSummary.textContent = candidate.summary;
  memoryCandidateNote.textContent = isUpdate
    ? "То, что было раньше, останется в нашей истории."
    : "Только если тебе хочется, чтобы это осталось с нами.";
  approveMemoryCandidate.textContent = isUpdate ? "Да, оставить новое" : "Запомнить";
  approveMemoryCandidate.disabled = false;
  rejectMemoryCandidate.disabled = false;
  transitionToSurface(() => {
    memoryCandidateSurface.hidden = false;
    document.documentElement.dataset.operation = "candidate";
  }, { preserveCandidate: true });
}

function objectEmpty(text) {
  const item = document.createElement("li");
  item.className = "object-empty";
  item.textContent = text;
  return item;
}

function reflectionActions(candidateId, actions, resolver) {
  const row = document.createElement("div");
  row.className = "object-actions";
  const labels = { adopt: "Согласен сохранить", reject: "Не согласен", accept: "Давай, помоги", dismiss: "Не сейчас" };
  for (const decision of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = labels[decision] || decision;
    button.addEventListener("click", () => {
      if (!ready || inFlight) return;
      resolver(candidateId, decision);
    });
    row.append(button);
  }
  return row;
}

function renderReflections(view) {
  reflectionList.replaceChildren();
  for (const pending of view?.pending || []) {
    const item = document.createElement("li");
    item.className = "reflection-item is-pending";
    item.append(
      Object.assign(document.createElement("p"), { className: "reflection-kind", textContent: "Нужно твоё решение · это интерпретация" }),
      Object.assign(document.createElement("h3"), { textContent: pending.text }),
      Object.assign(document.createElement("p"), { textContent: pending.meaning }),
      reflectionActions(pending.candidate_id, pending.allowed_actions, (id, decision) => bridge.resolveReflection(id, decision)),
    );
    reflectionList.append(item);
  }
  for (const help of view?.help_offers || []) {
    const item = document.createElement("li");
    item.className = "reflection-item is-help";
    item.append(
      Object.assign(document.createElement("p"), { className: "reflection-kind", textContent: "Честная помощь · только по согласию" }),
      Object.assign(document.createElement("h3"), { textContent: help.offer }),
      Object.assign(document.createElement("p"), { textContent: help.observation }),
      Object.assign(document.createElement("p"), { className: "reflection-benefit", textContent: help.expected_benefit }),
      reflectionActions(help.candidate_id, help.allowed_actions, (id, decision) => bridge.resolveHonestHelp(id, decision)),
    );
    reflectionList.append(item);
  }
  for (const adopted of view?.adopted || []) {
    const item = document.createElement("li");
    item.className = "reflection-item is-adopted";
    item.append(
      Object.assign(document.createElement("p"), { className: "reflection-kind", textContent: `Моё мнение · уверенность ${Math.round(adopted.confidence * 100)}%` }),
      Object.assign(document.createElement("h3"), { textContent: adopted.text }),
      Object.assign(document.createElement("p"), { textContent: adopted.meaning }),
    );
    reflectionList.append(item);
  }
  if (!reflectionList.children.length) reflectionList.append(objectEmpty("Здесь пока нет сохранённых мыслей или предложений помощи."));
}

function renderAgentRuns(view) {
  agentRunList.replaceChildren();
  for (const run of view?.items || []) {
    const item = document.createElement("li");
    item.className = "agent-run";
    item.dataset.status = run.status;
    const heading = document.createElement("h3");
    heading.textContent = run.goal;
    const status = document.createElement("p");
    status.className = "object-status";
    status.textContent = run.status_label;
    item.append(heading, status);
    for (const step of run.steps) {
      const row = document.createElement("p");
      row.className = "agent-step";
      row.dataset.status = step.status;
      row.textContent = step.title;
      item.append(row);
    }
    agentRunList.append(item);
  }
  if (!agentRunList.children.length) {
    const empty = document.createElement("li");
    empty.className = "object-empty";
    empty.textContent = "Проверенных агентных запусков пока не было.";
    agentRunList.append(empty);
  }
}

function renderProactiveInteractions(view) {
  proactiveList.replaceChildren();
  attentionMagicState.proactive = view?.items?.length || 0;
  updateAttentionMagic();
  for (const interaction of view?.items || []) {
    const item = document.createElement("li");
    item.className = "proactive-item";
    item.dataset.kind = interaction.interaction_type;
    const heading = document.createElement("h3");
    heading.textContent = interaction.title;
    const copy = document.createElement("p");
    copy.textContent = interaction.message;
    const actions = document.createElement("div");
    actions.className = "object-actions";
    for (const decision of interaction.allowed_actions) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = decision === "acknowledge" ? "Понял" : "Не сейчас";
      button.addEventListener("click", () => {
        bridge.resolveProactiveInteraction(interaction.interaction_id, decision);
      });
      actions.append(button);
    }
    item.append(heading, copy, actions);
    proactiveList.append(item);
  }
  if (!proactiveList.children.length) {
    const empty = document.createElement("li");
    empty.className = "object-empty";
    empty.textContent = "Сейчас ничего не ждёт твоего внимания.";
    proactiveList.append(empty);
  }
}

function formatDueAt(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

const commitmentStatusLabels = {
  open: "открыто",
  upcoming: "впереди",
  overdue: "просрочено",
  completed: "выполнено",
  cancelled: "отменено",
};

const commitmentGroupMeta = {
  fresh_overdue: {
    title: "Сейчас",
    countField: "fresh_overdue_total",
  },
  upcoming: {
    title: "Впереди",
    countField: "upcoming_total",
  },
  unscheduled: {
    title: "Когда будет время",
    countField: "unscheduled_total",
  },
  stale_overdue: {
    title: "Нужно разобрать",
    countField: "stale_overdue_total",
  },
};

function ensureCommitmentGroup(bucket, view) {
  const existing = commitmentsList.querySelector(
    `.commitment-group-heading[data-group="${bucket}"]`
  );

  if (existing) return;

  const meta = commitmentGroupMeta[bucket];
  if (!meta) return;

  const heading = document.createElement("li");
  heading.className = "commitment-group-heading";
  heading.dataset.group = bucket;

  const title = document.createElement("span");
  title.className = "commitment-group-title";
  title.textContent = meta.title;

  const count = document.createElement("span");
  count.className = "commitment-group-count";
  count.textContent = String(
    Number(view?.[meta.countField] || 0)
  );

  heading.append(title, count);
  commitmentsList.append(heading);
}

function renderCommitments(view, { append = false } = {}) {
  const items = view?.items || [];

  attentionMagicState.commitments =
    Number(view?.actionable_total ?? 0);

  attentionMagicState.freshOverdueCommitments =
    Number(view?.fresh_overdue_total || 0);

  updateAttentionMagic();

  commitmentsCount.textContent = String(
    view?.actionable_total ?? 0
  );

  if (!append) {
    commitmentsList.replaceChildren();
  }

  if (!items.length && !append) {
    const empty = document.createElement("li");
    empty.className = "commitment-empty";
    empty.textContent =
      "Сейчас здесь спокойно — открытых дел нет.";

    commitmentsList.append(empty);
    loadMoreCommitments.hidden = true;
    return;
  }

  for (const item of items) {
    ensureCommitmentGroup(
      item.time_bucket,
      view
    );

    const row = document.createElement("li");
    row.className = "commitment-item";
    row.dataset.status = item.status;
    row.dataset.timeBucket = item.time_bucket;

    const copy = document.createElement("div");
    copy.className = "commitment-copy";

    const text = document.createElement("p");
    text.className = "commitment-text";
    text.textContent = item.text;

    const meta = document.createElement("p");
    meta.className = "commitment-meta";

    const due = item.due_at
      ? ` · до ${formatDueAt(item.due_at)}`
      : "";

    meta.textContent =
      `${commitmentStatusLabels[item.status] || item.status}${due}`;

    copy.append(text, meta);
    row.append(copy);

    if (item.can_propose_completion) {
      const actions = document.createElement("div");
      actions.className = "commitment-actions";

      const complete = document.createElement("button");
      complete.type = "button";
      complete.className = "commitment-complete";
      complete.textContent = "Готово";

      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "commitment-cancel";
      cancel.textContent = "Убрать";

      let clearDue = null;

      if (item.time_bucket === "stale_overdue") {
        clearDue = document.createElement("button");
        clearDue.type = "button";
        clearDue.className = "commitment-cancel";
        clearDue.textContent = "Без срока";
      }

      complete.addEventListener("click", () => {
        if (
          !ready
          || inFlight
          || pendingConfirmation
        ) return;

        complete.disabled = true;
        cancel.disabled = true;

        if (clearDue) {
          clearDue.disabled = true;
        }

        bridge.proposeCommitmentCompletion(
          item.commitment_id
        );
      });

      cancel.addEventListener("click", () => {
        if (
          !ready
          || inFlight
          || pendingConfirmation
        ) return;

        complete.disabled = true;
        cancel.disabled = true;

        if (clearDue) {
          clearDue.disabled = true;
        }

        bridge.proposeCommitmentCancellation(
          item.commitment_id
        );
      });

      if (clearDue) {
        clearDue.addEventListener("click", () => {
          if (
            !ready
            || inFlight
            || pendingConfirmation
          ) return;

          complete.disabled = true;
          cancel.disabled = true;
          clearDue.disabled = true;

          bridge.proposeCommitmentClearDue(
            item.commitment_id
          );
        });
      }

      actions.append(complete);

      if (clearDue) {
        actions.append(clearDue);
      }

      actions.append(cancel);

      row.append(actions);
    }

    commitmentsList.append(row);
  }

  loadMoreCommitments.hidden = !view?.has_more;

  loadMoreCommitments.dataset.nextOffset =
    String(view?.next_offset ?? "");
}

function hideOperationSurface() {
  operationSurface.hidden = true;
  document.documentElement.dataset.operation = "none";
}

function renderPendingConfirmation(confirmation) {
  pendingConfirmation = confirmation;
  attentionMagicState.pendingConfirmation = Boolean(confirmation);
  updateAttentionMagic();
  if (!confirmation) {
    hideOperationSurface();
    setComposerState({ enabled: ready, waiting: inFlight });
    candidatePresentation.reconsider();
    return;
  }
  candidatePresentation.defer();
  operationEyebrow.textContent = "нужно твоё решение";
  operationTitle.textContent = confirmation.title;
  operationSubject.textContent = confirmation.subject;
  operationDue.textContent = confirmation.due_at ? `До: ${formatDueAt(confirmation.due_at)}` : "";
  operationDue.hidden = !confirmation.due_at;
  operationSteps.hidden = true;
  operationActions.hidden = false;
  closeOperation.hidden = true;
  confirmOperation.disabled = false;
  rejectOperation.disabled = false;
  transitionToSurface(() => {
    operationSurface.hidden = false;
    document.documentElement.dataset.operation = "confirmation";
  });
  setComposerState({ enabled: ready, waiting: inFlight });
}

function renderConfirmationActivity(decision) {
  operationEyebrow.textContent = "локальная операция";
  operationTitle.textContent = decision === "confirm" ? "Применяю подтверждение" : "Оставляю без изменений";
  operationSubject.textContent = pendingConfirmation?.subject || "Проверяю выбранное действие";
  operationDue.hidden = true;
  operationActions.hidden = true;
  closeOperation.hidden = true;
  operationSteps.hidden = false;
  for (const step of operationSteps.children) step.dataset.state = "waiting";
  operationSteps.children[0].dataset.state = "done";
  operationSteps.children[1].dataset.state = "active";
  operationSurface.hidden = false;
  document.documentElement.dataset.operation = "activity";
}

function renderConfirmationResult(result) {
  const confirmed = result?.status === "confirmed";
  const rejected = result?.status === "rejected";
  operationEyebrow.textContent = confirmed ? "готово" : rejected ? "без изменений" : "не получилось";
  operationTitle.textContent = confirmed ? "Изменение сохранено" : rejected ? "Ничего не меняла" : "Изменение не применено";
  operationSubject.textContent = result?.assistant_message?.content || "Предложение осталось без изменений.";
  operationSteps.hidden = false;
  for (const step of operationSteps.children) step.dataset.state = confirmed || rejected ? "done" : "waiting";
  operationActions.hidden = true;
  closeOperation.hidden = false;
  pendingConfirmation = result?.pending_confirmation || null;
  document.documentElement.dataset.operation = "result";
}

function renderHomeAttention(attention) {
  attentionLines.replaceChildren();

  const items = attention?.attention_items || [];
  const hasImportant = items.some(
  (item) => item.urgency === "important"
);

const hasPendingDecision = items.some(
  (item) =>
    item.kind === "pending_confirmation"
    || item.kind === "model_unavailable"
);

const hasSomething =
  items.length > 0
  || attention.stale_overdue_commitments_count > 0
  || attention.unscheduled_commitments_count > 0;

homeAttentionTitle.textContent =
  hasPendingDecision
    ? "Тут нужно твоё внимание."
    : hasImportant
      ? "Есть кое-что важное."
      : hasSomething
        ? "Вот что сейчас рядом."
        : "Здесь всё спокойно.";

  if (!items.length) {
    const quiet = document.createElement("p");
    quiet.className = "attention-empty";
    quiet.textContent = "Сейчас всё спокойно. Ничего отдельно не просит твоего внимания.";
    attentionLines.append(quiet);
    return;
  }

  for (const item of items) {
    const row = document.createElement("article");
    row.className = "attention-item";
    row.dataset.urgency = item.urgency;
    row.dataset.kind = item.kind;

    const marker = document.createElement("span");
    marker.className = "attention-marker";
    marker.setAttribute("aria-hidden", "true");

    const copy = document.createElement("div");
    copy.className = "attention-copy";

    const title = document.createElement("h3");
    title.textContent = item.title;

    copy.append(title);

    if (item.detail) {
      const detail = document.createElement("p");
      detail.textContent = item.detail;
      copy.append(detail);
    }

    row.append(marker, copy);
    attentionLines.append(row);
  }

  const summaryBits = [];

const totalOverdue =
  Number(attention.overdue_commitments_count || 0);

const staleOverdue =
  Number(attention.stale_overdue_commitments_count || 0);

const freshOverdue =
  Math.max(0, totalOverdue - staleOverdue);

const upcoming =
  Number(attention.upcoming_commitments_count || 0);

const unscheduled =
  Number(attention.unscheduled_commitments_count || 0);

const proactive =
  Number(attention.pending_interactions_count || 0);

if (freshOverdue > 0) {
  summaryBits.push(
    freshOverdue === 1
      ? "1 свежая просрочка"
      : `${freshOverdue} свежих просрочки`
  );
}

if (upcoming > 0) {
  summaryBits.push(
    upcoming === 1
      ? "1 дело впереди"
      : `${upcoming} дел впереди`
  );
}

if (staleOverdue > 0) {
  summaryBits.push(
    `${staleOverdue} нужно разобрать`
  );
}

if (unscheduled > 0) {
  summaryBits.push(
    unscheduled === 1
      ? "1 дело без срока"
      : `${unscheduled} дел без срока`
  );
}

if (proactive > 0) {
  summaryBits.push(
    proactive === 1
      ? "1 моя инициатива"
      : `${proactive} моих инициативы`
  );
}

if (summaryBits.length) {
  const summary = document.createElement("p");
  summary.className = "attention-summary";
  summary.textContent = summaryBits.join(" · ");
  attentionLines.append(summary);
}
}

function applySafety(engaged) {
  document.documentElement.dataset.safety = engaged ? "autonomy_stopped" : "autonomy_active";
  safetyOverlay.hidden = !engaged;
  safetyTrigger.hidden = engaged;
  if (engaged) {
    candidatePresentation.defer();
    closeTemporarySurfaces();
  } else {
    candidatePresentation.reconsider();
  }
}

function messageKey(message) {
  return message.message_id || `transient:${message.role}:${message.content}`;
}

function renderMessage(message, { provisional = false } = {}) {
  const key = messageKey(message);
  let item = transcript.querySelector(`[data-message-key="${CSS.escape(key)}"]`);
  if (!item) {
    item = document.createElement("li");
    item.dataset.messageKey = key;
    item.className = `message message-${message.role}`;
    transcript.append(item);
  }
  item.className = `message message-${message.role}${provisional ? " is-provisional" : ""}`;
  if (message.role === "assistant") {
    window.MashaSafeMarkdown.renderInto(item, message.content);
  } else {
    item.textContent = message.content;
  }
  return item;
}

function renderConversation(conversation) {
  transcript.replaceChildren();
  surface.classList.toggle("has-history", Boolean(conversation?.messages?.length));
  if (!conversation?.messages?.length) {
    title.textContent = "Я здесь.";
    surfaceStatus.textContent = "С чего начнём?";
    return;
  }
  title.textContent = "Я рядом.";
  surfaceStatus.textContent = "";
  for (const message of conversation.messages) renderMessage(message);
  scrollToLatestIfAppropriate(true);
}

function formatRecentTime(value) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(date);
}

function renderRecent(page, activeId = activeConversationId, { append = false } = {}) {
  const items = page?.items || [];
  const revision = Number(page?.revision ?? -1);
  if (!interactionSafety.acceptConversationPage(recentPageState, page, append)) return;
  if (!append) {
    recentList.replaceChildren();
    // A fresh Home/conversation snapshot is authoritative.  It invalidates
    // offsets from a previous shelf lifecycle before any later load-more.
    recentPageState = { revision, nextOffset: page?.next_offset ?? null, ids: new Set() };
  }
  surface.classList.toggle("has-conversations", Boolean(page?.total || items.length));
  if (!items.length && !append) {
    const empty = document.createElement("li");
    empty.className = "recent-empty";
    empty.textContent = "Здесь появятся наши разговоры.";
    recentList.append(empty);
    loadMoreConversations.hidden = true;
    return;
  }
  for (const item of items) {
    if (recentPageState.ids.has(item.conversation_id)) continue;
    recentPageState.ids.add(item.conversation_id);
    const entry = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "recent-item";
    button.disabled = inFlight;
    button.dataset.conversationId = item.conversation_id;
    if (item.conversation_id === activeId) button.classList.add("is-active");
    const preview = document.createElement("span");
    preview.className = "recent-preview";
    preview.textContent = item.preview;
    const time = document.createElement("time");
    time.className = "recent-time";
    time.dateTime = item.last_interaction_at;
    time.textContent = formatRecentTime(item.last_interaction_at);
    button.append(preview, time);
    button.addEventListener("click", () => {
      if (!ready || inFlight || item.conversation_id === activeConversationId) return;
      bridge.openConversation(item.conversation_id);
    });
    entry.append(button);
    recentList.append(entry);
  }
  loadMoreConversations.hidden = !page?.has_more;
  recentPageState.nextOffset = page?.next_offset ?? null;
  loadMoreConversations.dataset.nextOffset = String(recentPageState.nextOffset ?? "");
}

function applySnapshot(snapshot) {
  if (!snapshot) return;
  const { status, active_model: activeModel, presentation } = snapshot;
  attentionMagicState.modelAvailable = Boolean(status.model_available);
  attentionMagicState.safetyEngaged = Boolean(status.emergency_stop_engaged);
  updateAttentionMagic();
  document.documentElement.dataset.homeState = presentation.home_state;
  document.documentElement.dataset.safety = presentation.overlays.safety;
  document.documentElement.dataset.model = presentation.overlays.model;
  document.documentElement.dataset.presence = presentation.presence.activity;
  applyScene(presentation);

  const pieces = ["Локально", activeModel.display_name];
  if (!status.model_available) pieces.push("модель недоступна");
  if (status.emergency_stop_engaged) pieces.push("автономность на паузе");
  if (status.proactive_reason_label) pieces.push(status.proactive_reason_label);
  runtimeTruth.textContent = pieces.join(" · ");
  applySafety(status.emergency_stop_engaged);
}

function showLocalFailure(text) {
  surfaceStatus.textContent = text;
  surfaceStatus.classList.add("is-error");
}

function clearLocalFailure() {
  surfaceStatus.classList.remove("is-error");
}

function handleBridgeEvent(encoded) {
  let payload;
  try {
    payload = JSON.parse(encoded);
  } catch {
    showLocalFailure("Не удалось прочитать локальный ответ.");
    return;
  }

  if (payload.kind === "home_initial") {
    resetHumanSearchUi();
    applySnapshot(payload.snapshot);
    attentionMagicState.commitments =
        Number(payload.commitments_count || 0);
    attentionMagicState.freshOverdueCommitments =
        Number(payload.fresh_overdue_commitments_count || 0);
    attentionMagicState.proactive =
        Number(payload.proactive_interactions_count || 0);
    updateAttentionMagic();
    renderConversation(payload.conversation);
    activeConversationId = payload.conversation?.conversation_id || null;
    renderRecent(payload.recent, activeConversationId);
    commitmentsCount.textContent = String(payload.commitments_count || 0);
    activityTrigger.hidden = !(payload.agent_runs_count > 0);
    proactiveTrigger.hidden = !(payload.proactive_interactions_count > 0);
    // Empty history is still a real state: this is where the first explicitly
    // confirmed shared moment or open thread is created.
    continuityTrigger.hidden = false;
    reflectionsTrigger.hidden = !(payload.reflection_items_count > 0);
    ready = true;
    clearLocalFailure();
    setComposerState({ enabled: true });
    renderPendingConfirmation(payload.pending_confirmation);
    renderMemoryCandidate(payload.memory_candidate);
    return;
  }
  if (payload.kind === "workbench_loaded") {
    applySnapshot(payload.snapshot);
    renderWorkbench(payload.workbench);
    workbenchSurface.hidden = false;
    document.documentElement.dataset.objectSurface = "workbench";
    workbenchTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (payload.kind === "skill_install_preview") {
    pendingSkillInstall = payload.preview;
    const preview = payload.preview;
    skillInstallTitle.textContent = `${preview.action === "upgrade" ? "Обновить" : "Добавить"} «${preview.name}»?`;
    skillInstallCopy.textContent = `Версия ${preview.proposed_version}. Возможности: ${preview.capabilities.map(humanCapability).join(", ") || "не заявлены"}. Области: ${preview.requested_scopes.join(", ") || "не запрошены"}. Риск: ${preview.risk_level}. Автономность не выше ${preview.maximum_autonomy_level}.`;
    workbenchSurface.hidden = true;
    skillInstallSurface.hidden = false;
    return;
  }
  if (payload.kind === "skill_install_result") {
    pendingSkillInstall = null;
    skillInstallSurface.hidden = true;
    renderWorkbench(payload.result.workbench);
    workbenchSurface.hidden = false;
    surfaceStatus.textContent = payload.result.message;
    return;
  }
  if (payload.kind === "skill_install_cancelled") return;
  if (payload.kind === "skill_install_rejected") {
    pendingSkillInstall = null;
    skillInstallSurface.hidden = true;
    showLocalFailure("Пакет навыка не прошёл проверку или изменился после preview.");
    return;
  }
  if (payload.kind === "model_switch_started") {
    applySnapshot(payload.snapshot);
    setComposerState({ enabled: true, waiting: true });
    surfaceStatus.textContent = "Проверяю выбранную локальную модель…";
    return;
  }
  if (payload.kind === "model_switch_applied") {
    applySnapshot(payload.snapshot);
    renderWorkbench(payload.workbench);
    workbenchSurface.hidden = false;
    surfaceStatus.textContent = `Теперь отвечает ${payload.result.active_profile.display_name}.`;
    setComposerState({ enabled: ready });
    return;
  }
  if (payload.kind === "model_switch_rejected") {
    setComposerState({ enabled: ready });
    showLocalFailure(payload.result?.error_label || "Эта локальная модель сейчас недоступна.");
    return;
  }
  if (payload.kind === "commitments_loaded") {
    applySnapshot(payload.snapshot);
    renderCommitments(payload.commitments, { append: Boolean(payload.append) });
    commitmentsSurface.hidden = false;
    document.documentElement.dataset.commitments = "active";
    commitmentsTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (
  payload.kind === "commitment_completion_proposed"
  || payload.kind === "commitment_cancellation_proposed"
  || payload.kind === "commitment_due_change_proposed"
) {
    applySnapshot(payload.snapshot);
    const result = payload.result;
    activeConversationId = result.conversation_id;
    renderMessage(result.user_message);
    renderMessage(result.assistant_message);
    surface.classList.add("has-history");
    title.textContent = "Я рядом.";
    commitmentsSurface.hidden = true;
    document.documentElement.dataset.commitments = "closed";
    commitmentsTrigger.setAttribute("aria-expanded", "false");
    renderPendingConfirmation(result.pending_confirmation);
    bridge.loadRecentConversations();
    scrollToLatestIfAppropriate(true);
    return;
  }
  if (payload.kind === "agent_runs_loaded") {
    applySnapshot(payload.snapshot);
    renderAgentRuns(payload.runs);
    activityTrigger.hidden = !(payload.runs?.items?.length > 0);
    activitySurface.hidden = false;
    document.documentElement.dataset.objectSurface = "activity";
    activityTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (payload.kind === "proactive_interactions_loaded") {
    if (interactionSafety.isBackgroundProactiveProjection(payload)) {
      interactionSafety.preserveComposer(input, document, () => {
        renderProactiveInteractions(payload.interactions);
        proactiveTrigger.hidden = !(payload.interactions?.items?.length > 0);
      });
      return;
    }
    applySnapshot(payload.snapshot);
    renderProactiveInteractions(payload.interactions);
    proactiveTrigger.hidden = !(payload.interactions?.items?.length > 0);
    proactiveSurface.hidden = false;
    document.documentElement.dataset.objectSurface = "proactive";
    proactiveTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (payload.kind === "proactive_interaction_resolved") {
    applySnapshot(payload.snapshot);
    closeTemporarySurfaces();
    proactiveTrigger.hidden = !(payload.remaining_count > 0);
    surfaceStatus.textContent = payload.interaction.state === "acknowledged"
      ? "Хорошо, учла."
      : "Не сейчас — убрала без других изменений.";
    input.focus();
    return;
  }
  if (payload.kind === "shared_continuity_loaded") {
    applySnapshot(payload.snapshot);
    renderContinuity(payload.continuity);
    continuitySurface.hidden = false;
    document.documentElement.dataset.objectSurface = "continuity";
    continuityTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (payload.kind === "human_search_loaded") {
    renderHumanSearch(payload.items || [], payload.query || "");
    return;
  }
  if (payload.kind === "memory_restore_proposed") {
    applySnapshot(payload.snapshot);
    renderPendingConfirmation(payload.pending_confirmation);
    return;
  }
  if (payload.kind === "memory_candidate_resolved") {
    pendingMemoryCandidate = null;
    memoryCandidateSurface.hidden = true;
    document.documentElement.dataset.operation = "none";
    surface.hidden = false;
    surface.classList.remove("is-surface-concealed");
    surfaceStatus.textContent = payload.message;
    renderMemoryCandidate(payload.memory_candidate);
    return;
  }
  if (payload.kind === "reflection_workspace_loaded") {
    applySnapshot(payload.snapshot);
    renderReflections(payload.workspace);
    reflectionsSurface.hidden = false;
    document.documentElement.dataset.objectSurface = "reflections";
    reflectionsTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (payload.kind === "reflection_resolved") {
    applySnapshot(payload.snapshot);
    renderReflections(payload.workspace);
    reflectionsTrigger.hidden = !(payload.remaining_count > 0);
    surfaceStatus.textContent = payload.result.message;
    return;
  }
  if (payload.kind === "honest_help_started") {
    applySnapshot(payload.snapshot);
    setComposerState({ enabled: true, waiting: true });
    surfaceStatus.textContent = "Думаю над тем, как помочь без лишней магии…";
    return;
  }
  if (payload.kind === "honest_help_resolved") {
    applySnapshot(payload.snapshot);
    renderReflections(payload.workspace);
    reflectionsTrigger.hidden = !(payload.remaining_count > 0);
    if (payload.conversation) {
      activeConversationId = payload.conversation.conversation_id;
      renderConversation(payload.conversation);
      closeTemporarySurfaces();
      bridge.loadRecentConversations();
    }
    surfaceStatus.textContent = payload.result?.message || "Помощь сейчас не удалось сформулировать.";
    setComposerState({ enabled: ready });
    return;
  }
  if (["activities_unavailable", "proactive_unavailable", "proactive_resolution_rejected", "continuity_unavailable", "reflections_unavailable", "reflection_resolution_rejected", "honest_help_rejected", "workbench_unavailable"].includes(payload.kind)) {
    showLocalFailure("Локальное состояние сейчас не удалось открыть.");
    return;
  }
  if (["human_search_unavailable", "memory_candidate_rejected", "memory_restore_unavailable"].includes(payload.kind)) {
    showLocalFailure(payload.message || "Сейчас это действие недоступно. Попробуй ещё раз чуть позже.");
    return;
  }
  if (payload.kind === "commitment_operation_rejected" || payload.kind === "commitments_unavailable") {
    showLocalFailure("Не получилось открыть это действие. Обнови список дел и попробуй ещё раз.");
    commitmentsSurface.hidden = true;
    document.documentElement.dataset.commitments = "closed";
    commitmentsTrigger.setAttribute("aria-expanded", "false");
    return;
  }
  if (payload.kind === "conversation_started") {
    resetHumanSearchUi();
    applySnapshot(payload.snapshot);
    renderConversation(null);
    clearLocalFailure();
    activeConversationId = null;
    bridge.loadRecentConversations();
    setComposerState({ enabled: ready });
    input.focus();
    pendingConfirmation = null;
    hideOperationSurface();
    candidatePresentation.reconsider();
    return;
  }
  if (payload.kind === "recent_conversations") {
    interactionSafety.preserveComposer(input, document, () => {
      renderRecent(payload.recent, payload.active_conversation_id, { append: Boolean(payload.append) });
    });
    return;
  }
  if (payload.kind === "home_time") {
  applySnapshot(payload.snapshot);
  return;
    }
  if (payload.kind === "home_attention") {
    renderHomeAttention(payload.attention);
    homeAttention.hidden = false;
    document.documentElement.dataset.homeAttention = "active";
    homeAttentionTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (payload.kind === "safety_changed") {
    applySnapshot(payload.snapshot);
    applySafety(payload.safety.emergency_stop_engaged);
    if (!payload.safety.emergency_stop_engaged) input.focus();
    return;
  }
  if (payload.kind === "conversation_opened") {
    candidatePresentation.defer();
    resetHumanSearchUi();
    applySnapshot(payload.snapshot);
    renderConversation(payload.conversation);
    activeConversationId = payload.conversation.conversation_id;
    renderRecent(payload.recent, activeConversationId);
    recentPanel.hidden = true;
    recentToggle.setAttribute("aria-expanded", "false");
    surface.classList.remove("is-shelf-open");
    clearLocalFailure();
    setComposerState({ enabled: ready });
    renderPendingConfirmation(payload.pending_confirmation);
    return;
  }
  if (payload.kind === "turn_started") {
    candidatePresentation.defer();
    clearLocalFailure();
    provisionalUser = renderMessage({ role: "user", content: payload.content }, { provisional: true });
    surface.classList.add("has-history");
    title.textContent = "Слушаю.";
    surfaceStatus.textContent = "";
    applySnapshot(payload.snapshot);
    scrollToLatestIfAppropriate(true);
    return;
  }
  if (payload.kind === "turn_thinking") {
    applySnapshot(payload.snapshot);
    title.textContent = "Я рядом.";
    surfaceStatus.textContent = "";
    return;
  }
  if (payload.kind === "turn_result") {
    applySnapshot(payload.snapshot);
    const result = payload.result;
    if (result?.user_message?.persisted) {
      if (provisionalUser) provisionalUser.remove();
      renderMessage(result.user_message);
    }
    if (result?.status === "completed" && result.assistant_message) {
      renderMessage(result.assistant_message);
      title.textContent = "Я рядом.";
      surfaceStatus.textContent = "";
    } else {
      title.textContent = "Я рядом.";
      showLocalFailure(result?.error_label || "Локальный разговор сейчас недоступен.");
    }
    provisionalUser = null;
    activeConversationId = result?.conversation_id || activeConversationId;
    bridge.loadRecentConversations();
    setComposerState({ enabled: ready });
    renderPendingConfirmation(result?.pending_confirmation);
    renderMemoryCandidate(payload.memory_candidate);
    scrollToLatestIfAppropriate(true);
    return;
  }
  if (payload.kind === "continuity_thread_result") {
    applySnapshot(payload.snapshot);
    closeTemporarySurfaces();
    surface.hidden = false;
    surface.classList.remove("is-surface-concealed");
    const result = payload.result;
    if (result?.user_message) renderMessage(result.user_message);
    if (result?.assistant_message) renderMessage(result.assistant_message);
    activeConversationId = result?.conversation_id || activeConversationId;
    setComposerState({ enabled: ready });
    scrollToLatestIfAppropriate(true);
    return;
  }
  if (payload.kind === "confirmation_started") {
    applySnapshot(payload.snapshot);
    renderConfirmationActivity(payload.decision);
    setComposerState({ enabled: true, waiting: true });
    return;
  }
  if (payload.kind === "confirmation_result") {
    applySnapshot(payload.snapshot);
    const result = payload.result;
    if (result?.user_message) renderMessage(result.user_message);
    if (result?.assistant_message) renderMessage(result.assistant_message);
    renderConfirmationResult(result);
    commitmentsCount.textContent = String(payload.commitments_count || 0);
    bridge.loadRecentConversations();
    setComposerState({ enabled: ready });
    scrollToLatestIfAppropriate(true);
    return;
  }
  if (payload.kind === "confirmation_rejected") {
    if (payload.reason === "safety_stop") {
      showLocalFailure("Сначала верни возможность действовать: предложение осталось без изменений.");
      renderPendingConfirmation(pendingConfirmation);
    } else {
      renderConfirmationResult(null);
    }
    setComposerState({ enabled: ready });
    return;
  }
  if (payload.kind === "input_rejected") {
    showLocalFailure(payload.reason === "too_long" ? "Сообщение слишком длинное." : "Напиши хотя бы пару слов.");
    return;
  }
  if (payload.kind === "turn_rejected") {
    showLocalFailure("Я ещё отвечаю на предыдущее сообщение.");
    return;
  }
  if (payload.kind === "home_unavailable") {
    candidatePresentation.defer();
    ready = false;
    setComposerState({ enabled: false });
    showLocalFailure("Локальный Дом сейчас не готов к разговору.");
  }
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = input.value.trim();
  if (!ready || inFlight || !content) return;
  candidatePresentation.defer();
  input.value = "";
  fitComposer();
  setComposerState({ enabled: true, waiting: true });
  bridge.submitMessage(content);
});

newConversationButton.addEventListener("click", () => {
  if (!ready || inFlight) return;
  candidatePresentation.defer();
  bridge.startNewConversation();
});

recentToggle.addEventListener("click", () => {
  if (!ready || inFlight) return;
  const opening = recentPanel.hidden;
  if (opening) {
    candidatePresentation.defer();
    // The shelf belongs to the conversation surface.  Make it readable first;
    // never hide its parent while opening it.
    recentPanel.hidden = false;
    surface.classList.add("is-shelf-open");
    recentToggle.setAttribute("aria-expanded", "true");
    bridge.loadRecentConversations();
  } else {
    recentPanel.hidden = true;
    surface.classList.remove("is-shelf-open");
    recentToggle.setAttribute("aria-expanded", "false");
    input.focus();
    candidatePresentation.reconsider();
  }
});

loadMoreConversations.addEventListener("click", () => {
  const offset = Number(loadMoreConversations.dataset.nextOffset);
  if (!ready || inFlight || !Number.isInteger(offset)) return;
  bridge.loadMoreConversations(offset);
});

loadMoreCommitments.addEventListener("click", () => {
  const offset = Number(loadMoreCommitments.dataset.nextOffset);
  if (!ready || inFlight || !Number.isInteger(offset)) return;
  bridge.loadMoreCommitments(offset);
});

homeAttentionTrigger.addEventListener("click", () => {
  if (!ready || inFlight) return;

  const opening = homeAttention.hidden;

  if (opening) {
    acknowledgeAttentionNovelty();

    transitionToSurface(() => {
      bridge.loadHomeAttention();
    });
  } else {
    returnToConversation();
  }
});

commitmentsTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  const opening = commitmentsSurface.hidden;
  if (opening) {
    transitionToSurface(() => bridge.loadCommitments());
  } else {
    returnToConversation();
  }
});

closeCommitments.addEventListener("click", () => {
  returnToConversation();
});

addCommitment.addEventListener("click", () => {
  commitmentsSurface.hidden = true;
  commitmentCreateSurface.hidden = false;
  commitmentTitle.value = "";
  commitmentDue.value = "";
  commitmentTitle.focus();
});

cancelCommitment.addEventListener("click", () => {
  commitmentCreateSurface.hidden = true;
  commitmentsSurface.hidden = false;
});

submitCommitment.addEventListener("click", () => {
  const subject = commitmentTitle.value.trim();
  if (!subject || inFlight) return;
  const due = commitmentDue.value.trim();
  commitmentCreateSurface.hidden = true;
  closeTemporarySurfaces();
  surface.hidden = false;
  surface.classList.remove("is-surface-concealed");
  setComposerState({ enabled: true, waiting: true });
  bridge.submitMessage(`Добавь дело: ${due ? `${due} ` : ""}${subject}`);
});

activityTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  const opening = activitySurface.hidden;
  if (opening) transitionToSurface(() => bridge.loadAgentRuns());
  else returnToConversation();
});

proactiveTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  const opening = proactiveSurface.hidden;
  if (opening) transitionToSurface(() => bridge.loadProactiveInteractions());
  else returnToConversation();
});

continuityTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  const opening = continuitySurface.hidden;
  if (opening) transitionToSurface(() => bridge.loadSharedContinuity());
  else returnToConversation();
});

reflectionsTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  const opening = reflectionsSurface.hidden;
  if (opening) transitionToSurface(() => bridge.loadReflectionWorkspace());
  else returnToConversation();
});

workbenchTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  const opening = workbenchSurface.hidden;
  if (opening) transitionToSurface(() => bridge.loadWorkbench());
  else returnToConversation();
});

closeActivity.addEventListener("click", () => {
  returnToConversation();
});

closeProactive.addEventListener("click", () => {
  returnToConversation();
});

closeContinuity.addEventListener("click", () => {
  returnToConversation();
});

function requestHumanSearch() {
  clearTimeout(historySearchTimer);
  const query = historySearchInput.value.trim();
  if (!ready || inFlight) return;
  bridge.clearInformationSearch();
  if (!query) {
    renderHumanSearch([], "");
    return;
  }
  showHumanSearchPending(query);
  historySearchTimer = window.setTimeout(
    () => bridge.searchInformation(query, historySearchScope, historySearchForgotten),
    reducedMotion.matches ? 0 : 160,
  );
}

historySearchInput.addEventListener("input", requestHumanSearch);

for (const button of historySearchScopes) {
  button.addEventListener("click", () => {
    historySearchScope = button.dataset.searchScope;
    for (const choice of historySearchScopes) choice.classList.toggle("is-active", choice === button);
    requestHumanSearch();
  });
}

forgottenSearchToggle.addEventListener("click", () => {
  historySearchForgotten = !historySearchForgotten;
  forgottenSearchToggle.classList.toggle("is-active", historySearchForgotten);
  forgottenSearchToggle.setAttribute("aria-pressed", String(historySearchForgotten));
  historySearchInput.placeholder = historySearchForgotten
    ? "Найти среди забытого"
    : "Найти в нашем доме";
  requestHumanSearch();
});

approveMemoryCandidate.addEventListener("click", () => {
  if (!ready || inFlight || !pendingMemoryCandidate) return;
  approveMemoryCandidate.disabled = true;
  rejectMemoryCandidate.disabled = true;
  bridge.resolveMemoryCandidate(pendingMemoryCandidate.candidate_id, "approve");
});

rejectMemoryCandidate.addEventListener("click", () => {
  if (!ready || inFlight || !pendingMemoryCandidate) return;
  approveMemoryCandidate.disabled = true;
  rejectMemoryCandidate.disabled = true;
  bridge.resolveMemoryCandidate(pendingMemoryCandidate.candidate_id, "reject");
});

closeReflections.addEventListener("click", () => {
  returnToConversation();
});

closeWorkbench.addEventListener("click", () => {
  returnToConversation();
});

addSkill.addEventListener("click", () => {
  if (!ready || inFlight) return;
  bridge.chooseSkillPackage();
});

function openContinuityCreate(kind) {
  continuityCreateKind = kind;
  continuityCreateText.value = "";
  continuityCreateEyebrow.textContent = kind === "moment" ? "наш момент" : "открытая нить";
  continuityCreateTitle.textContent = kind === "moment" ? "Что останется с нами?" : "К чему вернуться позже?";
  continuitySurface.hidden = true;
  continuityCreateSurface.hidden = false;
  continuityCreateText.focus();
}

addSharedMoment.addEventListener("click", () => openContinuityCreate("moment"));
addContinuityThread.addEventListener("click", () => openContinuityCreate("thread"));
cancelContinuity.addEventListener("click", () => {
  continuityCreateKind = null;
  continuityCreateSurface.hidden = true;
  continuitySurface.hidden = false;
});
submitContinuity.addEventListener("click", () => {
  const text = continuityCreateText.value.trim();
  if (!ready || inFlight || !text || !continuityCreateKind) return;
  const message = continuityCreateKind === "moment"
    ? `Маша, запомни как часть нашей истории, что ${text}`
    : `Оставь это как открытую нить: ${text}`;
  continuityCreateKind = null;
  closeTemporarySurfaces();
  surface.hidden = false;
  surface.classList.remove("is-surface-concealed");
  setComposerState({ enabled: true, waiting: true });
  bridge.submitMessage(message);
});

confirmSkillInstall.addEventListener("click", () => {
  if (!pendingSkillInstall) return;
  bridge.resolveSkillInstall(pendingSkillInstall.proposal_id, "confirm");
});

rejectSkillInstall.addEventListener("click", () => {
  if (!pendingSkillInstall) return;
  bridge.resolveSkillInstall(pendingSkillInstall.proposal_id, "reject");
});

safetyTrigger.addEventListener("click", () => {
  if (!ready) return;
  candidatePresentation.defer();
  bridge.engageEmergencyStop();
});

resumeAction.addEventListener("click", () => {
  if (!ready) return;
  bridge.resumeAutonomy();
});

confirmOperation.addEventListener("click", () => {
  if (!ready || inFlight || !pendingConfirmation) return;
  confirmOperation.disabled = true;
  rejectOperation.disabled = true;
  bridge.resolveConfirmation(pendingConfirmation.proposal_id, "confirm");
});

rejectOperation.addEventListener("click", () => {
  if (!ready || inFlight || !pendingConfirmation) return;
  confirmOperation.disabled = true;
  rejectOperation.disabled = true;
  bridge.resolveConfirmation(pendingConfirmation.proposal_id, "reject");
});

closeOperation.addEventListener("click", () => {
  returnToConversation();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!recentPanel.hidden) {
      recentPanel.hidden = true;
      surface.classList.remove("is-shelf-open");
      recentToggle.setAttribute("aria-expanded", "false");
      input.focus();
      return;
    }
    returnToConversation();
    return;
  }
  if (event.ctrlKey && event.key.toLowerCase() === "h") {
    event.preventDefault();
    homeAttentionTrigger.click();
  }
  if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "s") {
    event.preventDefault();
    safetyTrigger.click();
  }
  if (event.ctrlKey && event.key.toLowerCase() === "l") {
    event.preventDefault();
    input.focus();
  }
});
// A native file picker legitimately unfocuses the Home window.  Surfaces are
// application state, not browser popovers, so focus loss must not discard them.

input.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (!sendButton.disabled) composer.requestSubmit();
});

input.addEventListener("input", () => {
  fitComposer();
  setComposerState({ enabled: ready, waiting: inFlight });
  if (input.value.trim()) candidatePresentation.defer();
  else candidatePresentation.reconsider();
});
fitComposer();
document.documentElement.dataset.homeAttention = "closed";
document.documentElement.dataset.commitments = "closed";

if (typeof QWebChannel === "function" && window.qt?.webChannelTransport) {
  window.MashaSceneMap.preload();
  new QWebChannel(window.qt.webChannelTransport, (channel) => {
    bridge = channel.objects.mashaHome;
    bridge.event.connect(handleBridgeEvent);
    bridge.loadInitialState();
  });
} else {
  showLocalFailure("Локальный bridge не подключился.");
}
