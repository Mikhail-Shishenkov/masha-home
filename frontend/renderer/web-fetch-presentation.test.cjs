"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "styles", "home.css"), "utf8");

assert.match(app, /external_observations/);
assert.match(app, /Прочитала страницу/);
assert.match(app, /bridge\.openObservationSource\(fetched\.observation_id, "page"\)/);
assert.doesNotMatch(app, /fetched\.page\.(?:url|final_url|requested_url)/);
assert.match(app, /network_access: "доступ к публичному интернету"/);
assert.match(app, /grant\.label \|\|/);
assert.match(css, /\.message-page/);

console.log("web fetch presentation boundary passed");
