#!/usr/bin/env python3
"""The Research Control Center: the site root's model and page (redesign, phase 2).

Every number on the page comes from the tracker's own state, so the model is tested on
fixtures that stand in for each file it reads: a ledger, a stage file, a feed, an NBA
board, a trading ledger, closing-price writer stamps and workflow runs. One fixture per
area status (Healthy, Stale, Attention, Waiting) and one per attention type (a bet open
past its start, a feed that could not be read, a Production pair paused or near the
stale-pair demotion, a failed workflow run, a closing-price writer gone quiet). No
network: the workflow-run reader is fed a fake opener. Nothing reads data/.
"""
import datetime
import io
import json
import os
import re
import sys
from datetime import timedelta, timezone

import control_center as CC
import sandbox_build as SB
import sandbox_sources as S
import sandbox_track as T
import shell_build
import site_root

ROOT = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


NOW = datetime.datetime(2026, 10, 11, 19, 30, tzinfo=timezone.utc)      # a Sunday
ISO = NOW.isoformat()
STAGES_EMPTY = {"pairs": {}, "events": []}
BLOB_EMPTY = {"leads": {}, "pairs": {}}


def _q(i, source, sport, status="open", hours=6, **over):
    """One ledger bet. `hours` is the start relative to NOW (negative = already started)."""
    start = NOW + timedelta(hours=hours)
    q = dict(id=f"{source}:{sport}:{i}", source=source, sport=sport, bet=True, status=status,
             pick="a", price=0.6, price_a=0.6, price_b=0.42, price_draw=None, venue="kalshi_binary",
             market_id=f"KXEPLTOTAL-26OCT{10 + i:02d}AAABBB-2", label=f"Alpha {i} v Beta {i}: over 1.5 goals",
             side_a="Yes", side_b="No", start=start.isoformat(), logged=(start - timedelta(hours=8)).isoformat(),
             date=start.date().isoformat(), stake=100.0, pnl=0.0, result=None,
             league="Premier League", espn_home=f"Alpha {i}", espn_away=f"Beta {i}", start_source="espn")
    if status == "won":
        q.update(result="a", pnl=66.67, settled=(start + timedelta(hours=3)).isoformat())
    elif status == "lost":
        q.update(result="b", pnl=-100.0, settled=(start + timedelta(hours=3)).isoformat())
    q.update(over)
    return q


def _ledger(quotes, coverage=None, lane_reads=None, updated=ISO, feed_status=None):
    meta = {"created": "2026-09-10T00:00:00+00:00", "updated": updated}
    if lane_reads is not None:
        meta["lane_reads"] = lane_reads
    d = {"quotes": list(quotes), "coverage": coverage or {}, "meta": meta}
    if feed_status is not None:
        d["feed_status"] = feed_status
    return d


def _model(d=None, st=None, blob=None, **inputs):
    return CC.model(d if d is not None else _ledger([]), st or STAGES_EMPTY, blob or BLOB_EMPTY, NOW,
                    **dict(dict(nba={}, market={}, closes={}, runs=None), **inputs))


def _area(m, key):
    return next(a for a in m["areas"] if a["key"] == key)


# ---------------------------------------------------------------------------
print("the clock: an interval counted on a calendar")
# ---------------------------------------------------------------------------
fri = datetime.datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
eq(CC.deadline(fri, 7), fri + timedelta(hours=7), "seven hours on every day is seven hours later")
eq(CC.deadline(fri, 36, "weekdays"), datetime.datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc),
   "36 weekday hours from Friday 20:00Z skip the weekend and land Tuesday 08:00Z")
thu = datetime.datetime(2026, 10, 8, 22, 0, tzinfo=timezone.utc)
eq(CC.deadline(thu, 30, "trading_days"), datetime.datetime(2026, 10, 12, 4, 0, tzinfo=timezone.utc),
   "30 trading-day hours from Thursday 22:00Z (18:00 ET) run through Friday ET (29 by 03:00Z Saturday) and resume Monday 00:00 ET")
wed = datetime.datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)
ok(CC.deadline(wed, 30, "trading_days") > datetime.datetime(2026, 11, 28, tzinfo=timezone.utc),
   "Thanksgiving does not count as a trading day")
eq(CC.EXPECTED["soccer"], (7, "always"), "soccer: a 3-hourly lane is stale past 7h, the pages' own bar")
eq(CC.EXPECTED["crypto"], (30, "always"), "crypto: one read a day, stale past 30h")
eq(CC.EXPECTED["commodities"], (30, "trading_days"), "commodities: 30h on trading days only")
eq(CC.EXPECTED["nba"], (36, "always"), "NBA: a daily board, stale past 36h")
eq(CC.EXPECTED["trading"], (36, "weekdays"), "trading: 36h on weekdays only")

# ---------------------------------------------------------------------------
print("\nthe tracker stamps the lanes it read")
# ---------------------------------------------------------------------------
ok(T.lane_read_signal({"kalshi_venue": 12, "polymarket_us": 0}), "a venue listing is a read")
ok(T.lane_read_signal({"kalshi_venue": 0, "o15_ranked": {"offered": 55, "picked": 0}}),
   "a rule that saw rows is a read, even with nothing picked")
ok(not T.lane_read_signal({"kalshi_venue": 0, "o15_ranked": {"offered": 0, "picked": 0}}),
   "an empty board is not a read")
ok(not T.lane_read_signal(None) and not T.lane_read_signal({}), "no cell is not a read")
prev = {"soccer": "2026-10-11T16:00:00+00:00", "crypto_fav": "2026-10-10T18:11:00+00:00"}
after = T.lane_reads_after(prev, {"soccer": {"kalshi_venue": 3}, "crypto_fav": {"kalshi_venue": 0},
                                  "tennis": {"polymarket_us_listed": 5}}, ISO)
eq(after, {"soccer": ISO, "crypto_fav": "2026-10-10T18:11:00+00:00", "tennis": ISO},
   "a lane read this run takes the run's stamp; one not read keeps its last")
eq(T.lane_reads_after(None, {}, ISO), {}, "nothing read, nothing stamped")
ok("lane_reads_after(" in open(os.path.join(ROOT, "sandbox_track.py")).read().split("d[\"coverage\"] = coverage", 1)[1][:400],
   "the tracker stamps lane reads beside the coverage it stores")

# ---------------------------------------------------------------------------
print("\narea status: Healthy, Stale, Attention, Waiting")
# ---------------------------------------------------------------------------
read_now = {"soccer": ISO, "tennis": ISO, "cricket": ISO, "crypto_fav": ISO, "commodities_fav": ISO}
healthy = _model(_ledger([_q(1, "o15_ranked", "soccer_o15")], lane_reads=read_now),
                 nba={"built": ISO, "games": [], "teams": {}},
                 market={"meta": {"updated": ISO}, "research": {"r1": {}}, "trades": []})
eq([a["status"] for a in healthy["areas"]], ["healthy"] * 7, "every area read just now with nothing wrong is Healthy")
eq(healthy["tiles"]["healthy"], (7, 7), "the tile counts 7 of 7")
eq(healthy["tiles"]["attention"], 0, "and nothing needs attention")
eq([a["label"] for a in healthy["areas"]], ["Soccer", "Cricket", "Tennis", "Crypto", "Commodities", "NBA", "Trading"],
   "the seven areas, in the site's order")

old = (NOW - timedelta(hours=9)).isoformat()
stale = _model(_ledger([], lane_reads={"soccer": old, "tennis": ISO, "cricket": ISO}, updated=old))
eq(_area(stale, "soccer")["status"], "stale", "a soccer lane last read 9h ago is Stale (7h bar)")
eq(_area(stale, "tennis")["status"], "healthy", "a tennis lane read now is Healthy")
eq(_area(stale, "crypto")["status"], "waiting", "a lane with no stamp, no coverage and no row is Waiting")
eq(_area(stale, "nba")["status"], "waiting", "an NBA board that was never built is Waiting")
eq(_area(stale, "trading")["status"], "waiting", "a trading ledger never updated is Waiting")
crypto_day = _model(_ledger([], lane_reads={"crypto_fav": (NOW - timedelta(hours=26)).isoformat()}))
eq(_area(crypto_day, "crypto")["status"], "healthy", "crypto read 26h ago is still inside its daily interval")
crypto_late = _model(_ledger([], lane_reads={"crypto_fav": (NOW - timedelta(hours=31)).isoformat()}))
eq(_area(crypto_late, "crypto")["status"], "stale", "and 31h ago is Stale")
# Commodities last read Friday 16:30Z; Sunday 19:30Z is 51 hours later but only 7.5 trading-day hours.
cmd = _model(_ledger([], lane_reads={"commodities_fav": "2026-10-09T16:30:00+00:00"}))
eq(_area(cmd, "commodities")["status"], "healthy", "commodities read on Friday is Healthy on Sunday: the weekend does not count")
cmd_old = _model(_ledger([], lane_reads={"commodities_fav": "2026-10-07T16:30:00+00:00"}))
eq(_area(cmd_old, "commodities")["status"], "stale", "but a read from Wednesday is Stale by Sunday")
trade = _model(market={"meta": {"updated": "2026-10-09T20:11:36+00:00"}, "research": {"a": {}}, "trades": []})
eq(_area(trade, "trading")["status"], "healthy", "trading updated Friday evening is Healthy on Sunday")
nba_old = _model(nba={"built": (NOW - timedelta(hours=40)).isoformat(), "games": []})
eq(_area(nba_old, "nba")["status"], "stale", "an NBA board 40h old is Stale")
ok("No successful read inside 7h" in CC._area_card(_area(stale, "soccer"), NOW),
   "a stale card says what interval it missed")
ok("never read" in CC._area_card(_area(stale, "crypto"), NOW), "a waiting card says it was never read")

print("\nwhere the last read comes from")
cov = {"soccer": {"kalshi_venue": 10}, "soccer_o15": {"kalshi_venue": 0}}
from_cov = _model(_ledger([], coverage=cov, updated=ISO))
eq(_area(from_cov, "soccer")["last_read"], NOW, "without a stamp, the last run's coverage says soccer was read on that run")
eq(_area(from_cov, "tennis")["status"], "waiting", "a lane the last run did not read, with no row, is Waiting")
logged = _q(1, "o15_ranked", "soccer_o15", logged=(NOW - timedelta(hours=5)).isoformat())
from_row = _model(_ledger([logged], coverage={}, updated=None))
eq(_area(from_row, "soccer")["last_read"], NOW - timedelta(hours=5), "failing both, the newest row the lane logged")
stamped = _model(_ledger([logged], coverage=cov, lane_reads={"soccer_o15": (NOW - timedelta(hours=1)).isoformat()}, updated=old))
eq(_area(stamped, "soccer")["last_read"], NOW - timedelta(hours=1),
   "a stamp newer than the run and the row wins; the newest of the three is the read")

# ---------------------------------------------------------------------------
print("\nthe cards' counts")
# ---------------------------------------------------------------------------
quotes = [
    _q(1, "o15_ranked", "soccer_o15", "open", hours=6),            # next 24h
    _q(2, "o15_ranked", "soccer_o15", "open", hours=30),           # open, later
    _q(3, "o15_ranked", "soccer_o15", "won", hours=-48),           # settled inside 14d
    _q(4, "o15_ranked", "soccer_o15", "lost", hours=-24 * 20),     # settled outside 14d
    _q(5, "tennis_fav_band_3h", "tennis", "open", hours=2, market_id="KXATPMATCH-26OCT12AAABBB-A"),
    _q(6, "oddspedia", "cricket", "won", hours=-12),
]
st = {"pairs": {"o15_ranked|soccer_o15": {"stage": "production", "by_hand": "2026-10-08",
                                           "ready_at": "2026-10-08T17:50:08+00:00",
                                           "promoted_at": "2026-10-08T17:50:08+00:00"}}}
counts = _model(_ledger(quotes, lane_reads=read_now), st)
soccer = _area(counts, "soccer")
eq((soccer["open"], soccer["settled"], soccer["next24"]), (2, 1, 1),
   "soccer: two open, one settled in the window, one starting in the next 24h")
n_soccer = sum(1 for r in SB.pair_list(_ledger(quotes), st) if not SB.eliminated(r) and SB.family(r["sport"]) == "Soccer")
eq(soccer["coverage"], f"{n_soccer} rules · 1 in Production",
   f"soccer's coverage line counts every configured soccer rule and how many are in Production ({soccer['coverage']})")
eq((_area(counts, "tennis")["open"], _area(counts, "cricket")["settled"]), (1, 1), "tennis and cricket count their own rows")
eq(_area(counts, "crypto")["coverage"], f"{len(S.COINS)} coins checked", "crypto's coverage line is its coins")
eq(_area(counts, "commodities")["coverage"], f"{len(S.COMMOD_FAV_SERIES)} series checked", "commodities' is its series")
eq(counts["tiles"]["pairs"], 1, "the pairs tile counts Production pairs")
eq(counts["tiles"]["open"], 3, "the open tile counts every open bet")
nba = {"built": ISO, "teams": {t: {} for t in range(30)}, "games": [
    {"id": "a", "start": (NOW + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%MZ"), "completed": False},
    {"id": "b", "start": (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ"), "completed": False},
    {"id": "c", "start": (NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%MZ"), "completed": True},
    {"id": "d", "start": (NOW - timedelta(days=20)).strftime("%Y-%m-%dT%H:%MZ"), "completed": True},
    {"id": "e", "start": (NOW + timedelta(days=3)).strftime("%Y-%m-%dT%H:%MZ"), "completed": False},
]}
nba_area = _area(_model(nba=nba), "nba")
eq((nba_area["open"], nba_area["settled"], nba_area["next24"], nba_area["coverage"]), (1, 1, 1, "5 games · 30 teams"),
   "NBA: one game in play, one completed in the window, one tipping off inside 24h")
market = {"meta": {"updated": ISO}, "research": {"a": {}, "b": {}}, "trades": [
    {"status": "open", "exit_day": None}, {"status": "open"},
    {"status": "closed", "exit_day": (NOW - timedelta(days=3)).date().isoformat()},
    {"status": "closed", "exit_day": (NOW - timedelta(days=30)).date().isoformat()},
]}
tr = _area(_model(market=market), "trading")
eq((tr["open"], tr["settled"], tr["next24"], tr["coverage"]), (2, 1, None, "2 rules under test"),
   "trading: open trades, closes in the window, no scheduled events")
ok("<dd>—</dd>" in CC._area_card(tr, NOW), "a card with no scheduled events prints a dash")

# ---------------------------------------------------------------------------
print("\nneeds attention, one fixture per type")
# ---------------------------------------------------------------------------
# A bet still open 48h past its start.
overdue = _q(7, "oddspedia", "cricket", "open", hours=-48, label="South Africa vs Australia",
             venue="polymarket_us", side_a="South Africa", side_b="Australia")
m = _model(_ledger([overdue], lane_reads=read_now))
items = m["attention"]
eq([i["kind"] for i in items], ["overdue"], "one item: the overdue bet")
eq(items[0]["area"], "cricket", "filed under its area")
ok("South Africa vs Australia" in items[0]["text"] and "48h past its start" in items[0]["text"], f"it names the contest and the lag ({items[0]['text']})")
eq(items[0]["href"], "./cricket.html", "and links the area's page")
eq(_area(m, "cricket")["status"], "attention", "the area is Attention")
eq(_area(m, "cricket")["items"], items, "the card carries the item")
eq(m["tiles"]["healthy"], (4, 7), "four other lanes read now are healthy")
fresh = _q(8, "oddspedia", "cricket", "open", hours=-6)
eq(_model(_ledger([fresh], lane_reads=read_now))["attention"], [], "a bet 6h past its start is not yet overdue")

# A feed that could not be read: pin_totals logged nothing on every sport it covers (the bare
# count shape; an offered-row dict with 0 offered is an empty board, not a dead feed).
cov_dark = {sp: {"kalshi_venue": 5, "pin_totals": 0} for sp in S.SOURCES["pin_totals"]["sports"]}
feeds = SB.dark_feeds(_ledger([], coverage=cov_dark))
eq([f[0] for f in feeds], ["pin_totals"], "dark_feeds names the feed with nothing offered on every sport")
m = _model(_ledger([], coverage=cov_dark, lane_reads=read_now))
eq([i["kind"] for i in m["attention"]], ["feed"], "one item: the feed")
ok("Pinnacle" in m["attention"][0]["text"] and "could not be read" in m["attention"][0]["text"], "it names the feed")
eq((m["attention"][0]["area"], m["attention"][0]["href"]), ("soccer", "./sandbox.html"), "filed under soccer, linking the Sandbox")
down = _model(_ledger([], coverage={}, feed_status={"oddspedia": "down: 403"}, lane_reads=read_now))
ok(any(i["kind"] == "feed" and "403" in i["text"] and i["area"] == "cricket" for i in down["attention"]),
   "an adapter that reported itself down is listed with its reason")
ok("Feed check" in SB.feed_health(_ledger([], coverage=cov_dark)), "feed_health still prints the same feeds")

# A Production pair paused in PAUSED_LANES, and one near the stale-pair demotion.
paused_key = next(k for k in T.PAIR_OVERRIDES if S.lane_paused(*k.split("|", 1)))
pname, psport = paused_key.split("|", 1)
st_p = {"pairs": {paused_key: {"stage": "production", "by_hand": "2026-10-08", "ready_at": "2026-10-08T17:50:08+00:00",
                               "promoted_at": "2026-10-08T17:50:08+00:00"}}}
m = _model(_ledger([], lane_reads=read_now), st_p)
eq([i["kind"] for i in m["attention"]], ["paused"], f"one item: {paused_key} is paused")
demote = datetime.datetime(2026, 10, 8, 17, 50, 8, tzinfo=timezone.utc) + timedelta(days=T.STALE_DAYS)
ok(f"demotes it on {demote.strftime('%b')} {demote.day}" in m["attention"][0]["text"]
   and "paused in PAUSED_LANES" in m["attention"][0]["text"]
   and f"({max(0, int((demote - NOW).total_seconds() // 86400))} days)" in m["attention"][0]["text"],
   f"it says the pair is paused and when the stale-pair net demotes it ({m['attention'][0]['text']})")
eq(m["attention"][0]["href"], "./production.html", "and links Production")
quiet_key = "team1_form_l5|soccer_team1"
quiet_last = NOW - timedelta(days=T.STALE_DAYS - 3)
st_q = {"pairs": {quiet_key: {"stage": "production", "by_hand": "2026-09-18", "ready_at": "2026-09-18T00:51:24+00:00",
                              "promoted_at": "2026-09-18T00:43:21+00:00"}}}
quiet_bet = _q(9, "team1_form_l5", "soccer_team1", "won", hours=-24 * (T.STALE_DAYS - 3), logged=quiet_last.isoformat())
m = _model(_ledger([quiet_bet], lane_reads=read_now), st_q)
eq([i["kind"] for i in m["attention"]], ["quiet"], "one item: a pair three days from demotion")
ok("(3 days)" in m["attention"][0]["text"] and "no new bet since" in m["attention"][0]["text"],
   f"it says how long is left ({m['attention'][0]['text']})")
safe_bet = _q(9, "team1_form_l5", "soccer_team1", "won", hours=-24, logged=(NOW - timedelta(days=1)).isoformat())
eq(_model(_ledger([safe_bet], lane_reads=read_now), st_q)["attention"], [], "a pair that logged yesterday is not listed")

# A failed workflow run, read from the runs list.
runs = [{"name": "Sandbox Tracker", "conclusion": "failure", "url": "https://github.com/x/y/actions/runs/1", "at": ISO},
        {"name": "Sandbox Tracker", "conclusion": "success", "url": "https://github.com/x/y/actions/runs/0", "at": old},
        {"name": "Refresh boards", "conclusion": "success", "url": "https://github.com/x/y/actions/runs/2", "at": ISO},
        {"name": "PR tests", "conclusion": "failure", "url": "https://github.com/x/y/actions/runs/3", "at": ISO}]
m = _model(_ledger([], lane_reads=read_now), runs=runs)
eq([i["kind"] for i in m["attention"]], ["run"], "one item: the tracker's last completed run failed")
ok("Sandbox Tracker" in m["attention"][0]["text"] and "failure" in m["attention"][0]["text"], "it names the workflow and the conclusion")
eq(m["attention"][0]["href"], "https://github.com/x/y/actions/runs/1", "and links the run")
eq(m["attention"][0]["area"], None, "a run is a system item, not an area's")
ok(m["runs_read"], "the model knows the runs were read")
eq(_model(_ledger([], lane_reads=read_now), runs=runs[1:])["attention"], [], "only the newest completed run per workflow counts, and PR tests are not watched")
ok(not _model(_ledger([], lane_reads=read_now))["runs_read"], "runs=None means not read, not green")

# A closing-price writer gone quiet.
closes = {"vps": (NOW - timedelta(minutes=20)).isoformat(), "watchdog": (NOW - timedelta(hours=5)).isoformat(),
          "boards": (NOW - timedelta(hours=2)).isoformat(), "mac": (NOW - timedelta(days=5)).isoformat()}
m = _model(_ledger([], lane_reads=read_now), closes=closes)
eq(sorted(i["text"].split(" ")[3] for i in m["attention"] if i["kind"] == "venue"), ["mac", "watchdog"],
   "the watchdog (hourly, 5h quiet) and the mac writer (5d) are listed; vps and boards are inside their intervals")
ok(any("expected within 3h" in i["text"] and "5h ago" in i["text"] for i in m["attention"]), "each names its age and its interval")
ok(any("5d ago" in i["text"] and "48h" in i["text"] for i in m["attention"]), "an unknown writer is read on the default interval")
eq(CC.VENUE_WRITERS, {"vps": 2, "watchdog": 3, "close": 2, "boards": 7}, "the writers' intervals")

# All together: counts and the tile.
m = _model(_ledger([overdue], coverage=cov_dark, lane_reads=read_now), st_p, runs=runs, closes=closes)
eq([i["kind"] for i in m["attention"]], ["overdue", "feed", "paused", "run", "venue", "venue"],
   "items are listed in a fixed order: open past start, feeds, pairs, runs, writers")
eq(m["tiles"]["attention"], 6, "the tile counts them")
eq({a["key"]: a["status"] for a in m["areas"] if a["status"] == "attention"}, {"cricket": "attention", "soccer": "attention"},
   "the areas with an item are Attention")
eq({a["key"] for a in m["areas"] if a["status"] == "healthy"}, {"tennis", "crypto", "commodities"},
   "the three lanes read now with no item stay healthy; NBA and trading, never read here, are Waiting")
eq(m["tiles"]["healthy"], (3, 7), "the tile counts them")

# ---------------------------------------------------------------------------
print("\nthe workflow-run reader")
# ---------------------------------------------------------------------------
class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(payload):
    def opener(req, timeout=None):
        opener.url = req.full_url
        return _Resp(json.dumps(payload).encode())
    return opener


op = _opener({"workflow_runs": [
    {"name": "Sandbox Tracker", "conclusion": "failure", "html_url": "u1", "updated_at": ISO, "head_branch": "main"},
    {"name": "Refresh boards", "conclusion": "success", "html_url": "u2", "updated_at": ISO, "head_branch": "claude/x"},
]})
got = CC.fetch_runs(op)
eq(got, [{"name": "Sandbox Tracker", "conclusion": "failure", "url": "u1", "at": ISO}],
   "runs on main are kept with their name, conclusion, link and time; other branches are not")
ok(op.url.startswith(f"https://api.github.com/repos/{CC.REPO}/actions/runs") and "status=completed" in op.url,
   "it reads the repository's completed runs")


def _boom(req, timeout=None):
    raise OSError("offline")


eq(CC.fetch_runs(_boom), None, "a failed read is None, never a verdict")
eq(CC.inputs(runs=False)["runs"], None, "inputs() reads no runs unless asked")

# ---------------------------------------------------------------------------
print("\nthe page")
# ---------------------------------------------------------------------------
blob = {"leads": {}, "pairs": {}}
html = CC.page(NOW, d=_ledger([overdue, quotes[0]], coverage=cov_dark, lane_reads=read_now), st=st_p, blob=blob,
               nba=nba, market=market, closes=closes, runs=runs)
ok(html.startswith("<!doctype html>") and "<title>Edge Machine · Home</title>" in html, "the root is a full page titled Home")
ok('<link rel="stylesheet" href="./control.css">' in html and 'href="./site.css"' in html,
   "it links the shared stylesheet and the Control Center's own")
ok(os.path.isfile(os.path.join(ROOT, "public_site", "control.css")), "control.css is on disk")
tiles = re.findall(r'<div class="tile"><b>([^<]*)</b><span>([^<]*)</span></div>', html)
eq([t[1] for t in tiles], ["pairs in Production", "open bets", "landed · last 14 days", "areas healthy", "needs attention"],
   "five tiles, in order")
tile_of = {label: value for value, label in tiles}
eq(tile_of["pairs in Production"], "1", "the pairs tile")
eq(tile_of["open bets"], "2", "the open tile")
eq(tile_of["needs attention"], "6", "the attention tile")
ok(re.fullmatch(r"\d+/\d+", tile_of["landed · last 14 days"]), "the landed tile is won/settled")
cards = re.findall(r'<article class="cc-card cc-(\w+)" data-area="(\w+)"', html)
eq([c[1] for c in cards], ["soccer", "cricket", "tennis", "crypto", "commodities", "nba", "trading"], "one card per area, in order")
ok('<span class="sig x">Attention</span>' in html and '<span class="sig y">Healthy</span>' in html,
   "cards carry Healthy and Attention chips")
for href in ("./soccer.html", "./cricket.html", "./tennis.html", "./crypto.html", "./commodities.html", "./nba.html", "./trading.html"):
    ok(f'<a class="cc-open" href="{href}">Open →</a>' in html, f"the card opens {href}")
ok("last read Today" in html or "last read " in html, "a card says when the area was last read, in CT")
ok('<ol class="cc-attention">' in html and html.count('<li class="cc-item') == 6, "the attention list has one row per item")
ok('<a href="https://github.com/x/y/actions/runs/1" rel="noopener">Open run →</a>' in html, "a run item links the run")
ok('id="running-list"' in html and 'id="rules-cards"' in html and 'id="rules-empty"' in html
   and 'class="running-filters"' in html and '<nav class="sports sport-filter"' in html,
   "the Live now card keeps the Running list and the rule cards shell.js drives")
ok('id="bets-roll"' not in html and 'class="bet-chip"' not in html and "Bets roll" not in html,
   "the Bets roll is gone from the home")
ok('id="status"' not in html and "System status" not in html, "the old System status pane is gone: the areas carry it")
ok("<style" not in html.lower() and not re.search(r"\sstyle\s*=", html), "no inline style")
nav = re.search(r'<nav class="toc"[^>]*>(.*?)</nav>', html, re.S)
eq(re.findall(r">([^<]+)</a>", nav.group(1)) if nav else None, ["Overview", "Areas", "Attention", "Live now"],
   "the section nav is the four Control Center sections")
empty = CC.page(NOW, d=_ledger([]), st=STAGES_EMPTY, blob=blob, nba={}, market={}, closes={}, runs=None)
ok("Nothing needs attention" in empty and "0 of 7" in empty and "Workflow run results were not read" in empty,
   "an empty ledger renders every area Waiting, no attention, and says the runs were not read")
ok("Select a contest in Running." in empty, "the rule cards start empty")
ok(shell_build.page(NOW, d=_ledger([]), st=STAGES_EMPTY, blob=blob, nba={}, market={}, closes={}) == empty,
   "shell_build.page is the same page: every old caller gets the Control Center")

print("\nthe takeover copies the clock only")
prod = ('<p class="stamp"><time datetime="2026-10-05T12:00:00Z">Updated Oct 5, 7:00 AM CT</time></p>'
        '<div class="tiles"><div class="tile"><b>10</b><span>leads still to come</span></div></div>')
index = ('<p class="stamp"><time datetime="2026-10-01T00:00:00Z">old</time></p>'
         '<div class="tiles"><div class="tile"><b>4</b><span>pairs in Production</span></div></div>'
         '<div class="running-filters" role="group"></div><div class="running-list" id="running-list"></div>')
copied = site_root._copy_from_tracker(index, prod)
ok("2026-10-05T12:00:00Z" in copied and "2026-10-01T00:00:00Z" not in copied, "the clock is production.html's")
ok('<b>4</b><span>pairs in Production</span>' in copied and '<b>10</b>' not in copied,
   "the Control Center's own tiles stay; production's strip is not copied over them")
eq(site_root._copy_from_tracker("no running block", prod), None, "a root without the Running block is rebuilt, not patched")

print(f"\n{len(FAILS)} FAILED" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
