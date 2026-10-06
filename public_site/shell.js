// Running filters show one bucket of the rows already on the page. They do not
// fetch bets or leave the page. Sport pills are aria-disabled chrome; this
// file does not arm them. Rows are plain buttons: each is its own tab stop,
// and Enter, Space, or a click presses one.
(function () {
  function rows() {
    return document.querySelectorAll(".running-row");
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
  }

  function apply(name) {
    var n = 0;
    Array.prototype.forEach.call(rows(), function (row) {
      var show = row.getAttribute("data-filter") === name;
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
    var selected = document.querySelector('.running-row[aria-pressed="true"]');
    if (selected && selected.hidden) clearSelection();
  }

  function select(row) {
    Array.prototype.forEach.call(rows(), function (other) {
      other.setAttribute("aria-pressed", other === row ? "true" : "false");
      other.removeAttribute("aria-selected");
      other.removeAttribute("aria-current");
    });
    var head = document.getElementById("rules-head");
    var line = document.getElementById("rules-line");
    var empty = document.getElementById("rules-empty");
    if (!head || !line) return;
    line.textContent = ["data-competition", "data-sport", "data-name", "data-kickoff", "data-price"]
      .map(function (attr) { return row.getAttribute(attr) || "—"; })
      .join(" · ");
    head.hidden = false;
    if (empty) empty.hidden = true;
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

  Array.prototype.forEach.call(rows(), function (row) {
    row.addEventListener("click", function () {
      select(row);
    });
    row.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") return;
      event.preventDefault();
      select(row);
    });
  });
})();
