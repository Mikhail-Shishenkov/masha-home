"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  preserveComposer,
  isBackgroundProactiveProjection,
  reminderToastProjection,
  acceptConversationPage,
} = require("./interaction-safety.js");

test("background projections preserve unfinished composer draft, focus and selection", () => {
  const documentRef = { activeElement: null };
  const input = {
    value: "Маша, напомни про чай",
    disabled: false,
    selectionStart: 12,
    selectionEnd: 12,
    focus() { documentRef.activeElement = input; },
    setSelectionRange(start, end) {
      this.selectionStart = start;
      this.selectionEnd = end;
    },
  };
  documentRef.activeElement = input;

  for (const event of ["recent_conversations", "proactive_interactions_loaded", "status"] ) {
    preserveComposer(input, documentRef, () => {
      input.value = `accidental mutation from ${event}`;
      input.disabled = true;
      documentRef.activeElement = null;
      input.selectionStart = 0;
      input.selectionEnd = 0;
    });
    assert.equal(input.value, "Маша, напомни про чай");
    assert.equal(input.disabled, false);
    assert.equal(documentRef.activeElement, input);
    assert.deepEqual([input.selectionStart, input.selectionEnd], [12, 12]);
  }
});

test("only runtime-delivered proactive projection is classified as background", () => {
  assert.equal(isBackgroundProactiveProjection({
    kind: "proactive_interactions_loaded",
    delivery_origin: "local_runtime",
  }), true);
  assert.equal(isBackgroundProactiveProjection({
    kind: "proactive_interactions_loaded",
  }), false);
  assert.equal(isBackgroundProactiveProjection({ kind: "recent_conversations" }), false);
});

test("new reminder projects a ten-second toast without taking composer focus", () => {
  const documentRef = { activeElement: null };
  const input = {
    value: "Дописываю сообщение",
    disabled: false,
    selectionStart: 10,
    selectionEnd: 10,
    focus() { documentRef.activeElement = input; },
    setSelectionRange(start, end) {
      this.selectionStart = start;
      this.selectionEnd = end;
    },
  };
  documentRef.activeElement = input;
  const toast = { hidden: true };
  let projection;

  preserveComposer(input, documentRef, () => {
    projection = reminderToastProjection({ items: [{
      interaction_id: "reminder-1",
      interaction_type: "reminder",
      message: "Пора закрыть окно.",
      due_at: "2026-08-24T21:02:00Z",
    }] }, "reminder-1");
    toast.hidden = false;
  });

  assert.deepEqual(projection, {
    interactionId: "reminder-1",
    title: "Напоминание",
    message: "Пора закрыть окно.",
    dueAt: "2026-08-24T21:02:00Z",
    durationMs: 10000,
  });
  assert.equal(toast.hidden, false);
  assert.equal(documentRef.activeElement, input);
  assert.equal(input.value, "Дописываю сообщение");
  assert.equal(reminderToastProjection({ items: [{
    interaction_id: "check-in-1",
    interaction_type: "check_in",
    message: "Как ты?",
  }] }, "check-in-1"), null);
});

test("conversation pagination rejects stale reset and append responses", () => {
  const state = { revision: 5, nextOffset: 10 };

  assert.equal(acceptConversationPage(state, { revision: 4, offset: 0 }, false), false);
  assert.equal(acceptConversationPage(state, { revision: 5, offset: 10 }, true), true);
  assert.equal(acceptConversationPage(state, { revision: 4, offset: 10 }, true), false);
  assert.equal(acceptConversationPage(state, { revision: 5, offset: 20 }, true), false);
  assert.equal(acceptConversationPage(state, { revision: 6, offset: 0 }, false), true);
});
