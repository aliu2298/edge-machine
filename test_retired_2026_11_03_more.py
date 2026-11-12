#!/usr/bin/env python3
"""Offline checks for the second batch of 2026-11-03 retirements (Olu): Oddspedia's cricket row with cricket consensus
(built from it), team 2+ form on Clubs (its Cups and Internationals scopes keep running), the MLS away fade, the
Argentina & Brasileirao over 1.5 lane (sa_o15), Double 7s, and crypto band 60, below. None is in Production; nothing in
Production moves. The first batch (RSI(2), the crypto Yes bands, UFC) is test_retired_2026_11_03.py."""
import datetime as dt
import html
import inspect
import re
import sys

import cricket_build
import crypto_build as CB
import lane_windows as W
import market_exec as X
import market_track as MT
import production as P
import sa_o15 as SA
import sa_o15_build as SAB
import sandbox_audit
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import soccer_build

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def fold_of(html):
    i = html.find('<section id="retired"')
    return i, html[i:html.find("</section>", i)]


def why_in(fold, name):
    m = re.search(rf'sp-retired-why" data-source="{name}"[^>]*>(.*?)</p>', fold, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else None


print("the registry: each scope off its live sports, retired with a dated record")
for name, scope, why in (("oddspedia", "cricket", S.ODDSPEDIA_CRICKET_RETIRED_WHY),
                         ("cricket_consensus", "cricket", S.CRICKET_CONSENSUS_RETIRED_WHY),
                         ("mls_away_band_fade", "soccer_p05", S.MLS_AWAY_FADE_RETIRED_WHY),
                         ("crypto_fav_band_below_60", "crypto_fav", S.CRYPTO_FAV_BAND_BELOW_60_RETIRED_WHY)):
    m = S.SOURCES[name]
    check(f"{name}: off the run, retired", (m["sports"], m["retired_sports"]), ([], {scope: why}))
    check(f"{name}: open rows still settle (a retired scope is not a removed row)",
          S.removed_row(dict(source=name, sport=scope)), False)
t2 = S.SOURCES["team2_form_l10"]
check("team 2+ form: Clubs retired, Cups and Internationals still run (the same predicate, untouched)",
      (t2["sports"], t2["retired_sports"]), (["soccer_team2_cup", "soccer_team2_intl"], {"soccer_team2": S.TEAM2_FORM_CLUBS_RETIRED_WHY}))
check("the records", ("6 won v 6.6 priced, −4.6% after fees" in S.ODDSPEDIA_CRICKET_RETIRED_WHY,
                      "17 won v 17.3 priced, −4.9% after fees" in S.TEAM2_FORM_CLUBS_RETIRED_WHY,
                      "13 won v 14.2 priced, −9.9% after fees" in S.MLS_AWAY_FADE_RETIRED_WHY,
                      "8–6, 8 won v 9.1 priced, −8.8% after fees" in S.CRYPTO_FAV_BAND_BELOW_60_RETIRED_WHY,
                      "it never fired" in S.CRICKET_CONSENSUS_RETIRED_WHY), (True,) * 5)
check("crypto band, below (No 0.70-0.80, in Production) keeps running", S.SOURCES["crypto_fav_band_below"]["sports"], ["crypto_fav"])

print("\ncricket consensus and Oddspedia take no new pick by their own paths")
src = inspect.getsource(T)
check("the consensus path checks the pair's live sports", 'and cfg["sport"] in S.SOURCES[name]["sports"]):' in src, True)
check("Oddspedia's browser page is not requested for a retired scope",
      'if not lane_removed("oddspedia", sport) and sport in SOURCES["oddspedia"]["sports"]:' in inspect.getsource(S), True)

print("\nthe Cricket page: both in its Retired fold, with their records, and not above it")
ch = cricket_build.build()
i, fold = fold_of(ch)
check("one Retired fold", (i > 0, ch.count('<section id="retired"')), (True, 1))
check("Oddspedia's line", why_in(fold, "oddspedia"), S.ODDSPEDIA_CRICKET_RETIRED_WHY)
check("cricket consensus's line", why_in(fold, "cricket_consensus"), S.CRICKET_CONSENSUS_RETIRED_WHY)
check("neither in the live rules above the fold",
      [n for n in ("oddspedia", "cricket_consensus") if f'data-source="{n}"' in ch[:i]], [])

print("\nthe Soccer page: team 2+ Clubs and the MLS away fade in Retired rules")
sh = soccer_build.build()
j, sfold = fold_of(sh)
check("the MLS away fade's line", why_in(sfold, "mls_away_band_fade"), S.MLS_AWAY_FADE_RETIRED_WHY)
check("team 2+ form's Clubs line", why_in(sfold, "team2_form_l10"), S.TEAM2_FORM_CLUBS_RETIRED_WHY)
check("no MLS away fade row above the fold", 'data-source="mls_away_band_fade"' in sh[:j], False)

print("\nthe Crypto page: band 60, below in Retired rules; band, below live")
cb = CB.build()
k, cfold = fold_of(cb)
check("in the fold, not above it", ('data-source="crypto_fav_band_below_60"' in cfold, 'data-source="crypto_fav_band_below_60"' in cb[:k]),
      (True, False))
check("the live coin lanes (the Yes twin's v2 joined 2026-11-12)", CB.live_lanes(), ("crypto_fav_band_below", "crypto_fav_band_v2"))
check("the crypto window waits only on the lanes still logging (a retired sibling never enters)",
      "S.SOURCES[n].get(\"sports\")" in inspect.getsource(W.entered_series), True)
led = {"quotes": [dict(source=n, bet=True, market_id="KXBTCD-26NOV0317-T70000") for n in ("crypto_fav_band_below", "crypto_fav_band_v2")]}
check("so one entry in each live lane is enough to skip that coin's later reads",
      W.entered_series("crypto_fav_band", dt.datetime(2026, 11, 3, 22, 0, tzinfo=UTC), led), {"KXBTCD"})

print("\nArgentina & Brasileirao over 1.5: both rows retired, open entries still settle, no window asked for")
check("both rows, dated", {k: v["on"] for k, v in SA.RETIRED.items()}, {"ARG": "2026-11-03", "BRA": "2026-11-03"})
check("the records", (SA.RETIRED["ARG"]["reason"][:41], SA.RETIRED["BRA"]["reason"][:41]),
      ("20 won v 19.1 priced on 28 settled, +2.5%", "17 won v 16.5 priced on 21 settled, +2.6%"))
before, after = dt.datetime(2026, 11, 3, 4, tzinfo=UTC), dt.datetime(2026, 11, 3, 6, tzinfo=UTC)   # 23:00 / 01:00 Eastern
check("the Eastern date gate", (SA.retired("ARG", before), SA.retired("ARG", after), SA.all_retired(after)), (False, True, True))
fx = [dict(league="Liga Profesional", home="Boca Juniors", away="River Plate", played=False,
           kickoff=(after + dt.timedelta(minutes=45)).isoformat())]
check("nothing is due and nothing is scheduled once retired", (SA.due(fx, after), SA.schedule(fx, after)), ([], []))
check("run() still settles its open entries", "errs += SR.settle(state, now, fetch)" in inspect.getsource(SA.run), True)
check("the VPS asks for no Argentine or Brazilian window once retired (and did before)",
      (W.sa_kickoffs(after, fx), len(W.sa_kickoffs(before, [dict(fx[0], kickoff=(before + dt.timedelta(minutes=45)).isoformat())]))),
      ([], 1))
check("lane_windows carries the same retirement day", W.SOCCER_SA_RETIRED_ON, max(v["on"] for v in SA.RETIRED.values()))
sec = SAB.section()
check("its Soccer section: both rows badged Retired with the reason, the head says no new entries",
      (sec.count('data-retired="2026-11-03"'), "Retired 2026-11-03: no new entries" in sec, "a blind lane with no team or matchup filter" in sec),
      (2, True, True))

print("\nDouble 7s: retired, its open trades still graded and exited")
d7 = MT.RULES["etf_double7"]
check("dated with its record", d7.get("retired"),
      "2026-11-03: no edge at 14 entry days — 19 closed trades, −0.19% a day after costs, t −0.46, 6 open")
check("not scanned (the live run scans ACTIVE only), not removed",
      ("etf_double7" in MT.ACTIVE, MT.rule_removed("etf_double7"), "added = scan(bars, d, rules=ACTIVE" in inspect.getsource(MT)),
      (False, False, True))
ok_rules, skipped = X.executable_rules()
check("no new paper entry, but its open trades still sell",
      ("etf_double7" in ok_rules, skipped.get("etf_double7"), "etf_double7" in X.exit_rules()),
      (False, "retired: sells its open trades, never a new entry", True))
check("the Trading page draws it as Retired", (MT.assess(MT.load(), "etf_double7")["verdict"],
      "no edge at 14 entry days" in B.trading_page()), ("retired", True))

print("\nnone is in Production")  # team2_form_l10 is not in this list: it is back in Production as team2_form_l10|soccer_team2_intl
st = T.load_stages()
gone = ("oddspedia", "cricket_consensus", "mls_away_band_fade", "crypto_fav_band_below_60", "sa_o15_arg", "sa_o15_bra")
check("no Production pair for any of them", sorted(k for k in P.production_pairs(st) if k.split("|")[0] in gone), [])

check("no guarded phrase in the new copy", sandbox_audit.COPY_RE.search(
    S.ODDSPEDIA_CRICKET_RETIRED_WHY + S.CRICKET_CONSENSUS_RETIRED_WHY + S.TEAM2_FORM_CLUBS_RETIRED_WHY + S.MLS_AWAY_FADE_RETIRED_WHY
    + S.CRYPTO_FAV_BAND_BELOW_60_RETIRED_WHY + str(SA.RETIRED) + d7["retired"] + fold + sfold + cfold + sec), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
