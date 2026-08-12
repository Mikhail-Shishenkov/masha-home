"use strict";

// UI-05D talks only to the closed `mashaHome` WebChannel object. It has no
// browser network access and no references to Python/domain services.
document.documentElement.dataset.renderer = "local-shell";

const surface = document.getElementById("conversation-surface");
const transcript = document.getElementById("transcript");
const composer = document.getElementById("composer");
const input = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const newConversationButton = document.getElementById("new-conversation");
const recentToggle = document.getElementById("recent-conversations-toggle");
const recentPanel = document.getElementById("recent-conversations");
const recentList = document.getElementById("recent-list");
const title = document.getElementById("conversation-title");
const surfaceStatus = document.getElementById("surface-status");
const runtimeTruth = document.getElementById("runtime-truth");
const homeAttentionTrigger = document.getElementById("home-attention-trigger");
const homeAttention = document.getElementById("home-attention");
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
const closeCommitments = document.getElementById("close-commitments");

let bridge = null;
let ready = false;
let inFlight = false;
let provisionalUser = null;
let activeSceneId = "scene.home.idle";
let activeSceneLayer = 0;
let activeConversationId = null;
let sceneTransitionRevision = 0;
let sceneTransitionTimer = null;
let pendingConfirmation = null;
const COMPOSER_MIN_HEIGHT = 44;
const COMPOSER_MAX_HEIGHT = 112;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function fitComposer() {
  input.style.height = `${COMPOSER_MIN_HEIGHT}px`;
  input.style.height = `${Math.min(input.scrollHeight, COMPOSER_MAX_HEIGHT)}px`;
  input.classList.toggle("is-scrollable", input.scrollHeight > COMPOSER_MAX_HEIGHT);
}

function applyScene(presentation) {
  const next = window.MashaSceneMap.resolveScene(presentation);
  document.documentElement.dataset.scene = next.id;
  if (next.id === activeSceneId) return;

  const revision = ++sceneTransitionRevision;
  const current = sceneLayers[activeSceneLayer];
  const incoming = sceneLayers[1 - activeSceneLayer];
  const transition = window.MashaSceneMap.resolveTransition({
    presentation,
    reducedMotion: reducedMotion.matches,
  });
  document.documentElement.dataset.sceneTransition = transition.kind;
  document.documentElement.style.setProperty("--scene-transition-ms", `${transition.durationMs}ms`);
  clearTimeout(sceneTransitionTimer);
  let transitionStarted = false;
  for (const layer of sceneLayers) {
    layer.onload = null;
    layer.onerror = null;
    layer.classList.remove("is-incoming");
  }
  incoming.classList.remove("is-active");

  const completeTransition = () => {
    if (revision !== sceneTransitionRevision) return;
    current.classList.remove("is-active", "is-incoming");
    incoming.classList.remove("is-incoming");
    incoming.classList.add("is-active");
    activeSceneLayer = sceneLayers.indexOf(incoming);
    activeSceneId = next.id;
  };
  const showIncoming = () => {
    if (revision !== sceneTransitionRevision || transitionStarted) return;
    transitionStarted = true;
    incoming.alt = next.alt;
    incoming.classList.add("is-incoming");
    sceneTransitionTimer = window.setTimeout(completeTransition, transition.durationMs + 40);
  };
  incoming.onload = showIncoming;
  incoming.onerror = () => {
    if (revision !== sceneTransitionRevision) return;
    incoming.src = "assets/canonical-master.png";
    incoming.alt = "Маша дома, в своей гостиной";
  };
  incoming.src = next.source;
  if (incoming.complete) showIncoming();
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
  safetyTrigger.disabled = !enabled;
}

function closeTemporarySurfaces() {
  recentPanel.hidden = true;
  homeAttention.hidden = true;
  commitmentsSurface.hidden = true;
  document.documentElement.dataset.commitments = "closed";
  document.documentElement.dataset.homeAttention = "closed";
  homeAttentionTrigger.setAttribute("aria-expanded", "false");
  commitmentsTrigger.setAttribute("aria-expanded", "false");
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

function renderCommitments(view) {
  const items = view?.items || [];
  commitmentsCount.textContent = String(items.filter((item) => item.can_propose_completion).length);
  commitmentsList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "commitment-empty";
    empty.textContent = "Сейчас здесь спокойно — открытых обязательств нет.";
    commitmentsList.append(empty);
    return;
  }
  for (const item of items) {
    const row = document.createElement("li");
    row.className = "commitment-item";
    row.dataset.status = item.status;
    const copy = document.createElement("div");
    copy.className = "commitment-copy";
    const text = document.createElement("p");
    text.className = "commitment-text";
    text.textContent = item.text;
    const meta = document.createElement("p");
    meta.className = "commitment-meta";
    const due = item.due_at ? ` · до ${formatDueAt(item.due_at)}` : "";
    meta.textContent = `${commitmentStatusLabels[item.status] || item.status}${due}`;
    copy.append(text, meta);
    row.append(copy);
    if (item.can_propose_completion) {
      const complete = document.createElement("button");
      complete.type = "button";
      complete.className = "commitment-complete";
      complete.textContent = "Готово";
      complete.addEventListener("click", () => {
        if (!ready || inFlight || pendingConfirmation) return;
        complete.disabled = true;
        bridge.proposeCommitmentCompletion(item.commitment_id);
      });
      row.append(complete);
    }
    commitmentsList.append(row);
  }
}

function hideOperationSurface() {
  operationSurface.hidden = true;
  document.documentElement.dataset.operation = "none";
}

function renderPendingConfirmation(confirmation) {
  pendingConfirmation = confirmation;
  if (!confirmation) {
    hideOperationSurface();
    setComposerState({ enabled: ready, waiting: inFlight });
    return;
  }
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
  operationSurface.hidden = false;
  document.documentElement.dataset.operation = "confirmation";
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
  operationTitle.textContent = confirmed ? "Обязательство обновлено" : rejected ? "Ничего не меняла" : "Изменение не применено";
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
  const lines = [];
  if (attention.emergency_stop_engaged) {
    lines.push("Автономные действия стоят на паузе.");
  } else {
    lines.push("Аварийная остановка сейчас не включена.");
  }
  if (!attention.model_available) lines.push(attention.model_label);
  if (attention.active_conversation) {
    lines.push(`Продолжается разговор: ${attention.active_conversation.preview}`);
  } else {
    lines.push("Наша первая беседа ещё впереди.");
  }
  if (attention.commitments_count) {
    lines.push(`Рядом ${attention.commitments_count} ${attention.commitments_count === 1 ? "дело" : "дел"}.`);
  }
  for (const content of lines) {
    const paragraph = document.createElement("p");
    paragraph.textContent = content;
    attentionLines.append(paragraph);
  }
}

function applySafety(engaged) {
  document.documentElement.dataset.safety = engaged ? "autonomy_stopped" : "autonomy_active";
  safetyOverlay.hidden = !engaged;
  safetyTrigger.hidden = engaged;
  if (engaged) closeTemporarySurfaces();
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
  item.textContent = message.content;
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

function renderRecent(items, activeId = activeConversationId) {
  recentList.replaceChildren();
  surface.classList.toggle("has-conversations", Boolean(items?.length));
  if (!items?.length) {
    const empty = document.createElement("li");
    empty.className = "recent-empty";
    empty.textContent = "Здесь появятся наши разговоры.";
    recentList.append(empty);
    return;
  }
  for (const item of items) {
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
}

function applySnapshot(snapshot) {
  if (!snapshot) return;
  const { status, active_model: activeModel, presentation } = snapshot;
  document.documentElement.dataset.homeState = presentation.home_state;
  document.documentElement.dataset.safety = presentation.overlays.safety;
  document.documentElement.dataset.model = presentation.overlays.model;
  document.documentElement.dataset.presence = presentation.presence.activity;
  applyScene(presentation);

  const pieces = ["Локально", activeModel.display_name];
  if (!status.model_available) pieces.push("модель недоступна");
  if (status.emergency_stop_engaged) pieces.push("автономность на паузе");
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
    applySnapshot(payload.snapshot);
    renderConversation(payload.conversation);
    activeConversationId = payload.conversation?.conversation_id || null;
    renderRecent(payload.recent, activeConversationId);
    commitmentsCount.textContent = String(payload.commitments_count || 0);
    ready = true;
    clearLocalFailure();
    setComposerState({ enabled: true });
    renderPendingConfirmation(payload.pending_confirmation);
    return;
  }
  if (payload.kind === "commitments_loaded") {
    applySnapshot(payload.snapshot);
    renderCommitments(payload.commitments);
    recentPanel.hidden = true;
    homeAttention.hidden = true;
    commitmentsSurface.hidden = false;
    document.documentElement.dataset.commitments = "active";
    commitmentsTrigger.setAttribute("aria-expanded", "true");
    return;
  }
  if (payload.kind === "commitment_completion_proposed") {
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
  if (payload.kind === "commitment_operation_rejected" || payload.kind === "commitments_unavailable") {
    showLocalFailure("Не получилось открыть это действие. Обнови список дел и попробуй ещё раз.");
    commitmentsSurface.hidden = true;
    document.documentElement.dataset.commitments = "closed";
    commitmentsTrigger.setAttribute("aria-expanded", "false");
    return;
  }
  if (payload.kind === "conversation_started") {
    applySnapshot(payload.snapshot);
    renderConversation(null);
    clearLocalFailure();
    surfaceStatus.textContent = "Новый разговор. Прежняя история сохранена.";
    activeConversationId = null;
    bridge.loadRecentConversations();
    setComposerState({ enabled: ready });
    input.focus();
    pendingConfirmation = null;
    hideOperationSurface();
    return;
  }
  if (payload.kind === "recent_conversations") {
    renderRecent(payload.recent, payload.active_conversation_id);
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
    applySnapshot(payload.snapshot);
    renderConversation(payload.conversation);
    activeConversationId = payload.conversation.conversation_id;
    renderRecent(payload.recent, activeConversationId);
    recentPanel.hidden = true;
    clearLocalFailure();
    setComposerState({ enabled: ready });
    renderPendingConfirmation(payload.pending_confirmation);
    return;
  }
  if (payload.kind === "turn_started") {
    clearLocalFailure();
    provisionalUser = renderMessage({ role: "user", content: payload.content }, { provisional: true });
    surface.classList.add("has-history");
    title.textContent = "Слушаю.";
    surfaceStatus.textContent = "Слушаю…";
    applySnapshot(payload.snapshot);
    scrollToLatestIfAppropriate(true);
    return;
  }
  if (payload.kind === "turn_thinking") {
    applySnapshot(payload.snapshot);
    surfaceStatus.textContent = "Думаю…";
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
      title.textContent = "Я здесь.";
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
    ready = false;
    setComposerState({ enabled: false });
    showLocalFailure("Локальный Дом сейчас не готов к разговору.");
  }
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = input.value.trim();
  if (!ready || inFlight || !content) return;
  input.value = "";
  fitComposer();
  setComposerState({ enabled: true, waiting: true });
  bridge.submitMessage(content);
});

newConversationButton.addEventListener("click", () => {
  if (!ready || inFlight) return;
  bridge.startNewConversation();
});

recentToggle.addEventListener("click", () => {
  if (!ready || inFlight) return;
  homeAttention.hidden = true;
  document.documentElement.dataset.homeAttention = "closed";
  homeAttentionTrigger.setAttribute("aria-expanded", "false");
  commitmentsSurface.hidden = true;
  document.documentElement.dataset.commitments = "closed";
  commitmentsTrigger.setAttribute("aria-expanded", "false");
  recentPanel.hidden = !recentPanel.hidden;
  if (!recentPanel.hidden) bridge.loadRecentConversations();
});

homeAttentionTrigger.addEventListener("click", () => {
  if (!ready || inFlight) return;
  recentPanel.hidden = true;
  commitmentsSurface.hidden = true;
  document.documentElement.dataset.commitments = "closed";
  commitmentsTrigger.setAttribute("aria-expanded", "false");
  if (homeAttention.hidden) {
    bridge.loadHomeAttention();
  } else {
    homeAttention.hidden = true;
    document.documentElement.dataset.homeAttention = "closed";
    homeAttentionTrigger.setAttribute("aria-expanded", "false");
  }
});

commitmentsTrigger.addEventListener("click", () => {
  if (!ready || inFlight || pendingConfirmation) return;
  recentPanel.hidden = true;
  homeAttention.hidden = true;
  document.documentElement.dataset.homeAttention = "closed";
  if (commitmentsSurface.hidden) {
    bridge.loadCommitments();
  } else {
    commitmentsSurface.hidden = true;
    document.documentElement.dataset.commitments = "closed";
    commitmentsTrigger.setAttribute("aria-expanded", "false");
  }
});

closeCommitments.addEventListener("click", () => {
  commitmentsSurface.hidden = true;
  document.documentElement.dataset.commitments = "closed";
  commitmentsTrigger.setAttribute("aria-expanded", "false");
  input.focus();
});

safetyTrigger.addEventListener("click", () => {
  if (!ready) return;
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
  hideOperationSurface();
  input.focus();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeTemporarySurfaces();
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
window.addEventListener("blur", closeTemporarySurfaces);

input.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (!sendButton.disabled) composer.requestSubmit();
});

input.addEventListener("input", () => {
  fitComposer();
  setComposerState({ enabled: ready, waiting: inFlight });
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
