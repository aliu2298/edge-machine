#!/usr/bin/env python3
"""Offline checks for the Flipped Unders paper lane (flipped_unders.py) and its Soccer row."""
import datetime as dt
import sys

import flipped_unders as FU
import sandbox_audit
import soccer_rules as SR

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
KO = NOW + dt.timedelta(minutes=45)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def fixture(home, away, league, ko=KO, played=False):
    return dict(kickoff=ko.strftime("%Y-%m-%dT%H:%MZ"), league=league, home=home, away=away, played=played,
                competitive=True, home_goals=None, away_goals=None)


def total(series, home, away, lines, day="26NOV22"):
    tag = f"{series}-{day}{home[:3].upper()}{away[:3].upper()}"
    ms = [dict(ticker=f"{tag}-{i + 2}", title=f"Will over {ln} goals be scored?", status="active",
               yes_bid_dollars=str(b), yes_ask_dollars=str(a)) for i, (ln, (b, a)) in enumerate(sorted(lines.items()))]
    return dict(event_ticker=tag, title=f"{home} vs {away}: Total Goals", markets=ms)


print("selection: the four rules' label filters, retired or not")
check("C5 pair selects Saudi O-D+ v O-D+", FU.sources_for("Saudi Pro League", "O-D+", "O-D+"), ["C5"])
check("C6 selects Ligue 1 O-D- v O+", FU.sources_for("Ligue 1", "O-D-", "O+D+"), ["C6"])
check("B4 selects either team O-D- in Scotland", FU.sources_for("Scottish Premiership", "O-D-", "O+D+"), ["B4"])
check("another league, or a label no rule wants, selects nothing", (FU.sources_for("Serie A", "O-D-", "O+D+"), FU.sources_for("Ligue 1", "O+D+", "O+D+")), ([], []))
check("C5-C7 are retired yet still selected here", all(SR.retired(k, NOW) for k in ("C5", "C6", "C7")), True)

print("\nthe window and the run")
fx = [fixture("Al Hilal", "Al Nassr", "Saudi Pro League"), fixture("Lyon", "Nice", "Ligue 1", ko=NOW + dt.timedelta(minutes=200)),
      fixture("Celtic", "Hearts", "Scottish Premiership"), fixture("Rangers", "Hibs", "Scottish Premiership", played=True),
      fixture("Arsenal", "Spurs", "Premier League")]
check("due: only the four leagues, in the 20-90 minute window, unplayed", [f["home"] for f in FU.due(fx, NOW)], ["Al Hilal", "Celtic"])
LABS = {"Al Hilal": ("O-D+", "O-D+"), "Celtic": ("O-D-", "O+D+")}
SR.labels = lambda fixtures, f: LABS[f["home"]]
events = {"KXSAUDIPLTOTAL": [total("KXSAUDIPLTOTAL", "Al Hilal", "Al Nassr", {1.5: (0.80, 0.82), 2.5: (0.58, 0.60), 3.5: (0.30, 0.32)})],
          "KXSCOTTISHPREMTOTAL": [total("KXSCOTTISHPREMTOTAL", "Celtic", "Hearts", {2.5: (0.60, 0.62), 3.5: (0.31, 0.40)})]}


def fake(path):
    if path.startswith("events?"):
        return {"events": events.get(path.split("series_ticker=")[1].split("&")[0], [])}
    t = path.split("/")[-1]
    return {"market": {"ticker": t, "status": "finalized", "result": "yes" if "SAUDI" in t else "no"}}


st = FU.load("/nonexistent/fu.json")
new = FU.run(st, fx, NOW, fake)
ps = st["rules"]["FU"]["picks"]
check("Saudi under NO is 1 - 0.58 = 42c, inside C5's 50c band: enters over 2.5 YES at the ask; Scotland's 3.5 has a 9c spread, no entry", [(p["sources"], p["line"], p["side"], p["price"]) for p in ps], [(["C5"], 2.5, "yes", 0.6)])
FU.run(st, fx, NOW + dt.timedelta(minutes=30), fake)
check("a second read adds nothing: one frozen entry a match", len(st["rules"]["FU"]["picks"]), 1)
p = st["rules"]["FU"]["picks"][0]
check("settled on Kalshi's result, profit per $100 after the fee", (p["status"], p["profit"]), ("won", round(100 * (1 / (0.6 + FU.fee(0.6)) - 1), 2)))
check("two source rules on one match are logged once with both", FU.picks_for(fixture("Al Hilal", "Al Nassr", "Saudi Pro League"), ("O-D+", "O-D+"), events["KXSAUDIPLTOTAL"][0], ["C5", "C7"], NOW)[0]["sources"], ["C5", "C7"])

pricey = total("KXSAUDIPLTOTAL", "Al Hilal", "Al Nassr", {2.5: (0.40, 0.42)})
check("the under's NO side must sit in the rule's band: NO 60c is above C5's 50c cap, so no entry", FU.picks_for(fixture("Al Hilal", "Al Nassr", "Saudi Pro League"), ("O-D+", "O-D+"), pricey, ["C5"], NOW), [])
sc = total("KXSCOTTISHPREMTOTAL", "Celtic", "Hearts", {3.5: (0.30, 0.32)})
check("B4's 60-75c band: NO 70c enters; the entry is the over's YES ask", [(p["sources"], p["price"], p["under_no"]) for p in FU.picks_for(fixture("Celtic", "Hearts", "Scottish Premiership"), ("O-D-", "O+D+"), sc, ["B4"], NOW)], [(["B4"], 0.32, 0.7)])
check("two rules whose band the under is inside are both listed", FU.picks_for(fixture("Al Hilal", "Al Nassr", "Saudi Pro League"), ("O-D+", "O-D+"), events["KXSAUDIPLTOTAL"][0], ["C5", "C7"], NOW)[0]["sources"], ["C5", "C7"])

print("\nthe record, per source rule")
rec = FU.record(ps)
check("one entry, won, hit 100%, price 60c, break-even price plus fee", (rec["entries"], rec["won"], rec["lost"], rec["hit"], rec["avg_price"], round(rec["break_even"], 4)), (1, 1, 0, 1.0, 0.6, round(0.6 + FU.fee(0.6), 4)))
by = FU.by_source(ps)
check("C5 has it; C6, C7, B4 are empty", (by["C5"]["entries"], by["C6"]["entries"], by["C7"]["entries"], by["B4"]["entries"]), (1, 0, 0, 0))
check("verdict waits for 10", FU.verdict(3).startswith("too early"), True)

print("\nthe Soccer row")
import soccer_lanes
rows = soccer_lanes.flipped_rows(st)
check("one row, named flipped_unders, record from the ledger", (len(rows), rows[0]["name"], rows[0]["a"]["n"], rows[0]["a"]["won"]), (1, "flipped_unders", 1, 1))
html = rows[0]["own"]["details"]
check("the fold has the per-source table and the in-sample row, not counted", all(x in html for x in ("Hit rate", "Break-even after fees", "In-sample, not counted", "C5", "B4")), True)
check("percentages only, no dollar sign", "$" in html + rows[0]["own"]["entries"], False)
check("the copy passes the audit's guarded phrases", sandbox_audit.COPY_RE.search(html + open("flipped_unders.py").read()), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
