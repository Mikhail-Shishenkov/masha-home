"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const core = require("./confirmation-core.js");

test("confirmation uses opaque local scene references and preserves visual identity", () => {
  Object.entries(core.registry).forEach(([id, asset]) => {
    assert.match(id, /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/);
    if (asset.source) assert.ok(fs.existsSync(path.resolve(__dirname, asset.source)));
  });
  const scene = core.project(core.initialState());
  assert.equal(scene.identityId, "masha.visual.identity");
  assert.equal(scene.decisionVisible, false);
  assert.equal(scene.sceneId, "scene.conversation");
});

test("conversation composer appends a bounded local message and waits for a fixture response", () => {
  const state = core.reduce(core.initialState(), { type: "SEND_DRAFT", content: "Давай продолжим." });
  const view = core.project(state);
  assert.equal(view.conversation.messages.at(-1).content, "Давай продолжим.");
  assert.equal(view.conversation.assistantStatus, "thinking");
  assert.equal(view.decisionVisible, false);
  assert.equal(view.sceneId, "scene.conversation");
  assert.equal(core.reduce(state, { type: "SEND_DRAFT", content: "Ещё одно" }), state);
  assert.equal(core.project(core.reduce(state, { type: "SIMULATED_ASSISTANT_RESPONSE" })).conversation.assistantStatus, "ready");
});

test("confirmation is bounded to its preview and does not expose a domain mutation", () => {
  const confirmation = core.reduce(core.initialState(), { type: "OPEN_CONFIRMATION" });
  const confirmed = core.project(core.reduce(confirmation, { type: "CONFIRM_PREVIEW" }));
  assert.equal(confirmed.decisionState, "confirmed");
  assert.equal(confirmed.decisionVisible, false);
  assert.equal(confirmed.sceneId, "scene.conversation");
  assert.equal(confirmed.conversationVisible, true);
});

test("confirmation cannot be accepted or dismissed when no preview is open", () => {
  const initial = core.initialState();
  assert.equal(core.reduce(initial, { type: "CONFIRM_PREVIEW" }), initial);
  assert.equal(core.reduce(initial, { type: "DISMISS_PREVIEW" }), initial);
});

test("activity has a bounded visual lifecycle and does not alter conversation or safety", () => {
  let state = core.reduce(core.initialState(), { type: "OPEN_ACTIVITY" });
  state = core.reduce(state, { type: "ACTIVITY_PROGRESS" });
  state = core.reduce(state, { type: "ACTIVITY_COMPLETE" });
  const view = core.project(state);
  assert.equal(view.activityVisible, true);
  assert.equal(view.activity.status, "completed");
  assert.equal(view.conversation.messages[0].content, "Я здесь. С чего начнём?");
  assert.equal(view.safety, "normal");
  assert.equal(core.project(core.reduce(state, { type: "DISMISS_ACTIVITY" })).activityVisible, false);
});

test("opening a confirmation focuses it without changing a running activity", () => {
  const running = core.reduce(core.initialState(), { type: "OPEN_ACTIVITY" });
  const view = core.project(core.reduce(running, { type: "OPEN_CONFIRMATION" }));
  assert.equal(view.decisionVisible, true);
  assert.equal(view.activityVisible, false);
  assert.equal(view.activity.status, "running");
  assert.equal(view.focus, "decision");
});

test("quiet navigation focus follows the visible human-facing surface", () => {
  assert.equal(core.project(core.initialState()).focus, "conversation");
  assert.equal(core.project(core.reduce(core.initialState(), { type: "OPEN_ACTIVITY" })).focus, "activity");
  assert.equal(core.project(core.reduce(core.initialState(), { type: "APPEAR_CHECKIN" })).focus, "checkin");
});

test("returning to conversation closes other main surfaces without changing their local fixture state", () => {
  let state = core.reduce(core.initialState(), { type: "OPEN_ACTIVITY" });
  state = core.reduce(state, { type: "OPEN_CONVERSATION" });
  const view = core.project(state);
  assert.equal(view.conversationVisible, true);
  assert.equal(view.activityVisible, false);
  assert.equal(view.activity.status, "running");
});

test("check-in is a bounded visual candidate and emergency stop suppresses it", () => {
  const pending = core.reduce(core.initialState(), { type: "APPEAR_CHECKIN" });
  assert.equal(core.project(pending).proactiveVisible, true);
  const acknowledged = core.reduce(pending, { type: "ACKNOWLEDGE_CHECKIN" });
  assert.equal(core.project(acknowledged).proactiveVisible, false);
  const stopped = core.reduce(core.reduce(core.initialState(), { type: "EMERGENCY_STOP" }), { type: "APPEAR_CHECKIN" });
  assert.equal(stopped.proactiveStatus, "idle");
});

test("emergency stop suppresses the decision surface and blocks prototype confirmation", () => {
  let state = core.reduce(core.reduce(core.initialState(), { type: "OPEN_CONFIRMATION" }), { type: "EMERGENCY_STOP" });
  const stopped = core.project(state);
  assert.equal(stopped.safety, "stopped");
  assert.equal(stopped.decisionVisible, false);
  assert.equal(core.reduce(state, { type: "CONFIRM_PREVIEW" }), state);
});

test("privacy masks the same visual state without changing identity or decision lifecycle", () => {
  const before = core.project(core.initialState());
  const after = core.project(core.reduce(core.initialState(), { type: "TOGGLE_PRIVACY" }));
  assert.equal(after.identityId, before.identityId);
  assert.equal(after.decisionState, before.decisionState);
  assert.equal(after.privacy, true);
});

test("prototype stays local and has no backend, model, persistence or network import", () => {
  const source = ["confirmation-core.js", "prototype.js", "index.html"].map((file) =>
    fs.readFileSync(path.join(__dirname, file), "utf8")).join("\n");
  assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|WebSocket|ollama|sqlite|localStorage|sessionStorage|backend[\\/]|ModelRouter|MemoryRetriever/i);
});
