const assert = require("node:assert/strict");
const { resolveScene } = require("./scene-map.js");

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
assert.equal(resolveScene(presentation("waiting")).id, "scene.home.listening");
assert.equal(resolveScene({ home_state: "ready", overlays: { model: "available" }, presence: { activity: "idle", ambient: "quiet", attention: "toward_user" } }).id, "scene.home.quiet_beside");
assert.equal(resolveScene({ home_state: "ready", overlays: { model: "available" }, presence: { activity: "idle", expression: { code: "skeptical" } } }).id, "scene.home.firm_disagreement");
assert.equal(resolveScene(presentation("speaking", { model: "model_unavailable" })).id, "scene.home.idle");
assert.equal(resolveScene(presentation("speaking", { homeState: "unavailable" })).id, "scene.home.idle");
assert.equal(resolveScene(null).id, "scene.home.idle");

console.log("scene-map: 10 passed");
