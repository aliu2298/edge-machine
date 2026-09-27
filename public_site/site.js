// Phone-view switch, fold open/close, and the row filter.
// The same behaviour the Sandbox page used to inline. No third-party code.
(function () {
  var root = document.documentElement, btn = document.getElementById("vw");
  if (!btn) return;
  var narrow = function () { return window.matchMedia("(max-width:760px)").matches; };
  var showing = function () {
    var v = root.getAttribute("data-view");
    return v ? v : (narrow() ? "cards" : "table");
  };
  var paint = function () { btn.textContent = showing() === "cards" ? "Full table" : "Phone view"; };
  try {
    var saved = localStorage.getItem("sandbox-view");
    if (saved === "cards" || saved === "table") root.setAttribute("data-view", saved);
  } catch (e) {}
  paint();
  window.matchMedia("(max-width:760px)").addEventListener("change", paint);
  btn.addEventListener("click", function () {
    var next = showing() === "cards" ? "table" : "cards";
    root.setAttribute("data-view", next);
    paint();
    try { localStorage.setItem("sandbox-view", next); } catch (e) {}
  });
})();

document.querySelectorAll(".folds-ctl button").forEach(function (b) {
  b.addEventListener("click", function () {
    document.querySelectorAll("details." + b.dataset.fold).forEach(function (dt) {
      dt.open = b.dataset.open === "1";
    });
  });
});

document.querySelectorAll("input.flt").forEach(function (inp) {
  inp.addEventListener("input", function () {
    var box = document.getElementById(inp.dataset.for), q = inp.value.trim().toLowerCase();
    box.querySelectorAll("details").forEach(function (dt) { if (q) dt.open = true; });
    box.querySelectorAll("table").forEach(function (t) {
      var grp = null, any = false;
      t.querySelectorAll("tr").forEach(function (tr) {
        if (tr.querySelector("th")) return;
        if (tr.classList.contains("grp")) {
          if (grp) grp.hidden = !any;
          grp = tr;
          any = false;
          return;
        }
        var hit = !q || tr.textContent.toLowerCase().includes(q);
        tr.hidden = !hit;
        any = any || hit;
      });
      if (grp) grp.hidden = !any;
      var fold = t.closest("details.grp-fold");
      if (fold) fold.hidden = q && !t.querySelector("tr:not([hidden]) td");
    });
  });
});
