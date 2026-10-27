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
       "nba": ["nba_ml_dog_tp50", "nba_tt_cheap_tp30"], "nfl": ["cfb_dog_tp50"]})
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
    check(f"{page}: the cheap-side section is the first section of the page", first and first.group(1), "cheap-side")
    for lane in CB.HOMES[page]:
        L = next(x for x in chaos_lanes.LANES if x["id"] == lane)
        if L.get("retired"):
            check(f"{page}: {lane} (retired) is in the collapsed Retired block", folded(html, f'<li data-lane="{lane}"'), True)
        elif lane in (C.load().get("lanes") or {}):
            check(f"{page}: {lane}'s card is visible without opening a fold",
                  folded(html, f'<details class="section-disclosure" data-lane="{lane}" open>'), False)
check("nfl: the college football block names itself", "College football" in pages["nfl"], True)

print("\nthe Sandbox index")
idx = CB.section()
check("an index: a row per lane, a link to each home, no lane cards", (
    all(f'data-lane="{x}"' in idx for x in ids if x in (C.load().get("lanes") or {})),
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
check("the NBA page keeps nba_ml_dog_tp50 open and folds nba_tt_cheap_tp30 into Retired",
      (folded(pages["nba"], '<details class="section-disclosure" data-lane="nba_ml_dog_tp50" open>'),
       folded(pages["nba"], '<li data-lane="nba_tt_cheap_tp30"')), (False, True))

print("\nCulture, Commodities and Fights: every active cheap-side lane visible")
import commodities_build
import culture_build
import fights_build
import fights_split
import mentions_split as MS
for name, html, cfgs in (("culture", culture_build.build(), culture_build.CHEAP),
                         ("commodities", commodities_build.build(), MS.COMMOD_LANES),
                         ("fights", fights_build.build(), fights_split.LANES)):
    hidden = [c["lane"] for c in cfgs if folded(html, f'id="{c["anchor"]}"') is not False]
    check(f"{name}: every lane card on the page and not folded", hidden, [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
