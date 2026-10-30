#!/usr/bin/env python3
"""The NBA win margin lane (2026-10-30): nba_winmargin_split on the chaos engine (paper), its in-sample
backfill row, the x2 exit, fills only from the tip on, and where both sit on the NBA page and the Sandbox index."""
import datetime as dt
import sys

import chaos_build as CB
import chaos_lanes as CL
import chaos_replay as C
import sandbox_audit

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


LD = {l["id"]: l for l in CL.LANES}
M, I = LD["nba_winmargin_split"], LD["nba_winmargin_split_insample"]
EV = "KXNBAWINMARGIN-26OCT30WASCLE"

print("the lane configs")
check("fresh from 2026-10-30; the in-sample row replays Oct 20-29 and stops", (M["since"], I["since"], I["until"], M.get("until")),
      ("2026-10-30", "2026-10-20", "2026-10-29", None))
check("the same rule on both: 1h before the tip, spread 5c or less, split headline, fills from the tip on",
      [(l["entry_hours"], l["max_spread"], l["headline"], l["fill_from_start"], l["series"]) for l in (M, I)],
      [((1,), 0.05, "split", True, ["KXNBAWINMARGIN"])] * 2)
check("exits: hold, the split, +50%, +100% and 2x only", M["exits"], ("hold", "split", "tp50", "tp100", "x2"))
check("only the in-sample row is flagged in-sample", (M.get("insample"), I.get("insample")), (None, True))

print("\nthe picker: YES of the 1-5 and 6-10 buckets, 10-20c, either team")
titles = {"A1": "Washington wins by 1-5 points", "A6": "Washington wins by 6-10 points", "A11": "Washington wins by 11-20 points",
          "B1": "Cleveland wins by 1-5 points", "B6": "Cleveland wins by 6-10 points", "B21": "Cleveland wins by 21+ points"}
mk = {EV + "-" + k: {"yes_sub_title": v} for k, v in titles.items()}
quotes = {"A1": (0.08, 0.11), "A6": (0.14, 0.17), "A11": (0.12, 0.14), "B1": (0.09, 0.21), "B6": (0.18, 0.20), "B21": (0.12, 0.16)}


def entry_view(t, s):
    bid, ask = quotes[t.split("-")[-1]]
    return dict(bid=bid, ask=ask, ts=1)


ctx = dict(event=EV, tickers=sorted(mk), markets=mk, entry_view=entry_view)
check("the 11-20 and 21+ buckets and a 12c spread are left out; both teams' qualifying buckets are taken, YES only",
      sorted((t.split("-")[-1], s) for t, s in M["picker"](ctx)), [("A1", "yes"), ("A6", "yes"), ("B6", "yes")])
quotes["A1"] = (0.06, 0.08)
check("an ask under 10c is left out", sorted(t.split("-")[-1] for t, s in M["picker"](ctx)), ["A6", "B6"])

print("\nthe tip rule: the KXNBAGAME expected expiration minus 3 hours")
EXP = "2026-10-31T03:30:00Z"


def fetch(path):
    if "event_ticker=KXNBAGAME-26OCT30WASCLE" in path and path.startswith("markets"):
        return {"markets": [{"ticker": "KXNBAGAME-26OCT30WASCLE-WAS", "expected_expiration_time": EXP}]}
    return {"markets": []}


tip = CL.winmargin_start(dict(event=EV, fetch=fetch))
check("tip = 00:30Z", dt.datetime.fromtimestamp(tip, dt.timezone.utc).isoformat(), "2026-10-31T00:30:00+00:00")
check("no moneyline market gives None (the engine falls back)", CL.winmargin_start(dict(event=EV, fetch=lambda p: {"markets": []})), None)

print("\nthe 2x exit and fills only from the tip on")
T0 = 1_800_000_000 - 1_800_000_000 % 60


def minute(k, bid, ask, px_hi=None):
    return dict(ts=T0 + 60 * k, bid=bid, ask=ask, bid_lo=bid, bid_hi=bid, ask_lo=ask, ask_hi=ask, px_hi=px_hi, px_lo=None)


# Entry at minute 0 (ask 0.15). A traded 0.32 at minute 2 is BEFORE the tip (minute 5); a 0.32 and a 0.46 print come after.
mins = [minute(0, 0.12, 0.15), minute(1, 0.12, 0.15), minute(2, 0.12, 0.15, px_hi=0.32), minute(3, 0.12, 0.15),
        minute(4, 0.12, 0.15), minute(5, 0.12, 0.15), minute(6, 0.20, 0.22, px_hi=0.32), minute(7, 0.20, 0.22, px_hi=0.46),
        minute(8, 0.01, 0.02)]
vs = [C.view(m, "yes") for m in mins]
before = C._split_trade(vs, 0, False, C.LEGGED[C.X2])
after = C._split_trade(vs, 0, False, C.LEGGED[C.X2], T0 + 5 * 60)
check("without a start gate the pre-tip print fills the 2x; gated, the first fill is the print at minute 6",
      (before["legs"][0]["filled_ts"], after["legs"][0]["filled_ts"]), (T0 + 2 * 60, T0 + 6 * 60))
sp_a = C._split_trade(vs, 0, False, C.SPLIT_LEGS, T0 + 5 * 60)
check("the split: 2x (0.30) fills at minute 6, 3x (0.45) at minute 7; both from the tip on", [l["filled_ts"] for l in sp_a["legs"]],
      [T0 + 6 * 60, T0 + 7 * 60])
fee = lambda p: C.maker_fee(p)
check("x2 pays 0.30 less the maker fee on the whole stake",
      round(after["profit"], 4), round(0.30 - fee(0.30) - C.cost(0.15), 4))
check("simulate() passes the gate through; x2 is judged against the hold row",
      (C.simulate(mins, "yes", "no", T0 + 5 * 60, 5 / 60, C.X2, 0.05, True)[0]["filled_2x"], C.control_of("t1h_x2")), (True, "t1h_hold"))
check("a lane that lists no x2 never replays it", C.X2 in C.LANE_EXITS, False)

print("\nuntil: the in-sample lane stops at its last night")
seen = []
real_list, real_replay = C.list_events, C.replay_event
C.list_events = lambda series, since, fetch, until=None, cap=400: ["KXNBAWINMARGIN-26OCT29AAABBB", "KXNBAWINMARGIN-26OCT30CCCDDD", "KXNBAWINMARGIN-26OCT28EEEFFF"]
C.replay_event = lambda lane, series, event, fetch, now=None: (seen.append(event) or ([], None))
try:
    C.run(C.empty(), [I], dt.datetime(2026, 10, 31, 8, tzinfo=dt.timezone.utc), lambda p: {})
finally:
    C.list_events, C.replay_event = real_list, real_replay
check("Oct 30 is not replayed for the in-sample lane", sorted(seen), ["KXNBAWINMARGIN-26OCT28EEEFFF", "KXNBAWINMARGIN-26OCT29AAABBB"])

print("\nthe page")


def tr(night, ticker, ex, roi, won, **kw):
    return dict(event=EV, ticker=ticker, side="yes", hours=1, exit_key=ex, variant=f"t1h_{ex}", night=night, entry=0.15, spread=0.03,
                entry_ts=1, cost=0.16, profit=round(roi * 0.16, 4), roi=roi, won=won, reason="settled" if ex == "hold" else "split", **kw)


def lane_state(cfg, nights):
    trades = []
    for i, n in enumerate(nights):
        t = f"{EV}-WAS1TO5"
        trades += [tr(n, t, "hold", -1.0, False), tr(n, t, "split", 1.3, True, filled_2x=True, filled_3x=True)]
    return dict(id=cfg["id"], label=cfg["label"], since=cfg["since"], entry_hours=[1], exits=list(cfg["exits"]), headline="split",
                note=cfg["note"], replayed={EV: 1}, trades=trades, skipped={}, series=cfg["series"], insample=cfg.get("insample"))


state = dict(lanes={"nba_winmargin_split": lane_state(M, ["2026-10-30"]),
                    "nba_winmargin_split_insample": lane_state(I, ["2026-10-22", "2026-10-23", "2026-10-24"])})
html = CB.sport_section("nba", state)
head = html[:html.find('id="cheap-side-insample"')]
check("the in-sample row is its own labelled block, apart from the lane", ('id="cheap-side-insample"' in html, "IN-SAMPLE" in html, "NOT evidence" in html),
      (True, True, True))
check("the headline summary lists the fresh lane and never the in-sample lane",
      ('data-lane="nba_winmargin_split"' in head, 'data-lane="nba_winmargin_split_insample"' in head), (True, False))
check("the in-sample summary row says so", "in-sample backfill, not evidence" in html[html.find('id="cheap-side-insample"'):], True)
card = html[html.find('data-lane="nba_winmargin_split" open'):html.find('id="cheap-side-insample"')]
check("the lane's card: split v hold first, then the other exits (+50%, +100%, 2x only)",
      ("Split v hold" in card, "sell at +50%" in card, "sell at +100%" in card, "sell everything at 2x" in card), (True, True, True, True))
check("each variant sits against its hold control", "Hold control" in card, True)
idx = CB.section(state)
check("the Sandbox's Chaos index lists both, the in-sample one marked",
      ('data-lane="nba_winmargin_split"' in idx, 'data-lane="nba_winmargin_split_insample"' in idx, "in-sample backfill, not evidence" in idx),
      (True, True, True))
check("both link to the NBA page", idx.count("./nba.html#cheap-side") >= 2, True)
check("public copy passes the guard", sandbox_audit.COPY_RE.search(html + idx), None)

print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED"))
sys.exit(1 if FAILS else 0)
