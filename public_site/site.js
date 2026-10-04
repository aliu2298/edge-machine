// Phone-view switch, fold open/close, and the row filter.
// The same behaviour the Sandbox page used to inline. No third-party code.
(function () {
  var root = document.documentElement, box = document.getElementById("vw");
  if (!box) return;
  var cardsBtn = box.querySelector('[data-view="cards"]');
  var tableBtn = box.querySelector('[data-view="table"]');
  if (!cardsBtn || !tableBtn) return;
  var phoneCards = function () {
    // 641–760px keeps the card layout. Under 640px the table scrolls sideways
    // until the reader asks for cards.
    return window.matchMedia("(max-width:760px)").matches
      && !window.matchMedia("(max-width:640px)").matches;
  };
  var showing = function () {
    var v = root.getAttribute("data-view");
    return v ? v : (phoneCards() ? "cards" : "table");
  };
  var paint = function () {
    var mode = showing();
    cardsBtn.setAttribute("aria-pressed", mode === "cards" ? "true" : "false");
    tableBtn.setAttribute("aria-pressed", mode === "table" ? "true" : "false");
  };
  function choose(next) {
    root.setAttribute("data-view", next);
    paint();
    try { localStorage.setItem("sandbox-view", next); } catch (e) {}
  }
  try {
    var saved = localStorage.getItem("sandbox-view");
    if (saved === "cards" || saved === "table") root.setAttribute("data-view", saved);
  } catch (e) {}
  paint();
  window.matchMedia("(max-width:760px)").addEventListener("change", paint);
  window.matchMedia("(max-width:640px)").addEventListener("change", paint);
  cardsBtn.addEventListener("click", function () { choose("cards"); });
  tableBtn.addEventListener("click", function () { choose("table"); });
})();

// On a phone the main nav is one sideways row. Bring the current page's pill
// into view, and fade the right edge only while more links sit past it.
(function () {
  var narrow = window.matchMedia("(max-width:640px)");

  function arm(bar, followCurrent) {
    if (!bar) return;
    function overflow() {
      return bar.scrollWidth > bar.clientWidth + 1
        && bar.scrollLeft + bar.clientWidth < bar.scrollWidth - 2;
    }
    function place() {
      if (!narrow.matches) {
        bar.classList.remove("nav-fade");
        return;
      }
      if (followCurrent) {
        var current = bar.querySelector('[aria-current="page"]');
        if (current) {
          var fade = 18;
          var navRect = bar.getBoundingClientRect();
          var aRect = current.getBoundingClientRect();
          var limit = navRect.right - fade;
          if (aRect.left < navRect.left - 0.5) bar.scrollLeft += aRect.left - navRect.left - 4;
          else if (aRect.right > limit + 0.5) bar.scrollLeft += aRect.right - limit;
        }
      }
      bar.classList.toggle("nav-fade", overflow());
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", place);
    else place();
    window.addEventListener("load", place);
    window.addEventListener("resize", place);
    bar.addEventListener("scroll", function () {
      if (narrow.matches) bar.classList.toggle("nav-fade", overflow());
    }, { passive: true });
  }

  if (window.EdgeNav) return;
  window.EdgeNav = true;
  arm(document.querySelector("nav.main"), true);
  arm(document.querySelector("nav.toc"), false);
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
      if (t.classList.contains("sortable")) return;
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
