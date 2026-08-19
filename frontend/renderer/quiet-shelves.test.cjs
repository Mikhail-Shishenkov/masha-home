"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "styles", "home.css"), "utf8");

assert.match(html, /id="history-count"/);
assert.match(html, /id="history-pending-dot"/);
assert.match(html, /id="history-inbox"/);
assert.match(html, /id="history-search-drawer"/);

assert.match(app, /function updateHistoryShelfState\(\)/);
assert.match(app, /function renderHistoryInbox\(\)/);
assert.match(app, /continuityItemCount/);
assert.doesNotMatch(app, /candidatePresentation\.offer\(candidate\)/);

const threadsAt = html.indexOf('class="history-column is-threads"');
const momentsAt = html.indexOf('class="history-column is-moments"');
assert.ok(threadsAt >= 0 && momentsAt > threadsAt);

assert.match(css, /Package B — quiet shelves/);
assert.match(css, /\.history-pending-dot/);
assert.match(css, /\.history-inbox/);

console.log("quiet shelves tests passed");
