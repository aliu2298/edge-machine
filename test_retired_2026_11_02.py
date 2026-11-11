#!/usr/bin/env python3
"""Offline checks for the 2026-11-02 decisions (Olu): ESPN FPI retired (its NFL scope, the only one it still ran: MLB is
a removed lane since 2026-10-04), the NFL team total OVER 35-45c lane kept to a decision at 50 settled, and the UTR daily
shortlist retired. None is in Production; nothing in Production moves. The Challenger hold lane registered the same day
is checked in test_challenger_form.py."""
import inspect
import re
import sys

import nfl_build
import nfl_tt as N
import nfl_tt_build as NB
import production as P
import sandbox_audit
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("ESPN FPI: the NFL scope retired, dated, with its record")
src = S.SOURCES["espn_fpi"]
WHY = ("Retired 2026-11-02 by Olu: no edge at 35 settled — 14 won v 17.8 priced, −26.4% after fees. No new entries "
       "from 2026-11-02; its rows stay on file and its open bets still settle.")
check("NFL moved from sports to retired_sports with the dated reason", ("nfl" in src["sports"], src["retired_sports"]), (False, {"nfl": WHY}))
check("its other scope, MLB, is a removed lane, so the source fetches nothing new on any sport",
      [sp for sp in src["sports"] if not S.lane_removed("espn_fpi", sp)], [])
check("the run only fetches a source's `sports` (both fetch loops read that list)",
      inspect.getsource(T).count('if sport not in S.SOURCES[name]["sports"]:') >= 2, True)

print("\nits open bets still settle; the record is kept")
row = dict(source="espn_fpi", sport="nfl", status="open")
check("a retired-scope row is not a removed row, so grade() still settles it", S.removed_row(row), False)
check("grade() skips only removed rows (not retired scopes)", "if S.removed_row(q) and not _removed_due(q, now):" in inspect.getsource(T.grade), True)
check("its settled rows leave the live feed for the archive like any retired rule's", B.off_record(row, {}), True)

print("\nnot in Production, and no Production feed reads it")
check("out of Production since 2026-10-27 (a removal, whole record kept), never re-listed",
      (T.PAIR_REMOVALS.get("espn_fpi|nfl"), "espn_fpi|nfl" in T.PAIR_OVERRIDES), (dict(removed_on="2026-10-27", keep_record=True), False))
st = T.load_stages()
check("the stage file does not hold it in Production, so production.py publishes no lead for it",
      sorted(k for k in P.production_pairs(st) if k.startswith("espn_fpi|")), [])

print("\nthe NFL page: in the Retired fold, out of the live rules")
html = nfl_build.build()
i = html.find('<section id="retired"')
fold = html[i:html.find("</section>", i)]
check("one Retired fold holding ESPN FPI and the retired team-total main line",
      (html.count('<section id="retired"'), 'data-source="espn_fpi"' in fold, 'data-source="nfl_tt_over_main"' in fold), (1, True, True))
m = re.search(r'sp-retired-why" data-source="espn_fpi"[^>]*>(.*?)</p>', fold, re.S)
check("its line carries the dated record", re.sub(r"<[^>]+>", "", m.group(1)) if m else None, WHY)
check("no ESPN FPI row in the live rules above the fold", 'data-source="espn_fpi"' in html[:i], False)

print("\nNFL team total OVER 35-45c: kept to 50 settled")
check("read at 50, with the note", (N.READ_AT, N.KEPT[N.LANE_BAND]),
      ({"nfl_tt_over_3545": 50}, "Kept to 50 by Olu 2026-11-02 (36 settled, +2.1% v blind baseline +1.4%)."))
check("kept to 50 then retired 2026-11-11 (END NFL); the main line stays retired from 2026-10-31",
      (N.RETIRED[N.LANE_BAND]["on"], N.RETIRED[N.LANE_MAIN]["on"]), ("2026-11-11", "2026-10-31"))
# The floor logic below is checked with the 2026-11-11 retirement lifted (the lane was live while it collected to 50).
_band_retired = N.RETIRED.pop(N.LANE_BAND)


def picks(n_won, n_lost, price=0.40):
    base = dict(price=price, start="2026-10-26T17:00:00+00:00", game="A at B", team="A", line="20.5")
    out = [dict(base, status="won", profit=100 * (1 - price) / price - 2, week=f"w{i % 6}") for i in range(n_won)]
    return out + [dict(base, status="lost", profit=-100.0, week=f"w{i % 6}") for i in range(n_lost)]


def state_of(ps):
    return {"rules": {N.LANE_BAND: {"picks": ps}, N.LANE_MAIN: {"picks": []}, N.BASE: {"picks": []}}}


for won, lost, want in ((16, 20, "promising"), (12, 30, "behind"), (25, 25, "working")):
    r = NB.row_data(N.LANE_BAND, state_of(picks(won, lost)))
    check(f"{won + lost} settled ({won} won at 40c): verdict {want}", r["v"], want)
r36 = NB.row_data(N.LANE_BAND, state_of(picks(16, 20)))
check("below 50 the chip counts to 50 ('Collecting 36/50 · Promising'), where a 30-floor lane would read Working",
      re.sub(r"<[^>]+>", "", NB.SP.verdict_badge(r36, NB.floor(N.LANE_BAND))), "Collecting 36/50 · Promising")
row = NB.row_html(N.LANE_BAND, state_of(picks(16, 20)))
check("its row: evidence out of 50 and the kept note in its details",
      (re.findall(r'data-l="Evidence">([^<]+)', row), "Kept to 50 by Olu 2026-11-02" in row), (["36/50"], True))
check("any other lane keeps the page's floor", NB.floor(N.LANE_MAIN), NB.SP.EVIDENCE_FLOOR)
N.RETIRED[N.LANE_BAND] = _band_retired

print("\nthe UTR daily shortlist: retired (its only scope), its open bets still settle")
utr = S.SOURCES["tennis_utr_shortlist_v1"]
UTR_WHY = ("Retired 2026-11-02 by Olu: at the price — 20 won v 19.4 priced, +10 no result, −7.8% after fees on 37; the shortlist did "
           "no better than the whole eligible pool (−7.5%). No new entries from 2026-11-02; its rows stay on file and its open "
           "bets still settle.")
check("tennis moved from sports to retired_sports with the dated reason", (utr["sports"], utr["retired_sports"]), ([], {"tennis": UTR_WHY}))
check("its own selection path checks the source's live sports, so it selects and logs nothing new",
      'and sport in S.SOURCES["tennis_utr_shortlist_v1"]["sports"]' in inspect.getsource(T), True)
check("a retired-scope row still settles", S.removed_row(dict(source="tennis_utr_shortlist_v1", sport="tennis")), False)
check("out of Production since 2026-10-27, not re-listed",
      (T.PAIR_REMOVALS.get("tennis_utr_shortlist_v1|tennis", {}).get("removed_on"), "tennis_utr_shortlist_v1|tennis" in T.PAIR_OVERRIDES),
      ("2026-10-27", False))
import tennis_build
th = tennis_build.build()
ti = th.find('<section id="retired"')
tfold = th[ti:th.find("</section>", ti)]
m = re.search(r'sp-retired-why" data-source="tennis_utr_shortlist_v1"[^>]*>(.*?)</p>', tfold, re.S)
check("the Tennis page lists it in Retired rules with the dated record, and not in the live rules",
      (re.sub(r"<[^>]+>", "", m.group(1)) if m else None, 'data-source="tennis_utr_shortlist_v1"' in th[:ti]), (UTR_WHY, False))

check("no guarded phrase in the new copy", sandbox_audit.COPY_RE.search(WHY + UTR_WHY + N.KEPT[N.LANE_BAND] + fold + row + tfold), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
