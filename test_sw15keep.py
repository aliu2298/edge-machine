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
check("a retired lane's cut is round 2's; a kept rule has none", (C.retire_at("s3v2"), C.retire_at("flipf1v2"),
      C.retire_at("sp500_fav5")), (C.CUT2_AT, C.CUT2_AT, None))
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
check("the live area: the three rules (A, C, the Lead Swap favourite) and the Loss Reader watch row, nothing else",
      re.findall(r'data-source="([a-z0-9_]+)"', live), ["sp500_fav5", "sp500_flip15", "leadswap_fav", "lossreader"])
check("each kept rule says why these markets, with the forward and history numbers",
      (live.count('class="sm sw15-why"'), "forward +4.9% (60 bets)" in live, "forward +66.5% (28 bets)" in live), (2, True, True))
check("the 25c companion is shown under C, not as a rule; the background folds are there",
      ("Companion · the same at 25c (observation, not a rule)" in live, live.count('class="fold sw15-bg"')), (True, 2))
check("the Loss Reader is a watch row to 30 bets", "Watch row · Solana · runs to 30 bets" in live, True)
arc = html.split('id="sw15-archive"')[1]
check("the archive: the seven lanes retired today with their records, and the v1 baselines",
      ("<h4>Narrowed to three rules (Nov 11)</h4>" in arc, arc.split("<h4>Narrowed to three rules (Nov 11)</h4>")[1]
       .split("</details>")[0].count("<tr>") - 1, "<h4>v1 baselines (background, every market)</h4>" in arc), (True, 7, True))
check("the Sandbox index lists the three rules and the watch row only (and the favourite's control)",
      [x["lane"] for x in WB.index_rows(real)], ["sp500_fav5", "sp500_flip15", "lossreader", "leadswap_fav", "leadswap_fav_ctrl"])
check("plain copy: no dollar amount, no guarded phrase, no inline style", (re.search(r"\$\d", html),
      sandbox_audit.COPY_RE.findall(html), "style=" in html), (None, [], False))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
