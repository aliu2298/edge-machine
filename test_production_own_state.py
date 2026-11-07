#!/usr/bin/env python3
"""Production pairs run from the follower's own state files (2026-11-07): the NBA win margin block shows TWO v3 rows and folds version 2 under
"Older versions"; Since Production is the follower's real trades after fees (sells counted), not a copy of the Sandbox paper numbers; the
own-state lanes table (over 3.5 cheap NO, NBA win margin, the top-5 dip) uses the same definitions. Offline, hermetic."""
import datetime as dt
import json
import os
import re
import sys
import tempfile

import nba_wm_production as X
import production as P
import production_live as PL
import sandbox_audit
import sandbox_sources as S

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


tmp = tempfile.mkdtemp(prefix="own-state-")
X.YES_PATH, X.NO_PATH = os.path.join(tmp, "yes.json"), os.path.join(tmp, "no.json")
PL.PATH = os.path.join(tmp, "live_record.json")

TIP3 = int(dt.datetime(2026, 11, 5, 0, 30, tzinfo=UTC).timestamp())
EV3 = "KXNBAWINMARGIN-26NOV04CHINYK"
V3 = dict(since="2026-11-04", rows={
    "yes:a": dict(lane=X.YES_LANE, ticker=EV3 + "-NYK1TO5", event=EV3, tip=TIP3, decided_at=dt.datetime.fromtimestamp(TIP3 - 3600, UTC).isoformat(), ask=0.15, roi=0.9, result="yes"),
    "no:b": dict(lane=X.NO_LANE, ticker=EV3 + "-CHI6TO10", event=EV3, tip=TIP3, fill_at=TIP3 + 60, limit=0.6, roi=0.3, result="no"),
})
CHAOS = dict(lanes={X.YES_LANE: dict(id=X.YES_LANE, since="2026-11-02", exits=["hold", "split"], trades=[
    dict(event="KXNBAWINMARGIN-26NOV02ATLIND", ticker="KXNBAWINMARGIN-26NOV02ATLIND-ATL1TO5", side="yes", hours=1, exit_key="split", variant="t1h_split",
         night="2026-11-02", entry=0.15, spread=0.03, entry_ts=TIP3 - 200000, start_ts=TIP3 - 190000, cost=0.16, profit=0.2, roi=1.2, won=True, reason="split", side_won=True)])})


def row(i, ko, st, r, legs="", hold=None, src="fills", side="yes", w=1.0):
    return dict(id=i, ko=ko, side=side, st=st, w=w, r=r, legs=legs, hold_r=hold, src=src)


LIVE = dict(generated="2026-11-07T11:00Z", pairs={}, lane_note="n", lanes={
    "nba_wm_yes": [
        row("KXNBAWINMARGIN-26NOV02ATLIND-ATL1TO5", "2026-11-03T01:30", "won", 0.6, "2x+3x", -1.0, "reconstructed"),            # version 2
        row("KXNBAWINMARGIN-26NOV04CHINYK-NYK1TO5", "2026-11-05T00:30", "won", 0.5, "2x+3x", -1.0, "reconstructed"),            # version 3
        row("KXNBAWINMARGIN-26NOV04CHINYK-NYK6TO10", "2026-11-05T00:30", "won", 0.2, "2x", -1.0, "reconstructed"),
        row("KXNBAWINMARGIN-26NOV04MILBOS-BOS1TO5", "2026-11-05T00:30", "lost", -1.0, "", -1.0, "reconstructed"),
        row("KXNBAWINMARGIN-26NOV06WASATL-ATL1TO5", "2026-11-07T01:00", "open", None, "2x", None)],
    "nba_wm_nofade": [
        row("KXNBAWINMARGIN-26NOV02BOSHOU-HOU6TO10", "2026-11-03T01:30", "lost", -1.0, "", None, "reconstructed", "no"),        # version 2
        row("KXNBAWINMARGIN-26NOV04CHINYK-CHI6TO10", "2026-11-05T00:30", "won", 0.32, "sold", None, "reconstructed", "no"),      # version 3
        row("KXNBAWINMARGIN-26NOV04MILBOS-MIL1TO5", "2026-11-05T00:30", "won", 0.32, "sold", None, "reconstructed", "no")],
    "o35_cheap_no": [row("KXUCLTOTAL-26NOV04FCPNAP-4", "2026-11-04T17:00", "won", 3.0, "sold", None, "reconstructed", "no"),
                     row("KXUCLTOTAL-26NOV04VIKSBH-4", "2026-11-04T17:00", "lost", -1.0, "", None, "reconstructed", "no")],
    "top5_dip": [row("KXEPLTOTAL-26NOV06EVECOV-2", "2026-11-06T15:00", "won", 0.8, "sold", None, "fills"),
                 row("KXSERIEATOTAL-26NOV06VENUDI-2", "2026-11-06T17:30", "won", 0.7, "sold", None, "fills")]})
json.dump(LIVE, open(PL.PATH, "w"))


def block(html, sport):
    """The sport's fold, nested folds included."""
    i = html.index(f'data-sport="{sport}"', html.index('class="fold sport-fold"') - 5 if 'class="fold sport-fold"' in html else 0)
    i = html.rfind("<details", 0, i)
    depth, j = 0, i
    for m in re.finditer(r"<details|</details>", html[i:]):
        depth += 1 if m.group() == "<details" else -1
        if depth == 0:
            return html[i:i + m.end()]
    return html[i:]


d, st, blob = {"quotes": []}, {"pairs": {}}, {"leads": {}, "pairs": {}}
html = P.page(d, st, blob, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade={"entries": []}, v3=V3))
b = block(html, "nba-wm")
head = b.split("</summary>", 1)[0]
older_at = b.index("Older versions")
main, older = b[:older_at], b[older_at:]

print("two rows, version 2 folded")
check("the sport block counts 2 pairs, not 4", ("2 pairs" in head, "4 pairs" in head), (True, False))
check("the active table names the two v3 pairs", (X.YES3_NAME in main, X.NO3_NAME in main), (True, True))
check("version 2 is not in the active table", (X.YES_NAME in main, X.NO_NAME in main), (False, False))
check("version 2 sits in the 'Older versions' fold inside the block", (X.YES_NAME in older, X.NO_NAME in older, "<details" in b[older_at - 40:older_at]), (True, True, True))
check("no loose text: the fold is the last thing in the block", b.rstrip().endswith("</details></details>"), True)
check("names are the short ones", (X.YES3_NAME, X.NO3_NAME, S.scoped_rule(f"{X.YES3_LANE}", "nba_wm")), ("Win margin YES split (v3)", "Win margin NO fade (v3)", "Win margin YES split (v3)"))

print("the moved dates")
check("v3 says moved 2026-11-04 (its first night), v2 keeps 2026-11-02", (main.count("moved 2026-11-04"), main.count("moved 2026-11-02"), older.count("moved 2026-11-02")), (2, 0, 2))

print("Since Production is the live record of v3 only")
# v3 live: YES won/won/lost (2 settled wins), NO won/won -> 4 won, 1 lost over 5 settled; v2 trades are not counted
check("the header is the live v3 record: 4-1, not the paper numbers and not v2's rows", ("since Production 4–0–1" in head, "since Production 3–0–2" in head), (True, False))
rows_main = main.split("<tr>")
yes_row = next(r for r in rows_main if X.YES3_NAME in r)
no_row = next(r for r in rows_main if X.NO3_NAME in r)
check("YES row: the live W-L is on the trade outcome (2 won, 1 lost), with legs filled and the hold control, not a held-only W-L",
      ("2–0–1" in yes_row, "legs filled: 2x <b>2</b> · 3x <b>1</b> of 3" in yes_row, "same entries held: -100.0%" in yes_row), (True, True, True))
check("YES row: ROI is the stake-weighted live trades after fees (0.5, 0.2, -1.0 -> -10.0%)", ("−10.0%" in yes_row or "-10.0%" in yes_row), True)
check("NO row: 2 trades won (sold at P), +32.0%", ("2–0–0" in no_row, "+32.0%" in no_row), (True, True))
check("reconstructed rows are labelled on the row", ("reconstructed from the exchange order list" in yes_row, "reconstructed from the exchange order list" in no_row), (True, True))
check("v2's own rows read v2's trades (YES won 1-0, NO lost 0-1)", ("1–0–0" in next(r for r in older.split("<tr>") if X.YES_NAME in r), "0–0–1" in next(r for r in older.split("<tr>") if X.NO_NAME in r)), (True, True))
check("the Sandbox record column is untouched (paper v3: 1 settled at +90% on YES)", "+90.0%" in yes_row, True)
check("no guarded phrase, no dollar amount in the block", (sandbox_audit.COPY_RE.search(b), "$" in b), (None, False))

print("without version 3 the v2 pairs are the active ones")
html0 = P.page(d, st, blob, "", now=NOW, nba_wm=dict(chaos=CHAOS, nofade={"entries": []}))
b0 = block(html0, "nba-wm")
check("no v3: two v2 pairs, no fold", ("Older versions" in b0, X.YES_NAME in b0), (False, True))

print("the own-state lanes table")
t = PL.lanes_table(LIVE)
check("the top-5 dip is listed beside the others", all(n in t for n in ("Top-5 goalless dip", "Over 3.5 cheap NO", "NBA win margin YES split", "NBA win margin NO fade")), True)
check("no 'held to settlement only; exits not counted' text any more", "exits not counted" in t, False)
yes_line = next(r for r in t.split("<tr>") if "NBA win margin YES split" in r)
check("YES split: W-L on the trade outcome (3 won, 1 lost), legs filled, the hold control, the open one named",
      ("3–0–1" in yes_line, "legs filled 2x 3, 3x 2 of 4" in yes_line, "held to settlement -100.0%" in yes_line, "1 open" in yes_line), (True, True, True, True))
o35_line = next(r for r in t.split("<tr>") if "Over 3.5 cheap NO" in r)
check("over 3.5: 1 won (sold early), 1 lost; reconstructed rows are named", ("1–0–1" in o35_line, "1 sold early" in o35_line, "2 reconstructed" in o35_line), (True, True, True))
dip_line = next(r for r in t.split("<tr>") if "Top-5 goalless dip" in r)
check("the dip: two sold at P, both wins", ("2–0–0" in dip_line, "+75.0%" in dip_line, "2 sold early" in dip_line), (True, True, True))

print("F = flat, within +-2% after fees")
FL = dict(LIVE, lanes=dict(LIVE["lanes"], top5_dip=LIVE["lanes"]["top5_dip"] + [row("KXSERIEATOTAL-26NOV06FLAT-2", "2026-11-06T19:00", "flat", 0.015, "", None, "fills")]))
check("a trade at +1.5% is F, at +2.5% W, at -2.5% L", [PL.own_class(dict(st="won", r=r)) for r in (0.015, 0.025, -0.025, -0.02, 0.02)], ["F", "W", "L", "F", "F"])
check("the table reads W–F–L and carries the F line", ("2–1–0" in PL.lanes_table(FL), "F = flat, within ±2% after fees" in PL.lanes_table(FL), "Live W–F–L" in PL.lanes_table(FL)), (True, True, True))
check("the block carries the F line inside a fold (the sport fold and the older fold)", ("F = flat, within ±2% after fees" in b, b.count("F = flat") >= 1), (True, True))

print("the NBA page reads the same trades")
import nba_page as NP
cell = NP.live_cell(NP.YES_ID, LIVE)
check("its live cell is the trade record with legs, not 'held, exits pending'", ("3–0–1" in cell, "legs 2x 3, 3x 2" in cell, "exits pending" in cell), (True, True, False))
old = dict(lanes={"nba_wm_yes": [dict(id="x", ko="2026-11-05T00:30", side="yes", st="won", w=1.0, r=1.0)]})
check("an export from before the trades schema still reads as held to settlement", "exits pending" in NP.live_cell(NP.YES_ID, old), True)

print("pair and lane names stay in step")
import top5_dip_production as TD, o35_production as OP
check("the pairs read the lanes the follower publishes", {k: v[0] for k, v in PL.OWN_PAIRS.items()},
      {f"{X.YES3_LANE}|nba_wm": "nba_wm_yes", f"{X.NO3_LANE}|nba_wm": "nba_wm_nofade", f"{X.YES_LANE}|nba_wm": "nba_wm_yes", f"{X.NO_LANE}|nba_wm": "nba_wm_nofade",
       f"{OP.LANE}|{OP.SPORT}": "o35_cheap_no", f"{TD.LANE}|{TD.SPORT}": "top5_dip"})

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
