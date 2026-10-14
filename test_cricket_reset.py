#!/usr/bin/env python3
"""The cricket reset (decided 2026-10-08): every cricket record restarts at
S.CRICKET_RESET_SINCE, by the site's reset convention (a stage row with `since`
and a `reset` note), with every row kept on file.

What is pinned: the registration lines; the code-driven stage rows (applied on
every read of the stage file, since the tracker rewrites that file each run);
the Sandbox record, verdict and Waiting state; the Production record, the home
roll's clock and the Early badge; the stamp window; the cricket page's tiles,
cards and the folded 'Before the reset' note; and that no ledger row changes.
"""
import copy
import datetime
import json
import os
import re
import tempfile
from datetime import timedelta, timezone

import cricket_build
import cricket_cards
import production as PR
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import sport_page as SP

FAILS = []
CLOCK = S.CRICKET_RESET_SINCE
NOW = datetime.datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc)
KEYS = ("oddspedia|cricket", "polymarket|cricket", "cricket_consensus|cricket")


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


def _quote(i, source, status, start, label, price=0.55, bet=True, venue="polymarket_us",
           logged=None, **extra):
    won = status == "won"
    q = dict(
        id=f"{source}:cricket:{i}:{label}", source=source, sport="cricket", bet=bet, status=status,
        pick="b", price=price, result=("b" if won else "a") if status in ("won", "lost") else None,
        venue=venue, pnl=(round(100 * (1 / price - 1), 2) if won else -100.0) if status in ("won", "lost") else None,
        start=start.isoformat(), logged=(logged or (start - timedelta(hours=2))).isoformat(),
        date=start.date().isoformat(), price_a=round(1 - price, 2), price_b=price,
        side_a="Home Side", side_b="Away Side", label=label, market_id=f"aec-m-{source}-{i}",
        url="https://polymarket.us/event/x", stake=T.STAKE if bet else 0)
    q.update(extra)
    return q


def _ledger(after=0):
    """Pre-reset bets on every cricket lane, and `after` settled wins on the clock."""
    clock = datetime.datetime.fromisoformat(CLOCK)
    old = [
        _quote(1, "oddspedia", "won", clock - timedelta(days=20), "Flames v Wolves", price=0.07),
        _quote(2, "oddspedia", "won", clock - timedelta(days=15), "Wolves v Flames", price=0.11),
        _quote(3, "oddspedia", "lost", clock - timedelta(days=10), "Lost v Early", price=0.5),
        _quote(4, "oddspedia", "void", clock - timedelta(days=9), "Void v Swap", price=0.5, pnl=0.0),
        _quote(5, "oddspedia", "settled", clock - timedelta(days=8), "Rain v Rain", price=0.4,
               settle_px=0.5, pnl=25.0, result="price"),
        _quote(6, "oddspedia", "won", clock - timedelta(days=3), "Kalshi v Won", price=0.6, venue="kalshi"),
        # Open before the clock, starting after it: it settles, and counts toward nothing.
        _quote(7, "oddspedia", "open", clock + timedelta(days=1), "Test v Match", price=0.55,
               logged=clock - timedelta(hours=8)),
        _quote(8, "polymarket", "won", clock - timedelta(days=20), "Flames v Wolves", price=0.07),
        _quote(9, "polymarket", "lost", clock - timedelta(days=12), "Lost v Gone", price=0.44),
    ]
    new = [
        _quote(100 + i, "oddspedia", "won", clock + timedelta(days=1 + i, hours=6), f"New v Win {i}", price=0.5)
        for i in range(after)
    ]
    return {"quotes": old + new, "coverage": {"cricket": {"polymarket_us": 3, "polymarket_us_listed": 3,
                                                           "polymarket_us_priced": 2}},
            "meta": {"updated": NOW.isoformat()}}


def _stages():
    """The stage file as the tracker left it before the reset: Oddspedia in Production
    since 2026-09-28 with no clock, the other two cricket pairs with no row."""
    return {"pairs": {"oddspedia|cricket": {
        "stage": "production", "by_hand": "2026-09-27", "entry_since": None,
        "promoted_at": "2026-09-28T02:59:44+00:00", "ready_at": "2026-09-28T02:59:44+00:00",
        "ready_since": "2026-09-28T02:59:44+00:00", "entry": {"n": 12}}},
        "events": [], "updated": "2026-10-11T21:58:19+00:00"}


print("-- the registration")
clock_dt = datetime.datetime.fromisoformat(CLOCK)
ok(clock_dt.tzinfo is not None and clock_dt.utcoffset() == timedelta(0), "the reset clock is an exact UTC instant")
ok(CLOCK > "2026-10-11T21:00:00+00:00", "the clock is after the last run on the old record")
eq(S.CRICKET_RESET_DECIDED, "2026-10-08", "the decision date is 2026-10-08")
eq(sorted(S.LANE_RESETS), [("cricket_consensus", "cricket"), ("oddspedia", "cricket"), ("polymarket", "cricket")],
   "the three cricket lanes are reset: Oddspedia, the Polymarket comparison rule, Cricket consensus")
ok(all(v == CLOCK for v in S.LANE_RESETS.values()), "all three on the one clock")
for src in ("oddspedia", "polymarket", "cricket_consensus"):
    note = S.SOURCES[src]["note"]
    ok(f"RESET {S.CRICKET_RESET_DECIDED}:" in note, f"{src}'s registration carries the dated RESET line")
    ok(CLOCK in note, f"{src}'s RESET line states the clock exactly")
    ok("Amsterdam Flames at 7c on Sep 16" in note and "Belfast Wolves at 11c on Sep 19" in note
       and "$2,138 of Oddspedia's $2,354 gross" in note and "side-swap voids" in note,
       f"{src}'s RESET line says why: the two longshots, their share of the gross, the side-swap voids")
    ok(S.CRICKET_RESET_LINE in (S.SOURCES[src].get("changes") or []), f"{src}'s dated change entries carry it too")
eq(S.source_reset_since("oddspedia"), CLOCK, "Oddspedia, cricket only, is reset as a source")
eq(S.source_reset_since("cricket_consensus"), CLOCK, "Cricket consensus too")
eq(S.source_reset_since("polymarket"), None, "Polymarket covers other sports, so it has no single source clock")
eq(S.lane_reset_since("polymarket", "cricket"), CLOCK, "but its cricket lane is on the clock")
eq(S.lane_reset_since("polymarket", "mlb"), None, "and its MLB lane is not")
ok("polymarket" in S.PAUSED_LANES and S.PAUSED_LANES["polymarket"] is None,
   "the Polymarket comparison lane's pause is untouched: the reset changes no rule")

print("-- the stage rows, applied on every read")
st = _stages()
changed = T.apply_resets(st)
eq(sorted(changed), sorted(KEYS), "apply_resets writes the three cricket rows")
odd = st["pairs"]["oddspedia|cricket"]
eq(odd["stage"], "production", "Oddspedia stays in Production")
eq(odd["since"], CLOCK, "its page record restarts at the clock (since)")
eq(odd["entry_since"], CLOCK, "and the record the tracker judges it on (entry_since)")
eq(odd["promoted_at"], "2026-09-28T02:59:44+00:00", "its promotion is not rewritten")
eq(odd["by_hand"], "2026-09-27", "nor its by-hand date")
eq(odd["reset"], S.CRICKET_RESET_LINE, "the row carries the reset note")
for key in ("polymarket|cricket", "cricket_consensus|cricket"):
    row = st["pairs"][key]
    eq((row["stage"], row["since"], row["reset"]), ("sandbox", CLOCK, S.CRICKET_RESET_LINE),
       f"{key} gets a Sandbox row on the clock with the note")
eq(T.record_since(odd), CLOCK, "record_since reads the clock")
eq(T.qa_since(odd, "cricket", "oddspedia|cricket"), CLOCK, "qa_since reads it for the demotion net")
events = [e for e in st["events"] if e.get("reset") == CLOCK]
eq(sorted(e["pair"] for e in events), sorted(KEYS), "each applied reset is one event")
snapshot = copy.deepcopy(st)
eq(T.apply_resets(st), [], "a second application changes nothing")
eq(st, snapshot, "and rewrites nothing")
later = copy.deepcopy(_stages())
later["pairs"]["polymarket|cricket"] = {"stage": "sandbox", "since": "2026-11-01T00:00:00+00:00",
                                        "demoted_at": "2026-11-01T00:00:00+00:00"}
T.apply_resets(later)
eq(later["pairs"]["polymarket|cricket"]["since"], "2026-11-01T00:00:00+00:00",
   "a clock already later than the reset (a demotion after it) is kept")
eq(later["pairs"]["polymarket|cricket"]["reset"], S.CRICKET_RESET_LINE, "and still carries the note")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "stages.json")
    json.dump(_stages(), open(path, "w"))
    loaded = T.load_stages(path)
    eq(loaded["pairs"]["oddspedia|cricket"]["since"], CLOCK, "load_stages applies the reset to the file's rows")
    eq(loaded["pairs"]["cricket_consensus|cricket"]["since"], CLOCK, "and adds the rows the file lacks")
    missing = T.load_stages(os.path.join(tmp, "none.json"))
    eq(sorted(k for k in missing["pairs"]), sorted(KEYS), "a missing file still yields the three rows")
real = T.load_stages()
ok(all(real["pairs"][k].get("since") == CLOCK for k in KEYS), "the repository's own stage file reads with the reset")
eq(real["pairs"]["oddspedia|cricket"]["stage"], "production", "and Oddspedia is still in Production there")
ok("oddspedia|cricket" in T.PAIR_OVERRIDES, "Oddspedia is still listed for Production (PAIR_OVERRIDES)")

print("-- the Sandbox record, verdict and Waiting state")
d = _ledger()
before = copy.deepcopy(d)
st = _stages()
T.apply_resets(st)
for key in KEYS:
    name, sport = key.split("|")
    group, a, _qa, open_n, _last, pair = B.pair_status(d, st, name, sport)
    eq((group, a["n"], a.get("n_price") or 0), ("waiting", 0, 0), f"{key}: nothing counted, Waiting")
    eq(B.verdict(a), "waiting", f"{key}: the verdict is Waiting")
eq(B.pair_status(d, st, "oddspedia", "cricket")[3], 1, "the open bet logged before the clock still shows as open")
rows = {f'{r["name"]}|{r["sport"]}': r for r in B.pair_list(d, st) if r["sport"] == "cricket"}
eq(sorted(rows), sorted(KEYS), "all three cricket pairs stay listed")
ok(all(r["v"] == "waiting" and r["a"]["n"] == 0 for r in rows.values()), "each listed as Waiting with an empty record")
eq(rows["oddspedia|cricket"]["since"], CLOCK, "the row carries the clock")
eq(rows["oddspedia|cricket"]["reset"], S.CRICKET_RESET_LINE, "and the reset note")
eq(T.assess(d, "oddspedia", "cricket", venues=T.TRADEABLE_VENUES)["n"], 4,
   "the whole record is still on file: four settled on the US exchanges before the clock")
d2 = _ledger(after=3)
group, a, *_ = B.pair_status(d2, st, "oddspedia", "cricket")
eq((a["n"], a["won"]), (3, 3), "bets logged on the clock count, and only those")
eq(B.verdict(a), "early", "three settled is too early to read, not Waiting")

print("-- the Production record, the roll's clock and the Early badge")
pair = st["pairs"]["oddspedia|cricket"]
eq(PR.entered_at(pair), CLOCK, "entered_at: the Production record restarts at the reset")
eq(PR.reset_after_entry(pair), CLOCK, "reset_after_entry names it")
eq(PR.entered_at({"ready_at": "2026-09-28T00:00:00+00:00", "promoted_at": "2026-09-28T00:00:00+00:00"}),
   "2026-09-28T00:00:00+00:00", "a pair with no reset enters when it was promoted")
eq(PR.entered_at({"ready_at": "2026-09-28T00:00:00+00:00", "since": "2026-09-20T00:00:00+00:00"}),
   "2026-09-28T00:00:00+00:00", "a since from before the entry (a fixture's) does not move the entry")
live = PR._assess_since_kickoff(d, "oddspedia|cricket", pair)
eq(live["n"], 0, "since-Production: nothing kicked off since the clock has settled")
live2 = PR._assess_since_kickoff(d2, "oddspedia|cricket", pair)
eq((live2["n"], live2["won"]), (3, 3), "the three on the clock are the since-Production record")
eq(PR.early_badge(d, "oddspedia|cricket", pair), "Early · 0 bets",
   "Oddspedia, moved 2026-09-27, is early again from the reset")
eq(PR.early_badge(d2, "oddspedia|cricket", pair), "Early · 3 bets", "and counts the bets since it")
old_pair = {"stage": "production", "by_hand": "2026-09-27", "promoted_at": "2026-09-28T02:59:44+00:00",
            "ready_at": "2026-09-28T02:59:44+00:00"}
eq(PR.early_badge(d2, "oddspedia|cricket", old_pair), None,
   "a pair moved before the Early state with no reset is still never badged")
feed = PR.build_feed(d2, st, now=NOW)
eq(feed["pairs"]["oddspedia|cricket"]["entered_at"], CLOCK, "the feed states the reset clock as the entry")
eq(feed["pairs"]["oddspedia|cricket"]["sandbox_n"], 3, "and its since-Production record is the three on the clock")
ok(not any(l["pair"] == "oddspedia|cricket" and l["kickoff"] < CLOCK for l in feed["leads"].values()),
   "no lead that kicked off before the clock is published")

print("-- the stamp window")
stamp = B.approval_table(d, T.score(d), full=d)
cell = stamp[stamp.find("Oddspedia community tips"):]
ok("0 bets over 0 days" in cell[:600], "Oddspedia's stamp row counts from the clock: nothing yet")
stamp2 = B.approval_table(d2, T.score(d2), full=d2)
cell2 = stamp2[stamp2.find("Oddspedia community tips"):]
ok("3 bets over" in cell2[:600], "and the bets on the clock when there are some")

print("-- the cricket page")
html = cricket_build.build(d, st, NOW)
tiles = re.findall(r'<div class="tile">(.*?)</div>', html, re.S)
ok(any("<b>—</b><span>since Production · Oddspedia community tips</span>" in t for t in tiles),
   "the record tile is empty since Production")
ok(any('<b class="mut">—</b><span>ROI after fees · since Production' in t for t in tiles), "so is the ROI tile")
card = html[html.find('data-source="oddspedia"'):]
card = card[:min(i for i in (card.find('<details class="sp-rule', 10), card.find('id="sandbox"'), len(card)) if i > 0)]
summary = card[:card.find("</summary>")]
ok('<span class="sig w early">Early · 0 bets</span>' in summary, "the Production row wears Early · 0 bets")
ok('<span class="sp-cell num" data-l="Record"><span class="mut">—</span></span>' in summary, "its record is empty")
ok('data-verdict="waiting"' in card, "its verdict chip is the Waiting verdict")
ok("RESET 2026-10-08:" in card, "its registration shows the RESET line")
fold = card[card.find('<details class="sp-more sp-before-reset">'):]
fold = fold[:fold.find("</details>")]
ok(fold.startswith('<details class="sp-more sp-before-reset"><summary>Before the reset · not counted</summary>'),
   "the old record is folded under 'Before the reset · not counted'")
ok("<b>Not counted.</b> 7 bets logged" in fold, "it counts every pre-reset row on file")
ok("3–1, 1 no result" in fold, "with the old W–L and no-result count on the US exchanges")
ok("after fees" in fold and "3 won v 1.3 the prices implied" in fold, "the old ROI and won-v-priced")
ok("gross at a flat $100 stake" in fold, "and the old gross")
ok(f"before the clock at {CLOCK}" in fold, "naming the clock")
ok("count toward nothing above" in fold, "and saying it counts toward nothing")
sand = html[html.find('<details class="fold sp-sandbox"'):]
ok(sand.count("Before the reset · not counted") == 1, "the Polymarket comparison rule folds its old record too")
ok('data-source="cricket_consensus"' in sand and sand.count("Before the reset · not counted") == 1,
   "Cricket consensus, which never bet, has nothing to fold")
ok(sand.count('data-verdict="waiting"') >= 2, "the Sandbox rows carry the Waiting verdict")
ok(f"every cricket record counts from {CLOCK}" in html, "the method fold states the reset once")
pre_html = cricket_build.build(d, _stages(), NOW)
ok("Before the reset · not counted" not in pre_html, "without the stage rows nothing is folded: the fold is the reset's")
eq(cricket_cards.before_reset(d, {"name": "oddspedia", "sport": "cricket", "since": None, "reset": None}), None,
   "before_reset is None without a clock")
eq(cricket_cards.before_reset(d, {"name": "cricket_consensus", "sport": "cricket", "since": CLOCK,
                                  "reset": S.CRICKET_RESET_LINE}), None, "and None with nothing logged before it")

print("-- nothing on file changes")
eq(d, before, "the page build changes no ledger row")
real_d = T.load()
pre = [q for q in real_d.get("quotes") or [] if q.get("sport") == "cricket" and q.get("bet")
       and str(q.get("logged") or "") < CLOCK and q.get("status") in ("won", "lost")]
ok(all(q.get("status") in ("won", "lost") for q in pre), "no settled cricket row was voided or rewritten")
longshots = [q for q in pre if q.get("source") == "oddspedia" and (q.get("price") or 1) < 0.15]
ok(longshots and all(q["status"] == "won" for q in longshots), "the two longshots stay won, on file")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    for f in FAILS:
        print(" -", f)
    raise SystemExit(1)
print("all checks passed")
