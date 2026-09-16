"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const app = fs.readFileSync(require("node:path").join(__dirname, "app.js"), "utf8");
function source(name) {
  const start = app.indexOf(`function ${name}(`);
  let cursor = app.indexOf(") {", start) + 2;
  let depth = 0;
  for (; cursor < app.length; cursor++) {
    if (app[cursor] === "{") depth++;
    if (app[cursor] === "}") {
      depth--;
      if (depth === 0) return app.slice(start, cursor + 1);
    }
  }
  throw new Error(name);
}
function element() {
  return { children: [], dataset: {}, handlers: {}, classList: { toggle() {}, add() {} },
    setAttribute() {}, append(...items) { this.children.push(...items); },
    replaceChildren() { this.children = []; },
    addEventListener(name, fn) { this.handlers[name] = fn; },
  };
}
const calls = [];
const dialog = element();
dialog.showModal = () => calls.push("dialog");
const context = {
  document: { createElement: element, documentElement: { dataset: { homeMoment: "ordinary" } } },
  ready: true, inFlight: false, activeConversationId: "one", pendingConfirmation: null,
  conversationToDelete: null, deleteConversationDialog: dialog,
  recentList: element(), surface: element(), loadMoreConversations: element(),
  recentPageState: { revision: -1, ids: new Set() },
  interactionSafety: require("./interaction-safety.js"), formatRecentTime: () => "Today",
  bridge: { deleteConversation: id => calls.push(id), setSpecialEvening: value => calls.push(value) },
  cornerSceneActive: false, mashaEveningEntry: { dataset: { available: "true" }, hidden: true },
};
vm.createContext(context);
vm.runInContext(source("renderRecent") + source("updateEveningEntry") + source("toggleSpecialEvening"), context);
const handlerStart = app.indexOf('deleteConversationDialog?.addEventListener("close"');
const handlerEnd = app.indexOf('\n});', handlerStart) + 4;
vm.runInContext(app.slice(handlerStart, handlerEnd), context);
context.renderRecent({ revision: 1, total: 1, items: [{ conversation_id: "one", preview: "Private" }] });
context.recentList.children[0].children[1].handlers.click();
assert.deepEqual(calls, ["dialog"], "cross opens confirmation, not deletion");
dialog.handlers.close();
assert.deepEqual(calls, ["dialog"], "cancel never deletes");
context.recentList.children[0].children[1].handlers.click();
dialog.returnValue = "delete";
dialog.handlers.close();
assert.deepEqual(calls, ["dialog", "dialog", "one"]);
const deletedStart = app.indexOf('  if (payload.kind === "conversation_deleted")');
const deletedEnd = app.indexOf('  if (payload.kind === "conversation_delete_failed")', deletedStart);
context.pendingConfirmation = { proposal_id: "pending" };
context.hideOperationSurface = () => calls.push("hide-operation");
context.renderConversation = value => calls.push(value);
context.renderActiveContinuityThread = () => {};
context.resetHumanSearchUi = () => {};
context.clearLocalFailure = () => {};
context.payload = { kind: "conversation_deleted", deleted_id: "one", active_conversation_id: null,
  recent: { revision: 2, total: 0, items: [] } };
vm.runInContext(`(function () { ${app.slice(deletedStart, deletedEnd)} })()`, context);
assert.equal(context.activeConversationId, null);
assert.equal(context.pendingConfirmation, null);
assert.ok(calls.includes("hide-operation"));
context.updateEveningEntry();
assert.equal(context.mashaEveningEntry.hidden, true);
context.cornerSceneActive = true;
context.updateEveningEntry();
assert.equal(context.mashaEveningEntry.hidden, false);
context.document.documentElement.dataset.homeMoment = "special_evening";
context.updateEveningEntry();
assert.equal(context.mashaEveningEntry.hidden, true);
assert.match(app, /specialEveningToggle.hidden = !specialEveningActive/);
console.log("conversation deletion confirmation and hidden evening entry passed");
