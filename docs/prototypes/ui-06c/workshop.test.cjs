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
  const acted = workshop.reduce(initial, { type: "ACT", actionIndex: 0 });
  assert.equal(acted.sceneId, initial.sceneId);
  assert.ok(acted.resolution.message);
  const reset = workshop.reduce(acted, { type: "RESET" });
  assert.equal(reset.resolution, null);
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
