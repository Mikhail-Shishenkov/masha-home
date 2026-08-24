"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");

assert.match(html, /id="add-local-document"/);
assert.match(html, /id="local-document-chip"/);
assert.doesNotMatch(html, /id="clear-local-document"/);
assert.doesNotMatch(app, /clearLocalDocument|clear-local-document/);
assert.match(app, /bridge\.chooseLocalDocument\(\)/);
assert.match(app, /bridge\.submitMessageWithDocument\(content, token\)/);
assert.match(app, /local_documents/);
assert.match(app, /локальный файл/);
const localReceipt = app.slice(
  app.indexOf("for (const pdf of message.local_documents"),
  app.indexOf("if (fetched?.page)")
);
assert.doesNotMatch(localReceipt, /(?:openObservationSource|file:\/\/)/);

console.log("local document presentation boundary passed");
