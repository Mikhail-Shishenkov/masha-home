"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const interactionSafety = require("./interaction-safety.js");

const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");

function functionSource(name) {
  const start = app.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `${name} must exist`);
  let cursor = app.indexOf("{", start);
  let depth = 0;
  for (; cursor < app.length; cursor += 1) {
    if (app[cursor] === "{") depth += 1;
    if (app[cursor] === "}") {
      depth -= 1;
      if (depth === 0) return app.slice(start, cursor + 1);
    }
  }
  throw new Error(`could not extract ${name}`);
}

assert.ok(
  app.indexOf("function showReminderToast(") < app.indexOf("function renderHomeAttention("),
  "toast helper must have module scope, not renderHomeAttention scope",
);
assert.match(
  app,
  /isBackgroundProactiveProjection\(payload\)[\s\S]{0,180}renderBackgroundProactiveProjection\(payload\)/,
);

const documentRef = { activeElement: null };
const input = {
  value: "unfinished reminder draft",
  disabled: false,
  selectionStart: 4,
  selectionEnd: 4,
  focus() { documentRef.activeElement = this; },
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; },
};
documentRef.activeElement = input;
const calls = [];
const context = {
  interactionSafety,
  input,
  document: documentRef,
  reminderToastTimer: null,
  reminderToast: { hidden: true },
  reminderToastMessage: { textContent: "" },
  proactiveTrigger: { hidden: true },
  clearTimeout() {},
  window: { setTimeout() { return 1; } },
  Date: class Date { toISOString() { return "2026-08-27T12:00:00Z"; } },
  formatDueAt(value) { return value; },
  bridge: { recordReminderPresented(id) { calls.push(`presented:${id}`); } },
  renderProactiveInteractions() { calls.push("interactions"); },
  renderHomeAttention() { calls.push("attention"); },
};
vm.createContext(context);
vm.runInContext(`${functionSource("showReminderToast")}\n${functionSource("renderBackgroundProactiveProjection")}`, context);

assert.doesNotThrow(() => context.renderBackgroundProactiveProjection({
  kind: "proactive_interactions_loaded",
  delivery_origin: "local_runtime",
  new_interaction_id: "reminder-1",
  interactions: { items: [{
    interaction_id: "reminder-1", interaction_type: "reminder",
    message: "Time to pause.", due_at: "2026-08-27T12:00:00Z",
  }] },
  attention: { attention_items: [] },
}));
assert.deepEqual(calls, ["interactions", "attention", "presented:reminder-1"]);
assert.equal(context.reminderToast.hidden, false);
assert.match(context.reminderToastMessage.textContent, /Time to pause/);
assert.equal(input.value, "unfinished reminder draft");
assert.equal(documentRef.activeElement, input);

console.log("proactive reminder route test passed");
