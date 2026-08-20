"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const scenes = fs.readFileSync(
  path.join(root, "scenes", "scene-map.js"),
  "utf8"
);

assert.match(scenes, /assets\/presence\/evening\/special-close\.png/);
assert.match(scenes, /assets\/presence\/evening\/special-near\.png/);
assert.match(scenes, /assets\/presence\/evening\/special-quiet-near\.png/);

assert.match(scenes, /specialNear: scene\(/);
assert.match(scenes, /specialQuietNear: scene\(/);

const specialAt = scenes.indexOf("if (specialEvening)");
const ordinaryAt = scenes.indexOf(
  '  if (\n  activity === "idle"\n',
  specialAt
);

assert.ok(specialAt >= 0);
assert.ok(ordinaryAt > specialAt);

const specialBlock = scenes.slice(specialAt, ordinaryAt);

assert.match(
  specialBlock,
  /specialProximity === "near"[\s\S]*scenes\.specialQuietNear/
);
assert.match(
  specialBlock,
  /specialProximity === "near"[\s\S]*return scenes\.specialNear/
);
assert.match(
  specialBlock,
  /specialProximity === "close"[\s\S]*return scenes\.specialClose/
);
assert.match(specialBlock, /return scenes\.specialEvening/);

assert.doesNotMatch(specialBlock, /chooseVariant\(/);
assert.doesNotMatch(specialBlock, /scenes\.specialMug/);
assert.doesNotMatch(specialBlock, /scenes\.specialQuiet;/);

console.log("special evening D3 visual asset tests passed");
