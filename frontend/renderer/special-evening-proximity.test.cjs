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
const boundaryAt = scenes.indexOf(
  'if (["skeptical", "serious"].includes(expression))',
  specialAt
);
const nearAt = scenes.indexOf(
  'if (specialProximity === "near")',
  specialAt
);

assert.ok(specialAt >= 0);
assert.ok(boundaryAt > specialAt && boundaryAt < nearAt);
assert.match(css, /Special Evening 2\.0 - proximity/);

console.log("special evening proximity tests passed");
