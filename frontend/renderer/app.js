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
const addLocalDocument = document.getElementById("add-local-document");
const localDocumentChip = document.getElementById("local-document-chip");
const localDocumentLabel = document.getElementById("local-document-label");
const newConversationButton = document.getElementById("new-conversation");
const specialEveningToggle = document.getElementById("special-evening-toggle");
const specialProximityToggle =
  document.getElementById("special-proximity-toggle");
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
const reminderToast = document.getElementById("reminder-toast");
const reminderToastMessage = document.getElementById("reminder-toast-message");
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
const historyCount = document.getElementById("history-count");
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
const threadContext = document.getElementById("thread-context");
const threadContextTitle = document.getElementById("thread-context-title");
const threadContextClear = document.getElementById("thread-context-clear");
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
const workbenchConnections = document.getElementById("workbench-connections");
const workbenchSkills = document.getElementById("workbench-skills");
const workbenchPermissions = document.getElementById("workbench-permissions");
const closeWorkbench = document.getElementById("close-workbench");
const addCommitment = document.getElementById("add-commitment");
const commitmentCreateSurface = document.getElementById("commitment-create-surface");
const commitmentRescheduleSurface =
  document.getElementById("commitment-reschedule-surface");
const commitmentRescheduleSubject =
  document.getElementById("commitment-reschedule-subject");
const commitmentRescheduleDue =
  document.getElementById("commitment-reschedule-due");
const commitmentRescheduleHint =
  document.getElementById("commitment-reschedule-hint");
const submitCommitmentReschedule =
  document.getElementById("submit-commitment-reschedule");
const cancelCommitmentReschedule =
  document.getElementById("cancel-commitment-reschedule");
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
let lastPresentation = null;
let cornerSceneActive = false;
let activeSceneLayer = 0;
let activeConversationId = null;
let homeTimeZone = "UTC";
let recentPageState = { revision: -1, nextOffset: null, ids: new Set() };
let sceneTransitionRevision = 0;
let sceneTransitionTimer = null;
let sceneSettleTimer = null;
let presenceSettleTimer = null;
let pendingPresenceSettleRevision = null;
let activeSceneChangedAt = performance.now();
let pendingConfirmation = null;
let pendingMemoryCandidate = null;
let continuityItemCount = 0;
let activeContinuityThread = null;
let historySearchScope = "all";
let historySearchForgotten = false;
let historySearchTimer = null;
let pendingSkillInstall = null;
let continuityCreateKind = null;
let pendingCommitmentReschedule = null;
let stagedLocalDocument = null;
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
let reminderToastTimer = null;
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

function cancelAssistantSettle() {
  if (presenceSettleTimer !== null) {
    clearTimeout(presenceSettleTimer);
  }

  presenceSettleTimer = null;
  pendingPresenceSettleRevision = null;
}

function assistantSettleDelay(result) {
  const textLength =
    result?.assistant_message?.content?.length || 0;

  /*
   * Short replies stay addressed to Misha for about 10 seconds.
   * Longer replies get a little more afterglow, capped at 20 seconds.
   */
  const textBlocks = Math.ceil(
    Math.max(textLength, 1) / 400
  );

  return Math.min(
    20_000,
    8_000 + textBlocks * 2_000
  );
}

function scheduleAssistantSettle(snapshot, result) {
  cancelAssistantSettle();

  const presentation = snapshot?.presentation;

  if (
    presentation?.presence?.activity !== "speaking"
  ) {
    return;
  }

  const revision = Number(
    presentation.revision
  );

  if (!Number.isInteger(revision)) {
    return;
  }

  pendingPresenceSettleRevision = revision;

  presenceSettleTimer = window.setTimeout(() => {
    const expectedRevision =
      pendingPresenceSettleRevision;

    presenceSettleTimer = null;
    pendingPresenceSettleRevision = null;

    if (
      !bridge
      || !Number.isInteger(expectedRevision)
    ) {
      return;
    }

    bridge.settleAssistantPresence(
      expectedRevision
    );
  }, assistantSettleDelay(result));
}

function fitComposer() {
  input.style.height = `${COMPOSER_MIN_HEIGHT}px`;
  input.style.height = `${Math.min(input.scrollHeight, COMPOSER_MAX_HEIGHT)}px`;
  input.classList.toggle("is-scrollable", input.scrollHeight > COMPOSER_MAX_HEIGHT);
}

function setCornerSceneActive(active) {
  const nextActive = Boolean(active);
  if (cornerSceneActive === nextActive) return;

  cornerSceneActive = nextActive;
  if (lastPresentation) applyScene(lastPresentation);
}

function applyScene(presentation) {
  if (presentation) lastPresentation = presentation;
  const sourcePresentation = presentation || lastPresentation;
  const next = cornerSceneActive
    ? window.MashaSceneMap.resolveCornerScene(sourcePresentation)
    : window.MashaSceneMap.resolveScene(sourcePresentation);
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
  addLocalDocument.disabled = !enabled || waiting;
  newConversationButton.disabled = !enabled || waiting;
  recentToggle.disabled = !enabled || waiting;
  specialEveningToggle.disabled = !enabled || waiting;
  specialProximityToggle.disabled =
    !enabled || waiting || Boolean(pendingConfirmation);
  homeAttentionTrigger.disabled = !enabled || waiting;
  commitmentsTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  activityTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  proactiveTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  continuityTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  reflectionsTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  workbenchTrigger.disabled = !enabled || waiting || Boolean(pendingConfirmation);
  safetyTrigger.disabled = !enabled;
}

function formatLocalByteSize(value) {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} МБ`;
  return `${Math.max(1, Math.ceil(value / 1024))} КБ`;
}

function renderLocalDocumentChip(document) {
  stagedLocalDocument = document || null;
  localDocumentChip.hidden = !stagedLocalDocument;
  localDocumentLabel.textContent = stagedLocalDocument
    ? `${stagedLocalDocument.display_name} · ${formatLocalByteSize(stagedLocalDocument.byte_size)}`
    : "";
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
  commitmentRescheduleSurface.hidden = true;
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
  // Any non-Workbench surface returns to the normal Presence scene first.
  setCornerSceneActive(false);
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
    operationSurface,
    memoryCandidateSurface,
    commitmentCreateSurface,
    commitmentRescheduleSurface,
    skillInstallSurface,
    continuityCreateSurface,
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
  setCornerSceneActive(false);
  candidatePresentation.defer();
  clearTimeout(surfaceTransitionTimer);
  const visible = [commitmentsSurface, activitySurface, proactiveSurface, continuitySurface, commitmentRescheduleSurface, reflectionsSurface, workbenchSurface, operationSurface]
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
    network_access: "доступ к публичному интернету",
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
  workbenchConnections.replaceChildren();
  workbenchSkills.replaceChildren();
  workbenchPermissions.replaceChildren();
  const profiles = view?.profiles || [];
  const connectionState = {
    ready: "Подключён",
    needs_reconnect: "Нужно переподключить",
    disconnected: "Не подключён",
  };
  const connectionAccess = {
    read_only: "Только чтение",
    read_with_create_setup: "Чтение · создание после отдельного подключения",
    read_and_create: "Чтение · создание и изменение событий",
    read_with_document_create_setup: "Чтение · создание документов после отдельного подключения",
    read_and_document_create: "Чтение · создание документов",
  };
  for (const connection of view?.connections || []) {
    workbenchConnections.append(workbenchItem(
      connection.display_name,
      `${connectionAccess[connection.access] || "Только чтение"} · ${connectionState[connection.state] || "Не подключён"}`,
    ));
  }
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
    const item = workbenchItem(
      skill.name,
      skill.summary || (skill.runtime_supported ? `Могу использовать для: ${capabilityText}.` : "Пока просто хранится здесь и ничего не запускает."),
    );
    if (skill.usage) item.append(Object.assign(document.createElement("p"), { textContent: skill.usage }));
    if (skill.can?.length) item.append(Object.assign(document.createElement("p"), { textContent: `Могу: ${skill.can.join(" · ")}` }));
    if (skill.cannot?.length) item.append(Object.assign(document.createElement("p"), { textContent: `Не могу: ${skill.cannot.join(" · ")}` }));
    const technical = document.createElement("details");
    technical.className = "workbench-other-options";
    technical.append(
      Object.assign(document.createElement("summary"), { textContent: "Технически" }),
      Object.assign(document.createElement("p"), { textContent: `${skill.integrity} · ${skill.risk || "—"} · ${skill.scopes?.join(", ") || "—"}` }),
    );
    item.append(technical);
    workbenchSkills.append(item);
  }
  const skillNames = new Map((view?.skills || []).map((skill) => [skill.skill_id, skill.name]));
  for (const grant of view?.grants || []) {
    workbenchPermissions.append(workbenchItem(
      grant.label || (grant.mode === "self" ? "Могу сама" : grant.mode === "forbidden" ? "Запрещено" : "Сначала спрошу тебя"),
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
  if (!workbenchConnections.children.length) workbenchConnections.append(objectEmpty("Пока ничего не подключено."));
  if (!workbenchSkills.children.length) workbenchSkills.append(objectEmpty("Навыков в локальном реестре пока нет."));
  if (!workbenchPermissions.children.length) workbenchPermissions.append(objectEmpty("Постоянных разрешений и ожидающих решений нет."));
}

function renderActiveContinuityThread(thread) {
  activeContinuityThread = thread || null;
  threadContext.hidden = !activeContinuityThread;
  threadContextTitle.textContent = activeContinuityThread?.summary || "";
  threadContextClear.disabled = inFlight || !activeContinuityThread;
}

function renderContinuity(view) {
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
    action.textContent = (
      activeContinuityThread?.thread_id === thread.thread_id
        ? "Эта нить уже рядом"
        : "Взять эту нить с собой"
    );
    action.disabled =
      inFlight
      || activeContinuityThread?.thread_id === thread.thread_id;
    action.addEventListener("click", () => {
      if (!ready || inFlight || action.disabled) return;
      bridge.activateContinuityThread(thread.thread_id);
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

function updateHistoryShelfState() {
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
      button.textContent = decision === "acknowledge" ? "Понял" : "Убрать";
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
    timeZone: homeTimeZone,
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

      let reschedule = null;
      let clearDue = null;

    if (item.time_bucket === "stale_overdue") {
      reschedule = document.createElement("button");
      reschedule.type = "button";
      reschedule.className = "commitment-cancel";
      reschedule.textContent = "Перенести";
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

        if (reschedule) {
          reschedule.disabled = true;
        }

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

        if (reschedule) {
          reschedule.disabled = true;
        }

        if (clearDue) {
          clearDue.disabled = true;
        }

        bridge.proposeCommitmentCancellation(
          item.commitment_id
        );
      });

      if (reschedule) {
        reschedule.addEventListener("click", () => {
        if (
          !ready
          || inFlight
          || pendingConfirmation
        ) return;

        pendingCommitmentReschedule = {
          id: item.commitment_id,
          text: item.text,
        };

        commitmentsSurface.hidden = true;

        commitmentRescheduleSubject.textContent =
          item.text;

        commitmentRescheduleDue.value = "";

        commitmentRescheduleHint.textContent =
          "Например: «завтра в 18:00» или «через 2 часа».";

        commitmentRescheduleHint.classList.remove(
          "is-error"
        );

        commitmentRescheduleSurface.hidden = false;
        commitmentRescheduleDue.focus();
      });
    }

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

      if (reschedule) {
        actions.append(reschedule);
      }

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

function showReminderToast(interactions, interactionId) {
  const reminder = interactionSafety.reminderToastProjection(
    interactions,
    interactionId,
  );
  if (!reminder) return;
  clearTimeout(reminderToastTimer);
  const due = reminder.dueAt ? ` · ${formatDueAt(reminder.dueAt)}` : "";
  reminderToastMessage.textContent = `${reminder.message}${due}`;
  reminderToast.hidden = false;
  bridge.recordReminderPresented(reminder.interactionId, new Date().toISOString());
  reminderToastTimer = window.setTimeout(() => {
    reminderToast.hidden = true;
    reminderToastTimer = null;
  }, reminder.durationMs);
}

function renderBackgroundProactiveProjection(payload) {
  interactionSafety.preserveComposer(input, document, () => {
    renderProactiveInteractions(payload.interactions);
    renderHomeAttention(payload.attention);
    showReminderToast(payload.interactions, payload.new_interaction_id);
    proactiveTrigger.hidden = !(payload.interactions?.items?.length > 0);
  });
}

function renderHomeAttention(attention) {
  attentionLines.replaceChildren();

  const items = attention?.attention_items || [];
  const actualKinds = new Set(items.map((item) => item.kind));
  attentionMagicState.commitments = items.filter((item) =>
    item.kind === "overdue_commitment" || item.kind === "upcoming_commitment"
  ).length;
  attentionMagicState.freshOverdueCommitments = actualKinds.has("overdue_commitment") ? 1 : 0;
  attentionMagicState.proactive = items.filter((item) => item.kind === "proactive_interaction").length;
  attentionMagicState.pendingConfirmation = actualKinds.has("pending_confirmation");
  attentionMagicState.modelAvailable = !actualKinds.has("model_unavailable");
  attentionMagicState.safetyEngaged = actualKinds.has("safety_stop");
  if (items.length === 0) {
    Object.assign(attentionMagicState, {
      commitments: 0,
      freshOverdueCommitments: 0,
      proactive: 0,
      pendingConfirmation: false,
      modelAvailable: true,
      safetyEngaged: false,
    });
  }
  updateAttentionMagic();
  const hasImportant = items.some(
  (item) => item.urgency === "important"
);

const hasPendingDecision = items.some(
  (item) =>
    item.kind === "pending_confirmation"
    || item.kind === "model_unavailable"
);

const hasSomething = items.length > 0;

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

    if (item.kind === "proactive_interaction" && item.interaction_id && item.allowed_actions?.length) {
      const actions = document.createElement("div");
      actions.className = "attention-actions";
      const addAction = (decision, label) => {
        if (!item.allowed_actions.includes(decision)) return;
        const action = document.createElement("button");
        action.type = "button";
        action.textContent = label;
        action.disabled = inFlight;
        action.addEventListener("click", () => bridge.resolveHomeAttentionProactive(item.interaction_id, decision));
        actions.append(action);
      };
      addAction("acknowledge", "Понял");
      addAction("dismiss", "Убрать");
      copy.append(actions);
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
  const remainder100 = freshOverdue % 100;
  const remainder10 = freshOverdue % 10;
  const noun = remainder10 === 1 && remainder100 !== 11
    ? "просроченное дело"
    : remainder10 >= 2 && remainder10 <= 4 && (remainder100 < 12 || remainder100 > 14)
      ? "просроченных дела"
      : "просроченных дел";
  summaryBits.push(
    `${freshOverdue} ${noun}`
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
    const observations = message.external_observations?.length
      ? message.external_observations
      : message.external_observation ? [message.external_observation] : [];
    const search = observations.find((observation) => observation.kind === "web_search" && observation.sources?.length);
    const fetched = observations.find((observation) => observation.kind === "web_fetch" && observation.page);
    const documentRead = observations.find((observation) => observation.kind === "web_fetch" && observation.document);
    if (documentRead?.document) {
      const pdf = documentRead.document;
      const details = document.createElement("details");
      details.className = "message-page";
      const summary = document.createElement("summary");
      const scope = pdf.truncated ? "Прочитала часть PDF" : "Прочитала PDF";
      summary.textContent = `${scope} · ${pdf.page_count} стр. · ${pdf.display_name || pdf.domain}`;
      const body = document.createElement("div");
      body.className = "message-page-body";
      if (pdf.title) body.append(Object.assign(document.createElement("span"), { textContent: pdf.title }));
      body.append(Object.assign(document.createElement("span"), {
        textContent: `Прочитано страниц: ${pdf.pages_read}`,
      }));
      if (pdf.source_kind === "web") {
        const open = document.createElement("button");
        open.type = "button";
        open.className = "message-source";
        open.textContent = "Открыть источник";
        open.addEventListener("click", () => {
          if (ready) bridge.openObservationSource(documentRead.observation_id, "page");
        });
        body.append(open);
      }
      const technical = document.createElement("details");
      technical.className = "message-page-technical";
      technical.append(
        Object.assign(document.createElement("summary"), { textContent: "Технически" }),
        Object.assign(document.createElement("span"), {
          textContent: `PDF · ${pdf.truncated ? "частично" : "полностью"} · ${pdf.extractor}`,
        }),
      );
      body.append(technical);
      details.append(summary, body);
      item.append(details);
    }
    for (const pdf of message.local_documents || []) {
      const details = document.createElement("details");
      details.className = "message-page";
      const summary = document.createElement("summary");
      const scope = pdf.truncated ? "Прочитала часть PDF" : "Прочитала PDF";
      summary.textContent = `${scope} · ${pdf.page_count} стр. · ${pdf.display_name || "локальный файл"}`;
      const body = document.createElement("div");
      body.className = "message-page-body";
      if (pdf.title) body.append(Object.assign(document.createElement("span"), { textContent: pdf.title }));
      body.append(Object.assign(document.createElement("span"), { textContent: `Прочитано страниц: ${pdf.pages_read}` }));
      const technical = document.createElement("details");
      technical.className = "message-page-technical";
      technical.append(
        Object.assign(document.createElement("summary"), { textContent: "Технически" }),
        Object.assign(document.createElement("span"), { textContent: `PDF · локальный файл · ${pdf.truncated ? "частично" : "полностью"} · ${pdf.extractor}` }),
      );
      body.append(technical);
      details.append(summary, body);
      item.append(details);
    }
    if (fetched?.page) {
      const details = document.createElement("details");
      details.className = "message-page";
      const summary = document.createElement("summary");
      summary.textContent = `Прочитала страницу · ${fetched.page.domain} · ${search?.sources?.length ? `Источники ${search.sources.length}` : "Источник"}`;
      const body = document.createElement("div");
      body.className = "message-page-body";
      if (fetched.page.title) body.append(Object.assign(document.createElement("span"), { textContent: fetched.page.title }));
      const open = document.createElement("button");
      open.type = "button";
      open.className = "message-source";
      open.textContent = "Открыть источник";
      open.addEventListener("click", () => {
        if (ready) bridge.openObservationSource(fetched.observation_id, "page");
      });
      body.append(open);
      const technical = document.createElement("details");
      technical.className = "message-page-technical";
      technical.append(
        Object.assign(document.createElement("summary"), { textContent: "Технически" }),
        Object.assign(document.createElement("span"), {
          textContent: `${fetched.page.content_type} · ${fetched.page.truncated ? "частично" : "полностью"} · ${fetched.page.extractor}`,
        }),
      );
      body.append(technical);
      details.append(summary, body);
      item.append(details);
    }
    if (search?.sources?.length) {
      const observation = search;
      const sources = document.createElement("div");
      sources.className = "message-sources";
      sources.append(Object.assign(document.createElement("span"), {
        className: "message-sources-label",
        textContent: "Источники",
      }));
      for (const source of observation.sources) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "message-source";
        button.textContent = `${source.source_id} · ${source.domain}`;
        button.title = source.title;
        button.addEventListener("click", () => {
          if (!ready) return;
          bridge.openObservationSource(observation.observation_id, source.source_id);
        });
        sources.append(button);
      }
      item.append(sources);
    }
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

  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: homeTimeZone,
    day: "numeric",
    month: "short",
  }).format(date);
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
  homeTimeZone =
    snapshot.home_timezone || homeTimeZone;
  const { status, active_model: activeModel, presentation } = snapshot;
  const presentationRevision =
  Number(presentation?.revision);

if (
  presenceSettleTimer !== null
  && Number.isInteger(
    pendingPresenceSettleRevision
  )
  && Number.isInteger(
    presentationRevision
  )
  && presentationRevision
    !== pendingPresenceSettleRevision
) {
  cancelAssistantSettle();
}
  attentionMagicState.modelAvailable = Boolean(status.model_available);
  attentionMagicState.safetyEngaged = Boolean(status.emergency_stop_engaged);
  updateAttentionMagic();
  document.documentElement.dataset.homeState = presentation.home_state;
  const homeMoment =
  presentation.home_moment || "ordinary";

const specialEveningActive =
  homeMoment === "special_evening";

const specialEveningAvailable =
  window.MashaSceneMap.resolveHomePeriod(presentation)
  === "evening";

document.documentElement.dataset.homeMoment =
  homeMoment;

const homeProximity =
  presentation.home_proximity || "wide";

document.documentElement.dataset.homeProximity =
  homeProximity;

specialEveningToggle.hidden =
  !specialEveningAvailable;

specialProximityToggle.hidden =
  !specialEveningActive;

specialProximityToggle.dataset.proximity =
  homeProximity;

specialProximityToggle.textContent =
  homeProximity === "wide"
    ? "Ближе"
    : homeProximity === "close"
    ? "Ещё ближе"
    : "Чуть дальше";

specialEveningToggle.setAttribute(
  "aria-pressed",
  String(specialEveningActive)
);

specialEveningToggle.textContent =
  specialEveningActive
    ? "Вернуться"
    : "Вдвоём";
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
    renderHomeAttention(payload.attention);
    renderConversation(payload.conversation);
    activeConversationId = payload.conversation?.conversation_id || null;
    renderRecent(payload.recent, activeConversationId);
    commitmentsCount.textContent = String(payload.commitments_count || 0);
    activityTrigger.hidden = !(payload.agent_runs_count > 0);
    proactiveTrigger.hidden = !(payload.proactive_interactions_count > 0);
    // Empty history is still a real state: this is where the first explicitly
    // confirmed shared moment or open thread is created.
    continuityTrigger.hidden = false;
    continuityItemCount = Number(payload.continuity_count || 0);
    updateHistoryShelfState();
    reflectionsTrigger.hidden = !(payload.reflection_items_count > 0);
    ready = true;
    clearLocalFailure();
    setComposerState({ enabled: true });
    renderPendingConfirmation(payload.pending_confirmation);
    renderMemoryCandidate(payload.memory_candidate);
    renderActiveContinuityThread(payload.active_continuity_thread);
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
    payload.kind === "commitment_reschedule_rejected"
    ) {
    submitCommitmentReschedule.disabled = false;
    cancelCommitmentReschedule.disabled = false;
    commitmentRescheduleHint.textContent =
      payload.message
      || "Не смогла понять этот срок.";

    commitmentRescheduleHint.classList.add(
      "is-error"
    );
    commitmentRescheduleDue.focus();
    return;
  }
  if (
  payload.kind === "commitment_completion_proposed"
  || payload.kind === "commitment_cancellation_proposed"
  || payload.kind === "commitment_due_change_proposed"
) {
  if (
  payload.kind === "commitment_due_change_proposed"
    ) {
      pendingCommitmentReschedule = null;

      submitCommitmentReschedule.disabled = false;
      cancelCommitmentReschedule.disabled = false;
    }
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
      renderBackgroundProactiveProjection(payload);
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
      : "Убрала без других изменений.";
    bridge.loadHomeAttention();
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
  if (payload.kind === "continuity_thread_activated") {
    applySnapshot(payload.snapshot);
    renderActiveContinuityThread(payload.thread);
    returnToConversation();
    surfaceStatus.textContent = "Нить рядом. Продолжай своими словами.";
    input.focus();
    return;
  }

  if (payload.kind === "continuity_thread_cleared") {
    applySnapshot(payload.snapshot);
    renderActiveContinuityThread(null);
    surfaceStatus.textContent = "";
    input.focus();
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
  if (["activities_unavailable", "proactive_unavailable", "proactive_resolution_rejected", "continuity_unavailable", "continuity_context_unavailable", "reflections_unavailable", "reflection_resolution_rejected", "honest_help_rejected", "workbench_unavailable"].includes(payload.kind)) {
    showLocalFailure("Локальное состояние сейчас не удалось открыть.");
    return;
  }
  if (["human_search_unavailable", "memory_candidate_rejected", "memory_restore_unavailable"].includes(payload.kind)) {
    showLocalFailure(payload.message || "Сейчас это действие недоступно. Попробуй ещё раз чуть позже.");
    return;
  }
  if (payload.kind === "external_source_unavailable") {
    showLocalFailure("Этот источник сейчас не удалось открыть.");
    return;
  }
  if (payload.kind === "local_document_selected") {
    renderLocalDocumentChip(payload.document);
    if (!input.value.trim()) {
      input.value = "Прочитай этот PDF и расскажи, о чём он.";
      fitComposer();
    }
    setComposerState({ enabled: ready });
    return;
  }
  if (payload.kind === "local_document_cleared" || payload.kind === "local_document_cancelled") {
    renderLocalDocumentChip(null);
    setComposerState({ enabled: ready });
    return;
  }
  if (payload.kind === "local_document_failed" || payload.kind === "local_document_rejected") {
    if (provisionalUser) provisionalUser.remove();
    provisionalUser = null;
    renderLocalDocumentChip(null);
    setComposerState({ enabled: ready });
    showLocalFailure("Этот PDF сейчас не получилось безопасно прочитать.");
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
    renderActiveContinuityThread(null);
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
  if (payload.kind === "presence_settled") {
  cancelAssistantSettle();

  applySnapshot(payload.snapshot);

  title.textContent = "Я рядом.";
  surfaceStatus.textContent = "";

  return;
  }
  if (payload.kind === "home_attention") {
    renderHomeAttention(payload.attention);
    homeAttention.hidden = false;
    document.documentElement.dataset.homeAttention = "active";
    homeAttentionTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (payload.kind === "home_attention_resolved") {
    applySnapshot(payload.snapshot);
    renderHomeAttention(payload.attention);
    surfaceStatus.textContent = payload.interaction.state === "acknowledged"
      ? "Хорошо, учла."
      : "Убрала без других изменений.";
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
    renderActiveContinuityThread(payload.active_continuity_thread);
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
        scheduleAssistantSettle(
        payload.snapshot,
        result
      );
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
    renderActiveContinuityThread(payload.active_continuity_thread);
    if (payload.continuity_count !== undefined) {
      continuityItemCount = Number(payload.continuity_count || 0);
      updateHistoryShelfState();
    }
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
  if (payload.kind === "special_evening_changed") {
    clearLocalFailure();
    applySnapshot(payload.snapshot);
    return;
  }

  if (payload.kind === "special_evening_unavailable") {
    showLocalFailure(
      "Этот уголок Дома оставим для вечера."
    );
    return;
  }

  if (payload.kind === "special_evening_rejected") {
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
  if (stagedLocalDocument) {
    const token = stagedLocalDocument.token;
    renderLocalDocumentChip(null);
    bridge.submitMessageWithDocument(content, token);
  } else {
    bridge.submitMessage(content);
  }
});

addLocalDocument.addEventListener("click", () => {
  if (ready && !inFlight) bridge.chooseLocalDocument();
});

newConversationButton.addEventListener("click", () => {
  if (!ready || inFlight) return;
  candidatePresentation.defer();
  bridge.startNewConversation();
});

specialEveningToggle.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) {
    return;
  }

  const active =
    document.documentElement.dataset.homeMoment
    === "special_evening";

  bridge.setSpecialEvening(!active);
});

specialProximityToggle.addEventListener("click", () => {
  if (
    !ready
    || inFlight
    || pendingConfirmation
    || specialProximityToggle.hidden
  ) {
    return;
  }

  bridge.advanceSpecialEveningProximity();
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

cancelCommitmentReschedule.addEventListener(
  "click",
  () => {
    pendingCommitmentReschedule = null;

    commitmentRescheduleSurface.hidden = true;
    commitmentsSurface.hidden = false;

    commitmentRescheduleDue.value = "";
    commitmentRescheduleHint.classList.remove(
      "is-error"
    );
  }
);

submitCommitmentReschedule.addEventListener(
  "click",
  () => {
    if (
      !ready
      || inFlight
      || pendingConfirmation
      || !pendingCommitmentReschedule
    ) return;

    const dueText =
      commitmentRescheduleDue.value.trim();

    if (!dueText) {
      commitmentRescheduleHint.textContent =
        "Скажи, когда теперь это сделать.";

      commitmentRescheduleHint.classList.add(
        "is-error"
      );

      commitmentRescheduleDue.focus();
      return;
    }

    submitCommitmentReschedule.disabled = true;
    cancelCommitmentReschedule.disabled = true;

    bridge.proposeCommitmentReschedule(
      pendingCommitmentReschedule.id,
      dueText
    );
  }
);

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
  if (opening) {
    transitionToSurface(() => bridge.loadWorkbench());
    // Workbench owns a distinct visual state while keeping the same Home.
    setCornerSceneActive(true);
  } else {
    returnToConversation();
  }
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

threadContextClear.addEventListener("click", () => {
  if (!ready || inFlight || !activeContinuityThread) return;
  threadContextClear.disabled = true;
  bridge.clearContinuityThread();
});

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
