// Sort and filter, with no dependencies. Run: node test_tables.js
// "−$100" (data-v -100) sorts below "+$6" (data-v 6) because the order
// reads data-v, not the rendered text.
"use strict";

var assert = require("assert");
var tables = require("./public_site/tables.js");

var rows = [
  { dataV: "-100", text: "\u2212$100", haystack: "alpha loss" },
  { dataV: "6", text: "+$6", haystack: "beta win" },
];

var sorted = tables.sortRecords(rows, { numeric: true, direction: "desc" });
assert.strictEqual(sorted[0].text, "+$6", "higher data-v is first when sorting down");
assert.strictEqual(sorted[1].text, "\u2212$100", "\u2212$100 (data-v -100) sorts below +$6 (data-v 6)");

// The rendered minus is U+2212. If the sort parsed that text it would not
// see a negative number. Swapping data-v reverses the order anyway.
var swapped = tables.sortRecords([
  { dataV: "6", text: "\u2212$100", haystack: "looks negative" },
  { dataV: "-100", text: "+$6", haystack: "looks positive" },
], { numeric: true, direction: "desc" });
assert.strictEqual(swapped[0].dataV, "6");
assert.strictEqual(swapped[0].text, "\u2212$100", "order follows data-v, not the rendered minus");
assert.strictEqual(swapped[1].text, "+$6");

var filtered = tables.filterRecords(rows, "alpha");
assert.strictEqual(filtered.length, 1);
assert.strictEqual(filtered[0].haystack, "alpha loss");
assert.strictEqual(tables.filterRecords(rows, "   ").length, 2, "a blank query keeps every row");
assert.strictEqual(tables.filterRecords(rows, "nope").length, 0);

console.log("ok: \u2212$100 sorts below +$6, and the text filter keeps the matching row");

// Phone cards and the row filter share one predicate. Boston + MLB keeps the
// Boston row and drops the tennis combo. paintRow hides a card with
// display:none !important, because the card layout's display:block beats
// the hidden attribute on its own.
var boston = { haystack: "Boston Red Sox MLB", text: "Boston Red Sox MLB" };
var tennis = {
  haystack: "2-leg tennis combo: Denis Shapovalov + Kimberly Birrell Tennis · Combos",
  text: "2-leg tennis combo: Denis Shapovalov + Kimberly Birrell Tennis · Combos",
};
assert.strictEqual(
  tables.passesFilters(boston, "Boston", [{ text: "MLB", value: "MLB" }]),
  true,
  "Boston + MLB matches the Boston row");
assert.strictEqual(
  tables.passesFilters(tennis, "Boston", [{ text: "Tennis · Combos", value: "MLB" }]),
  false,
  "Boston + MLB does not match the tennis combo");
assert.strictEqual(
  tables.passesFilters(tennis, "shapovalov", [{ text: "Tennis · Combos", value: "" }]),
  true,
  "a blank sport select does not filter the row out");
assert.strictEqual(
  tables.passesFilters(boston, "Boston", [{ text: "MLB", value: "Tennis · Combos" }]),
  false,
  "a sport select has to match the sport cell");
assert.strictEqual(tables.passesFilters(boston, "", []), true, "no query and no selects keeps the row");

function fakeRow() {
  var props = {};
  return {
    hidden: false,
    style: {
      setProperty: function (name, value, priority) {
        props[name] = priority ? value + " !" + priority : value;
      },
      removeProperty: function (name) { delete props[name]; },
    },
    props: props,
  };
}
var hiddenRow = fakeRow();
tables.paintRow(hiddenRow, false);
assert.strictEqual(hiddenRow.hidden, true, "a filtered row is hidden");
assert.strictEqual(hiddenRow.props.display, "none !important",
  "a filtered card is display:none !important so the card layout cannot show it");
var shownRow = fakeRow();
shownRow.hidden = true;
shownRow.props.display = "none !important";
tables.paintRow(shownRow, true);
assert.strictEqual(shownRow.hidden, false);
assert.strictEqual(shownRow.props.display, undefined, "a row that passes clears the inline display");

console.log("ok: Boston + MLB matches the row and the card, and the tennis combo does not");

// Keyboard flip. Enter/Space on a .rule-flip clicks the card. After paint(),
// focus has to land on the .rule-flip of the face now showing, or the next
// keypress hits BODY and a screen reader loses the control.
var sha = "unknown";
try {
  sha = require("child_process").execSync("git rev-parse HEAD", {
    cwd: require("path").join(__dirname),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }).trim() || "unknown";
} catch (e) {
  sha = "unknown";
}
console.log("SHA " + sha);

function classListOf(node) {
  return {
    contains: function (name) { return node.classes.indexOf(name) !== -1; },
    toggle: function (name, force) {
      var has = node.classes.indexOf(name) !== -1;
      var on = force === undefined ? !has : !!force;
      if (on && !has) node.classes.push(name);
      if (!on && has) node.classes.splice(node.classes.indexOf(name), 1);
      return on;
    },
  };
}

function matches(node, sel) {
  if (sel.charAt(0) === ".") return node.classList.contains(sel.slice(1));
  return node.tag === sel;
}

function descendants(node, out) {
  node.children.forEach(function (child) {
    out.push(child);
    descendants(child, out);
  });
  return out;
}

function queryAll(root, selector) {
  var parts = selector.trim().split(/\s+/);
  return descendants(root, []).filter(function (node) {
    var part = parts.length - 1;
    var cur = node;
    if (!matches(cur, parts[part])) return false;
    while (part > 0) {
      part -= 1;
      var found = false;
      cur = cur.parent;
      while (cur) {
        if (matches(cur, parts[part])) { found = true; break; }
        cur = cur.parent;
      }
      if (!found) return false;
    }
    return true;
  });
}

function el(tag, classes, children) {
  var node = {
    tag: tag,
    classes: classes ? classes.split(/\s+/).filter(Boolean) : [],
    children: children || [],
    parent: null,
    attrs: {},
    tabIndex: 0,
    listeners: {},
  };
  node.classList = classListOf(node);
  node.children.forEach(function (child) { child.parent = node; });
  node.setAttribute = function (name, value) { node.attrs[name] = String(value); };
  node.getAttribute = function (name) {
    return Object.prototype.hasOwnProperty.call(node.attrs, name) ? node.attrs[name] : null;
  };
  node.querySelectorAll = function (selector) { return queryAll(node, selector); };
  node.querySelector = function (selector) { return queryAll(node, selector)[0] || null; };
  node.closest = function (selector) {
    var cur = node;
    while (cur) {
      if (matches(cur, selector)) return cur;
      cur = cur.parent;
    }
    return null;
  };
  node.addEventListener = function (type, fn) {
    (node.listeners[type] = node.listeners[type] || []).push(fn);
  };
  node.focus = function () { global.document.activeElement = node; };
  node.click = function () {
    var ev = { target: node };
    var cur = node;
    while (cur) {
      (cur.listeners.click || []).slice().forEach(function (fn) { fn(ev); });
      cur = cur.parent;
    }
  };
  return node;
}

var openGames = el("button", "rule-flip");
var verdict = el("button", "rule-flip");
openGames.name = "Open games";
verdict.name = "Verdict";
var front = el("div", "rule-face rule-front", [openGames]);
var back = el("div", "rule-face rule-back", [verdict]);
var card = el("article", "rule-card", [el("div", "rule-rotator", [front, back])]);
var doc = el("div", "", [card]);
global.document = doc;
doc.activeElement = doc;

function focusedFlip() {
  var current = document.activeElement;
  if (!current || !current.classList || !current.classList.contains("rule-flip")) return "(none)";
  var face = current.closest(".rule-face");
  var side = face && face.classList.contains("rule-back") ? "back"
    : face && face.classList.contains("rule-front") ? "front" : "?";
  return side + ":" + (current.name || "?");
}

tables.wireRuleCards(doc);
openGames.focus();
openGames.click();
assert.ok(card.classList.contains("is-flipped"), "the card flips");
assert.strictEqual(focusedFlip(), "back:Verdict",
  "after flip from a .rule-flip, focus is on the visible face's .rule-flip");
assert.strictEqual(back.getAttribute("aria-hidden"), "false");
assert.strictEqual(front.getAttribute("aria-hidden"), "true");
verdict.click();
assert.ok(!card.classList.contains("is-flipped"), "a second flip returns to the front");
assert.strictEqual(focusedFlip(), "front:Open games",
  "a second flip puts focus back on the front .rule-flip");

doc.activeElement = doc;
card.click();
assert.ok(card.classList.contains("is-flipped"), "a click elsewhere on the card still flips");
assert.strictEqual(document.activeElement, doc,
  "a click that was not on a .rule-flip leaves focus where it was");

console.log("ok: flip from a .rule-flip keeps focus on the face now showing");
console.log("SHA " + sha + " PASSED");
