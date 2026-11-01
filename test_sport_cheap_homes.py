#!/usr/bin/env python3
"""Every cheap-side lane on its own page (2026-10-27, Olu: "Each strategy needs to be under its own
sport/event and arranged in the tab"): the chaos lanes on Tennis, NBA and NFL, the Sandbox's Chaos section
an index, every active lane visible without opening a fold, the nav listing every such page."""
import datetime as dt
import json
import os
import re
import sys

import chaos_build as CB
import chaos_lanes
import chaos_replay as C
import site_chrome as SC

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def folded(html, marker):
    """True when `marker` sits inside a <details> that is not open."""
    i = html.find(marker)
    if i < 0:
        return None
    opens = [m for m in re.finditer(r"<details([^>]*)>", html[:i])]
    depth = []
    for m in re.finditer(r"<details([^>]*)>|</details>", html[:i]):
        if m.group(0) == "</details>":
            depth and depth.pop()
        else:
            depth.append(" open" in (m.group(1) or ""))
    return any(not o for o in depth)


print("homes")
ids = [l["id"] for l in chaos_lanes.LANES]
check("every registered chaos lane has a home page", sorted(x for x in ids if x not in CB.HOME_OF), [])
check("the map", {p: list(v) for p, v in CB.HOMES.items()},
      {"tennis": ["challenger_cheap_split", "challenger_dog_tp30", "atp_coinflip_tp30"],
       "nba": ["nba_ml_dog_tp50", "nba_winmargin_split", "nba_winmargin_split_insample", "nba_tt_cheap_tp30"],
       "nfl": ["cfb_home_dog_x4", "cfb_dog_tp50"]})
check("every home page is in the nav's Markets menu", all(p in SC.MARKET_GROUP for p in CB.HOMES), True)
check("and so are Culture, Commodities and Fights", all(p in SC.MARKET_GROUP for p in ("culture", "commodities", "fights")), True)

print("\nthe sport pages")
import nfl_build
import tennis_build
pages = {"tennis": tennis_build.build(), "nfl": nfl_build.build()}
import nba_pace_build
if os.path.exists(nba_pace_build.SRC):
    pages["nba"] = nba_pace_build.build(json.load(open(nba_pace_build.SRC)))
for page, html in pages.items():
    first = re.search(r'<(?:section|details)[^>]*id="([^"]+)"', html[html.find("<main"):])
    check(f"{page}: the cheap-side section is the first section of the page (the NBA page opens on its glance table, 2026-10-31)",
          first and first.group(1), "glance" if page == "nba" else "cheap-side")
    for lane in CB.HOMES[page]:
        L = next(x for x in chaos_lanes.LANES if x["id"] == lane)
        if L.get("retired"):
            check(f"{page}: {lane} (retired) is in the collapsed Retired block", folded(html, f'<li data-lane="{lane}"'), True)
        elif L.get("baseline"):
            check(f"{page}: {lane} (baseline) is its own open Baseline block, not under Retired",
                  (folded(html, f'id="baseline-{lane}" open>'), f'<li data-lane="{lane}"' in html), (False, False))
        elif L.get("insample"):
            check(f"{page}: {lane} (in-sample) sits in its lane's in-sample fold", f'id="{L["id"].replace("_insample", "")}-insample"' in html or "nofade-insample" in html, True)
        elif lane in (C.load().get("lanes") or {}):
            check(f"{page}: {lane}'s card is visible without opening a fold",
                  folded(html, f'<details class="section-disclosure" data-lane="{lane}" open>'), False)
check("nfl: the college football block names itself", "College football" in pages["nfl"], True)

print("\nthe Sandbox index")
idx = CB.section()
check("an index: a row per lane, a link to each home, no lane cards", (
    all(f'data-lane="{x}"' in idx for x in ids if x in (C.load().get("lanes") or {}) and not
        next(l for l in chaos_lanes.LANES if l["id"] == x).get("baseline")),
    all(f'href="./{p}.html#cheap-side"' in idx for p in CB.HOMES), "Split v hold" in idx), (True, True, False))
check("challenger_dog_tp30 is marked retired there", "retired 2026-10-27" in idx, True)

print("\nthe retirement")
lane = next(x for x in chaos_lanes.LANES if x["id"] == "challenger_dog_tp30")
check("dated, with its record and reason", (lane["retired"]["on"], "45 settled, 13 won" in lane["retired"]["at"],
      "superseded by challenger_cheap_split" in lane["retired"]["reason"]), ("2026-10-27", True, True))
seen = []
fake_events = ["KXATPCHALLENGERMATCH-26OCT26AAABBB", "KXATPCHALLENGERMATCH-26OCT27CCCDDD"]
_le, _re = C.list_events, C.replay_event
C.list_events = lambda series, since, fetch, until=None: list(fake_events)
C.replay_event = lambda ln, series, event, fetch, now=None: (seen.append(event), ([], "not settled with a clean result"))[1]
try:
    st = C.empty()
    C.run(st, [lane], now=dt.datetime(2026, 10, 28, 10, tzinfo=C.UTC), fetch=None)
finally:
    C.list_events, C.replay_event = _le, _re
check("no event from its retirement night on is replayed; the night before still is", seen, ["KXATPCHALLENGERMATCH-26OCT26AAABBB"])
check("the ledger carries the retirement", st["lanes"]["challenger_dog_tp30"]["retired"]["on"], "2026-10-27")
tt = next(x for x in chaos_lanes.LANES if x["id"] == "nba_tt_cheap_tp30")
check("nba_tt_cheap_tp30 retired 2026-10-27 with its record", (tt["retired"]["on"], "145 settled, 26 won" in tt["retired"]["at"]),
      ("2026-10-27", True))
check("the NBA page keeps the nba_ml_dog_tp50 baseline open and folds nba_tt_cheap_tp30 into Retired",
      (folded(pages["nba"], 'id="baseline-nba_ml_dog_tp50" open>'),
       folded(pages["nba"], '<li data-lane="nba_tt_cheap_tp30"')), (False, True))
if "nba_ml_dog_tp50" in (C.load().get("lanes") or {}):
    ml = pages["nba"][pages["nba"].find('id="baseline-nba_ml_dog_tp50" open'):]
    check("NBA: the moneyline baseline opens on its split v hold record, the ask 10-30c row in it, then the other exits fold",
          (ml.find("chaos-split") < ml.find("Other exits"), "ask 10-30c" in ml[:ml.find("Other exits")]), (True, True))
    glance = pages["nba"][pages["nba"].find('<section id="glance"'):pages["nba"].find('<section id="cheap-side">')]
    check("NBA: the glance table lists the two active lanes in order, each linking to its card (the ML underdog is a baseline)",
          re.findall(r'<a href="#([^"]+)"><b>', glance), ["wm-yes", "wm-no"])

print("\nblind lanes demoted to baselines (2026-11-01, Olu: a lane needs a team or matchup filter)")
for lid, at in (("cfb_dog_tp50", "33 settled events; split -0.5%, hold -15.9%"),
                ("nba_ml_dog_tp50", "31 settled events; split +8.7%, hold -16.5%")):
    cfg = next(x for x in chaos_lanes.LANES if x["id"] == lid)
    check(f"{lid}: a baseline, not retired, dated with its record and the reason", (
        cfg["baseline"]["on"], cfg["baseline"]["at"], "blind selection (price band only, no team filter)" in cfg["baseline"]["reason"],
        "retired" in cfg), ("2026-11-01", at, True, False))
check("the win margin YES split is not demoted (its buckets came from tracker research)",
      next(x for x in chaos_lanes.LANES if x["id"] == "nba_winmargin_split").get("baseline"), None)
cfb = next(x for x in chaos_lanes.LANES if x["id"] == "cfb_dog_tp50")
seen_b = []
_le, _re = C.list_events, C.replay_event
C.list_events = lambda series, since, fetch, until=None: ["KXNCAAFGAME-26NOV01AAABBB", "KXNCAAFGAME-26NOV07CCCDDD"]
C.replay_event = lambda ln, series, event, fetch, now=None: (seen_b.append(event), ([], "not settled with a clean result"))[1]
try:
    st_b = C.empty()
    C.run(st_b, [cfb], now=dt.datetime(2026, 11, 8, 10, tzinfo=C.UTC), fetch=None)
finally:
    C.list_events, C.replay_event = _le, _re
check("a baseline keeps replaying every new night (a live baseline, unlike a retired lane)", seen_b,
      ["KXNCAAFGAME-26NOV01AAABBB", "KXNCAAFGAME-26NOV07CCCDDD"])
check("the ledger carries the baseline mark", st_b["lanes"]["cfb_dog_tp50"]["baseline"]["on"], "2026-11-01")
check("a baseline has no review status", CB.status_of(dict(baseline=cfb["baseline"]), 40), "baseline, not a lane")
nfl_cs = pages["nfl"][pages["nfl"].find('<section id="cheap-side">'):]
nfl_cs = nfl_cs[:nfl_cs.find("</section>")]
check("NFL: no lane summary row for it; the baseline block says a filtered lane must beat it; no decide-at status in it",
      ('<tr data-lane="cfb_dog_tp50"' in nfl_cs, "Baseline · College football underdog (blind, price band only)" in nfl_cs,
       "must beat" in nfl_cs, "decide at" in nfl_cs[nfl_cs.find("Baseline ·"):].lower()), (False, True, True, False))
check("the Sandbox index lists the baselines apart, linking to each block, with no lane row",
      ('<tr data-lane="cfb_dog_tp50"' in idx, 'href="./nfl.html#baseline-cfb_dog_tp50"' in idx), (False, True))

print("\nCulture, Commodities and Fights: every active cheap-side lane visible")
import commodities_build
import culture_build
import fights_build
import fights_split
import mentions_split as MS
for name, html, cfgs in (("culture", culture_build.build(), culture_build.LIVE_CHEAP),   # the weekly and monthly mention lanes retired 2026-10-31: in a Retired fold
                         ("commodities", commodities_build.build(), MS.COMMOD_LANES),
                         ("fights", fights_build.build(), fights_split.LANES)):
    hidden = [c["lane"] for c in cfgs if folded(html, f'id="{c["anchor"]}"') is not False]
    check(f"{name}: every lane card on the page and not folded", hidden, [])
fights_html = fights_build.build()
check("fights: each card says it is price band only and becomes a baseline when a filtered fights lane exists",
      (fights_html.count("Price band only: becomes a baseline when a filtered fights lane exists."), len(fights_split.LANES)), (2, 2))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
