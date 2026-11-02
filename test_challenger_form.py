#!/usr/bin/env python3
"""Offline checks for the Challenger cheap-side HOLD lane (2026-11-02, Olu): the pre-registered "won here, favourite
cold" filter (challenger_form.py), point-in-time with no look-ahead, its blind 15-30c baseline, and the Tennis page."""
import datetime as dt
import re
import sys

import chaos_build as CB
import chaos_lanes
import chaos_replay as C
import challenger_form as F
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


CUT = int(dt.datetime(2026, 11, 4, 10, tzinfo=UTC).timestamp())
BEFORE, AFTER = "2026-11-03T20:00:00Z", "2026-11-04T12:00:00Z"


def match(event, comp, a, b, winner, settled=BEFORE):
    return dict(event_ticker=event, product_metadata=dict(competition=comp), markets=[
        dict(yes_sub_title=a, result="yes" if winner == a else "no", settlement_ts=settled),
        dict(yes_sub_title=b, result="yes" if winner == b else "no", settlement_ts=settled)])


EVENTS = [
    match("E1", "ATP Challenger Taipei", "Yosuke Watanuki", "Q One", "Yosuke Watanuki"),          # the dog won here
    match("E2", "ATP Challenger Taipei", "Dog Two", "Q Two", "Dog Two"),
    match("E3", "ATP Challenger Taipei", "Fav Two", "Q Three", "Fav Two"),                         # this favourite played
    match("E4", "ATP Challenger Taipei", "Dog Three", "Q Four", "Dog Three", settled=AFTER),       # settled after the entry
    match("E5", "ATP Challenger Brest", "Dog Four", "Q Five", "Dog Four"),                         # another tournament
    match("NOW", "ATP Challenger Taipei", "Yosuke Watanuki", "Fav One", "Fav One"),                # the event itself
]


def fake(path):
    if path.startswith("events/"):
        ev = path.split("/", 1)[1]
        return {"event": dict(event_ticker=ev, product_metadata=dict(competition="" if ev == "NOCOMP" else "ATP Challenger Taipei"))}
    return {"events": EVENTS}


def reset():
    F._EVENTS.clear()
    F._WINDOWS.clear()


print("the history: point-in-time, this tournament only, this event excluded")
reset()
h = F.history("NOW", F.SERIES, "ATP Challenger Taipei", CUT, fake)
check("a win settled before the entry counts; one settled after does not; another tournament and the event itself do not",
      (h.get("yosukewatanuki"), h.get("dogtwo"), h.get("favtwo"), h.get("dogthree"), h.get("dogfour"), h.get("favone")),
      ((1, 1), (1, 1), (1, 1), None, None, None))
check("names match accent-insensitively", F.norm("Tomás Barrios Vera"), F.norm("Tomas Barrios Vera"))


def ctx(names, asks, event="NOW"):
    views = {t: dict(ask=a, bid=a - 0.02) for t, a in zip(names, asks)}
    return dict(event=event, series=F.SERIES, tickers=list(names), markets={t: dict(yes_sub_title=n) for t, n in names.items()},
                start_ts=CUT + 3600, hours=1, entry_view=lambda t, s: views[t] if s == "yes" else None)


pick = F.won_here_picker(0.15, 0.30, 0.05, fetch=fake)
print("\nthe picker")
reset()
check("the 15-30c player who won here, against a favourite with no match here: kept",
      pick(ctx({"T-WAT": "Yosuke Watanuki", "T-FAV": "Fav One"}, (0.22, 0.80))), [("T-WAT", "yes")])
reset()
check("the favourite has already played here: dropped", pick(ctx({"T-D2": "Dog Two", "T-F2": "Fav Two"}, (0.22, 0.80))), [])
reset()
check("the cheap player's win settled after the entry (no look-ahead): dropped",
      pick(ctx({"T-D3": "Dog Three", "T-F9": "Fav Nine"}, (0.22, 0.80))), [])
reset()
check("a win at another tournament does not count", pick(ctx({"T-D4": "Dog Four", "T-F9": "Fav Nine"}, (0.22, 0.80))), [])
reset()
check("outside the 15-30c band nothing is read", pick(ctx({"T-WAT": "Yosuke Watanuki", "T-FAV": "Fav One"}, (0.35, 0.67))), [])
reset()
try:
    pick(ctx({"T-WAT": "Yosuke Watanuki", "T-FAV": "Fav One"}, (0.22, 0.80), event="NOCOMP"))
    got = None
except C.SkipEvent as e:
    got = str(e)
check("no tournament on the event: skipped with a note, never guessed", got, "Kalshi gives no tournament for the event")
reset()

print("\nthe lane and its baseline")
cfg = {l["id"]: l for l in chaos_lanes.LANES}
lane, base = cfg["challenger_won_here_hold"], cfg["challenger_cheap_hold_base"]
check("the lane: Challenger, 1h, 5c spread, HOLD only, fresh from 2026-11-02, not a baseline",
      (lane["series"], lane["entry_hours"], lane["max_spread"], lane["exits"], lane["headline"], lane["since"], "baseline" in lane),
      (["KXATPCHALLENGERMATCH"], (1,), 0.05, ("hold",), "hold", "2026-11-02", False))
check("the baseline: the same entry on every 15-30c player, held, marked a baseline, fresh from 2026-11-02",
      (base["series"], base["entry_hours"], base["max_spread"], base["exits"], base["since"], base["baseline"]["on"], "who" in base["baseline"]),
      (["KXATPCHALLENGERMATCH"], (1,), 0.05, ("hold",), "2026-11-02", "2026-11-02", True))
check("both live on the Tennis page", (CB.HOME_OF["challenger_won_here_hold"], CB.HOME_OF["challenger_cheap_hold_base"]), ("tennis", "tennis"))
check("the pre-registration is dated in the lane's own copy", "Registered 2026-11-02" in lane["caution"], True)

print("\nthe Tennis page")
st = C.empty()
now = dt.datetime(2026, 11, 2, 12, tzinfo=UTC)
for l in (lane, base):
    C.lane_state(st, l, now)
sec = CB.sport_section("tennis", st)
summ = sec[sec.find('class="chaos-summary"'):sec.find("</table>", sec.find('class="chaos-summary"'))]
check("the lane has a summary row with a review status; the baseline has none",
      re.findall(r'<tr data-lane="([^"]+)"', summ), ["challenger_won_here_hold"])
b = sec[sec.find('id="baseline-challenger_cheap_hold_base"'):]
check("the baseline block names its population and says a filtered lane must beat it",
      ("Baseline · Challenger 15-30c player (blind, price band only)" in b, "no player or matchup filter" in b, "must beat" in b,
       "10-40c" in b), (True, True, True, False))
check("the section says the Tennis lanes hold (no split sell)", ("Hold to settlement: no sell." in sec, "Rest a split sell" in sec), (True, False))
idx = CB.section(st)
check("the Sandbox index: a row for the lane, the baseline in the Baselines line",
      (re.findall(r'<tr data-lane="(challenger_[^"]+)"', idx), 'href="./tennis.html#baseline-challenger_cheap_hold_base"' in idx), (["challenger_won_here_hold"], True))
check("no guarded phrase in the new copy", sandbox_audit.COPY_RE.search(sec + str(lane) + str(base)), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
