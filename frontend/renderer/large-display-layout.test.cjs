"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const css = fs.readFileSync(path.join(__dirname, "..", "styles", "home.css"), "utf8");
assert.match(css, /@media \(min-width: 1800px\)/);
assert.match(css, /width:\s*clamp\(610px,\s*28vw,\s*920px\)/);
assert.match(css, /height:\s*min\(76vh,\s*1120px\)/);
assert.match(css, /font-size:\s*clamp\(16px,\s*\.54vw,\s*20px\)/);
assert.match(css, /Segoe UI Emoji.*Apple Color Emoji.*Noto Color Emoji/);

function largeWidth(viewportWidth) {
  return Math.min(920, Math.max(610, viewportWidth * 0.28));
}
assert.ok(Math.abs(largeWidth(2560) - 716.8) < 0.01);
assert.equal(largeWidth(3840), 920);
assert.ok(largeWidth(3840) < 3840 * 0.25);

console.log("large display layout tests passed");
