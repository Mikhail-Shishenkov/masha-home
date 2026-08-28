"use strict";

const assert = require("node:assert/strict");
const { resolveScene } = require("../scenes/scene-map.js");

function special({
  proximity = "close",
  expression = "warm_smile",
  activity = "speaking",
  ambient = "active",
} = {}) {
  return {
    home_state: "ready",
    home_moment: "special_evening",
    home_proximity: proximity,
    observed_at: "2026-08-28T22:00:00+03:00",
    overlays: {
      model: "model_available",
      safety: "autonomy_active",
    },
    presence: {
      activity,
      attention: "toward_user",
      ambient,
      expression: { code: expression },
    },
  };
}

// WARM -> accepted Stage 2 canonical pair.
assert.equal(
  resolveScene(special({ proximity: "close" })).id,
  "scene.home.evening.special_close"
);
assert.equal(
  resolveScene(special({ proximity: "near" })).id,
  "scene.home.evening.special_near"
);

// Classifier playful -> Presentation ExpressionCode.PLAYFUL.
assert.equal(
  resolveScene(
    special({ proximity: "close", expression: "playful" })
  ).id,
  "scene.home.evening.special_close_playful"
);
assert.equal(
  resolveScene(
    special({ proximity: "near", expression: "playful" })
  ).id,
  "scene.home.evening.special_near_playful"
);

// Classifier supportive -> Presentation ExpressionCode.SYMPATHETIC.
assert.equal(
  resolveScene(
    special({ proximity: "close", expression: "sympathetic" })
  ).id,
  "scene.home.evening.special_close_supportive"
);
assert.equal(
  resolveScene(
    special({ proximity: "near", expression: "sympathetic" })
  ).id,
  "scene.home.evening.special_near_supportive"
);

// Classifier firm -> Presentation ExpressionCode.SERIOUS.
// Skeptical shares the bounded firm visual family.
for (const expression of ["serious", "skeptical"]) {
  assert.equal(
    resolveScene(
      special({ proximity: "close", expression })
    ).id,
    "scene.home.evening.special_close_firm"
  );
  assert.equal(
    resolveScene(
      special({ proximity: "near", expression })
    ).id,
    "scene.home.evening.special_near_firm"
  );
}

// Expression never owns distance: WIDE stays WIDE for every mood.
for (const expression of [
  "warm_smile",
  "playful",
  "sympathetic",
  "serious",
  "skeptical",
]) {
  assert.equal(
    resolveScene(
      special({ proximity: "wide", expression })
    ).id,
    "scene.home.evening.special"
  );
}

// Unsupported expression -> canonical current distance.
assert.equal(
  resolveScene(
    special({ proximity: "close", expression: "surprised" })
  ).id,
  "scene.home.evening.special_close"
);

// Warm idle NEAR keeps the quiet scene.
assert.equal(
  resolveScene(
    special({
      proximity: "near",
      expression: "warm_smile",
      activity: "idle",
      ambient: "quiet",
    })
  ).id,
  "scene.home.evening.special_quiet_near"
);

// Explicit expression wins over quiet-idle only inside the same NEAR level.
assert.equal(
  resolveScene(
    special({
      proximity: "near",
      expression: "playful",
      activity: "idle",
      ambient: "quiet",
    })
  ).id,
  "scene.home.evening.special_near_playful"
);

console.log("special evening expression layer tests passed");
