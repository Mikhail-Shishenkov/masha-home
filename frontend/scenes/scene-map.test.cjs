const assert = require("node:assert/strict");
const { resolveScene, resolveTransition } = require("./scene-map.js");

function presentation(activity, { homeState = "ready", model = "available" } = {}) {
  return {
    home_state: homeState,
    overlays: { model },
    presence: { activity },
  };
}

assert.equal(resolveScene(presentation("idle")).id, "scene.home.idle");
assert.equal(resolveScene(presentation("speaking")).id, "scene.home.conversation");
assert.equal(resolveScene(presentation("processing")).id, "scene.home.thinking");
assert.equal(resolveScene(presentation("working")).id, "scene.home.activity");
assert.equal(resolveScene(presentation("confirmation")).id, "scene.home.listening");
assert.equal(resolveScene(presentation("waiting")).id, "scene.home.listening");
assert.equal(resolveScene({ home_state: "ready", overlays: { model: "available" }, presence: { activity: "idle", ambient: "quiet", attention: "toward_user" } }).id, "scene.home.quiet_beside");
assert.equal(resolveScene({ home_state: "ready", overlays: { model: "available" }, presence: { activity: "idle", expression: { code: "skeptical" } } }).id, "scene.home.firm_disagreement");
assert.equal(resolveScene(presentation("speaking", { model: "model_unavailable" })).id, "scene.home.idle");
assert.equal(resolveScene(presentation("speaking", { homeState: "unavailable" })).id, "scene.home.idle");
assert.equal(resolveScene(null).id, "scene.home.idle");
assert.deepEqual(resolveTransition({}), { kind: "normal", durationMs: 520 });
assert.deepEqual(resolveTransition({ reducedMotion: true }), { kind: "reduced", durationMs: 1 });
assert.deepEqual(resolveTransition({ initial: true }), { kind: "initial", durationMs: 620 });
assert.deepEqual(
  resolveTransition({ presentation: { overlays: { safety: "autonomy_stopped" } } }),
  { kind: "safety", durationMs: 300 },
);
assert.deepEqual(
  resolveTransition({ presentation: { presence: { activity: "listening" } } }),
  { kind: "attention", durationMs: 390 },
);

console.log("scene-map: 15 passed");
