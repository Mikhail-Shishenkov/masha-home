"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "styles", "home.css"), "utf8");

assert.match(html, /id="thread-context"/);
assert.match(html, /id="thread-context-title"/);
assert.match(html, /id="thread-context-clear"/);
assert.match(app, /function renderActiveContinuityThread\(thread\)/);
assert.match(app, /bridge\.activateContinuityThread\(thread\.thread_id\)/);
assert.match(app, /bridge\.clearContinuityThread\(\)/);
assert.doesNotMatch(app, /bridge\.continueContinuityThread\(thread\.thread_id\)/);
assert.match(css, /Package C — living threads/);
assert.match(css, /\.thread-context/);
console.log("living threads tests passed");
