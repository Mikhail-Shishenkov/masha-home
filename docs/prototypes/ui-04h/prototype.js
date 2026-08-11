"use strict";

let state = UI04H.initialState();
const root = document.querySelector("#home");
const scene = document.querySelector("#scene");
const conversation = document.querySelector("#conversation");
const decision = document.querySelector("#decision");
const receipt = document.querySelector("#receipt");
const activity = document.querySelector("#activity");
const checkin = document.querySelector("#checkin");
const composerInput = document.querySelector("#composer-input");
const safetyButton = document.querySelector("#safety");
const messageHistory = document.querySelector("#message-history");
const thinking = document.querySelector("#thinking");
const composerButton = document.querySelector("#composer button");

function render() {
  const view = UI04H.project(state);
  root.dataset.safety = view.safety;
  root.dataset.phase = view.decisionState;
  root.dataset.focus = view.focus;
  root.classList.toggle("is-private", view.privacy);
  safetyButton.setAttribute("aria-pressed", String(view.safety === "stopped"));
  safetyButton.setAttribute("aria-label", view.safety === "stopped" ? "Возобновить автономную активность" : "Остановить автономную активность");
  safetyButton.querySelector(".safety-label").textContent = view.safety === "stopped" ? "Продолжить" : "Стоп";
  scene.src = view.sceneSource;
  conversation.hidden = !view.conversationVisible;
  decision.hidden = !view.decisionVisible;
  activity.hidden = !view.activityVisible;
  checkin.hidden = !view.proactiveVisible;
  document.querySelector("#conversation-origin").textContent = view.conversation.origin;
  composerInput.placeholder = view.conversation.composerPlaceholder;
  const waiting = view.conversation.assistantStatus === "thinking";
  thinking.hidden = !waiting;
  composerButton.disabled = waiting;
  composerButton.textContent = waiting ? "Жду" : "Отправить";
  document.querySelector("#composer").setAttribute("aria-busy", String(waiting));
  messageHistory.replaceChildren(...view.conversation.messages.map((message) => {
    const item = document.createElement("p");
    item.className = `message message-${message.role}`;
    item.textContent = message.content;
    return item;
  }));
  messageHistory.scrollTop = messageHistory.scrollHeight;
  document.querySelector("#decision-title").textContent = view.decision.title;
  document.querySelector("#decision-preview").textContent = view.decision.preview;
  document.querySelector("#confirm").textContent = view.decision.confirmLabel;
  document.querySelector("#edit").textContent = view.decision.editLabel;
  document.querySelector("#dismiss").textContent = view.decision.dismissLabel;
  document.querySelector("#activity-eyebrow").textContent = view.activity.eyebrow;
  document.querySelector("#activity-title").textContent = view.activity.title;
  document.querySelector("#activity-detail").textContent = view.activity.detail;
  document.querySelector("#activity-action").textContent = view.activity.actionLabel;
  document.querySelector("#checkin-eyebrow").textContent = view.proactive.eyebrow;
  document.querySelector("#checkin-message").textContent = view.proactive.message;
  document.querySelector("#checkin-reply").textContent = view.proactive.replyLabel;
  document.querySelector("#checkin-dismiss").textContent = view.proactive.dismissLabel;
  document.querySelector("#activity-steps").replaceChildren(...view.activity.steps.map((label, index) => {
    const item = document.createElement("li");
    item.textContent = label;
    item.dataset.state = index < view.activity.step ? "done" : "next";
    return item;
  }));
  document.querySelectorAll("#home-nav [data-focus]").forEach((button) => {
    const current = button.dataset.focus === view.focus;
    button.toggleAttribute("data-current", current);
    button.setAttribute("aria-current", current ? "page" : "false");
  });
  receipt.textContent = view.decisionState === "confirmed" ? "Готово. В этом прототипе решение только показано." :
    view.decisionState === "dismissed" ? "Хорошо. Ничего не изменилось." : "";
}
function send(type) { state = UI04H.reduce(state, { type }); render(); }
document.querySelector("#confirm").addEventListener("click", () => send("CONFIRM_PREVIEW"));
document.querySelector("#dismiss").addEventListener("click", () => send("DISMISS_PREVIEW"));
document.querySelector("#activity-action").addEventListener("click", () => {
  if (state.activityStatus !== "running") return send("DISMISS_ACTIVITY");
  send(state.activityStep >= 3 ? "ACTIVITY_COMPLETE" : "ACTIVITY_PROGRESS");
});
document.querySelector("#checkin-reply").addEventListener("click", () => {
  send("ACKNOWLEDGE_CHECKIN");
  composerInput.focus();
});
document.querySelector("#checkin-dismiss").addEventListener("click", () => send("DISMISS_CHECKIN"));
document.querySelector("#home-nav").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-focus]");
  if (!button) return;
  const events = { conversation: "OPEN_CONVERSATION", activity: "OPEN_ACTIVITY", decision: "OPEN_CONFIRMATION", checkin: "APPEAR_CHECKIN" };
  send(events[button.dataset.focus]);
});
document.querySelector("#edit").addEventListener("click", () => {
  send("OPEN_CONVERSATION");
  composerInput.focus();
});
safetyButton.addEventListener("click", () => send(state.safety === "normal" ? "EMERGENCY_STOP" : "RESUME_PRESENTATION"));
document.querySelector("#privacy").addEventListener("click", () => send("TOGGLE_PRIVACY"));
document.querySelector("#composer").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!composerInput.value.trim()) return;
  const before = state;
  state = UI04H.reduce(state, { type: "SEND_DRAFT", content: composerInput.value });
  if (state === before) return;
  composerInput.value = "";
  render();
  window.setTimeout(() => send("SIMULATED_ASSISTANT_RESPONSE"), 700);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.target !== composerInput) send("CONFIRM_PREVIEW");
  if (event.target === composerInput) return;
  if (event.key === "Escape") send("DISMISS_PREVIEW");
  if (event.key.toLowerCase() === "e") send("EMERGENCY_STOP");
  if (event.key.toLowerCase() === "p") send("TOGGLE_PRIVACY");
  if (event.key.toLowerCase() === "c") send("OPEN_CONFIRMATION");
  if (event.key.toLowerCase() === "a") send(state.activityStatus === "idle" ? "OPEN_ACTIVITY" : "ACTIVITY_COMPLETE");
  if (event.key.toLowerCase() === "i") send("APPEAR_CHECKIN");
});
render();
