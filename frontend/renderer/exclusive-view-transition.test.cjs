"use strict";

const assert = require("node:assert/strict");
const { create } = require("./exclusive-view-transition.js");

class Classes {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach((value) => this.values.add(value)); }
  remove(...values) { values.forEach((value) => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
}

const history = { hidden: false, classList: new Classes() };
const search = { hidden: true, classList: new Classes() };
let timer = null;
const transition = create({
  history,
  search,
  exitMs: 110,
  setTimer: (callback, delay) => { timer = { callback, delay }; return timer; },
  clearTimer: (selected) => { if (timer === selected) timer = null; },
  requestFrame: (callback) => callback(),
});

transition.show("search");
assert.equal(history.hidden, false);
assert.equal(search.hidden, true);
assert.equal(history.classList.contains("is-history-leaving"), true);
assert.equal(timer.delay, 110);
timer.callback();
assert.equal(history.hidden, true);
assert.equal(search.hidden, false);
assert.equal(transition.visible(), "search");

transition.show("history");
assert.equal(history.hidden, true);
assert.equal(search.hidden, false);
timer.callback();
assert.equal(history.hidden, false);
assert.equal(search.hidden, true);

console.log("exclusive history transition: 11 passed");
