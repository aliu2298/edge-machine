/* Disclosure navigation for the static sport pages. Same-origin, no inline code. */
(function () {
  "use strict";
  function reveal() {
    var id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
    var target = document.getElementById(id);
    if (!target) return;
    for (var node = target; node; node = node.parentElement) {
      if (node.tagName === "DETAILS") node.open = true;
    }
    var section = target.querySelector(":scope > details");
    if (section) section.open = true;
    target.scrollIntoView({block: "start"});
  }
  // tables.js does the same on every page. Kept for a page that loads only this file.
  if (!(window.EdgeTables && window.EdgeTables.revealHash)) {
    reveal();
    window.addEventListener("hashchange", reveal);
  }

  // NBA board: the chevron on a game row shows or hides the detail row
  // under it. The detail row is on the page already; this only flips its
  // hidden attribute and the button's aria-expanded.
  Array.prototype.forEach.call(document.querySelectorAll("button.nba-more"), function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.getAttribute("aria-controls");
      var row = id ? document.getElementById(id) : null;
      if (!row) return;
      var open = row.hidden;
      row.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      var host = btn.closest("tr");
      if (host) host.classList.toggle("is-open", open);
    });
  });
})();
