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
})();
