"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") { this.tag = tag; this.children = []; this.listeners = {}; this.value = ""; this.textContent = ""; this.style = {}; this.disabled = false; }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.children.push(item); return item; }
  replaceChildren(...items) { this.children = [...items]; }
  remove() {}
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  fire(type, target = this) { for (const fn of this.listeners[type] || []) fn({ target }); }
  click() { if (!this.disabled && this.onclick) this.onclick(); else if (!this.disabled) this.fire("click"); }
  scrollIntoView() {}
}

const defaults = { title: "Thử nghiệm", idea: "Một người cha tìm con trong thành phố sau động đất.", genre: "Thảm họa", duration: "30", ratio: "16:9", character: "Minh" };
const elements = new Map();
const get = id => { if (!elements.has(id)) { const e = new Element(); e.id = id; e.disabled = ["aiScript", "prompts", "produce"].includes(id); if (defaults[id] !== undefined) e.value = defaults[id]; elements.set(id, e); } return elements.get(id); };
const storage = new Map();
const context = {
  document: { getElementById: get, createElement: tag => new Element(tag), body: new Element("body") },
  localStorage: { setItem: (k, v) => storage.set(k, String(v)), getItem: k => storage.get(k) ?? null },
  URL: { createObjectURL: () => "blob:test", revokeObjectURL() {} },
  Blob: class Blob { constructor(parts) { this.parts = parts; context.lastBlob = this; } },
  setTimeout: () => 1, clearTimeout() {}, alert: message => { throw new Error("Unexpected alert: " + message); },
  console, Math, Number, String, Array, JSON, Object, Promise
};
context.window = context;
const html = fs.readFileSync("index.html", "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length, 1, "Expected the main UI script to remain inline");
vm.runInNewContext(scripts[0][1], context);

get("draft").click();
assert.equal(get("sceneCount").textContent, 3, "30 sec target should use the minimum supported 10 sec clips");
assert.equal(get("seconds").textContent, "30s");
get("approve").click();
assert.equal(get("approvalState").textContent, "✓ Đã duyệt");
get("prompts").click();
assert.match(String(context.lastBlob.parts[0]), /CẢNH 1 — 10 GIÂY/);

const savedTitle = get("title").value;
get("save").click();
const firstScene = get("scenes").children[0];
const actionField = firstScene.children.find(child => child.tag === "textarea");
actionField.value += " Thay đổi thử.";
actionField.fire("input");
assert.equal(get("approvalState").textContent, "Cần duyệt lại");
get("load").click();
assert.equal(get("title").value, savedTitle, "Draft should restore saved fields");
assert.equal(get("scenes").children.length, 3, "Draft should restore scenes");
assert.equal(get("scenes").children[0].children.find(child => child.tag === "textarea").value.includes("Thay đổi thử"), false,
  "Draft should restore original scene after an edit");
assert.equal(get("approvalState").textContent, "Cần duyệt lại", "Restored script must require re-approval");

get("duration").value = "15";
get("duration").fire("input");
get("draft").click();
assert.equal(get("seconds").textContent, "16s", "15 sec target should use supported clips and allow 1 sec trim");
get("approve").click();
assert.equal(get("approvalState").textContent, "✓ Đã duyệt");
assert.equal(get("produce").disabled, true, "No real generation adapter is configured");
console.log("Frontend draft, edit invalidation, save/restore, supported clip plan and production gate: OK");
