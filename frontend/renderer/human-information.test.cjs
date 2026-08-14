"use strict";

const assert = require("node:assert/strict");
const { describe } = require("./human-information.js");

assert.deepEqual(describe({ kind: "memory", state: "active", availability: "active" }), {
  context: "То, что я помню сейчас", tone: "current",
});
assert.deepEqual(describe({ kind: "memory", state: "active", availability: "forgotten" }), {
  context: "Сейчас не использую в памяти", tone: "forgotten",
});
assert.deepEqual(describe({ kind: "task", state: "completed", availability: "archived" }), {
  context: "Завершённое дело", tone: "past",
});
assert.deepEqual(describe({ kind: "thread", state: "open", availability: "active" }), {
  context: "Открытая нить", tone: "current",
});
assert.deepEqual(describe({ kind: "thread", state: "resolved", availability: "archived" }), {
  context: "Закрытая тема", tone: "past",
});
assert.ok(!JSON.stringify(describe({ kind: "memory", state: "superseded", availability: "archived" })).includes("superseded"));

console.log("human information presentation: 6 passed");
