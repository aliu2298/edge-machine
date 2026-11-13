#!/usr/bin/env python3
"""The 15-Minute section narrowed to three rules (sw15keep.py, sw15cuts round 2, Lead Swap round 3; Olu 2026-11-11)."""
import datetime as dt
import re
import sys

import leadswap as L
import sandbox_audit
import sw15cuts as C
import sw15keep as K
import swing15 as W
import swing15_build as WB

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


print("the registration")
check("round 2 is frozen (fingerprint), its cut a window boundary after round 1",
      (C.fingerprint2() == C.ROUND2_SHA256, W._ts(C.CUT2_AT) % 900, C.CUT2_AT > C.CUT_AT), (True, 0, True))
check("retired in round 2: Rules 2-5 v2, Steady Favourites B, Swing v3 S2, Lead Swap swing", C.RETIRED2,
      ("s3v2", "flipf1v2", "flipf2v2", "flipf3v2", "steadyfav_b", "swing15v2_s2", "leadswap_swing"))
check("A and C read v1's cells on the S&P 500 only, fresh from the cut", (K.MARKET, K.FROM, K.RULES["sp500_fav5"]["key"],
      K.RULES["sp500_flip15"]["key"], K.COMPANION["sp500_flip25"]["key"]),
      ("KXINX15M", C.CUT2_AT, ("swing15_s3",), ("swing15_s1", "0.15", "2.0", "bid"), ("swing15_s1", "0.25", "2.0", "bid")))
check("review at 30, decide at 100", (K.REVIEW_AT, K.DECIDE_AT), (30, 100))

print("\nthe records")
fav = lambda won, p=0.7: dict(status="filled", side="yes", price=p, won=won, roi=round(won / (p + W.fee(p, W.TAKER)) - 1, 4))


def win(series, open_iso, s3=None):
    return dict(ticker=f"{series}-{open_iso}", series=series, group="Financials", open=open_iso, day=open_iso[:10],
                us_hours=True, fee_multiplier=1.0, s1={}, s2=dict(status="no_quote"), s3=s3 or dict(status="no_quote"))


after = dt.datetime.fromisoformat(C.CUT2_AT) + dt.timedelta(hours=16)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
ws = [win("KXINX15M", iso(after), fav(1.0)), win("KXINX15M", iso(after + dt.timedelta(minutes=15)), fav(0.0)),
      win("KXGOLD15M", iso(after), fav(1.0)), win("KXINX15M", "2026-11-11T15:00:00Z", fav(1.0))]
st = dict(W.empty(), windows={w["ticker"]: w for w in ws})
rec = K.records(st)
check("A counts the S&P 500 only, from the cut (1 won of 2; the 15:00Z window is before it)",
      (rec["sp500_fav5"]["all"]["n"], rec["sp500_fav5"]["all"]["hits"]), (2, 1))
check("every other market is tracked in the background, never counted", (rec["sp500_fav5"]["background"]["KXGOLD15M"]["n"],
      "KXINX15M" in rec["sp500_fav5"]["background"]), (1, False))

print("\nretired lanes stop entering at the cut")
import flipf1v2, s3v2
check("a retired lane's cut is round 2's; rule A's is round 4's", (C.retire_at("s3v2"), C.retire_at("flipf1v2"),
      C.retire_at("sp500_fav5")), (C.CUT2_AT, C.CUT2_AT, C.CUT4_AT))
check("the flip and Rule 2 lanes report retired", (flipf1v2.retired(), s3v2.records(st)["lane"]["all"]), (True, None))
H0, HB = W._ts(C.CUT2_AT) + 3600, W._ts(C.CUT2_AT) - 3600
xw = lambda s, o: dict(series=s, open=dt.datetime.fromtimestamp(o, dt.timezone.utc).isoformat(), group="Crypto",
                       fee_multiplier=1.0, s1={"0.35": dict(won=1.0, trigger=dict(ts=o + 60))},
                       s3=dict(status="filled", won=1.0, price=0.8, roi=0.2))
rows = [(s, "Crypto", o, o + 900, {}, xw(s, o)) for s in ("KXPALLADIUM15M", "KXETH15M", "KXHYPE15M") for o in (HB, H0)]
key = lambda h: dt.datetime.fromtimestamp(h - h % 3600, dt.timezone.utc).isoformat()
picks = {key(o): dict(top=["KXHYPE15M"], bottom=["KXPALLADIUM15M", "KXETH15M"], at=key(o)) for o in (HB, H0)}
r = L.routing(rows, picks)
check("Lead Swap favourite: Palladium (round 3) skipped from the cut, no backfill; Ethereum continues",
      {m: v[0] for m, v in r["leadswap_fav"]["series"].items()}, {"KXETH15M": 2})
check("the swing trade enters nothing after its retirement (its earlier entry stays)",
      {m: v[0] for m, v in r["leadswap_swing"]["series"].items()}, {"KXHYPE15M": 1})
check("round 3 is recorded with its cut and data; the controls exclude nothing",
      ([x["n"] for x in L.ROUNDS], L.ROUNDS[2]["markets"], sorted(r["leadswap_fav_ctrl"]["series"])),
      ([1, 2, 3], {"leadswap_fav": ("KXPALLADIUM15M", "KXUSDCAD15M")}, ["KXHYPE15M"]))

print("\nthe page")
real = W.load()
html = WB.section(real)
live = html.split('id="sw15-archive"')[0]
check("the live area: rule C version 2's three rows only; A, B and C version 1 are retired (2026-11-13), the Loss Reader 2026-11-12",
      re.findall(r'data-source="([a-z0-9_]+)"', live), ["sw15c2_10", "sw15c2_15", "sw15c2_25"])
check("one list: the three C v2 rows", re.findall(r'id="sw15-([a-z0-9_]+)"', live)[:3], ["c2_10", "c2_15", "c2_25"])
check("short names", all(n in live for n in ("C v2 · S&amp;P 500 opening sweep, 10c sell 3x", "C v2 · S&amp;P 500 opening sweep, 15c sell 2x",
      "C v2 · S&amp;P 500 opening sweep, 25c sell 2x")), True)
check("A, B and C version 1 are not in the live area, and the intro says one rule",
      ("S&amp;P 500 favourite, 5 min left" in live, "Lead Swap favourite v2" in live, "S&amp;P 500 underdog at 15c" in live, "one rule" in live), (False, False, False, True))
check("one section heading, no per-lane h3 blocks; one closed method fold", (live.count("<h3"), live.count("sw15-how")),
      (0, 1))
check("the Loss Reader is no longer in the live area, and C v2 reads Too early until its bets", ("Loss Reader" in live, "Too early (" in live), (False, True))
check("ONE retired block, closed", (html.count('id="sw15-archive"'), "<b>Retired · final records</b>" in html), (1, True))
arc = html.split('id="sw15-archive"')[1]
check("the archive: the seven lanes retired today with their records, and the v1 baselines",
      ("<h4>Narrowed to three rules (Nov 11)</h4>" in arc, arc.split("<h4>Narrowed to three rules (Nov 11)</h4>")[1]
       .split("</details>")[0].count("<tr>") - 1, "<h4>v1 baselines (background, every market)</h4>" in arc), (True, 7, True))
check("the Sandbox index lists rule C version 2's three rows (A, B and C version 1 retired 2026-11-13)",
      [x["lane"] for x in WB.index_rows(real)], ["sw15c2_10", "sw15c2_15", "sw15c2_25"])
print("\nround 4: A and B retired 2026-11-13 by Olu")
check("round 4 is frozen (fingerprint) and its cut is a window boundary after round 3",
      (C.fingerprint4() == C.ROUND4_SHA256, W._ts(C.CUT4_AT) % 900, C.CUT4_AT > C.CUT3_AT, C.RETIRED4), (True, 0, True, ("sp500_fav5", "leadswap_v2", "leadswap_v2_ctrl")))
cut4 = dt.datetime.fromisoformat(C.CUT4_AT)
ws4 = [win("KXINX15M", iso(cut4 - dt.timedelta(minutes=15)), fav(1.0)), win("KXINX15M", iso(cut4), fav(0.0)),
       win("KXINX15M", iso(cut4 + dt.timedelta(minutes=15)), fav(0.0))]
s4 = dict(W.empty(), windows={w["ticker"]: w for w in ws4})
r4 = K.records(s4)
check("A counts the window before the cut and none from it: its record is final", (r4["sp500_fav5"]["all"]["n"], r4["sp500_fav5"]["all"]["hits"]), (1, 1))
check("rule C version 1 and its companion stop at round 5's cut (C v2's first window)", (C.retire_at("sp500_flip15"), C.retire_at("sp500_flip25")), (C.CUT5_AT, C.CUT5_AT))
check("round 5 is frozen (fingerprint) and its cut is a window boundary", (C.fingerprint5() == C.ROUND5_SHA256, W._ts(C.CUT5_AT) % 900, C.RETIRED5), (True, 0, ("sp500_flip15", "sp500_flip25")))
cut5 = dt.datetime.fromisoformat(C.CUT5_AT)
w5 = [win("KXINX15M", iso(cut5 - dt.timedelta(minutes=15)), fav(1.0)), win("KXINX15M", iso(cut5), fav(0.0))]
for w in w5:
    w["s1"] = {"0.15": dict(exits={"2.0": dict(filled=True, fill_ts=0, roi_bid=0.5, roi_hold=0.5)}, bid14=0.2)}
check("C v1's S&P 500 background reads stop at the cut", K.in_record(w5[0], None, C.CUT5_AT) and not K.in_record(w5[1], None, C.CUT5_AT), True)
arc5 = html.split('id="sw15-archive"')[1]
check("the Retired block holds C version 1 and its companion with the dated line 'Retired 2026-11-13, replaced by C v2.'",
      ("Retired 2026-11-13, replaced by C v2." in arc5, "C · S&amp;P 500 underdog at 15c" in arc5, "C companion · at 25c (observation)" in arc5), (True, True, True))
import leadswap_v2 as V2
o4 = int(W._ts(C.CUT4_AT))
mk4 = lambda s, o: (s, "Crypto", o, o + 900, {}, dict(series=s, open=dt.datetime.fromtimestamp(o, dt.timezone.utc).isoformat(), group="Crypto", fee_multiplier=1.0,
                    s1={"0.35": dict(won=1.0, trigger=dict(ts=o + 60))}, s3=dict(status="filled", won=1.0, price=0.8, roi=0.2)))
k4 = lambda h: dt.datetime.fromtimestamp(h - h % 3600, dt.timezone.utc).isoformat()
rows4 = [mk4("KXBTC15M", o4 - 900), mk4("KXBTC15M", o4), mk4("KXBTC15M", o4 + 900)]
p4 = {k4(o4 - 3600): dict(top=[], bottom=["KXBTC15M"], at=k4(o4 - 3600)), k4(o4): dict(top=["KXBTC15M"], bottom=[], at=k4(o4))}
rb = V2.routing(rows4, p4)
check("B enters the window before the cut and nothing from it; its control (top 3) enters nothing from it either",
      ({m: v[0] for m, v in rb["leadswap_v2"]["series"].items()}, rb["leadswap_v2_ctrl"]), ({"KXBTC15M": 1}, None))
arc4 = html.split('id="sw15-archive"')[1]
check("the Retired Nov 13 block holds A and B (with B's control), dated and credited",
      ("<h4>Retired Nov 13</h4>" in arc4, "Retired 2026-11-13 by Olu" in arc4, "S&amp;P 500 favourite, 5 min left" in arc4.split("<h4>Retired Nov 13</h4>")[1][:2500],
       "Control · the same markets when swappy" in arc4.split("<h4>Retired Nov 13</h4>")[1][:2500]), (True, True, True, True))
check("the workflow was not edited: the same hourly run keeps grading (rows stay, records final)",
      "python3 leadswap_v2.py" in open(".github/workflows/swing15.yml").read(), True)
check("plain copy: no dollar amount, no guarded phrase, no inline style", (re.search(r"\$\d", html),
      sandbox_audit.COPY_RE.findall(html), "style=" in html), (None, [], False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
