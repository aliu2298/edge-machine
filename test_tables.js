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
