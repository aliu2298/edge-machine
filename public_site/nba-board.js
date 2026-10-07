/* Full NBA analysis on desktop; native summary disclosures on mobile. */
(function () {
  "use strict";
  var wide = window.matchMedia("(min-width: 801px)");
  function layout() {
    document.querySelectorAll("details.nba-game").forEach(function (game) {
      game.open = wide.matches;
    });
  }
  layout();
  wide.addEventListener("change", layout);
})();
