// Running filters show one bucket of the rows already on the page. They do not
// fetch bets or leave the page. Sport pills stay aria-disabled chrome; this
// file does not arm them. A chip can still clear a sport filter that is
// hiding its contest, then press that contest's row. Rows and chips are
// plain buttons: each is its own tab stop, and Enter, Space, or a click
// presses one. The pressed row's card payload was embedded at build time.
// This file only reads attributes and writes text.
(function () {
  var SAFE_PAGE = /^\.\/(?:soccer|tennis|cricket|nba|crypto|production)\.html$/;

  function rows() {
    return document.querySelectorAll(".running-row");
  }

  function fullPage() {
    return document.querySelector("a.full-page");
  }

  function clearCards() {
    var section = document.getElementById("rules-section");
    var host = document.getElementById("rules-cards");
    if (section) {
      section.textContent = "";
      section.hidden = true;
    }
    if (host) {
      while (host.firstChild) host.removeChild(host.firstChild);
      host.hidden = true;
    }
    var link = fullPage();
    if (link) link.setAttribute("href", "./production.html");
  }

  function announce(text) {
    var live = document.getElementById("rules-live");
    if (live) live.textContent = text || "";
  }

  function chips() {
    return document.querySelectorAll(".bet-chip");
  }

  function syncChips() {
    var selected = document.querySelector('.running-row[aria-pressed="true"]');
    var id = selected ? selected.getAttribute("data-contest") : "";
    Array.prototype.forEach.call(chips(), function (chip) {
      var on = !!id && chip.getAttribute("data-contest") === id;
      chip.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function clearSelection() {
    Array.prototype.forEach.call(rows(), function (row) {
      row.setAttribute("aria-pressed", "false");
      row.removeAttribute("aria-selected");
      row.removeAttribute("aria-current");
    });
    var head = document.getElementById("rules-head");
    var line = document.getElementById("rules-line");
    var empty = document.getElementById("rules-empty");
    if (line) line.textContent = "";
    if (head) head.hidden = true;
    if (empty) empty.hidden = false;
    clearCards();
    syncChips();
    announce("Select a contest in Running.");
  }

  function readCards(row) {
    var raw = row.getAttribute("data-cards") || "[]";
    try {
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function addLine(parent, className, text) {
    if (!text) return;
    var node = document.createElement("p");
    node.className = className;
    node.textContent = text;
    parent.appendChild(node);
  }

  function addStatus(parent, card) {
    var status = document.createElement("p");
    status.className = "running-status";
    var token = card.status === "Awaiting result" ? "awaiting" : card.status;
    if (token) status.setAttribute("data-status", token);
    var visual = document.createElement("span");
    visual.setAttribute("aria-hidden", "true");
    visual.textContent = card.status || "";
    var spoken = document.createElement("span");
    spoken.className = "sr-only";
    spoken.textContent = card.spoken || "";
    status.appendChild(visual);
    status.appendChild(spoken);
    parent.appendChild(status);
  }

  function renderCards(row) {
    var section = document.getElementById("rules-section");
    var host = document.getElementById("rules-cards");
    clearCards();
    var cards = readCards(row);
    var n = cards.length;
    var noun = n === 1 ? "lane fired" : "lanes fired";
    if (section) {
      section.textContent = "Rules applied · " + n + " " + noun;
      section.hidden = false;
    }
    if (!host) return;
    cards.forEach(function (card) {
      if (!card || typeof card !== "object") return;
      var article = document.createElement("article");
      article.className = "rule-mini";
      var title = document.createElement("p");
      title.className = "rule-mini-name";
      var name = document.createElement("span");
      name.textContent = card.lane || "—";
      title.appendChild(name);
      if (card.pill) {
        var pill = document.createElement("span");
        pill.className = card.pill === "Sandbox" ? "lane-pill sandbox" : "lane-pill";
        pill.textContent = card.pill;
        title.appendChild(pill);
      }
      article.appendChild(title);
      addLine(article, "rule-mini-market", card.market || "");
      if (card.venue || card.price) {
        var meta = document.createElement("p");
        meta.className = "rule-mini-meta";
        if (card.venue) {
          var badge = document.createElement("span");
          badge.className = "venue-badge";
          badge.textContent = card.venue;
          meta.appendChild(badge);
        }
        if (card.price) {
          var price = document.createElement("span");
          price.className = "rule-mini-price";
          price.textContent = card.price;
          meta.appendChild(price);
        }
        article.appendChild(meta);
      }
      addStatus(article, card);
      if (card.edge) addLine(article, "rule-mini-edge", card.edge + " edge");
      if (card.verdict) addLine(article, "rule-mini-verdict", card.verdict);
      if (card.roi) addLine(article, "rule-mini-roi", card.roi + " Sandbox ROI after fees");
      if (card.record) addLine(article, "rule-mini-record", card.record + " Sandbox record");
      if (card.stats_note) addLine(article, "rule-mini-scope", card.stats_note);
      host.appendChild(article);
    });
    host.hidden = n === 0;
    if (window.matchMedia("(max-width: 640px)").matches && section && section.scrollIntoView) {
      section.scrollIntoView({ block: "start" });
    }
    var link = fullPage();
    if (link) {
      var page = row.getAttribute("data-page") || "./production.html";
      if (!SAFE_PAGE.test(page)) page = "./production.html";
      link.setAttribute("href", page);
    }
  }

  function sportsNav() {
    return document.querySelector("nav.sports");
  }

  function sportFilter() {
    var nav = sportsNav();
    var name = nav && nav.getAttribute("data-sport-filter");
    return name || "all";
  }

  function sportLabel(key) {
    if (!key || key === "all") return "";
    var button = document.querySelector('nav.sports button[data-sport="' + key + '"]');
    return button ? (button.textContent || "").replace(/\s+/g, " ").trim().toLowerCase() : String(key).toLowerCase();
  }

  function sportAllows(row) {
    var key = sportFilter();
    if (key === "all") return true;
    return (row.getAttribute("data-sport") || "").replace(/\s+/g, " ").trim().toLowerCase() === sportLabel(key);
  }

  function sportKeyFor(row) {
    var label = (row.getAttribute("data-sport") || "").replace(/\s+/g, " ").trim().toLowerCase();
    var buttons = document.querySelectorAll("nav.sports button[data-sport]");
    for (var i = 0; i < buttons.length; i++) {
      var text = (buttons[i].textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      if (text === label) return buttons[i].getAttribute("data-sport") || "all";
    }
    return "all";
  }

  function currentBucket() {
    var bar = document.querySelector(".running-filters");
    var pressed = bar && bar.querySelector("button[aria-pressed='true']");
    return pressed ? pressed.getAttribute("data-filter") : "live";
  }

  function setSportFilter(name) {
    var nav = sportsNav();
    if (nav) nav.setAttribute("data-sport-filter", name || "all");
    apply(currentBucket());
  }

  function apply(name) {
    var n = 0;
    Array.prototype.forEach.call(rows(), function (row) {
      var show = row.getAttribute("data-filter") === name && sportAllows(row);
      row.hidden = !show;
      if (show) n += 1;
    });
    Array.prototype.forEach.call(document.querySelectorAll(".running-group"), function (group) {
      group.hidden = !group.querySelector(".running-row:not([hidden])");
    });
    var empty = document.getElementById("running-empty");
    if (empty) {
      empty.hidden = n !== 0;
      empty.textContent = empty.getAttribute("data-" + name) || "";
    }
    var bar = document.querySelector(".running-filters");
    if (bar) {
      Array.prototype.forEach.call(bar.querySelectorAll("button"), function (btn) {
        btn.setAttribute("aria-pressed", btn.getAttribute("data-filter") === name ? "true" : "false");
      });
    }
    var caption = document.getElementById("settled-caption");
    if (caption) caption.hidden = name !== "settled";
    var selected = document.querySelector('.running-row[aria-pressed="true"]');
    if (selected && selected.hidden) clearSelection();
  }

  function select(row, force) {
    if (!force && row.getAttribute("aria-pressed") === "true") {
      clearSelection();
      return;
    }
    Array.prototype.forEach.call(rows(), function (other) {
      other.setAttribute("aria-pressed", other === row ? "true" : "false");
      other.removeAttribute("aria-selected");
      other.removeAttribute("aria-current");
    });
    var head = document.getElementById("rules-head");
    var line = document.getElementById("rules-line");
    var empty = document.getElementById("rules-empty");
    if (!head || !line) {
      syncChips();
      return;
    }
    var text = ["data-competition", "data-sport", "data-name", "data-kickoff", "data-price"]
      .map(function (attr) { return row.getAttribute(attr) || "—"; })
      .join(" · ");
    line.textContent = text;
    announce(text);
    head.hidden = false;
    if (empty) empty.hidden = true;
    renderCards(row);
    syncChips();
  }

  function rowForChip(chip) {
    var id = chip.getAttribute("data-contest");
    var found = null;
    Array.prototype.forEach.call(rows(), function (row) {
      if (row.getAttribute("data-contest") === id) found = row;
    });
    return found;
  }

  function openFromChip(chip) {
    if (chip.getAttribute("aria-pressed") === "true") {
      clearSelection();
      return;
    }
    var row = rowForChip(chip);
    if (!row) return;
    if (!sportAllows(row)) setSportFilter(sportKeyFor(row));
    if (row.hidden) apply(row.getAttribute("data-filter"));
    select(row, true);
  }

  var bar = document.querySelector(".running-filters");
  if (bar) {
    Array.prototype.forEach.call(bar.querySelectorAll("button"), function (btn) {
      btn.addEventListener("click", function () {
        apply(btn.getAttribute("data-filter"));
      });
    });
    var pressed = bar.querySelector('[aria-pressed="true"]');
    apply(pressed ? pressed.getAttribute("data-filter") : "live");
  }

  function bindPress(el, press) {
    el.addEventListener("click", function () {
      press();
    });
    el.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        if (el.getAttribute("aria-pressed") === "true") clearSelection();
        return;
      }
      if (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") return;
      event.preventDefault();
      press();
    });
  }

  Array.prototype.forEach.call(rows(), function (row) {
    bindPress(row, function () { select(row); });
  });
  Array.prototype.forEach.call(chips(), function (chip) {
    bindPress(chip, function () { openFromChip(chip); });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var selected = document.querySelector('.running-row[aria-pressed="true"]');
    if (selected) clearSelection();
  });
})();
