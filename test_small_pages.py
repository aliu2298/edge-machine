#!/usr/bin/env python3
"""Offline checks for the small page fixes of 2026-11-06: archived tabs leave Control Center, the tennis and NFL header tiles count their cheap-side
lanes, the econ Production row and its header tile are one basis, and the Frozen badge says what it means."""
import datetime as dt
import re
import sys

import chaos_build
import control_center as CC
import daily_build
import daily_track as D
import sandbox_track as T
import site_chrome
import tennis_build

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("Control Center: an archived tab is not an area")
m = CC.model(T.load(), T.load_stages(), {"leads": {}, "pairs": {}}, dt.datetime.now(dt.timezone.utc))
keys = [a["key"] for a in m["areas"]]
check("cricket (archived) is gone, soccer and tennis stay", ("cricket" in keys, "soccer" in keys, "tennis" in keys), (False, True, True))
check("no archived tab is an area", sorted(set(keys) & set(site_chrome.archived_tabs())), [])

print("\nthe tennis header tiles count their cheap-side lanes")
for page in ("tennis",):                     # NFL's college football lanes retired 2026-11-11: nothing live to count
    t = chaos_build.page_tiles(page)
    check(f"{page}: at least one lane counted, with a held record", (t["active"] >= 1, t["record"] is not None and t["record"]["n"] > 0), (True, True))
html = tennis_build.build()
tiles = html[html.find('class="tiles sp-tiles"'):][:900]
text = re.sub(r"<[^>]+>", " ", tiles)
check("the tennis page no longer reads 0 active rules and an empty record", ("0 active rules" in re.sub(r"\s+", " ", text), "—" in re.sub(r"\s+", " ", text).split("open picks")[1][:40]), (False, False))

t = chaos_build.page_tiles("nfl")
check("nfl: no live cheap-side lane since 2026-11-11, so no tile record", (t["active"], t["record"], t["n_lanes"]), (0, None, 0))

print("\nEcon Daily: one basis for the Production lane")
state = D.load()
html = daily_build.build("econ_daily", state, dt.datetime.now(dt.timezone.utc))
row = re.search(r'data-source="econ_nc_yes".*?<span class="sp-cell num" data-l="Record">(.*?)</span>', html, re.S)
tile = re.search(r"<b>(\d+–\d+)</b><span>since Production", html)
check("the row's record and the header tile's are the same W–L", (row is not None and re.sub(r"<[^>]+>", "", row.group(1)).strip()) == (tile.group(1) if tile else None), True)
check("the row says what frozen means and what the record counts", ("the rule itself was frozen the day it was registered" in html, "Counted since Production" in html), (True, True))

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
