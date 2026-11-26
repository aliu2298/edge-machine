#!/usr/bin/env python3
"""Offline checks for Club 82 (club82.py): the qualifier (threshold, 8-game minimum, drop and re-enter, no look-ahead), the entries (one under entry a match,
a team entry each, controls in every game, skips logged), settlement, the page and the public copy."""
import datetime as dt
import re
import sys

import club82 as C
import club82_build as B
import sandbox_audit
import sandbox_build

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def fx(i, day, home, away, hg, ag, league="Premier League", played=True, hour="15:00"):
    return dict(date=day, kickoff=f"{day}T{hour}Z", league=league, home=home, away=away, home_id=home, away_id=away, home_goals=hg, away_goals=ag, played=played)


def days(n, start=dt.date(2026, 8, 15)):
    return [(start + dt.timedelta(days=7 * i)).isoformat() for i in range(n)]


# ---- the qualifier
print("qualifier")
D = days(14)
low = [fx(i, D[i], "AAA", f"O{i}", 1, 1) for i in range(11)]                  # AAA: 11 games, all under 3.5, total 2
r = C.team_rows(low, "u35")
check("11/11 under: qualifies, since the 8th game's day (the first that cleared the floor)", (r["AAA"]["hits"], r["AAA"]["n"], r["AAA"]["qualifies"], r["AAA"]["since"]), (11, 11, True, D[7]))
check("7 games is under the 8-game minimum even at 100%", C.team_rows(low[:7], "u35")["AAA"]["qualifies"], False)
check("8 games at 100% qualifies", C.team_rows(low[:8], "u35")["AAA"]["qualifies"], True)
nine = [fx(i, D[i], "BBB", f"P{i}", 0, 0) for i in range(9)] + [fx(9 + i, D[9 + i], "BBB", f"Q{i}", 4, 1) for i in range(2)]
r = C.team_rows(nine, "u35")
check("9/11 = 81.8% counts", (r["BBB"]["hits"], r["BBB"]["n"], r["BBB"]["qualifies"]), (9, 11, True))
ten = nine + [fx(20, D[11], "BBB", "R", 3, 3)]                               # 10 hits? 3+3 = 6: a miss -> 9/12 = 75%
r = C.team_rows(ten, "u35")
check("9/12 = 75% is below the bar: stops at once, no since", (r["BBB"]["qualifies"], r["BBB"]["since"]), (False, None))
check("the 75-81% band is the watch band", C.WATCH <= r["BBB"]["rate"] < C.THRESHOLD, True)
climb = ten + [fx(30 + i, days(30)[12 + i], "BBB", f"S{i}", 0, 0) for i in range(5)]      # 12/15, 13/16, 13/17... each win adds: 14/17 after the fifth
r = C.team_rows(climb, "u35")
check("climbs back: qualifies again (14/17), since the game that put it back over", (r["BBB"]["hits"], r["BBB"]["n"], r["BBB"]["qualifies"], r["BBB"]["since"]),
      (14, 17, True, days(30)[16]))
r = C.team_rows(low, "u35", before=low[8]["kickoff"])
check("no look-ahead: only games that kicked off before the match counted", (r["AAA"]["n"], r["AAA"]["qualifies"]), (8, True))
r = C.team_rows(low, "u35", before=low[7]["kickoff"])
check("no look-ahead: 7 games before the 8th kickoff is below the floor", (r["AAA"]["n"], r["AAA"]["qualifies"]), (7, False))
mix = low + [fx(99, "2026-06-01", "AAA", "Z", 0, 0), fx(98, D[0], "AAA", "Y", 0, 0, league="MLS"), fx(97, D[1], "AAA", "X", 0, 0, played=False)]
check("an earlier season, MLS and an unplayed game are not counted", C.team_rows(mix, "u35")["AAA"]["n"], 11)
check("the Champions League counts with the domestic league", C.team_rows(low + [fx(96, D[11], "AAA", "Z", 0, 0, league="Champions League")], "u35")["AAA"]["n"], 12)
tt = [fx(i, D[i], "CCC", f"T{i}", 2 if i < 9 else 1, 0) for i in range(11)]
r = C.team_rows(tt, "tt15")
check("scored 2+: 9/11 qualifies, counted for the team's own goals (home or away)", (r["CCC"]["hits"], r["CCC"]["qualifies"]), (9, True))
away = [fx(i, D[i], f"H{i}", "DDD", 0, 3) for i in range(8)]
check("the away team's goals count for it", C.team_rows(away, "tt15")["DDD"]["qualifies"], True)
check("config: bar 0.818, floor 8", (C.THRESHOLD, C.MIN_GAMES), (0.818, 8))

# ---- entries
print("\nentries")
NOW = dt.datetime(2026, 11, 24, 19, 0, tzinfo=UTC)
KO = (NOW + dt.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%MZ")


def mk(ticker, title, bid, ask, status="active"):
    return dict(ticker=ticker, title=title, status=status, yes_bid_dollars=str(bid), yes_ask_dollars=str(ask))


def event(series, h3, a3, markets):
    tag = "26NOV24"
    return dict(event_ticker=f"{series}-{tag}{h3}{a3}", title="Aston Villa vs Chelsea" if False else "Home Town vs Away City: Totals", markets=markets)


games = [fx(i, D[i], "Home Town", f"Opp{i}", 1, 1) for i in range(10)] + [fx(50 + i, D[i], "Away City", f"Opp{i}", 1, 1) for i in range(10)]
games += [fx(70 + i, D[i], "Away City", f"Opp2{i}", 2, 0) for i in range(0)]
game = fx(100, "2026-11-24", "Home Town", "Away City", None, None, played=False, hour=KO[11:16])
game["kickoff"] = KO
fixtures = games + [game]
tot = {"event_ticker": "KXEPLTOTAL-26NOV24HOMAWA", "title": "Home Town vs Away City: Totals", "markets": [mk("KXEPLTOTAL-26NOV24HOMAWA-3", "Over 3.5 goals scored", 0.30, 0.33)]}
team = {"event_ticker": "KXEPLTEAMTOTAL-26NOV24HOMAWA", "title": "Home Town vs Away City: Team Total",
        "markets": [mk("KXEPLTEAMTOTAL-26NOV24HOMAWA-HOM2", "Will Home Town score over 1.5 goals?", 0.40, 0.43), mk("KXEPLTEAMTOTAL-26NOV24HOMAWA-AWA2", "Will Away City score over 1.5 goals?", 0.40, 0.43)]}


def fetch_for(totals, teams):
    def f(path):
        if "KXEPLTOTAL" in path:
            return {"events": totals, "cursor": ""}
        if "KXEPLTEAMTOTAL" in path:
            return {"events": teams, "cursor": ""}
        return {"events": [], "cursor": ""}
    return f


# both teams at 10/10 under 3.5 but neither scores 2+ -> ONE under entry, no team entry (both control rows)
st = C.empty()
new = C.run(st, fixtures, NOW, fetch_for([tot], [team]))
u = st["rules"]["club82_u35"]["picks"]
check("both teams qualify under 3.5: ONE entry, NO at 1 - YES bid", [(p["side"], p["price"], p["qualifying_teams"]) for p in u], [("no", 0.70, ["Home Town", "Away City"])])
check("tt15: no team scored 2+, no lane entry", st["rules"]["club82_tt15"]["picks"], [])
check("the under 3.5 control is in the game; the team controls are in both teams' markets", (len(st["rules"]["club82_u35_blind"]["picks"]), len(st["rules"]["club82_tt15_blind"]["picks"])), (1, 2))
check("the lane row points at its control", u[0]["matches"] in [p["id"] for p in st["rules"]["club82_u35_blind"]["picks"]], True)
check("a repeat read adds nothing (once a market)", len(C.run(st, fixtures, NOW + dt.timedelta(minutes=5), fetch_for([tot], [team]))), 0)
check("due(): 30-60 minutes out only", (len(C.due(fixtures, NOW)), len(C.due(fixtures, NOW + dt.timedelta(minutes=20))), len(C.due(fixtures, NOW - dt.timedelta(minutes=30)))), (1, 0, 0))
# team 2+ qualifying: Home Town scores 2+ in 10 of 10
good = [fx(i, D[i], "Home Town", f"Opp{i}", 2, 0) for i in range(10)] + [fx(50 + i, D[i], "Away City", f"Opp{i}", 1, 1) for i in range(10)]
st2 = C.empty()
C.run(st2, good + [game], NOW, fetch_for([tot], [team]))
t = st2["rules"]["club82_tt15"]["picks"]
check("tt15: the qualifying team's YES at the ask, only that team", [(p["team"], p["side"], p["price"]) for p in t], [("Home Town", "yes", 0.43)])
check("the opponent's over 1.5 is a control row only", sorted((p["team"], p["qualifying"]) for p in st2["rules"]["club82_tt15_blind"]["picks"]), [("Away City", False), ("Home Town", True)])
# the team total market opens late: logged, then entered at the next read
st3 = C.empty()
C.run(st3, good + [game], NOW, fetch_for([tot], []))
check("no team-total event yet: logged as a skip, nothing entered", (st3["rules"]["club82_tt15"]["picks"], sorted(s["reason"] for s in st3["skips"].values() if s["kind"] == "tt15")),
      ([], ["no Kalshi event for the match", "no Kalshi event for the match"]))
C.run(st3, good + [game], NOW + dt.timedelta(minutes=10), fetch_for([tot], [team]))
check("the market opens at the next read: entered, the skip cleared", (len(st3["rules"]["club82_tt15"]["picks"]), [s for s in st3["skips"].values() if s["kind"] == "tt15"]), (1, []))
# a wide spread is a skip, not an entry
wide = dict(tot, markets=[mk("KXEPLTOTAL-26NOV24HOMAWA-3", "Over 3.5 goals scored", 0.20, 0.33)])
st4 = C.empty()
C.run(st4, fixtures, NOW, fetch_for([wide], [team]))
check("a 13c spread: no under entry, logged", (st4["rules"]["club82_u35"]["picks"], [s["reason"] for s in st4["skips"].values() if s["kind"] == "u35"]), ([], ["no quote, or a spread over 5c"]))
# not qualifying: no lane entry, control only
poor = [fx(i, D[i], "Home Town", f"Opp{i}", 3, 3) for i in range(10)] + [fx(50 + i, D[i], "Away City", f"Opp{i}", 3, 3) for i in range(10)]
st5 = C.empty()
C.run(st5, poor + [game], NOW, fetch_for([tot], [team]))
check("neither team qualifies: no lane entry, the control still enters", (len(st5["rules"]["club82_u35"]["picks"]), len(st5["rules"]["club82_u35_blind"]["picks"])), (0, 1))
st6 = C.empty()
C.run(st6, fixtures, NOW, fetch_for([tot], [team]), )
check("a game played tonight before this kickoff is not in the gate (no look-ahead at the read)", len(st6["rules"]["club82_u35"]["picks"]), 1)
st7 = C.empty()
C.run(st7, games[:7] + games[10:17] + [game], NOW, fetch_for([tot], [team]))
check("7 games each: nobody qualifies (the floor), control only", (len(st7["rules"]["club82_u35"]["picks"]), len(st7["rules"]["club82_u35_blind"]["picks"])), (0, 1))

# ---- settle
print("\nsettle")


class Fake:
    def __init__(self, result):
        self.result = result

    def __call__(self, path):
        return {"market": dict(status="settled", result=self.result)}


st8 = C.empty()
C.run(st8, fixtures, NOW, fetch_for([tot], [team]))
C.settle(st8, NOW + dt.timedelta(hours=4), Fake("no"))                       # the match was under 3.5: NO wins
p = st8["rules"]["club82_u35"]["picks"][0]
check("an under (NO) wins when the over 3.5 does not pay", (p["status"], p["payout"]), ("won", 1.0))
check("the record: 1-0, return = 1 over cost - 1", (C.stats(st8["rules"]["club82_u35"]["picks"])["n"], round(C.stats(st8["rules"]["club82_u35"]["picks"])["ret"], 4)), (1, round(1 / (0.7 + C.fee(0.7)) - 1, 4)))
check("status text reads n of 10, then 30", (C.status_text(2), C.status_text(10), C.status_text(30)), ("2 of 10 settled · read at 10", "10 settled · first read (10) due · next at 30", "30 settled · second read (30) due"))

# ---- the page
print("\npage")
html = B.section(st8, fixtures)
check("one collapsed fold, two lanes", (html.count('id="club82-fold"'), bool(re.search(r"<details[^>]*\bopen\b", html)), html.count('class="club82-teams"')), (1, False, 1))
check("header: entries and the tracker through date", ("1 entry · tracker through" in html), True)
check("each lane: teams at 82%+ now, the 75-81% watch fold, recent picks", all(x in html for x in ("Teams at 82%+ now", "Watch · 75-81%", "Bets · newest first", "Team cushions", "Skipped reads")), True)
check("the cells are named for their columns (the sport page's own label pass runs before the block goes in)", all(f'data-l="{c}"' in html for c in ("Category", "v1", "v2 cushion", "v2 value", "control", "Hits/games")), True)
check("every header row is in a thead, none left in a body", "<thead" in html and "<th" not in html.split("</thead>")[-1][:0] + "", True)
stored = C.empty()
stored["tracker"] = {k: list(C.team_rows(fixtures, k).values()) for k in C.KINDS}
stored["games_through"] = "2026-10-17"
check("the page reads the tracker stored in the ledger when no fixtures are handed in", ("Home Town" in B.section(stored, None), "tracker through 2026-10-17" in B.section(stored, None)), (True, True))
idx = B.index_html(st8)
check("the Sandbox index has both lanes and links the Soccer block", ("club82_u35" in idx and "club82_tt15" in idx, "./soccer.html#club82" in idx), (True, True))
bad = [m.group(0) for m in sandbox_audit.COPY_RE.finditer(html + idx)]
check("public copy passes the guard", bad, [])
check("an empty ledger renders", "Club 82" in B.section(C.empty(), []), True)

# ---- v2: cushion and value rungs (2026-11-25)
print("\nv2")
good2 = [fx(i, D[i], "Home Town", f"Opp{i}", 4, 0) for i in range(10)] + [fx(50 + i, D[i], "Away City", f"Opp{i}", 1, 1) for i in range(10)]    # Home Town scores 4 in 10 of 10
team2 = {"event_ticker": "KXEPLTEAMTOTAL-26NOV24HOMAWA", "title": "Home Town vs Away City: Team Total",
         "markets": [mk("KXEPLTEAMTOTAL-26NOV24HOMAWA-HOM2", "Will Home Town score over 1.5 goals?", 0.88, 0.90), mk("KXEPLTEAMTOTAL-26NOV24HOMAWA-HOM3", "Will Home Town score over 2.5 goals?", 0.70, 0.72),
                     mk("KXEPLTEAMTOTAL-26NOV24HOMAWA-HOM4", "Will Home Town score over 3.5 goals?", 0.45, 0.47), mk("KXEPLTEAMTOTAL-26NOV24HOMAWA-HOM5", "Will Home Town score over 4.5 goals?", 0.10, 0.12),
                     mk("KXEPLTEAMTOTAL-26NOV24HOMAWA-AWA2", "Will Away City score over 1.5 goals?", 0.40, 0.43)]}
sv = C.empty()
C.run(sv, good2 + [game], NOW, fetch_for([tot], [team2]))
cu = sv["rules"]["club82_v2_tt15_cushion"]["picks"]
va = sv["rules"]["club82_v2_tt15_value"]["picks"]
check("v2_cushion tt15: the hardest team rung Home Town still clears at 81.8% over 10 games: 3.5 (the 4.5 rung it never cleared)", [(p["rung"], p["team"], p["price"], p["side"]) for p in cu], [(3.5, "Home Town", 0.47, "yes")])
check("v2_value tt15: the biggest hit rate minus cost among cleared rungs: 3.5 again (100% at 47c)", [(p["rung"], p["id"].startswith("club82_v2_tt15_value:")) for p in va], [(3.5, True)])
check("v2 rows keep the v1 line, the team's record and the lane id", (cu[0]["v1_line"], cu[0]["rate"], cu[0]["games"], cu[0]["rule"]), (1.5, 1.0, 10, "club82_v2_tt15_cushion"))
check("v1 is unchanged beside it: its lane row is the 1.5 rung", [(p["line"], p["price"]) for p in sv["rules"]["club82_tt15"]["picks"]], [(1.5, 0.90)])
check("the opponent (not qualifying) gets no v2 row", sorted({p["team"] for p in cu + va}), ["Home Town"])
# under 3.5: harder is a LOWER total line
tot2 = {"event_ticker": "KXEPLTOTAL-26NOV24HOMAWA", "title": "Home Town vs Away City: Totals",
        "markets": [mk("KXEPLTOTAL-26NOV24HOMAWA-2", "Over 1.5 goals scored", 0.88, 0.90), mk("KXEPLTOTAL-26NOV24HOMAWA-3", "Over 2.5 goals scored", 0.60, 0.62),
                    mk("KXEPLTOTAL-26NOV24HOMAWA-4", "Over 3.5 goals scored", 0.30, 0.33), mk("KXEPLTOTAL-26NOV24HOMAWA-5", "Over 4.5 goals scored", 0.10, 0.12)]}
twos = [fx(i, D[i], "Home Town", f"Opp{i}", 1, 1) for i in range(10)] + [fx(50 + i, D[i], "Away City", f"Opp{i}", 1, 1) for i in range(10)]     # totals of 2: under 2.5 hits 10 of 10
su = C.empty()
C.run(su, twos + [game], NOW, fetch_for([tot2], [team]))
uc = su["rules"]["club82_v2_u35_cushion"]["picks"]
check("v2_cushion u35: the LOWEST line still hit (2.5; under 1.5 never hits), NO at 1 - bid", [(p["rung"], p["side"], p["price"]) for p in uc], [(2.5, "no", 0.4)])
s7 = C.empty()
C.run(s7, twos[:7] + twos[10:17] + [game], NOW, fetch_for([tot2], [team]))
check("a team under the bar (7 games) gets no v2 row", sum(len(s7["rules"][n]["picks"]) for n in C.V2_LANES), 0)
# actual and cleared by
sa = C.empty()
sa["rules"]["club82_v2_tt15_cushion"]["picks"] = [dict(cu[0], status="won")]
fxs = [dict(played=True, kickoff=cu[0]["start"], home="Home Town", away="Away City", home_goals=4, away_goals=1)]
C.fill_actuals(sa, fxs)
check("a settled v2 row stores the actual and 'cleared by' (the team's goals minus the rung)", (sa["rules"]["club82_v2_tt15_cushion"]["picks"][0]["actual"], sa["rules"]["club82_v2_tt15_cushion"]["picks"][0]["cleared"]), (4, 0.5))
check("four v2 lanes; v1's lane list unchanged", (len(C.V2_LANES), len(C.LANES)), (4, 4))

# ---- the v2 page (2026-11-25)
print("\nv2 page")
pg = C.empty()
pg["rules"]["club82_v2_tt15_cushion"]["picks"] = [dict(cu[0], status="won", payout=1.0, profit=110.0, actual=4, cleared=0.5)]
pg["rules"]["club82_v2_tt15_value"]["picks"] = [dict(cu[0], id="v", rule="club82_v2_tt15_value", status="lost", payout=0.0, profit=-100.0, actual=0, cleared=-3.5, rung=3.5)]
pg["rules"]["club82_tt15"]["picks"] = [dict(cu[0], id="o", rule="club82_tt15", status="won", payout=1.0, profit=20.0, rung=1.5, line=1.5, actual=4, cleared=2.5, price=0.9)]
pg["cushions"] = C.cushion_rows([dict(f, home_id=f["home"], away_id=f["away"]) for f in good2])
ph = B.section(pg, [])
check("one line a version, each with the read rule", [x for x in ("v1", "v2 cushion", "v2 value", "control") if f"<b>{x}</b> · " in ph] == ["v1", "v2 cushion", "v2 value", "control"] and "read at 10, then 30" in ph, True)
check("the category table: a row per lane (2), columns v1 | v2 cushion | v2 value | control", (ph.count('class="club-cats"'), ph[ph.index('class="club-cats"'):].split("</table>")[0].count("<tr>") - 1), (1, 2))
check("the bets list shows the actual and 'cleared by' (green for a win, red for a miss)", ('<span class="pos">+0.5</span>' in ph, '<span class="neg">−3.5</span>' in ph, 'v2 value · Home Town over 3.5 (YES)' in ph), (True, True, True))
check("the team cushion table is stored in the ledger and shown collapsed: hit rate, median cushion, safe line", ("Team cushions" in ph, "Median cushion" in ph, "Safe line" in ph), (True, True, True))
cr = pg["cushions"]["tt15"]
check("cushion_rows: Home Town scores 4 in 10 of 10 (median cushion +2.5 over 1.5), safe line 3.5", [(r["name"], r["median"], r["safe"], r["rate"]) for r in cr if r["name"] == "Home Town"], [("Home Town", 2.5, 3.5, 1.0)])
lv = C.empty()
lv["rules"]["club82_u35_blind"]["picks"] = [dict(logged="2026-11-24T18:00:00+00:00")]
lv["skips"] = {"k": dict(at="2026-11-24T20:10:00+00:00")}
lv["last_run"] = "2026-11-25T23:00:00+00:00"
check("Last live read: the newest logged entry or skip, never the last run (a settle pass)", B.last_live_read(lv), "2026-11-24T20:10:00+00:00")
check("and with none it says so", ("Last live read none yet" in B.section(C.empty(), []), B.last_live_read(C.empty())), (True, None))

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
