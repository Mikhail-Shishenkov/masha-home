"use strict";

const {
  assetRegistry,
  scenarios,
  motionSequences,
  initialState,
  reduce,
  project,
  currentLabel,
} = UI04E;

const workshop = document.querySelector("#workshop");
const roomLayer = document.querySelector("#room-layer");
const poseFrame = document.querySelector("#masha-pose-frame");
const poseImage = document.querySelector("#masha-pose");
const expressionFrame = document.querySelector("#masha-expression-frame");
const expressionImage = document.querySelector("#masha-expression");
const currentLabelElement = document.querySelector("#current-label");
const readouts = {
  pose: document.querySelector("#readout-pose"),
  expression: document.querySelector("#readout-expression"),
  attention: document.querySelector("#readout-attention"),
  outfit: document.querySelector("#readout-outfit"),
};
const surfaces = {
  conversation: document.querySelector("#surface-conversation"),
  activity: document.querySelector("#surface-activity"),
  confirmation: document.querySelector("#surface-confirmation"),
  proactive: document.querySelector("#surface-proactive"),
};

let state = initialState();
let transitionToken = 0;
let motionTimers = [];

function dispatch(event) {
  const previousScene = project(state);
  const nextState = reduce(state, event);
  if (nextState === state) return;
  state = nextState;
  const nextScene = project(state);
  render(nextScene);
  if (previousScene.id !== nextScene.id) pulseTransition();
}

function render(scene) {
  const roomAsset = assetRegistry[`room.${scene.room}`];
  roomLayer.src = roomAsset.source;
  roomLayer.alt = scene.room === "evening" ? "Комната Маши особенным вечером" : "Тёплая комната Маши";

  const outfitPreview = state.mode === "outfit" || scene.id === "special_evening";
  const bodyAssetId = outfitPreview ? `masha.outfit.${scene.outfit}` : `masha.pose.${scene.pose}`;
  applyAtlas(poseFrame, poseImage, assetRegistry[bodyAssetId], bodyAssetId);

  const expressionAssetId = `masha.expression.${scene.expression}`;
  applyAtlas(expressionFrame, expressionImage, assetRegistry[expressionAssetId], expressionAssetId);

  workshop.dataset.mode = state.mode;
  workshop.dataset.scenario = scene.id;
  workshop.dataset.attention = scene.attention;
  workshop.dataset.safety = scene.safety;
  workshop.dataset.depth = scene.depth;
  workshop.dataset.room = scene.room;
  workshop.classList.toggle("chrome-hidden", state.chromeHidden);
  workshop.classList.toggle("reduced-motion", state.reducedMotion);

  Object.entries(surfaces).forEach(([name, element]) => {
    element.classList.toggle("is-visible", scene.surfaces.includes(name));
  });

  currentLabelElement.textContent = currentLabel(state);
  readouts.pose.textContent = `pose · ${scene.pose}`;
  readouts.expression.textContent = `expression · ${scene.expression}`;
  readouts.attention.textContent = `attention · ${scene.attention}`;
  readouts.outfit.textContent = `outfit · ${scene.outfit}`;
  document.querySelectorAll(".mode-dock [data-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.mode === state.mode);
  });
}

function applyAtlas(frame, image, asset, label) {
  frame.style.setProperty("--atlas-columns", asset.columns);
  frame.style.setProperty("--atlas-rows", asset.rows);
  frame.style.setProperty("--atlas-column", asset.column);
  frame.style.setProperty("--atlas-row", asset.row);
  image.src = asset.source;
  image.alt = label;
}

function pulseTransition() {
  const token = ++transitionToken;
  workshop.classList.add("is-transitioning");
  window.setTimeout(() => {
    if (token === transitionToken) workshop.classList.remove("is-transitioning");
  }, state.reducedMotion ? 1 : 920);
}

function cancelMotion() {
  motionTimers.forEach(window.clearTimeout);
  motionTimers = [];
  transitionToken += 1;
  workshop.classList.remove("is-transitioning");
  delete workshop.dataset.motionPrimitive;
}

function playMotion() {
  cancelMotion();
  if (state.mode !== "motion") dispatch({ type: "SET_MODE", mode: "motion" });
  const sequence = motionSequences[state.motionIndex];
  const interval = state.reducedMotion || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 720;
  dispatch({ type: "MOTION_STEP", step: -1 });
  sequence.primitives.forEach((primitive, index) => {
    const timer = window.setTimeout(() => {
      workshop.dataset.motionPrimitive = primitive;
      dispatch({ type: "MOTION_STEP", step: index });
    }, interval * (index + 1));
    motionTimers.push(timer);
  });
  motionTimers.push(window.setTimeout(() => {
    delete workshop.dataset.motionPrimitive;
  }, interval * (sequence.primitives.length + 1)));
}

function selectScenario(index) {
  cancelMotion();
  dispatch({ type: "SELECT_SCENARIO", index });
}

function setMode(mode) {
  cancelMotion();
  dispatch({ type: "SET_MODE", mode });
}

function toggleFullscreen() {
  if (document.fullscreenElement) return document.exitFullscreen();
  return document.documentElement.requestFullscreen();
}

document.querySelector("#previous").addEventListener("click", () => dispatch({ type: "PREVIOUS" }));
document.querySelector("#next").addEventListener("click", () => dispatch({ type: "NEXT" }));
document.querySelectorAll(".mode-dock [data-mode]").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

document.addEventListener("keydown", (event) => {
  if (/^[1-8]$/.test(event.key)) selectScenario(Number(event.key) - 1);
  else if (event.key === "ArrowLeft") dispatch({ type: "PREVIOUS" });
  else if (event.key === "ArrowRight") dispatch({ type: "NEXT" });
  else if (event.key === " ") { event.preventDefault(); playMotion(); }
  else if (event.key.toLowerCase() === "e") setMode("expression");
  else if (event.key.toLowerCase() === "a") setMode("attention");
  else if (event.key.toLowerCase() === "p") setMode("pose");
  else if (event.key.toLowerCase() === "o") setMode("outfit");
  else if (event.key.toLowerCase() === "s") setMode("surface");
  else if (event.key.toLowerCase() === "m") setMode("motion");
  else if (event.key.toLowerCase() === "h") dispatch({ type: "TOGGLE_CHROME" });
  else if (event.key.toLowerCase() === "f") toggleFullscreen();
  else if (event.key.toLowerCase() === "r") { cancelMotion(); dispatch({ type: "RESET" }); }
});

state = reduce(state, {
  type: "SET_REDUCED_MOTION",
  enabled: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
});
render(project(state));
