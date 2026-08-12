"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const workshop = require("./workshop-core.js");

test("workshop exposes exactly ten agreed capability scenes", () => {
  assert.equal(workshop.SCENES.length, 10);
  assert.deepEqual(
    workshop.SCENES.map((item) => item.id),
    ["commitment", "confirmation", "activity", "reminder", "checkin", "continuity", "reflection", "skills", "models", "runtime"],
  );
});

test("all scenes preserve one visual identity and one static canonical room", () => {
  let state = workshop.initialState();
  const identity = workshop.project(state).visualIdentityId;
  const room = workshop.project(state).roomAssetId;
  for (const scene of workshop.SCENES) {
    state = workshop.reduce(state, { type: "SELECT", sceneId: scene.id });
    const view = workshop.project(state);
    assert.equal(view.visualIdentityId, identity);
    assert.equal(view.roomAssetId, room);
  }
});

test("scene selection and circular navigation are deterministic", () => {
  const initial = workshop.initialState();
  assert.equal(workshop.project(workshop.reduce(initial, { type: "PREVIOUS" })).scene.id, "runtime");
  assert.equal(workshop.project(workshop.reduce(initial, { type: "NEXT" })).scene.id, "confirmation");
  assert.equal(workshop.reduce(initial, { type: "SELECT", sceneId: "missing" }), initial);
});

test("workshop actions create presentation receipts only", () => {
  const initial = workshop.initialState();
  const focused = workshop.reduce(initial, { type: "FOCUS" });
  const waiting = workshop.reduce(focused, { type: "WAIT" });
  const acted = workshop.reduce(waiting, { type: "ACT", actionIndex: 0 });
  assert.equal(acted.sceneId, initial.sceneId);
  assert.equal(acted.phase, "resolved");
  assert.ok(acted.resolution.message);
  const reset = workshop.reduce(acted, { type: "RESET" });
  assert.equal(reset.phase, "appeared");
  assert.equal(reset.resolution, null);
});

test("every capability follows appeared focused waiting resolved or dismissed grammar", () => {
  for (const scene of workshop.SCENES) {
    let state = workshop.reduce(workshop.initialState(), { type: "SELECT", sceneId: scene.id });
    assert.equal(state.phase, "appeared");
    state = workshop.reduce(state, { type: "FOCUS" });
    assert.equal(state.phase, "focused");
    state = workshop.reduce(state, { type: "WAIT" });
    assert.equal(state.phase, "waiting");
    assert.equal(workshop.reduce(state, { type: "ACT", actionIndex: 0 }).phase, "resolved");
    assert.equal(workshop.reduce(state, { type: "ACT", actionIndex: 1 }).phase, "dismissed");
  }
});

test("each scene has human content, a spatial zone and bounded actions", () => {
  for (const scene of workshop.SCENES) {
    assert.match(scene.id, /^[a-z][a-z0-9_-]+$/);
    assert.ok(["sofa", "table", "desk"].includes(scene.zone));
    assert.ok(scene.title.length >= 10);
    assert.ok(scene.summary.length >= 30);
    assert.ok(scene.actions.length >= 2 && scene.actions.length <= 3);
  }
});

test("prototype remains offline, disposable and disconnected from production state", () => {
  const source = ["index.html", "prototype.js", "workshop-core.js"].map((file) =>
    fs.readFileSync(path.join(__dirname, file), "utf8")).join("\n");
  assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|WebSocket|localStorage|sessionStorage|QWebChannel|MemorySqliteRepository|ModelRouter/i);
  assert.match(source, /данные не подключены/);
});

test("canonical room asset exists outside the disposable workshop", () => {
  assert.ok(fs.existsSync(path.resolve(__dirname, "../../../frontend/assets/canonical-master.png")));
});
