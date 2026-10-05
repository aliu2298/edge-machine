// Sport pills and Running filters record which control is pressed.
// They do not load contests, hide rows, or leave the page. The list is a later slice.
(function () {
  function arm(root) {
    if (!root) return;
    var buttons = root.querySelectorAll("button");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        Array.prototype.forEach.call(buttons, function (other) {
          other.setAttribute("aria-pressed", other === btn ? "true" : "false");
        });
      });
    });
  }
  arm(document.querySelector("nav.sports"));
  arm(document.querySelector(".running-filters"));
})();
