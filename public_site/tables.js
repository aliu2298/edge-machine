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
      api.containWideTables(document);
      api.wireRuleCards(document);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go);
    else go();
    // Pages that do not load site.js (Production, Trading, NBA, the index stub)
    // still need the active phone pill scrolled into view. site.js arms this
    // first when it is on the page; this is the same behaviour for the rest.
    if (!root.EdgeNav) {
      root.EdgeNav = true;
      var narrowNav = root.matchMedia ? root.matchMedia("(max-width:640px)") : null;
      var fadeWidth = function () {
        var raw = getComputedStyle(document.documentElement).getPropertyValue("--nav-fade");
        var n = parseFloat(raw);
        return n > 0 ? n : 22;
      };
      var armNav = function (bar, followCurrent) {
        if (!bar || !narrowNav) return;
        function pastRight() {
          return bar.scrollWidth > bar.clientWidth + 1
            && bar.scrollLeft + bar.clientWidth < bar.scrollWidth - 2;
        }
        function pastLeft() {
          return bar.scrollLeft > 2;
        }
        function paint() {
          bar.classList.toggle("nav-fade", narrowNav.matches && pastRight());
          bar.classList.toggle("nav-fade-left", narrowNav.matches && pastLeft());
        }
        function ringOutset(el) {
          try {
            var cs = getComputedStyle(el);
            var width = parseFloat(cs.outlineWidth) || 0;
            var offset = parseFloat(cs.outlineOffset) || 0;
            if (!width || cs.outlineStyle === "none") return 0;
            var extra = width + offset;
            return extra > 0 ? extra : 0;
          } catch (e) {
            return 0;
          }
        }
        // Same reveal as site.js. Keyboard focus only. Instant scroll.
        function reveal(el) {
          if (!narrowNav.matches || !el) return;
          var fade = fadeWidth() + ringOutset(el);
          var navRect = bar.getBoundingClientRect();
          var aRect = el.getBoundingClientRect();
          var delta = 0;
          if (aRect.left < navRect.left + fade - 0.5) delta = aRect.left - navRect.left - fade;
          else if (aRect.right > navRect.right - fade + 0.5) delta = aRect.right - (navRect.right - fade);
          if (delta) bar.scrollLeft += delta;
        }
        var placedWidth = -1;
        function place() {
          placedWidth = root.innerWidth;
          if (!narrowNav.matches) {
            bar.classList.remove("nav-fade");
            bar.classList.remove("nav-fade-left");
            return;
          }
          if (followCurrent) reveal(bar.querySelector('[aria-current="page"]'));
          paint();
        }
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", place);
        else place();
        root.addEventListener("load", place);
        root.addEventListener("resize", function () {
          if (root.innerWidth === placedWidth) {
            paint();
            return;
          }
          place();
        });
        bar.addEventListener("scroll", function () {
          paint();
        }, { passive: true });
        bar.addEventListener("focusin", function (ev) {
          var el = ev.target;
          if (!el || el.tagName !== "A" || !bar.contains(el)) return;
          try {
            if (el.matches && !el.matches(":focus-visible")) return;
          } catch (e) {
            return;
          }
          reveal(el);
          paint();
        });
      };
      armNav(document.querySelector("nav.main"), true);
      armNav(document.querySelector("nav.toc"), false);
    }
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

  // The same predicate the row filter uses: the search text, then each
  // column select. An empty select value keeps the row. A card is shown
  // only when its row passes.
  function passesFilters(record, query, filters) {
    if (!matchesText(record, query)) return false;
    var list = filters || [];
    for (var i = 0; i < list.length; i++) {
      var item = list[i] || {};
      if (!item.value) continue;
      if (String(item.text == null ? "" : item.text) !== String(item.value)) return false;
    }
    return true;
  }

  // Phone cards set display:block on every tr, which beats the hidden
  // attribute. important wins that fight, so a hidden row stays hidden.
  function paintRow(row, shown) {
    row.hidden = !shown;
    if (row.style) {
      if (shown) row.style.removeProperty("display");
      else row.style.setProperty("display", "none", "important");
    }
    return row;
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
    // Desktop sticks the whole header. On a phone only the top bar sticks and
    // the section nav scrolls away, so the offset follows that bar.
    function stuck() {
      var topbar = header.querySelector(".topbar");
      if (view && view.getComputedStyle) {
        // On a phone the header box is removed so the bar can stick to the
        // page. Measuring the header then returns an empty box.
        if (view.getComputedStyle(header).display === "contents") return topbar || header;
        var headPos = view.getComputedStyle(header).position;
        if (headPos === "sticky" || headPos === "fixed") return header;
        if (topbar) {
          var barPos = view.getComputedStyle(topbar).position;
          if (barPos === "sticky" || barPos === "fixed") return topbar;
        }
      }
      return header;
    }
    function apply() {
      var box = stuck().getBoundingClientRect();
      if (!(box.height > 0)) return;
      root.style.setProperty("--hdr-h", box.height + "px");
    }
    apply();
    if (view && typeof view.ResizeObserver === "function") {
      var watch = new view.ResizeObserver(apply);
      watch.observe(header);
      var topbar = header.querySelector(".topbar");
      if (topbar) watch.observe(topbar);
    } else if (view) {
      view.addEventListener("resize", apply);
    }
    if (view) view.addEventListener("load", apply);
  }

  // A table wider than the viewport used to stretch the page. Only those
  // cards scroll sideways. A table that fits stays overflow:visible so its
  // header can stick to the page. Closed sections have no size yet; the
  // toggle listener measures them when they open.
  function containWideTables(doc) {
    var view = doc.defaultView;
    function measure() {
      var boxes = doc.querySelectorAll(".tbl");
      Array.prototype.forEach.call(boxes, function (box) {
        box.classList.remove("scroll-x");
      });
      var vw = doc.documentElement.clientWidth;
      Array.prototype.forEach.call(boxes, function (box) {
        var table = box.querySelector("table");
        if (!table) return;
        var rect = table.getBoundingClientRect();
        if (!(rect.width > 0)) return;
        var limit = box.clientWidth;
        if ((limit > 0 && rect.width > limit + 1) || rect.right > vw + 1) {
          box.classList.add("scroll-x");
        }
      });
      if (doc.documentElement.scrollWidth > vw + 1) {
        Array.prototype.forEach.call(boxes, function (box) {
          var table = box.querySelector("table");
          if (!table) return;
          var rect = table.getBoundingClientRect();
          if (rect.right > vw + 1 || rect.width > vw - 32) box.classList.add("scroll-x");
        });
      }
    }
    measure();
    if (view) view.addEventListener("resize", measure);
    doc.addEventListener("toggle", function (event) {
      var target = event.target;
      if (target && String(target.tagName).toLowerCase() === "details") measure();
    }, true);
  }

  // Soccer rule cards. A click flips the card; a link on the back is left alone.
  // With script off, the front still shows the verdict and the ROI.
  function wireRuleCards(doc) {
    Array.prototype.forEach.call(doc.querySelectorAll(".rule-card"), function (card) {
      if (card.getAttribute("data-wired") === "1") return;
      card.setAttribute("data-wired", "1");
      function paint(on) {
        card.classList.toggle("is-flipped", on);
        var front = card.querySelector(".rule-front");
        var back = card.querySelector(".rule-back");
        if (front) front.setAttribute("aria-hidden", on ? "true" : "false");
        if (back) back.setAttribute("aria-hidden", on ? "false" : "true");
        Array.prototype.forEach.call(card.querySelectorAll(".rule-flip"), function (btn) {
          var face = btn.closest(".rule-face");
          var shown = !!(face && ((on && face.classList.contains("rule-back"))
            || (!on && face.classList.contains("rule-front"))));
          btn.setAttribute("aria-expanded", on ? "true" : "false");
          btn.tabIndex = shown ? 0 : -1;
        });
      }
      card.addEventListener("click", function (ev) {
        var target = ev.target;
        if (target && target.closest && target.closest("a")) return;
        var kbd = document.activeElement && document.activeElement.classList && document.activeElement.classList.contains("rule-flip");
        paint(!card.classList.contains("is-flipped"));
        if (kbd) { var btn = card.querySelector(card.classList.contains("is-flipped") ? ".rule-back .rule-flip" : ".rule-front .rule-flip"); if (btn) btn.focus(); }
      });
    });
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
        var filters = selects.map(function (item) {
          return { text: cellText(row.cells[item.index]), value: item.select.value };
        });
        var ok = passesFilters(record, query, filters);
        paintRow(row, ok);
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
    passesFilters: passesFilters,
    paintRow: paintRow,
    containWideTables: containWideTables,
    wireRuleCards: wireRuleCards,
  };
});
