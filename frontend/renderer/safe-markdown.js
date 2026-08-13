"use strict";

// Small allow-listed Markdown subset. It creates DOM/text nodes only and never
// interprets model text as HTML.
(function registerSafeMarkdown(global) {
  function inlineParts(text) {
    const parts = [];
    const token = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
    let cursor = 0;
    for (const match of text.matchAll(token)) {
      if (match.index > cursor) parts.push({ type: "text", text: text.slice(cursor, match.index) });
      const value = match[0];
      if (value.startsWith("**")) parts.push({ type: "strong", text: value.slice(2, -2) });
      else if (value.startsWith("*")) parts.push({ type: "em", text: value.slice(1, -1) });
      else parts.push({ type: "code", text: value.slice(1, -1) });
      cursor = match.index + value.length;
    }
    if (cursor < text.length) parts.push({ type: "text", text: text.slice(cursor) });
    return parts;
  }

  function parse(text) {
    const lines = String(text).replace(/\r\n?/g, "\n").split("\n");
    const blocks = [];
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      if (line.startsWith("```")) {
        const language = line.slice(3).trim();
        const code = [];
        index += 1;
        while (index < lines.length && !lines[index].startsWith("```")) code.push(lines[index++]);
        if (index < lines.length) index += 1;
        blocks.push({ type: "code_block", language, text: code.join("\n") });
        continue;
      }
      const unordered = /^\s*[-+]\s+(.+)$/.exec(line);
      const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
      if (unordered || ordered) {
        const type = unordered ? "ul" : "ol";
        const items = [];
        while (index < lines.length) {
          const item = (type === "ul" ? /^\s*[-+]\s+(.+)$/ : /^\s*\d+[.)]\s+(.+)$/).exec(lines[index]);
          if (!item) break;
          items.push(inlineParts(item[1]));
          index += 1;
        }
        blocks.push({ type, items });
        continue;
      }
      if (!line.trim()) {
        index += 1;
        continue;
      }
      const paragraph = [line];
      index += 1;
      while (
        index < lines.length
        && lines[index].trim()
        && !lines[index].startsWith("```")
        && !/^\s*[-+]\s+/.test(lines[index])
        && !/^\s*\d+[.)]\s+/.test(lines[index])
      ) paragraph.push(lines[index++]);
      blocks.push({ type: "paragraph", lines: paragraph.map(inlineParts) });
    }
    return blocks;
  }

  function appendInline(parent, parts, documentRef) {
    for (const part of parts) {
      if (part.type === "text") parent.append(documentRef.createTextNode(part.text));
      else {
        const element = documentRef.createElement(part.type);
        element.textContent = part.text;
        parent.append(element);
      }
    }
  }

  function renderInto(root, text, documentRef = document) {
    root.replaceChildren();
    for (const block of parse(text)) {
      if (block.type === "code_block") {
        const pre = documentRef.createElement("pre");
        const code = documentRef.createElement("code");
        if (block.language) code.dataset.language = block.language;
        code.textContent = block.text;
        pre.append(code);
        root.append(pre);
      } else if (block.type === "ul" || block.type === "ol") {
        const list = documentRef.createElement(block.type);
        for (const parts of block.items) {
          const item = documentRef.createElement("li");
          appendInline(item, parts, documentRef);
          list.append(item);
        }
        root.append(list);
      } else {
        const paragraph = documentRef.createElement("p");
        block.lines.forEach((parts, index) => {
          if (index) paragraph.append(documentRef.createElement("br"));
          appendInline(paragraph, parts, documentRef);
        });
        root.append(paragraph);
      }
    }
  }

  const api = Object.freeze({ parse, renderInto });
  global.MashaSafeMarkdown = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
