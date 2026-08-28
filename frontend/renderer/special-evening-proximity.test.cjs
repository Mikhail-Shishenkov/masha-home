"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "styles", "home.css"), "utf8");
const scenes = fs.readFileSync(path.join(root, "scenes", "scene-map.js"), "utf8");

assert.match(html, /id="special-proximity-toggle"/);
assert.match(app, /advanceSpecialEveningProximity/);
assert.match(app, /dataset\.homeProximity/);
assert.match(app, /Ещё ближе/);
assert.match(app, /Чуть дальше/);

assert.match(scenes, /presentation\.home_proximity/);
assert.match(scenes, /specialProximity === "close"/);
assert.match(scenes, /specialProximity === "near"/);

const specialAt = scenes.indexOf("if (specialEvening)");
const ordinaryAt = scenes.indexOf(
  '  if (\n  activity === "idle"\n',
  specialAt
);

assert.ok(specialAt >= 0);
assert.ok(ordinaryAt > specialAt);

const specialBlock = scenes.slice(specialAt, ordinaryAt);

// Expression may change only the asset inside the current relationship
// distance. It must never jump to the ordinary boundary scene.
assert.doesNotMatch(specialBlock, /return scenes\.firmDisagreement/);

assert.match(
  specialBlock,
  /specialProximity === "near"[\s\S]*specialNearPlayful/
);
assert.match(
  specialBlock,
  /specialProximity === "near"[\s\S]*specialNearSupportive/
);
assert.match(
  specialBlock,
  /specialProximity === "near"[\s\S]*specialNearFirm/
);
assert.match(
  specialBlock,
  /specialProximity === "close"[\s\S]*specialClosePlayful/
);
assert.match(
  specialBlock,
  /specialProximity === "close"[\s\S]*specialCloseSupportive/
);
assert.match(
  specialBlock,
  /specialProximity === "close"[\s\S]*specialCloseFirm/
);
assert.match(specialBlock, /WIDE intentionally stays canonical/);

assert.match(css, /Special Evening 2\.0 - proximity/);

console.log("special evening proximity tests passed");
