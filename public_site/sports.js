/* Disclosure navigation for the static sport pages. Same-origin, no inline code. */
(function () {
  "use strict";
  var current = document.querySelector("nav.sports [aria-current='page']");
  if (current) current.scrollIntoView({block: "nearest", inline: "center"});
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
  reveal();
  window.addEventListener("hashchange", reveal);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      var menu = document.querySelector(".page-menu[open]");
      if (menu) { menu.open = false; menu.querySelector("summary").focus(); }
    }
  });
})();
