const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { SCENES, resolveHomePeriod, resolveScene, resolveTransition } = require("./scene-map.js");

function presentation(activity, { homeState = "ready", model = "available", attention, observedAt } = {}) {
  return {
    home_state: homeState,
    observed_at: observedAt,
    overlays: { model },
    presence: { activity, attention },
  };
}

assert.equal(resolveHomePeriod(presentation("idle", { observedAt: "2026-08-14T11:30:00+04:00" })), "day");
assert.equal(resolveHomePeriod(presentation("idle", { observedAt: "2026-08-14T21:30:00+04:00" })), "evening");
assert.equal(resolveHomePeriod(presentation("idle")), "evening");
assert.equal(resolveScene(presentation("idle")).id, "scene.home.evening.idle");
assert.equal(resolveScene(presentation("speaking")).id, "scene.home.evening.conversation");
assert.equal(resolveScene(presentation("processing")).id, "scene.home.evening.thinking");
assert.equal(resolveScene(presentation("working")).id, "scene.home.evening.activity");
assert.equal(resolveScene(presentation("confirmation")).id, "scene.home.evening.idle");
assert.equal(resolveScene(presentation("waiting")).id, "scene.home.evening.idle");
assert.equal(resolveScene(presentation("waiting", { attention: "toward_user" })).id, "scene.home.evening.listening");
assert.equal(resolveScene(presentation("idle", { observedAt: "2026-08-14T11:30:00+04:00" })).source, "assets/presence/day/idle.png");
assert.equal(resolveScene({ home_state: "ready", overlays: { model: "available" }, presence: { activity: "idle", ambient: "quiet", attention: "toward_user" } }).id, "scene.home.evening.quiet_beside");
assert.equal(resolveScene({ home_state: "ready", overlays: { model: "available" }, presence: { activity: "idle", expression: { code: "skeptical" } } }).id, "scene.home.evening.firm_disagreement");
assert.equal(resolveScene(presentation("speaking", { model: "model_unavailable" })).id, "scene.home.evening.idle");
assert.equal(resolveScene(presentation("speaking", { homeState: "unavailable" })).id, "scene.home.evening.idle");
assert.equal(resolveScene(null).id, "scene.home.evening.idle");
for (const family of Object.values(SCENES)) {
  for (const scene of Object.values(family)) {
    assert.equal(fs.existsSync(path.join(__dirname, "..", scene.source)), true, scene.source);
  }
}
assert.deepEqual(resolveTransition({}), { kind: "normal", exitMs: 190, enterMs: 330, settleMs: 110, minimumHoldMs: 720 });
assert.deepEqual(resolveTransition({ reducedMotion: true }), { kind: "reduced", exitMs: 0, enterMs: 1, settleMs: 0, minimumHoldMs: 0 });
assert.deepEqual(resolveTransition({ initial: true }), { kind: "initial", exitMs: 0, enterMs: 520, settleMs: 0, minimumHoldMs: 500 });
assert.deepEqual(
  resolveTransition({ presentation: { overlays: { safety: "autonomy_stopped" } } }),
  { kind: "safety", exitMs: 120, enterMs: 220, settleMs: 0, minimumHoldMs: 300 },
);
assert.deepEqual(
  resolveTransition({ presentation: { presence: { activity: "listening" } } }),
  { kind: "attention", exitMs: 160, enterMs: 280, settleMs: 120, minimumHoldMs: 620 },
);

console.log("scene-map: presence states and asset registry passed");
