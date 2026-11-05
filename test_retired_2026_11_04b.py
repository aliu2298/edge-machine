#!/usr/bin/env python3
"""Offline checks for the second 2026-11-04 retirement round (Olu): WTI oil · cheap YES, and the two Turkey
heavy-mismatch lanes (over 2.5 and BTTS, siblings on the same fixtures). None is in Production. The AAA gas cheap-NO
lanes stay, and are live again: they were copies of the mentions WIDE config, so they had inherited its 2026-10-31
retirement and logged nothing from that day."""
import datetime as dt
import html
import inspect
import re
import sys

import commodities_build as CB
import lane_preflight as LP
import mentions_split as MS
import production as P
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


print("the Turkey pair: off the run, retired with dated records")
for name, scope, why, rec in (("turkey_o25_dog", "soccer_o25", S.TURKEY_O25_DOG_RETIRED_WHY, "4 won v 5.1 priced, −24.5% after fees"),
                              ("turkey_btts_dog", "soccer_btts", S.TURKEY_BTTS_DOG_RETIRED_WHY, "3 won v 4.2 priced, −29.4% after fees")):
    m = S.SOURCES[name]
    check(f"{name}: off the run, retired", (m["sports"], m["retired_sports"]), ([], {scope: why}))
    check(f"{name}: the record", rec in why, True)
    check(f"{name}: its rows still settle (a retired scope is not a removed row)", S.removed_row(dict(source=name, sport=scope)), False)
check("the pre-flight no longer probes their series (board_sport needs a live sport)",
      sorted({lane for lane, _s, _k in LP.checks()} & {"turkey_o25_dog", "turkey_btts_dog"}), [])

print("\nthe Soccer page: both in Retired rules, not above the fold")
sh = soccer_build.build()
i = sh.find('<section id="retired"')
fold = sh[i:sh.find("</section>", i)]
for name, why in (("turkey_o25_dog", S.TURKEY_O25_DOG_RETIRED_WHY), ("turkey_btts_dog", S.TURKEY_BTTS_DOG_RETIRED_WHY)):
    m = re.search(rf'sp-retired-why" data-source="{name}"[^>]*>(.*?)</p>', fold, re.S)
    check(f"{name}: its line in the fold", html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else None, why)
    check(f"{name}: not above the fold", f'data-source="{name}"' in sh[:i], False)

print("\nthe stamp-of-approval table tags both RETIRED")
check("source_retired", (B.source_retired("turkey_o25_dog"), B.source_retired("turkey_btts_dog")), (True, True))
page = B.build()
k = page.find("Stamp of approval")
table = page[k:page.find("</table>", k)]
for name in ("turkey_o25_dog", "turkey_btts_dog"):
    row = next((r for r in re.findall(r"<tr><td><b>(.*?)</td>", table) if html.escape(S.SOURCES[name]["label"], quote=False) in r
                or S.SOURCES[name]["label"] in html.unescape(r)), None)
    check(f"{name}: tagged", bool(row) and "data-retired" in row, True)

print("\nWTI oil · cheap YES: retired; the gas lanes live (no inherited retirement)")
now = dt.datetime(2026, 11, 5, 12, tzinfo=UTC)
check("WTI dated with its record", (MS.WTI["retired"]["on"], MS.WTI["retired"]["at"]),
      ("2026-11-04", "13 entries on 4 settled events, 1 won; split −60.2%, hold −75.6%"))
check("the Eastern date gate", (MS.retired(MS.WTI, dt.datetime(2026, 11, 4, 4, tzinfo=UTC)),
                                MS.retired(MS.WTI, dt.datetime(2026, 11, 4, 5, tzinfo=UTC))), (False, True))
check("gas daily and weekly carry no retirement, and are not retired", [(c["lane"], c.get("retired"), MS.retired(c, now))
                                                                         for c in (MS.GAS, MS.GAS_WEEK)],
      [("gas_cheap_no", None, False), ("gas_week_cheap_no", None, False)])
check("WTI is built without WIDE's mentions retirement", "if k != \"retired\"" in inspect.getsource(MS), True)
check("live and retired commodity lanes", ([c["lane"] for c in MS.LIVE_COMMOD], [c["lane"] for c in MS.GONE_COMMOD]),
      (["gas_cheap_no", "gas_week_cheap_no"], ["wti_cheap_yes"]))
check("the album lanes are still live", [MS.ALBUM.get("retired"), MS.ALBUM_NO.get("retired")], [None, None])
check("run() takes no new entry for a retired lane, fills and settlement go on",
      "pending = []                       # retired" in inspect.getsource(MS.run), True)

print("\nthe Commodities page: WTI in the cheap-side Retired fold, the gas lanes above it")
ch = CB.build()
a, j = ch.find('id="cheap-side"'), ch.find('id="retired-cheap"')
cheap = ch[a:ch.find("</section>", j)]
check("one fold", (j > a > 0, ch.count('id="retired-cheap"')), (True, 1))
check("WTI's card in the fold, not above it", ('id="wti-cheap-yes"' in ch[j:], 'id="wti-cheap-yes"' in ch[a:j]), (True, False))
check("both gas cards live", ('id="gas-cheap-no"' in ch[a:j], 'id="gas-week-cheap-no"' in ch[a:j]), (True, True))
check("the fold names the record", "split −60.2%, hold −75.6%" in html.unescape(ch[j:]), True)

print("\nnone is in Production")
st = T.load_stages()
check("no Production pair for any of them",
      sorted(p for p in P.production_pairs(st) if p.split("|")[0] in ("turkey_o25_dog", "turkey_btts_dog", "wti_cheap_yes")), [])

check("no guarded phrase in the new copy", sandbox_audit.COPY_RE.search(
    S.TURKEY_O25_DOG_RETIRED_WHY + S.TURKEY_BTTS_DOG_RETIRED_WHY + str(MS.WTI["retired"]) + fold + cheap + table), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
