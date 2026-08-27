"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const sceneMap = require("./scene-map.js");

test("Workbench corner follows Home day/evening period", () => {
  const day = sceneMap.resolveCornerScene({
    observed_at: "2026-08-27T12:00:00+03:00",
  });
  const evening = sceneMap.resolveCornerScene({
    observed_at: "2026-08-27T20:00:00+03:00",
  });

  assert.equal(day.id, "scene.home.day.corner");
  assert.equal(day.source, "assets/presence/day/corner/corner_day.png");
  assert.equal(evening.id, "scene.home.evening.corner");
  assert.equal(evening.source, "assets/presence/evening/corner/corner_evening.png");
});

test("Corner period uses Home observed_at, not the browser clock", () => {
  assert.equal(
    sceneMap.resolveHomePeriod({ observed_at: "2026-08-27T06:59:59+03:00" }),
    "evening"
  );
  assert.equal(
    sceneMap.resolveHomePeriod({ observed_at: "2026-08-27T07:00:00+03:00" }),
    "day"
  );
  assert.equal(
    sceneMap.resolveHomePeriod({ observed_at: "2026-08-27T17:59:59+03:00" }),
    "day"
  );
  assert.equal(
    sceneMap.resolveHomePeriod({ observed_at: "2026-08-27T18:00:00+03:00" }),
    "evening"
  );
});
