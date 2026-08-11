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
const sceneLayers = [...document.querySelectorAll(".scene")];

let bridge = null;
let ready = false;
let inFlight = false;
let provisionalUser = null;
let activeSceneId = "scene.home.idle";
let activeSceneLayer = 0;
let activeConversationId = null;

function applyScene(presentation) {
  const next = window.MashaSceneMap.resolveScene(presentation);
  document.documentElement.dataset.scene = next.id;
  if (next.id === activeSceneId) return;

  const current = sceneLayers[activeSceneLayer];
  const incoming = sceneLayers[1 - activeSceneLayer];
  let applied = false;
  const showIncoming = () => {
    if (applied) return;
    applied = true;
    incoming.alt = next.alt;
    incoming.classList.add("is-active");
    current.classList.remove("is-active");
    activeSceneLayer = sceneLayers.indexOf(incoming);
    activeSceneId = next.id;
  };
  incoming.addEventListener("load", showIncoming, { once: true });
  incoming.addEventListener("error", () => {
    incoming.src = "assets/canonical-master.png";
    incoming.alt = "Маша дома, в своей гостиной";
  }, { once: true });
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
    ready = true;
    clearLocalFailure();
    setComposerState({ enabled: true });
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
    return;
  }
  if (payload.kind === "recent_conversations") {
    renderRecent(payload.recent, payload.active_conversation_id);
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
    scrollToLatestIfAppropriate(true);
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
  setComposerState({ enabled: true, waiting: true });
  bridge.submitMessage(content);
});

newConversationButton.addEventListener("click", () => {
  if (!ready || inFlight) return;
  bridge.startNewConversation();
});

recentToggle.addEventListener("click", () => {
  if (!ready || inFlight) return;
  recentPanel.hidden = !recentPanel.hidden;
  if (!recentPanel.hidden) bridge.loadRecentConversations();
});

input.addEventListener("input", () => setComposerState({ enabled: ready, waiting: inFlight }));

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
