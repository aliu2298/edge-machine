#!/usr/bin/env python3
"""Offline checks (2026-11-05, Olu: "if nothing is running, archive it"): a sport tab with no active lane leaves the nav.

Active = not retired, not a baseline, with a bet or an open pick in its current record window. Checked at build time
(tab_activity.py writes data/tab_activity.json; site_chrome.nav reads it). A tab whose check fails stays. Nothing is
retired by the rule, and the tab returns on the first pick.
"""
import json
import os
import re
import sys
import tempfile

import site_chrome as C
import tab_activity as A

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the row rule")
row = lambda **kw: dict(dict(v="promising", meta={}, a={"n": 0, "n_price": 0}, open=0), **kw)   # noqa: E731
check("a settled bet makes a lane active", A._row_active(row(a={"n": 3})), True)
check("an open pick makes it active", A._row_active(row(open=1)), True)
check("a registered lane with nothing on its current record is not", A._row_active(row()), False)
check("retired is not, whatever its record", A._row_active(row(v="retired", a={"n": 40})), False)
check("a baseline is not, whatever its record", A._row_active(row(meta={"kind": "Baseline"}, a={"n": 40})), False)

print("\nthe check")
real = A.check()
check("every sport tab is checked", sorted(real), sorted(A.TABS))
check("Cricket is archived: Polymarket (international) has no bet on its current record, the rest is retired",
      (real["cricket"]["archived"], real["cricket"]["active"]), (True, []))
check("Cricket's Polymarket row is NOT retired by the rule (its scope keeps logging)",
      "cricket" in __import__("sandbox_sources").SOURCES["polymarket"]["sports"], True)
check("Fights is archived: a baseline and a retired lane", (real["fights"]["archived"], real["fights"]["active"]), (True, []))
check("NFL stays: the team total over; the college football home underdog is retired (2026-11-11)",
      (real["nfl"]["archived"], "nfl_tt_over_3545" in real["nfl"]["active"], "cfb_home_dog_x4" in real["nfl"]["active"]), (False, True, False))
for tab in ("nba", "soccer", "tennis", "crypto", "commodities", "econ_daily", "finance_daily", "culture"):
    check(f"{tab} stays: it has an active lane", real[tab]["archived"], False)
saved = A.ADAPTERS["soccer"]
A.ADAPTERS["soccer"] = lambda d, st, now: 1 / 0
try:
    boom = A.check()["soccer"]
finally:
    A.ADAPTERS["soccer"] = saved
check("a tab whose check raises stays in the nav, with the error kept", (boom["archived"], bool(boom["error"])), (False, True))
prev = {"tabs": {"cricket": {"archived": True, "since": "2026-11-01"}}}
check("the first date a tab was archived is kept", A.check(previous=prev)["cricket"]["since"], "2026-11-01")

print("\nthe nav")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "t.json")
    json.dump({"tabs": {"cricket": {"archived": True}, "fights": {"archived": True}, "nba": {"archived": False}}}, open(path, "w"))
    check("archived() reads the file", A.archived(path), {"cricket", "fights"})
    check("no file: nothing archived, every tab shows", A.archived(os.path.join(tmp, "none.json")), set())
saved_arch = C._ARCHIVED
try:
    C._ARCHIVED = frozenset({"cricket", "fights"})
    links = lambda key: re.findall(r"<a [^>]*>([^<]+)</a>", C.nav(key))   # noqa: E731
    check("an archived tab leaves the top nav", ("Cricket" in links("soccer"), "Fights" in links("soccer")), (False, False))
    check("the other market tabs stay in the menu", all(x in links("soccer") for x in ("NBA", "NFL", "Soccer", "Tennis", "Daily Markets", "Culture")), True)
    check("its own page (still built, linked from Archives) keeps its link, current",
          bool(re.search(r'href="\./cricket\.html" aria-current="page">Cricket<', C.nav("cricket"))), True)
    C._ARCHIVED = frozenset()
    check("it comes back as soon as the check finds an active lane", "Cricket" in links("soccer"), True)
finally:
    C._ARCHIVED = saved_arch

print("\nthe Archives entry")
blob = {"tabs": {k: v for k, v in real.items()}}
h = A.archive_html(blob)
check("one entry per archived tab, under #archived-tabs", (h.startswith('<section id="archived-tabs">'),
      [x for x in re.findall(r'id="archived-([a-z_]+)"', h) if x != "tabs"]), (True, sorted(k for k, v in real.items() if v["archived"])))
c = h[h.find('id="archived-cricket"'):h.find("</details>", h.find('id="archived-cricket"'))]
check("Cricket's entry: its one line why, its retired lanes and the registered row, with records",
      ("Archived 2026-11-05" in c, "Oddspedia" in c, "Cricket consensus" in c, "no pick on its current record" in c,
       './cricket.html' in c), (True, True, True, True, True))
f = h[h.find('id="archived-fights"'):]
check("Fights' entry keeps the baseline and the retired UFC record", ("Boxing" in f and "baseline" in f, "UFC" in f and "retired" in f), (True, True))
check("no archived tab but NHL (taken out by hand): only its section", ('id="archived-nhl"' in A.archive_html({"tabs": {"nba": {"archived": False}}}),
      'id="archived-nba"' in A.archive_html({"tabs": {"nba": {"archived": False}}})), (True, False))
print("\nthe NHL tab, taken out by hand (2026-11-11, Olu: END NHL for now)")
saved = {k: A.ADAPTERS[k] for k in ("nhl",)}
A.ADAPTERS["nhl"] = lambda d, st, now: ["a lane"]           # even an adapter that says active
try:
    out = A.check()
    A.ADAPTERS["nhl"] = lambda d, st, now: 1 / 0             # or one that raises
    out2 = A.check()
finally:
    A.ADAPTERS.update(saved)
check("NHL is archived whatever its adapter says, dated from its retirement",
      (out["nhl"]["archived"], out["nhl"]["active"], out["nhl"]["since"], out2["nhl"]["archived"], out2["nhl"]["error"]),
      (True, [], "2026-11-11", True, None))
check("no tab is pinned any more", A.PINNED, {})
hn = A.archive_html({"tabs": {"nhl": {"archived": True, "since": "2026-11-11"}}})
check("its Archives entry keeps both retired lanes' final records, their baselines and the reason",
      all(x in hn for x in ('id="archived-nhl"', "6–1 (7 bets)", "−9.3%", "0–1 (1 bet)", "No edge in two full NHL studies",
                            "baseline", './nhl.html', "taken out of the top nav by hand")), True)
import site_chrome
site_chrome._ARCHIVED = None
check("NHL leaves the nav on every other page from the first build, but its own page still names it",
      ("nhl" in [k for k, _l, _h in site_chrome.shown_pages("nba")], "nhl" in [k for k, _l, _h in site_chrome.shown_pages("nhl")]),
      (False, True))
import sandbox_audit
check("no guarded phrase in the entries", (sandbox_audit.COPY_RE.search(h), sandbox_audit.COPY_RE.search(hn)), (None, None))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
