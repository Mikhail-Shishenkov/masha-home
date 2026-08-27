"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");

assert.match(app, /confirmation\.confirmation_type === "google_drive_document_create"/);
assert.match(app, /confirmation\.confirmation_type === "google_drive_document_recovery"/);
assert.match(app, /`Название:\\n\$\{confirmation\.preview_title\}\\n\\nСодержимое:\\n\$\{confirmation\.preview_body\}`/);
assert.match(app, /documentRecovery \? "Проверить" : "Подтвердить"/);
assert.match(app, /documentRecovery\s*\? decision === "confirm" \? "Проверяю документ"/);
assert.match(app, /recoveryDeferred\s*\?\s*"Документ уже создан"/);
assert.match(app, /"Документ не создан"/);
assert.match(app, /"Не удалось подтвердить создание документа"/);
assert.match(app, /"Документ создан"/);
assert.match(app, /: confirmed \? "Изменение сохранено"/);

console.log("Google Docs confirmation presentation passed");
