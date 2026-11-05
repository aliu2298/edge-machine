#!/usr/bin/env python3
"""Offline checks for the 2026-11-03 retirements (Olu, records review of the 2026-11-02 pages): the RSI(2) pullback
trading rule (with its live pilot held off), the crypto favourite bands 70-80 and 60-70, and the UFC underdog fights
lane. None is in Production; nothing in Production moves. Oddspedia's cricket row was held here (cricket consensus reads
it) and retired the same day with consensus, once asked: test_retired_2026_11_03_more.py, with the second batch."""
import datetime as dt
import inspect
import os
import re
import sys

import crypto_build as CB
import fights_build as FB
import fights_split as FS
import market_exec as X
import market_track as MT
import mentions_split as MS
import production as P
import sandbox_audit
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("RSI(2) pullback: retired, its open trades still graded and exited, the live pilot held off")
rsi = MT.RULES["sw_rsi2_pullback"]
check("dated with its record", rsi.get("retired"),
      "2026-11-03: no edge after costs at 29 days — 588 trades on 29 entry days, −0.89% per trade after the measured costs, t −1.37")
check("not scanned (no new entry), but not removed: it stays on the Trading page as Retired and its rows grade",
      ("sw_rsi2_pullback" in MT.ACTIVE, MT.rule_removed("sw_rsi2_pullback")), (False, False))
check("grade() closes a retired (not removed) rule's open trades", "if rule_removed(t.get(\"rule\")) and not rule_exit_only" in inspect.getsource(MT.grade), True)
ok_rules, skipped = X.executable_rules()
check("market_exec sends it no new entry", ("sw_rsi2_pullback" in ok_rules, skipped.get("sw_rsi2_pullback")),
      (False, "retired: sells its open trades, never a new entry"))
check("but still sells its open paper trades (exits are never stranded)", "sw_rsi2_pullback" in X.exit_rules(), True)
check("the Trading page draws it as Retired, with its reason", (MT.assess(MT.load(), "sw_rsi2_pullback")["verdict"],
      "no edge after costs at 29 days" in B.trading_page()), ("retired", True))

print("\nthe live pilot refuses to start on a retired rule")
_only = X.ONLY_RULES
X.ONLY_RULES = {"sw_rsi2_pullback"}
try:
    check("the live pass's rules include a retired one", X.retired_live_rules(), ["sw_rsi2_pullback"])
    _live, _conf = X.live, X.M.configured
    X.live, X.M.configured = (lambda: True), (lambda: True)
    called = []
    _plan, _place = X.plan, X.place
    X.plan = lambda *a, **k: called.append("plan") or ([], [])
    X.place = lambda *a, **k: called.append("place") or ([], [])
    try:
        rc = X.main(["--place"])
    finally:
        X.live, X.M.configured, X.plan, X.place = _live, _conf, _plan, _place
    check("a live run exits non-zero before planning or sending anything", (rc, called), (1, []))
finally:
    X.ONLY_RULES = _only
check("--live-check reports it NOT READY", "retired on the board" in inspect.getsource(X.main), True)
check("the switch file is never touched by the code", "alpaca-live.env.off" in inspect.getsource(X), False)

print("\ncrypto favourite bands 70-80 and 60-70: retired; the Production and below lanes untouched")
for name, why in (("crypto_fav_band", S.CRYPTO_FAV_BAND_RETIRED_WHY), ("crypto_fav_band_60", S.CRYPTO_FAV_BAND_60_RETIRED_WHY)):
    m = S.SOURCES[name]
    check(f"{name}: off the run, retired with a dated record", (m["sports"], m["retired_sports"]), ([], {"crypto_fav": why}))
check("the records", (S.CRYPTO_FAV_BAND_RETIRED_WHY[:110], "8–6, 8 won v 8.9 priced, −10.7% after fees" in S.CRYPTO_FAV_BAND_60_RETIRED_WHY),
      ("Retired 2026-11-03 by Olu: no edge at 23 market-days — 15–8, 15 won v 17.2 priced, −7.8% after fees. No new en", True))
check("crypto band, below keeps running (band 60, below retired in the second batch)", S.SOURCES["crypto_fav_band_below"]["sports"],
      ["crypto_fav"])
check("open rows still settle (a retired scope is not a removed row)", S.removed_row(dict(source="crypto_fav_band", sport="crypto_fav")), False)
html = CB.build()
i = html.find('<section id="retired"')
fold = html[i:html.find("</section>", i)]
check("the Crypto page lists both in Retired rules, and nowhere above it",
      ([n for n in ("crypto_fav_band", "crypto_fav_band_60") if f'data-source="{n}"' in fold],
       [n for n in ("crypto_fav_band", "crypto_fav_band_60") if f'data-source="{n}"' in html[:i]]),
      (["crypto_fav_band", "crypto_fav_band_60"], []))
check("the scanner line reads a live lane's coverage", CB.live_lanes()[0], "crypto_fav_band_below")

print("\nUFC underdog 15-30c: retired; boxing keeps running")
check("dated with its record", (FS.UFC["retired"]["on"], FS.UFC["retired"]["at"]), ("2026-11-03", "7 fights, 0 won; split −86.5%, hold −100%"))
check("the live, baseline and retired fights lanes (boxing a baseline from 2026-11-04)",
      ([c["lane"] for c in FS.LIVE], [c["lane"] for c in FS.BASES], [c["lane"] for c in FS.GONE]), ([], ["boxing_cheap_dog"], ["ufc_dog"]))
check("Eastern date gate", (MS.retired(FS.UFC, dt.datetime(2026, 11, 3, 4, tzinfo=UTC)), MS.retired(FS.UFC, dt.datetime(2026, 11, 3, 6, tzinfo=UTC))),
      (False, True))
check("run() takes no new entry for a retired lane, open entries still fill and settle", "if MS.retired(cfg, now):" in inspect.getsource(FS.run), True)
fh = FB.build()
j = fh.find('id="retired"')
check("the Fights page: UFC in its Retired fold, not in the live lanes; boxing above it as a baseline",
      ("UFC · dog" in fh[:j], "UFC · dog" in fh[j:], 'id="baseline-boxing_cheap_dog"' in fh[:j], '<details class="fold sec" id="retired">' in fh),
      (False, True, True, True))

print("\nnone is in Production: no Production pair for any of them")
st = T.load_stages()
prod = P.production_pairs(st)
check("no Production pair for any of them", sorted(k for k in prod if k.split("|")[0] in ("crypto_fav_band", "crypto_fav_band_60", "ufc_dog")), [])
check("the crypto 70-80 band was pulled from Production on 2026-10-20 and not re-listed",
      (T.PAIR_REMOVALS["crypto_fav_band|crypto_fav"]["removed_on"], "crypto_fav_band|crypto_fav" in T.PAIR_OVERRIDES), ("2026-10-20", False))

print("\ncricket consensus is built from Oddspedia and Polymarket, so the two retire together (second batch)")
check("consensus's sources", T.CONSENSUS["cricket_consensus"]["sources"], ("oddspedia", "polymarket"))

check("no guarded phrase in the new copy", sandbox_audit.COPY_RE.search(
    rsi["retired"] + S.CRYPTO_FAV_BAND_RETIRED_WHY + S.CRYPTO_FAV_BAND_60_RETIRED_WHY + str(FS.UFC["retired"]) + fold + fh[j:]), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
