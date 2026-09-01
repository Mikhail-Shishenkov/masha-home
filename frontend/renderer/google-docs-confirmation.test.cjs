"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "styles", "home.css"), "utf8");

assert.match(app, /confirmation\.confirmation_type === "google_drive_document_create"/);
assert.match(app, /confirmation\.confirmation_type === "google_drive_document_recovery"/);
assert.match(app, /`Название:\\n\$\{confirmation\.preview_title\}\\n\\nСодержимое:\\n\$\{confirmation\.preview_body\}`/);
assert.match(app, /recoveryConfirmation \? "Проверить" : "Подтвердить"/);
assert.match(app, /documentRecovery\s*\? decision === "confirm" \? "Проверяю документ"/);
assert.match(app, /recoveryDeferred\s*\?\s*"Документ уже создан"/);
assert.match(app, /"Документ не создан"/);
assert.match(app, /"Не удалось подтвердить создание документа"/);
assert.match(app, /"Документ создан"/);
assert.match(app, /: confirmed \? "Изменение сохранено"/);
assert.match(app, /!confirmed && !rejected && result\?\.pending_confirmation[\s\S]*renderPendingConfirmation\(result\.pending_confirmation\)/);
assert.match(app, /operationActions\.hidden = true/);
assert.match(css, /\.operation-actions\[hidden\]\s*\{\s*display:\s*none;/);

console.log("Google Docs confirmation presentation passed");
