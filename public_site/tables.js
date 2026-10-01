// Sort and filter for tables marked class="sortable".
// Same origin, no dependencies. With script off, the table is still the full table.
// Numeric order reads data-v only. Display text such as "−$100" is never parsed.
// Also measures header.site and writes --hdr-h so sticky table headers sit flush under it.
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (typeof document !== "undefined") {
    var go = function () {
      api.enhance(document);
      api.syncHeaderOffset(document);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go);
    else go();
  }
  root.EdgeTables = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var FILTERS = { sport: "Sport", status: "Status" };

  function finite(raw) {
    if (raw == null) return null;
    var text = String(raw).trim();
    if (!/^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(text)) return null;
    var n = Number(text);
    return Number.isFinite(n) ? n : null;
  }

  function compareNumeric(a, b, dir) {
    var av = finite(a.dataV);
    var bv = finite(b.dataV);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (av === bv) return 0;
    return (av < bv ? -1 : 1) * dir;
  }

  function sortRecords(records, options) {
    var opts = options || {};
    var numeric = !!opts.numeric;
    var direction = opts.direction || (numeric ? "desc" : "asc");
    var dir = direction === "asc" ? 1 : -1;
    var copy = records.slice();
    copy.sort(function (a, b) {
      if (numeric) return compareNumeric(a, b, dir);
      var cmp = String(a.text || "").localeCompare(String(b.text || ""), undefined, { sensitivity: "base" });
      return cmp * dir;
    });
    return copy;
  }

  function matchesText(record, query) {
    var q = String(query || "").trim().toLowerCase();
    if (!q) return true;
    var hay = record.haystack == null ? record.text : record.haystack;
    return String(hay || "").toLowerCase().indexOf(q) !== -1;
  }

  function filterRecords(records, query) {
    return records.filter(function (record) { return matchesText(record, query); });
  }

  function cellText(cell) {
    return (cell && cell.textContent ? cell.textContent : "").replace(/\s+/g, " ").trim();
  }

  function headerLabel(th) {
    return cellText(th).replace(/[↑↓]\s*$/, "").trim().toLowerCase();
  }

  function bodyRows(table) {
    var body = table.tBodies && table.tBodies[0];
    if (!body) return [];
    return Array.prototype.filter.call(body.rows, function (row) {
      return !row.classList.contains("grp");
    });
  }

  function columnNumeric(rows, index) {
    var any = false;
    for (var i = 0; i < rows.length; i++) {
      var cell = rows[i].cells[index];
      if (!cell || !cell.hasAttribute("data-v")) continue;
      var raw = cell.getAttribute("data-v");
      if (raw === "") continue;
      if (finite(raw) == null) return false;
      any = true;
    }
    return any;
  }

  function syncHeaderOffset(doc) {
    var header = doc.querySelector("header.site");
    if (!header) return;
    var root = doc.documentElement;
    var view = doc.defaultView;
    function apply() {
      var box = header.getBoundingClientRect();
      if (!(box.height > 0)) return;
      root.style.setProperty("--hdr-h", box.height + "px");
    }
    apply();
    if (view && typeof view.ResizeObserver === "function") {
      new view.ResizeObserver(apply).observe(header);
    } else if (view) {
      view.addEventListener("resize", apply);
    }
    if (view) view.addEventListener("load", apply);
  }

  function enhance(doc) {
    Array.prototype.forEach.call(doc.querySelectorAll("table.sortable"), function (table) {
      var rows = bodyRows(table);
      var headRow = table.tHead && table.tHead.rows.length
        ? table.tHead.rows[table.tHead.rows.length - 1]
        : null;
      if (!headRow) return;
      wireSort(table, headRow, rows);
      wireFilters(doc, table, headRow, rows);
    });
  }

  function wireSort(table, headRow, rows) {
    Array.prototype.forEach.call(headRow.cells, function (th, index) {
      th.setAttribute("tabindex", "0");
      th.setAttribute("role", "columnheader");
      if (!th.getAttribute("aria-sort")) th.setAttribute("aria-sort", "none");
      var numeric = columnNumeric(rows, index);
      function toggle() {
        var next = th.getAttribute("aria-sort") === "ascending" ? "descending"
          : th.getAttribute("aria-sort") === "descending" ? "ascending"
          : (numeric ? "descending" : "ascending");
        Array.prototype.forEach.call(headRow.cells, function (other) {
          other.setAttribute("aria-sort", other === th ? next : "none");
        });
        var records = rows.map(function (row) {
          var cell = row.cells[index];
          return {
            row: row,
            dataV: cell ? cell.getAttribute("data-v") : "",
            text: cellText(cell),
          };
        });
        sortRecords(records, { numeric: numeric, direction: next === "ascending" ? "asc" : "desc" })
          .forEach(function (record) { record.row.parentNode.appendChild(record.row); });
      }
      th.addEventListener("click", toggle);
      th.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggle();
        }
      });
    });
  }

  function wireFilters(doc, table, headRow, rows) {
    var box = table.closest(".tbl");
    var tools = box && box.previousElementSibling;
    if (!tools || !tools.classList.contains("table-tools")) {
      tools = doc.createElement("div");
      tools.className = "table-tools";
      var search = doc.createElement("input");
      search.type = "search";
      search.className = "flt";
      search.setAttribute("aria-label", "Filter rows");
      search.placeholder = "Search…";
      tools.appendChild(search);
      (box || table).parentNode.insertBefore(tools, box || table);
    }
    var input = tools.querySelector("input.flt");
    var selects = [];
    Array.prototype.forEach.call(headRow.cells, function (th, index) {
      var label = headerLabel(th);
      if (!FILTERS[label]) return;
      var select = doc.createElement("select");
      select.setAttribute("aria-label", FILTERS[label]);
      var all = doc.createElement("option");
      all.value = "";
      all.textContent = FILTERS[label] + ": all";
      select.appendChild(all);
      var seen = {};
      rows.forEach(function (row) {
        var text = cellText(row.cells[index]);
        if (!text || seen[text]) return;
        seen[text] = true;
      });
      Object.keys(seen).sort(function (a, b) {
        return a.localeCompare(b, undefined, { sensitivity: "base" });
      }).forEach(function (text) {
        var opt = doc.createElement("option");
        opt.value = text;
        opt.textContent = text;
        select.appendChild(opt);
      });
      tools.appendChild(select);
      selects.push({ select: select, index: index });
    });
    var count = doc.createElement("span");
    count.className = "count";
    tools.appendChild(count);

    function apply() {
      var query = input ? input.value : "";
      var shown = 0;
      rows.forEach(function (row) {
        var record = { haystack: row.textContent || "", text: row.textContent || "" };
        var ok = matchesText(record, query);
        for (var i = 0; i < selects.length && ok; i++) {
          var want = selects[i].select.value;
          if (want && cellText(row.cells[selects[i].index]) !== want) ok = false;
        }
        row.hidden = !ok;
        if (ok) shown += 1;
      });
      count.textContent = shown + " of " + rows.length + " rows";
    }
    if (input) input.addEventListener("input", apply);
    selects.forEach(function (item) { item.select.addEventListener("change", apply); });
    apply();
  }

  return {
    sortRecords: sortRecords,
    filterRecords: filterRecords,
    matchesText: matchesText,
    enhance: enhance,
    syncHeaderOffset: syncHeaderOffset,
  };
});
