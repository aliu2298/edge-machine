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
