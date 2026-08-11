"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const core = require("./workshop-core.js");

test("asset registry uses opaque IDs and local sources", () => {
  const ids = Object.keys(core.assetRegistry);
  assert.equal(ids.length, 29);
  ids.forEach((id) => assert.match(id, /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/));
  Object.values(core.assetRegistry).forEach((asset) => {
    if (!asset.source) return;
    assert.ok(asset.source.startsWith("../../assets/ui-04e/"));
    assert.doesNotMatch(asset.source, /https?:|file:|\\/);
    assert.ok(fs.existsSync(path.resolve(__dirname, asset.source)), asset.source);
  });
});

test("workshop state and reducer outputs are immutable", () => {
  const initial = core.initialState();
  const next = core.reduce(initial, { type: "NEXT" });
  assert.ok(Object.isFrozen(initial));
  assert.ok(Object.isFrozen(next));
  assert.notEqual(next, initial);
  assert.equal(initial.scenarioIndex, 0);
  assert.equal(next.scenarioIndex, 1);
});

test("unknown events do not create phantom state changes", () => {
  const initial = core.initialState();
  assert.equal(core.reduce(initial, { type: "LLM_CHOSE_LAYOUT" }), initial);
});

test("all eight scenarios project deterministic bounded visual axes", () => {
  assert.equal(core.scenarios.length, 8);
  core.scenarios.forEach((expected, index) => {
    const state = core.reduce(core.initialState(), { type: "SELECT_SCENARIO", index });
    assert.deepEqual(core.project(state), expected);
    assert.ok(core.poses.includes(expected.pose));
    assert.ok(core.expressions.includes(expected.expression));
    assert.ok(core.attentions.includes(expected.attention));
    assert.ok(core.outfits.includes(expected.outfit));
  });
});

test("special evening is a visual scenario and not a separate mode", () => {
  const special = core.scenarios[7];
  assert.equal(special.id, "special_evening");
  assert.equal(special.outfit, "special_evening");
  assert.equal(special.room, "evening");
  assert.ok(!core.modes.includes("special_evening"));
});

test("expression workshop changes expression without identity or room mutation", () => {
  let state = core.reduce(core.initialState(), { type: "SET_MODE", mode: "expression" });
  const first = core.project(state);
  state = core.reduce(state, { type: "NEXT" });
  const second = core.project(state);
  assert.equal(first.id, second.id);
  assert.equal(first.room, second.room);
  assert.notEqual(first.expression, second.expression);
  assert.equal(core.assetRegistry["masha.visual.identity"].version, "workshop-1");
});

test("attention workshop has none user and surface semantics", () => {
  assert.deepEqual(core.attentions, ["none", "user", "surface"]);
  let state = core.reduce(core.initialState(), { type: "SET_MODE", mode: "attention" });
  const outputs = [];
  for (let index = 0; index < core.attentions.length; index += 1) {
    outputs.push(core.project(state).attention);
    state = core.reduce(state, { type: "NEXT" });
  }
  assert.deepEqual(outputs, core.attentions);
});

test("motion sequences use authored primitives and terminate in known scenarios", () => {
  assert.equal(core.motionSequences.length, 7);
  const scenarioIds = new Set(core.scenarios.map((scenario) => scenario.id));
  core.motionSequences.forEach((sequence) => {
    assert.ok(scenarioIds.has(sequence.from));
    assert.ok(scenarioIds.has(sequence.to));
    assert.ok(sequence.primitives.length > 0);
    assert.ok(Object.isFrozen(sequence.primitives));
  });
});

test("emergency stop freezes autonomy without removing Masha or conversation", () => {
  const emergency = core.scenarios.find((scenario) => scenario.id === "emergency_stop");
  assert.equal(emergency.safety, "stopped");
  assert.equal(emergency.pose, "idle");
  assert.ok(emergency.surfaces.includes("conversation"));
});

test("reset is deterministic and reduced motion is explicit state", () => {
  let state = core.reduce(core.initialState(), { type: "SET_REDUCED_MOTION", enabled: true });
  state = core.reduce(state, { type: "NEXT" });
  assert.equal(state.reducedMotion, true);
  assert.deepEqual(core.reduce(state, { type: "RESET" }), core.initialState());
});

test("responsive and reduced-motion fallbacks are authored in one stylesheet", () => {
  const source = fs.readFileSync(path.join(__dirname, "styles.css"), "utf8");
  assert.match(source, /@media \(max-width: 820px\)/);
  assert.match(source, /@media \(max-width: 560px\)/);
  assert.match(source, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(source, /display:\s*grid[^}]*grid-template-columns:\s*1fr\s*;/i);
});

test("prototype contains no LLM network or persistence calls", () => {
  const files = ["workshop-core.js", "prototype.js", "index.html"];
  const source = files.map((file) => fs.readFileSync(path.join(__dirname, file), "utf8")).join("\n");
  assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|WebSocket|EventSource|ollama|sqlite|localStorage|sessionStorage/i);
});
