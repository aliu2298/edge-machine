// Phone-view switch, fold open/close, and the row filter.
// The same behaviour the Sandbox page used to inline. No third-party code.
(function () {
  var root = document.documentElement, box = document.getElementById("vw");
  if (!box) return;
  var cardsBtn = box.querySelector('[data-view="cards"]');
  var tableBtn = box.querySelector('[data-view="table"]');
  if (!cardsBtn || !tableBtn) return;
  var phoneCards = function () {
    // Under 760px the card layout is the default. A phone-width table was
    // 1131px wide in a 390px viewport with no scroll affordance; the reader
    // can still ask for the table with the toggle, and it then scrolls.
    return window.matchMedia("(max-width:760px)").matches;
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
  cardsBtn.addEventListener("click", function () { choose("cards"); });
  tableBtn.addEventListener("click", function () { choose("table"); });
})();

// On a phone the main nav is one sideways row. Bring the current page's pill
// into view, and fade an edge while more links sit past it. The fade width is
// --nav-fade, the same length the mask uses.
(function () {
  var narrow = window.matchMedia("(max-width:640px)");

  function fadeWidth() {
    var raw = getComputedStyle(document.documentElement).getPropertyValue("--nav-fade");
    var n = parseFloat(raw);
    return n > 0 ? n : 22;
  }

  function arm(bar, followCurrent) {
    if (!bar) return;
    function pastRight() {
      return bar.scrollWidth > bar.clientWidth + 1
        && bar.scrollLeft + bar.clientWidth < bar.scrollWidth - 2;
    }
    function pastLeft() {
      return bar.scrollLeft > 2;
    }
    function paint() {
      bar.classList.toggle("nav-fade", (narrow.matches || overflowing()) && pastRight());
      bar.classList.toggle("nav-fade-left", (narrow.matches || overflowing()) && pastLeft());
    }
    // The outset ring (3px outline + 2px offset) hangs past a chip. Main-nav
    // pills inset theirs, so this is 0 there.
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
    // Chrome does not scroll a partly visible link on keyboard focus. Pull it
    // clear of both fades and its own ring. Instant, so reduced motion is not animated.
    // The row also scrolls above the phone width once ten pills outgrow the
    // bar, so the current pill is pulled into view whenever the row overflows.
    function overflowing() {
      return bar.scrollWidth > bar.clientWidth + 1;
    }
    function reveal(el) {
      if (!el || !(narrow.matches || overflowing())) return;
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
      placedWidth = window.innerWidth;
      if (!narrow.matches && !overflowing()) {
        bar.classList.remove("nav-fade");
        bar.classList.remove("nav-fade-left");
        return;
      }
      if (followCurrent) reveal(bar.querySelector('[aria-current="page"]'));
      paint();
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", place);
    else place();
    window.addEventListener("load", place);
    // The mobile URL bar changes height only. Re-place when the width changes.
    window.addEventListener("resize", function () {
      if (window.innerWidth === placedWidth) {
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
      // Pointerdown focuses the link before the click. Scrolling then moves
      // the pill out from under the finger. Only a keyboard focus shows
      // :focus-visible. Without that selector, leave the row where it is.
      try {
        if (el.matches && !el.matches(":focus-visible")) return;
      } catch (e) {
        return;
      }
      reveal(el);
      paint();
    });
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
