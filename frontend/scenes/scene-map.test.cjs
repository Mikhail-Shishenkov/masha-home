const assert = require("node:assert/strict");
const { resolveScene, resolveTransition } = require("./scene-map.js");

function presentation(activity, { homeState = "ready", model = "available", attention } = {}) {
  return {
    home_state: homeState,
    overlays: { model },
    presence: { activity, attention },
  };
}

assert.equal(resolveScene(presentation("idle")).id, "scene.home.idle");
assert.equal(resolveScene(presentation("speaking")).id, "scene.home.conversation");
assert.equal(resolveScene(presentation("processing")).id, "scene.home.thinking");
assert.equal(resolveScene(presentation("working")).id, "scene.home.activity");
assert.equal(resolveScene(presentation("confirmation")).id, "scene.home.idle");
assert.equal(resolveScene(presentation("waiting")).id, "scene.home.idle");
assert.equal(resolveScene(presentation("waiting", { attention: "toward_user" })).id, "scene.home.listening");
assert.equal(resolveScene({ home_state: "ready", overlays: { model: "available" }, presence: { activity: "idle", ambient: "quiet", attention: "toward_user" } }).id, "scene.home.quiet_beside");
assert.equal(resolveScene({ home_state: "ready", overlays: { model: "available" }, presence: { activity: "idle", expression: { code: "skeptical" } } }).id, "scene.home.firm_disagreement");
assert.equal(resolveScene(presentation("speaking", { model: "model_unavailable" })).id, "scene.home.idle");
assert.equal(resolveScene(presentation("speaking", { homeState: "unavailable" })).id, "scene.home.idle");
assert.equal(resolveScene(null).id, "scene.home.idle");
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

console.log("scene-map: 16 passed");
