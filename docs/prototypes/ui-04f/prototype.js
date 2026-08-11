"use strict";

const {
  registry,
  scenarioOrder,
  initialState,
  reduce,
  project,
  characterAsset,
} = UI04F;

const root = document.querySelector("#living-home");
const roomImage = document.querySelector("#room-image");
const frames = [
  { frame: document.querySelector("#character-frame-a"), image: document.querySelector("#character-a") },
  { frame: document.querySelector("#character-frame-b"), image: document.querySelector("#character-b") },
];
const conversation = document.querySelector("#conversation-surface");
const activity = document.querySelector("#activity-zone");
const progressFill = document.querySelector("#progress-fill");
const progressLabel = document.querySelector("#progress-label");
const activityStatus = document.querySelector("#activity-status");
const title = document.querySelector("#scene-title");
const traces = {
  pose: document.querySelector("#pose-trace"),
  expression: document.querySelector("#expression-trace"),
  attention: document.querySelector("#attention-trace"),
};

let state = initialState();
let activeFrame = 0;
let activeAssetKey = null;
let transitionToken = 0;
let sequenceTimers = [];

function dispatch(event) {
  const next = reduce(state, event);
  if (next === state) return;
  state = next;
  render(project(state));
}

function render(scene) {
  const roomAsset = registry[scene.roomId];
  roomImage.src = roomAsset.source;
  roomImage.alt = scene.ambient === "evening" ? "Комната Маши вечером" : "Комната Маши";
  renderCharacter(scene);

  const conversationState = scene.surfaces.find((item) => item.id === "conversation");
  const activityState = scene.surfaces.find((item) => item.id === "activity");
  conversation.classList.toggle("is-visible", Boolean(conversationState));
  conversation.classList.toggle("is-supporting", conversationState?.role === "supporting");
  activity.classList.toggle("is-visible", Boolean(activityState));
  activity.classList.toggle("is-completed", activityState?.lifecycle === "completed");
  activity.classList.toggle("is-collapsing", scene.completionPhase === "collapsing");
  activity.classList.toggle("is-closing", activityState?.lifecycle === "closing");

  const progress = scene.activityProgress ?? 0;
  progressFill.style.width = `${progress}%`;
  progressLabel.textContent = `${progress}%`;
  activityStatus.textContent = activityMessage(progress, scene.completionPhase);

  root.dataset.scenario = scene.id;
  root.dataset.ambient = scene.ambient;
  root.dataset.attention = scene.attention;
  root.dataset.safety = scene.safety;
  root.classList.toggle("is-private", scene.privacy);
  root.classList.toggle("chrome-hidden", state.chromeHidden);
  root.classList.toggle("reduced-motion", scene.reducedMotion);
  title.textContent = scene.title;
  traces.pose.textContent = `pose · ${scene.pose}`;
  traces.expression.textContent = `expression · ${scene.expression}`;
  traces.attention.textContent = `attention · ${scene.attention}`;
  document.querySelectorAll(".scenario-rail [data-scenario]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.scenario === scene.id);
  });
}

function renderCharacter(scene) {
  const asset = characterAsset(scene);
  const assetKey = `${asset.source}:${asset.column}:${asset.row}`;
  if (assetKey === activeAssetKey) return;
  const nextFrame = activeFrame === 0 ? 1 : 0;
  const target = frames[nextFrame];
  target.frame.style.setProperty("--atlas-columns", asset.columns);
  target.frame.style.setProperty("--atlas-rows", asset.rows);
  target.frame.style.setProperty("--atlas-column", asset.column);
  target.frame.style.setProperty("--atlas-row", asset.row);
  target.image.src = asset.source;
  target.image.alt = `Маша: ${scene.pose}, ${scene.expression}, ${scene.outfit}`;
  target.frame.classList.add("is-visible");
  frames[activeFrame].frame.classList.remove("is-visible");
  activeFrame = nextFrame;
  activeAssetKey = assetKey;
  pulseTransition();
}

function activityMessage(progress, phase) {
  if (phase === "collapsing") return "Спокойно закрываю рабочее пространство";
  if (phase === "ambient_return") return "Возвращаю комнату к обычному ритму";
  if (progress >= 100) return "Готово. Нить проекта сохранена";
  if (progress >= 62) return "Проверяю последние связи";
  if (progress >= 28) return "Основная структура уже собрана";
  return "Начинаю с контекста";
}

function pulseTransition() {
  const token = ++transitionToken;
  root.classList.add("is-transitioning");
  window.setTimeout(() => {
    if (token === transitionToken) root.classList.remove("is-transitioning");
  }, state.reducedMotion ? 1 : 880);
}

function cancelSequence() {
  sequenceTimers.forEach(window.clearTimeout);
  sequenceTimers = [];
  transitionToken += 1;
  root.classList.remove("is-transitioning");
}

function selectScenario(scenarioId) {
  cancelSequence();
  dispatch({ type: "SELECT_SCENARIO", scenarioId });
}

function advance() {
  cancelSequence();
  if (state.scenarioId !== "completed") {
    dispatch({ type: "ADVANCE" });
    return;
  }
  const reduced = state.reducedMotion || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    dispatch({ type: "SET_COMPLETION_PHASE", phase: "ambient_return" });
    dispatch({ type: "ADVANCE" });
    return;
  }
  dispatch({ type: "SET_COMPLETION_PHASE", phase: "completed" });
  sequenceTimers.push(window.setTimeout(() => dispatch({ type: "SET_COMPLETION_PHASE", phase: "collapsing" }), 760));
  sequenceTimers.push(window.setTimeout(() => dispatch({ type: "SET_COMPLETION_PHASE", phase: "ambient_return" }), 1650));
  sequenceTimers.push(window.setTimeout(() => dispatch({ type: "ADVANCE" }), 2700));
}

function toggleFullscreen() {
  if (document.fullscreenElement) return document.exitFullscreen();
  return document.documentElement.requestFullscreen();
}

document.querySelectorAll(".scenario-rail [data-scenario]").forEach((button) => {
  button.addEventListener("click", () => selectScenario(button.dataset.scenario));
});

document.addEventListener("keydown", (event) => {
  if (/^[1-8]$/.test(event.key)) selectScenario(scenarioOrder[Number(event.key) - 1]);
  else if (event.key === " ") { event.preventDefault(); advance(); }
  else if (event.key === "ArrowLeft") selectScenario(scenarioOrder[(scenarioOrder.indexOf(state.scenarioId) + 7) % 8]);
  else if (event.key === "ArrowRight") selectScenario(scenarioOrder[(scenarioOrder.indexOf(state.scenarioId) + 1) % 8]);
  else if (event.key.toLowerCase() === "h") dispatch({ type: "TOGGLE_CHROME" });
  else if (event.key.toLowerCase() === "v") dispatch({ type: "TOGGLE_PRIVACY" });
  else if (event.key.toLowerCase() === "f") toggleFullscreen();
  else if (event.key.toLowerCase() === "r") { cancelSequence(); dispatch({ type: "RESET" }); }
});

state = reduce(state, {
  type: "SET_REDUCED_MOTION",
  enabled: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
});
render(project(state));
