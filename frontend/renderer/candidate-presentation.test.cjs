"use strict";

const assert = require("node:assert/strict");
const { create } = require("./candidate-presentation.js");

let quiet = true;
let timer = null;
const revealed = [];
const presenter = create({
  delayMs: 1200,
  isQuiet: () => quiet,
  onReveal: (candidate) => revealed.push(candidate),
  setTimer: (callback, delay) => { timer = { callback, delay }; return timer; },
  clearTimer: (selected) => { if (timer === selected) timer = null; },
});
const candidate = { candidate_id: "internal", summary: "Любит чай" };

presenter.offer(candidate);
assert.deepEqual(revealed, []);
assert.equal(timer.delay, 1200);

quiet = false;
presenter.defer();
assert.equal(timer, null);
assert.equal(presenter.pending(), candidate);
presenter.reconsider();
assert.equal(timer, null);

quiet = true;
presenter.reconsider();
assert.equal(timer.delay, 1200);
timer.callback();
assert.deepEqual(revealed, [candidate]);

presenter.clear();
assert.equal(presenter.pending(), null);
console.log("candidate presentation timing: 8 passed");
