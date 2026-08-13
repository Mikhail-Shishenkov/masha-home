"use strict";

const assert = require("node:assert/strict");
const scenes = require("../scenes/scene-map.js");
const { restoreActiveLayer } = require("./scene-transition-safety.js");

class FakeClassList {
  constructor(...names) { this.names = new Set(names); }
  add(...names) { names.forEach((name) => this.names.add(name)); }
  remove(...names) { names.forEach((name) => this.names.delete(name)); }
  toggle(name, enabled) { enabled ? this.names.add(name) : this.names.delete(name); }
  contains(name) { return this.names.has(name); }
}

const payload = (activity, attention = "ambient") => ({
  home_state: "ready",
  overlays: {},
  presence: { activity, attention },
});
const sequence = [
  payload("idle"),
  payload("waiting", "toward_user"),
  payload("processing", "thinking_away"),
  payload("confirmation", "toward_surface"),
];
assert.deepEqual(sequence.map((item) => scenes.resolveScene(item).id), [
  "scene.home.idle",
  "scene.home.listening",
  "scene.home.thinking",
  "scene.home.idle",
]);

// Exact interrupted state from idle -> listening/thinking -> idle: the old
// callback is invalidated while both layers are transparent.
const layers = [
  { classList: new FakeClassList("is-active", "is-leaving"), onload: () => {}, onerror: () => {} },
  { classList: new FakeClassList("is-incoming"), onload: () => {}, onerror: () => {} },
];
restoreActiveLayer(layers, 0);
assert.equal(layers[0].classList.contains("is-active"), true);
assert.equal(layers[0].classList.contains("is-leaving"), false);
assert.equal(layers[1].classList.contains("is-active"), false);
assert.equal(layers[1].classList.contains("is-incoming"), false);
assert.equal(layers[0].onload, null);
assert.equal(layers[1].onerror, null);

for (const resolution of ["confirmed", "rejected"]) {
  assert.equal(
    scenes.resolveScene(payload("completed", "ambient")).id,
    "scene.home.idle",
    resolution,
  );
}

console.log("scene transition safety tests passed");
