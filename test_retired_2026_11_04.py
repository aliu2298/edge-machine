#!/usr/bin/env python3
"""Offline checks for the 2026-11-04 retirements (Olu): the team +0.5 unbeaten rule on every scope (its last live one,
Cups, goes now; Clubs and Internationals went 2026-10-14), with the congestion under 2.5 rule and the tennis favourite
band within 3h, which were already retired on every scope. None is in Production. The Sandbox's stamp-of-approval table
tags every source that no longer runs as RETIRED."""
import html
import re
import sys

import production as P
import sandbox_audit
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import soccer_build
import tennis_build

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def fold_of(page):
    i = page.find('<section id="retired"')
    return i, page[i:page.find("</section>", i)]


def whys_in(fold, name):
    return [html.unescape(re.sub(r"<[^>]+>", "", m))
            for m in re.findall(rf'sp-retired-why" data-source="{name}"[^>]*>(.*?)</p>', fold, re.S)]


print("the team +0.5 unbeaten rule: retired on every scope, open rows still settle")
m = S.SOURCES["p05_unbeaten"]
check("off the run, all three scopes retired", (m["sports"], sorted(m["retired_sports"])),
      ([], ["soccer_p05", "soccer_p05_cup", "soccer_p05_intl"]))
check("the Cups line, dated with its record", m["retired_sports"]["soccer_p05_cup"], S.P05_UNBEATEN_CUPS_RETIRED_WHY)
check("the record", "6 won v 5.7 priced, +3.6% after fees" in S.P05_UNBEATEN_CUPS_RETIRED_WHY, True)
check("an open Cups bet still settles (a retired scope is not a removed row)",
      S.removed_row(dict(source="p05_unbeaten", sport="soccer_p05_cup")), False)
check("the Cups +0.5 scope is still fetched for its blind baseline", "soccer_p05_cup" in S.SOURCES["goals_market"]["sports"], True)

print("\nalready retired on every scope, unchanged")
for name, scopes in (("o25_congestion", ["soccer_o25", "soccer_o25_cup", "soccer_o25_intl"]), ("tennis_fav_band_3h", ["tennis"])):
    check(f"{name}: off the run", (S.SOURCES[name]["sports"], sorted(S.SOURCES[name]["retired_sports"])), ([], scopes))
check("the tennis basket lanes built from its legs were retired too, so none is left running",
      [n for n in ("tennis_combo2", "tennis_combo3", "tennis_combo4", "pm_combo2", "pm_combo3", "pm_combo4")
       if S.SOURCES[n]["sports"]], [])

print("\neach in its page's Retired fold, not above it")
sh = soccer_build.build()
i, sfold = fold_of(sh)
check("Soccer: the unbeaten rule's three lines", sorted(w[:21] for w in whys_in(sfold, "p05_unbeaten")),
      ["Retired 2026-10-14 by", "Retired 2026-10-14 by", "Retired 2026-11-04 by"])
check("Soccer: the Cups line in full", S.P05_UNBEATEN_CUPS_RETIRED_WHY in whys_in(sfold, "p05_unbeaten"), True)
check("Soccer: congestion's three lines", len(whys_in(sfold, "o25_congestion")), 3)
check("Soccer: neither above the fold", [n for n in ("p05_unbeaten", "o25_congestion") if f'data-source="{n}"' in sh[:i]], [])
th = tennis_build.build()
j, tfold = fold_of(th)
check("Tennis: the favourite band within 3h in the fold, not above it",
      (len(whys_in(tfold, "tennis_fav_band_3h")), 'data-source="tennis_fav_band_3h"' in th[:j]), (1, False))

print("\nthe stamp-of-approval table tags every source that no longer runs")
check("source_retired", (B.source_retired("p05_unbeaten"), B.source_retired("o25_congestion"),
                         B.source_retired("tennis_fav_band_3h"), B.source_retired("mls_away_band_fade"),
                         B.source_retired("crypto_fav_band"), B.source_retired("crypto_fav_band_below"),
                         B.source_retired("team2_form_l10")),
      (True, True, True, True, True, False, False))
page = B.build()
k = page.find("Stamp of approval")
table = page[k:page.find("</table>", k)]
rows = {html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<span[^>]*data-retired[^>]*>.*?</span>", "", r))).strip(): "data-retired" in r
        for r in re.findall(r"<tr><td><b>(.*?)</td>", table)}
for name in ("p05_unbeaten", "o25_congestion", "tennis_fav_band_3h", "mls_away_band_fade", "crypto_fav_band", "crypto_fav_band_60"):
    check(f"{name}: tagged RETIRED", rows.get(S.SOURCES[name]["label"]), True)
check("a live lane is not tagged", rows.get(S.SOURCES["crypto_fav_band_below"]["label"]), False)
check("every tagged row is a source that runs nothing",
      sorted(n for n, v in rows.items() if v) == sorted(S.SOURCES[s]["label"] for s in S.SOURCES
                                                         if S.SOURCES[s]["label"] in rows and B.source_retired(s)), True)

print("\nnone is in Production")
st = T.load_stages()
check("no Production pair for any of them",
      sorted(p for p in P.production_pairs(st) if p.split("|")[0] in ("p05_unbeaten", "o25_congestion", "tennis_fav_band_3h")), [])

check("no guarded phrase in the new copy", sandbox_audit.COPY_RE.search(S.P05_UNBEATEN_CUPS_RETIRED_WHY + sfold + tfold + table), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
