#!/usr/bin/env python3
"""The retirements of 2026-10-24 (Olu): no new entries, rows kept, shown as Retired.

Soccer: thirteen Sandbox pairs and the label rule D2. Tennis: six Sandbox pairs (the 3h
favourite band and five combo lanes). None of them is in Production; the Production pairs
that share a source or a page (o15_ranked · Internationals, the UTR shortlist) and the kept
lanes (tennis_combo2, tennis_atp_low_over) are untouched. No network.
"""
import datetime as dt
import sys
import unittest.mock as um

import lane_preflight as P
import lane_windows as W
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import soccer_build
import soccer_rules as SR
import soccer_rules_build as SRB
import sport_tab
import tennis_build

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


RETIRED = {
    "o15_cup_mismatch|soccer_o15_cup", "o15_ranked|soccer_o15_cup", "o15_ranked|soccer_o15",
    "ftts_no_60_70|soccer_ftts", "o25_congestion|soccer_o25", "o25_congestion|soccer_o25_cup",
    "o15_form_l10|soccer_o15", "o15_form_l10|soccer_o15_cup", "o15_form_l10|soccer_o15_intl",
    "btts_form_l10_fade|soccer_btts", "bund_o35|soccer_u35", "bund_o35_fav|soccer_u35",
    "corners_team_fade|soccer_corners",
}
SPLIT = [k.split("|") for k in sorted(RETIRED)]

print("the registry: each retired scope leaves `sports` for `retired_sports`, dated")
check("the list is the thirteen pairs, and sandbox_sources names the same ones",
      (len(RETIRED), set(S.RETIRED_ON_2026_10_24)), (13, RETIRED))
for name, sport in SPLIT:
    meta = S.SOURCES[name]
    why = (meta.get("retired_sports") or {}).get(sport) or ""
    check(f"{name}|{sport}: off the run, retired with a dated reason",
          (sport in meta["sports"], why.startswith("Retired 2026-10-24 by Olu")), (False, True))
check("o15_ranked keeps ONLY its Internationals scope, which is in Production",
      (S.SOURCES["o15_ranked"]["sports"], "o15_ranked|soccer_o15_intl" in T.PAIR_OVERRIDES), (["soccer_o15_intl"], True))
check("no retired pair is a Production pair", sorted(RETIRED & set(T.PAIR_OVERRIDES)), [])
check("every Production pair is still on its source's live sports",
      [k for k in T.PAIR_OVERRIDES if k.split("|")[0] in S.SOURCES
       and k.split("|")[1] not in S.SOURCES[k.split("|")[0]]["sports"]], [])
check("the live FTTS 0.70-0.80 lane is untouched", S.SOURCES["ftts_no_70_80"]["sports"], ["soccer_ftts"])

print("\nthe run: a retired lane is not fetched and logs nothing; a live lane beside it still logs")


def row(sport, mid, price=0.55):
    start = NOW + dt.timedelta(hours=3)
    return dict(market_id=mid, sport=sport, venue="kalshi_binary", league="Premier League",
                start=start.isoformat(), date=start.date().isoformat(), price_a=price, price_b=1 - price + 0.02,
                price_draw=None, untraded=False, tradeable={"a": True, "b": True}, label=mid,
                side_a="Yes", side_b="No", url="u", volume=0.0, espn_home="H", espn_away="A")


sports = sorted({sp for _n, sp in SPLIT} | {"soccer_o15_intl"})
board = {sp: [row(sp, f"KX{sp.upper()}-26OCT25{i}") for i in range(2)] for sp in sports}
called = []


def stub(name):
    def fetch(sport, *a, **k):
        called.append((name, sport))
        return [dict(market_id=r["market_id"], pick="a") for r in board.get(sport, [])]
    return fetch


names = sorted({n for n, _sp in SPLIT}) + ["ftts_no_70_80"]
_ch, _st = S.CHALLENGERS, T._started
S.CHALLENGERS = {n: stub(n) for n in names}
T._started = lambda r, now: False
try:
    led = {"quotes": [], "meta": {}, "coverage": {}}
    with um.patch.object(S, "datetime", wraps=S.datetime) as m:
        m.now.side_effect = lambda tz=None: NOW
        T.publish(led, board, {}, verbose=False)
finally:
    S.CHALLENGERS, T._started = _ch, _st
logged = {f'{q["source"]}|{q["sport"]}' for q in led["quotes"]}
check("no retired pair was fetched", sorted(f"{n}|{s}" for n, s in called if f"{n}|{s}" in RETIRED), [])
check("no retired pair logged a quote or a bet", sorted(logged & RETIRED), [])
check("the live o15_ranked · Internationals and FTTS 0.70-0.80 lanes still log",
      {"o15_ranked|soccer_o15_intl", "ftts_no_70_80|soccer_ftts"} <= logged, True)

print("\nthe ledger: every retired pair keeps its rows, and the Soccer page lists it as Retired")
d, st = T.load(), T.load_stages()
counts = {k: sum(1 for q in T.all_bets(d) if f'{q.get("source")}|{q.get("sport")}' == k) for k in RETIRED}
check("every retired pair that ever bet still has its rows (o15_form_l10 · Cups never bet)",
      sorted(k for k, n in counts.items() if not n), ["o15_form_l10|soccer_o15_cup"])
rows = {f'{r["name"]}|{r["sport"]}': r for r in sport_tab.retired_rows(d, st, soccer_build.FAMILY)}
check("the Soccer page's Retired list holds all thirteen, the one that never bet included",
      sorted(RETIRED - set(rows)), [])
for k in sorted(RETIRED & set(rows)):
    r = rows[k]
    name, sport = k.split("|")
    a = T.assess(d, name, sport, since=T.record_since((st.get("pairs") or {}).get(k)), venues=T.TRADEABLE_VENUES)
    check(f"{k}: verdict Retired, the record it carried, the dated reason",
          (r["v"], r["a"]["n"], r["a"]["won"], r["gone"].startswith("Retired 2026-10-24")),
          ("retired", a["n"], a["won"], True))
live = {f'{r["name"]}|{r["sport"]}' for r in sport_tab.family_rows(d, st, soccer_build.FAMILY)}
check("no retired pair is in the live Soccer rules (tiles, Sandbox count)", sorted(live & RETIRED), [])
check("o15_ranked · Internationals is still a live Soccer row", "o15_ranked|soccer_o15_intl" in live, True)
html = soccer_build.build(d, st, NOW)
fold = html[html.find('id="retired"'):]
check("the Soccer page has a Retired rules fold", 'id="retired"' in html and "Retired rules" in fold, True)
check("each retired pair is drawn in it with its reason",
      sorted(k for k in RETIRED if f'data-source="{k.split("|")[0]}" data-sport="{k.split("|")[1]}"' not in fold), [])
check("and the fold carries the date", fold.count("Retired 2026-10-24 by Olu") >= len(RETIRED & set(rows)), True)
check("the main Sandbox pair list (no retired rows) leaves them out", sorted(
    {f'{r["name"]}|{r["sport"]}' for r in B.pair_list(d, st)} & RETIRED), [])

print("\ntennis: six Sandbox lanes retired, the 2-leg Kalshi combo and the UTR shortlist kept")
TENNIS = {"tennis_fav_band_3h|tennis", "pm_combo2|tennis_pmcombo", "pm_combo3|tennis_pmcombo",
          "pm_combo4|tennis_pmcombo", "tennis_combo3|tennis_combo", "tennis_combo4|tennis_combo"}
check("sandbox_sources names the same six", set(S.TENNIS_RETIRED_ON_2026_10_24), TENNIS)
for k in sorted(TENNIS):
    name, sport = k.split("|")
    meta = S.SOURCES[name]
    check(f"{k}: off the run, retired with a dated reason",
          (sport in meta["sports"], (meta.get("retired_sports") or {}).get(sport, "").startswith("Retired 2026-10-24 by Olu")),
          (False, True))
check("kept: tennis_combo2 (Kalshi 2-leg) and the UTR shortlist stay on their sports",
      (S.SOURCES["tennis_combo2"]["sports"], S.SOURCES["tennis_utr_shortlist_v1"]["sports"]), (["tennis_combo"], ["tennis"]))
check("the UTR shortlist went back to the Sandbox 2026-10-27, and no retired tennis pair is in Production", (
    "tennis_utr_shortlist_v1|tennis" in T.PAIR_OVERRIDES, sorted(TENNIS & set(T.PAIR_OVERRIDES))), (False, []))
called.clear()
tboard = {sp: [row(sp, f"KX{sp.upper()}-26OCT25{i}") for i in range(2)] for sp in ("tennis", "tennis_combo", "tennis_pmcombo")}
board.update(tboard)
_ch, _st = S.CHALLENGERS, T._started
S.CHALLENGERS = {n: stub(n) for n in sorted({k.split("|")[0] for k in TENNIS})}
T._started = lambda r, now: False
try:
    tled = {"quotes": [], "meta": {}, "coverage": {}}
    with um.patch.object(S, "datetime", wraps=S.datetime) as m:
        m.now.side_effect = lambda tz=None: NOW
        T.publish(tled, tboard, {}, verbose=False)
finally:
    S.CHALLENGERS, T._started = _ch, _st
check("no retired tennis lane was fetched or logged anything",
      (called, [q["id"] for q in tled["quotes"] if f'{q["source"]}|{q["sport"]}' in TENNIS]), ([], []))
tcount = {k: sum(1 for q in T.all_bets(d) if f'{q.get("source")}|{q.get("sport")}' == k) for k in TENNIS}
check("the retired tennis lanes that bet keep their rows",
      sorted(k for k in ("tennis_fav_band_3h|tennis", "pm_combo2|tennis_pmcombo", "pm_combo4|tennis_pmcombo") if not tcount[k]), [])
trows = {f'{r["name"]}|{r["sport"]}': r for r in sport_tab.retired_rows(d, st, tennis_build.FAMILY)}
check("the Tennis page's Retired list is the six", set(trows), TENNIS)
for k in ("tennis_fav_band_3h|tennis", "pm_combo2|tennis_pmcombo"):
    name, sport = k.split("|")
    a = T.assess(d, name, sport, since=T.record_since((st.get("pairs") or {}).get(k)), venues=T.TRADEABLE_VENUES)
    check(f"{k}: the record since its reset, as the page read it", (trows[k]["a"]["n"], trows[k]["a"]["won"]), (a["n"], a["won"]))
tlive = {f'{r["name"]}|{r["sport"]}' for r in sport_tab.family_rows(d, st, tennis_build.FAMILY)}
check("none of the six is a live Tennis row; the 2-leg Kalshi combo and the shortlist are",
      (sorted(tlive & TENNIS), {"tennis_combo2|tennis_combo", "tennis_utr_shortlist_v1|tennis"} <= tlive), ([], True))
thtml = tennis_build.build(d, st, NOW)
tfold = thtml[thtml.find('id="retired"'):]
check("the Tennis page draws all six in its Retired fold, dated",
      (sorted(k for k in TENNIS if f'data-source="{k.split("|")[0]}" data-sport="{k.split("|")[1]}"' not in tfold),
       tfold.count("Retired 2026-10-24 by Olu") >= 6), ([], True))
check("tennis_atp_low_over (its own ledger) still sits in the Sandbox list, not the Retired fold",
      'data-source="tennis_atp_low_over"' in thtml[:thtml.find('id="retired"')], True)

print("\nlane windows and the pre-flight follow the retirement")
check("the FTTS window closes once the one live NO lane holds its five picks",
      W.ftts_day_full("2026-10-25", {"quotes": [dict(source="ftts_no_70_80", bet=True, date="2026-10-25")] * S.FTTS_NO_PICKS}),
      True)
check("bund_o35 and bund_o35_fav are out of the pre-flight", {l for l, _s, _k in P.checks()} & {"bund_o35", "bund_o35_fav"}, set())

print("\nD2 (label rules): retired inside soccer_rules, rows kept, Retired on the Soccer page")
check("D2 is retired from 2026-10-24 with its reason", (SR.RETIRED["D2"]["on"], "3/11" in SR.RETIRED["D2"]["reason"]),
      ("2026-10-24", True))
check("retired from that day, Eastern, and not before",
      (SR.retired("D2", dt.datetime(2026, 10, 24, 3, 59, tzinfo=UTC)), SR.retired("D2", dt.datetime(2026, 10, 24, 4, 0, tzinfo=UTC)),
       SR.retired("D3", NOW)), (False, True, False))


def bev(series, home, away, bid, ask, day="26OCT25"):
    tag = f"{series}-{day}{home[:3].upper()}{away[:3].upper()}"
    return dict(event_ticker=tag, title=f"{home} vs {away}: BTTS",
                markets=[dict(ticker=f"{tag}-BTTS", title="Both Teams To Score", status="active",
                              yes_bid_dollars=str(bid), yes_ask_dollars=str(ask))])


ef = dict(kickoff=(NOW + dt.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%MZ"), league="Premier League",
          home="Everton", away="Arsenal", home_goals=None, away_goals=None, played=False, competitive=True)
e = bev("KXEPLBTTS", "Everton", "Arsenal", 0.55, 0.57)
before = dt.datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
check("the same O-D- v O+D+ match took D2 before the date and takes nothing after",
      ([p["rule"] for p in SR.picks_for(ef, ("O-D-", "O+D+"), e, before, "btts")],
       [p["rule"] for p in SR.picks_for(ef, ("O-D-", "O+D+"), e, NOW, "btts")]), (["D2"], []))
check("an O+D- v O-D- match still takes D3 after it", [p["rule"] for p in SR.picks_for(
    dict(ef, home="Osasuna", away="Santander", league="La Liga"), ("O+D-", "O-D-"),
    bev("KXLALIGABTTS", "Osasuna", "Santander", 0.54, 0.55), NOW, "btts")], ["D3"])
state = SR.load()
check("D2's ledger rows stay (11 settled at retirement)", len(state["rules"]["D2"]["picks"]) >= 11, True)
sec = SRB.section(state)
d2 = sec[sec.find('data-rule="D2"'):]
d2 = d2[:d2.find("</div>")]
check("the label-rules section marks D2 Retired, dated, with its record",
      ('data-retired="2026-10-24"' in d2, "Retired" in d2, "3/11" in d2), (True, True, True))
check("and no other label rule is marked", sec.count("data-retired="), 1)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
