"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const core = require("./living-core.js");

test("canonical registry uses opaque IDs and only local authored assets", () => {
  const entries = Object.entries(core.registry);
  assert.equal(entries.length, 31);
  entries.forEach(([id, asset]) => {
    assert.match(id, /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/);
    if (!asset.source) return;
    assert.doesNotMatch(asset.source, /https?:|file:|\\/);
    assert.ok(fs.existsSync(path.resolve(__dirname, asset.source)), asset.source);
  });
});

test("six poses ten expressions three attention states and five outfits are bounded", () => {
  assert.deepEqual(core.poses, ["idle", "conversation", "thinking", "working", "attention_user", "attention_surface"]);
  assert.equal(core.expressions.length, 10);
  assert.deepEqual(core.attentions, ["none", "user", "surface"]);
  assert.deepEqual(core.outfits, ["everyday", "work", "evening", "home_evening", "special_evening"]);
});

test("asset selection composes pose expression attention and outfit without identity drift", () => {
  core.scenarioOrder.forEach((scenarioId) => {
    const state = core.reduce(core.initialState(), { type: "SELECT_SCENARIO", scenarioId });
    const scene = core.project(state);
    const asset = core.characterAsset(scene);
    assert.equal(scene.identityId, "masha.visual.identity");
    assert.ok(core.poses.includes(scene.pose));
    assert.ok(core.expressions.includes(scene.expression));
    assert.ok(core.attentions.includes(scene.attention));
    assert.ok(core.outfits.includes(scene.outfit));
    assert.equal(asset.kind, "atlas");
  });
});

test("vertical slice advances deterministically through progress completion and ambient return", () => {
  let state = core.initialState();
  const trace = [];
  const capture = () => trace.push([state.scenarioId, core.project(state).activityProgress, state.completionPhase]);
  capture();
  for (let step = 0; step < 10; step += 1) {
    state = core.reduce(state, { type: "ADVANCE" });
    capture();
  }
  assert.deepEqual(trace.slice(0, 8), [
    ["idle", null, "settled"],
    ["conversation", null, "settled"],
    ["activity", 0, "settled"],
    ["activity", 28, "settled"],
    ["activity", 62, "settled"],
    ["activity", 88, "settled"],
    ["activity", 100, "settled"],
    ["completed", 100, "completed"],
  ]);
  state = core.reduce(state, { type: "SET_COMPLETION_PHASE", phase: "collapsing" });
  assert.equal(core.project(state).surfaces.find((item) => item.id === "activity").lifecycle, "completed");
  state = core.reduce(state, { type: "SET_COMPLETION_PHASE", phase: "ambient_return" });
  const returning = core.project(state);
  assert.equal(returning.pose, "attention_user");
  assert.equal(returning.attention, "user");
  assert.ok(returning.surfaces.every((surface) => surface.lifecycle === "closing"));
  state = core.reduce(state, { type: "ADVANCE" });
  assert.equal(state.scenarioId, "idle");
});

test("activity progress changes inside one stable surface lifecycle", () => {
  let state = core.reduce(core.initialState(), { type: "SELECT_SCENARIO", scenarioId: "activity" });
  const first = core.project(state);
  state = core.reduce(state, { type: "ADVANCE" });
  const second = core.project(state);
  assert.equal(first.surfaces.find((item) => item.id === "activity").lifecycle, "running");
  assert.deepEqual(first.surfaces, second.surfaces);
  assert.notEqual(first.activityProgress, second.activityProgress);
});

test("emergency stop leaves Masha and conversation while removing autonomous activity", () => {
  const state = core.reduce(core.initialState(), { type: "SELECT_SCENARIO", scenarioId: "safety" });
  const scene = core.project(state);
  assert.equal(scene.safety, "stopped");
  assert.equal(scene.identityId, "masha.visual.identity");
  assert.ok(scene.surfaces.some((surface) => surface.id === "conversation"));
  assert.ok(!scene.surfaces.some((surface) => surface.id === "activity"));
});

test("privacy masks sensitive content without changing scene identity or lifecycle", () => {
  let state = core.reduce(core.initialState(), { type: "SELECT_SCENARIO", scenarioId: "conversation" });
  const before = core.project(state);
  state = core.reduce(state, { type: "TOGGLE_PRIVACY" });
  const after = core.project(state);
  assert.equal(after.identityId, before.identityId);
  assert.equal(after.pose, before.pose);
  assert.equal(after.surfaces[0].lifecycle, before.surfaces[0].lifecycle);
  assert.equal(after.surfaces[0].masked, true);
});

test("reduced motion is explicit immutable presentation state", () => {
  const initial = core.initialState();
  const reduced = core.reduce(initial, { type: "SET_REDUCED_MOTION", enabled: true });
  assert.ok(Object.isFrozen(initial));
  assert.ok(Object.isFrozen(reduced));
  assert.equal(reduced.reducedMotion, true);
  assert.equal(core.project(reduced).reducedMotion, true);
});

test("one stylesheet owns standard narrow very-narrow and reduced-motion fallbacks", () => {
  const css = fs.readFileSync(path.join(__dirname, "styles.css"), "utf8");
  assert.match(css, /@media \(max-width: 980px\)/);
  assert.match(css, /@media \(max-width: 760px\)/);
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(css, /grid-template-columns:\s*repeat\(/i);
});

test("prototype has no model network persistence or production imports", () => {
  const source = ["living-core.js", "prototype.js", "index.html"]
    .map((file) => fs.readFileSync(path.join(__dirname, file), "utf8"))
    .join("\n");
  assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|WebSocket|EventSource|ollama|sqlite|localStorage|sessionStorage/i);
  assert.doesNotMatch(source, /backend[\\/]|CompositionResolver|ModelRouter|MemoryRetriever/);
});
