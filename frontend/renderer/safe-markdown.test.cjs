"use strict";

const assert = require("node:assert/strict");
const { parse, renderInto } = require("./safe-markdown.js");

class FakeNode {
  constructor(tag = "#text", text = "") {
    this.tag = tag;
    this.textContent = text;
    this.children = [];
    this.dataset = {};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = [...children]; }
}

const documentRef = {
  createElement: (tag) => new FakeNode(tag),
  createTextNode: (text) => new FakeNode("#text", text),
};

const blocks = parse(
  "Обычный **жирный** и *курсив*, затем `код`.\n\n"
  + "- первый\n- второй\n\n1. один\n2. два\n\n"
  + "```js\nconst x = '<script>alert(1)</script>';\n```",
);
assert.deepEqual(blocks.map((block) => block.type), [
  "paragraph", "ul", "ol", "code_block",
]);
assert.deepEqual(blocks[0].lines[0].map((part) => part.type), [
  "text", "strong", "text", "em", "text", "code", "text",
]);

const root = new FakeNode("root");
renderInto(root, "<script onclick=\"alert(1)\">x</script> **да**", documentRef);
const tags = [];
const texts = [];
(function walk(node) {
  tags.push(node.tag);
  if (node.tag === "#text") texts.push(node.textContent);
  node.children.forEach(walk);
})(root);
assert.equal(tags.includes("script"), false);
assert.equal(tags.includes("strong"), true);
assert.equal(texts.join("").includes("<script onclick=\"alert(1)\">"), true);

const malformed = parse("**незакрытый текст и `код");
assert.equal(malformed[0].type, "paragraph");
assert.equal(malformed[0].lines[0].map((part) => part.text).join(""), "**незакрытый текст и `код");

console.log("safe markdown tests passed");
