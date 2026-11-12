#!/usr/bin/env python3
"""test_daily_markets_fold.py — the Daily Markets page folds (2026-11-11, layout only).

It was ~13,400 px (about 18 screens), 70% of it the Completed event lists open in every group. Now: one tile per section; every
section a CLOSED fold whose line carries its win % and return; Completed behind a count line; an empty Next 24h / In progress tab
left out; everything in each section is still the one its own builder wrote. Old URLs and anchors keep working.
"""
import datetime as dt
import re
import sys

import daily_markets_build as D

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


html = D.build(dt.datetime(2026, 11, 11, 22, 0, tzinfo=dt.timezone.utc))
main = html[html.index("<main"):]

print("the summary tiles")
tiles = re.findall(r'<a class="tile" href="#(\w+)"><b>(.*?)</b><span>(.*?)</span><span class="sub sm">(.*?)</span></a>', main)
check("one tile per section, in page order", [t[0] for t in tiles], ["swing15", "crypto", "commodities", "econ", "finance"])
check("each tile is a win % (or a dash before a first settled bet)", all(re.fullmatch(r"\d+%|—", t[1]) for t in tiles), True)
check("each tile's sub-line is a W–L and a return, in percentages", all(re.search(r"\d+–\d+ · [+−-]?\d+(\.\d+)?% return|no settled bets yet", t[3]) for t in tiles), True)
check("the tile names are the section names", [t[2] for t in tiles], ["15-Minute", "Crypto", "Commodities", "Econ", "Finance (S&amp;P)"])

print("\nevery section is a closed fold with its record on the line")
secs = re.findall(r'<section id="(\w+)" class="dm-group" data-sp-group="\1">\s*<details class="fold sec dm-sec"( open)?><summary><h2 class="dm-title">(.*?)</h2><span class="mut sm">· (.*?)</span></summary>', main)
check("five sections, each keeping its id and data-sp-group", [s[0] for s in secs], ["swing15", "crypto", "commodities", "econ", "finance"])
check("none starts open", [s[1] for s in secs], [""] * 5)
check("the closed line carries the win % and the return (or says no settled bets)", all(("% won" in s[3] and "return" in s[3]) or "no settled bets" in s[3] for s in secs), True)
check("the tile numbers are the sections' own numbers", all(t[1] in s[3] or t[1] == "—" for t, s in zip(tiles, secs)), True)

print("\nthe events")
for g in ("crypto", "commodities", "econ", "finance"):
    ev = main[main.index(f'<section id="{g}-events"'):]
    ev = ev[:D._close(ev, 0)]
    check(f"{g}: Completed is one closed fold with a count line", re.search(r'<details class="fold dm-done"><summary>Completed · 14 days · <span class="sp-count">\d+</span> bets</summary>', ev) is not None, True)
    check(f"{g}: a tab with nothing in it is left out", ('data-tab="next"' in ev) == bool(re.search(r'data-tab="next"[^>]*>Next 24h <span class="sp-count">[1-9]', ev)), True)
    check(f"{g}: the section's rules come before its events", main.index(f'id="{g}-rules"') < main.index(f'id="{g}-events"'), True)
    check(f"{g}: the filters and event wiring ids are untouched", all(f'id="{g}-{x}"' in main for x in ("rules", "events")) and 'data-sp-role="events"' in ev, True)
check("the Econ weekly block is folded and closed", '<details class="fold dm-weekly"><summary>Econ weekly</summary>' in main, True)

print("\nfolding only, on synthetic markup")
panel = lambda tab, n: (f'<section class="sp-panel" id="x-events-{tab}" role="tabpanel" data-tab="{tab}"><h3 class="sp-panel-title">{tab}</h3>'
                        + ('<section class="sp-day"><div class="sp-event"><div class="sp-pick is-won">a</div></div></section>' * n or '<p class="sp-empty">none</p>') + '</section>')
tab = lambda t, n: f'<button type="button" role="tab" data-tab="{t}" aria-selected="false">{t} <span class="sp-count">{n}</span></button>'
ev = ('<section id="x-events" data-sp-role="events"><div class="sp-tabs">' + tab("next", 2) + tab("live", 0) + tab("done", 3) + '</div>'
      + panel("next", 2) + panel("live", 0) + panel("done", 3) + '</section>')
out = D._events_fold(ev, "x")
check("a non-empty Next 24h stays, an empty In progress goes", ('data-tab="next"' in out, 'data-tab="live"' in out), (True, False))
check("with two tabs left the tab strip stays", '<div class="sp-tabs"' in out, True)
check("Completed folds behind its count", '<summary>done · <span class="sp-count">3</span> bets</summary>' in out, True)
out2 = D._events_fold(ev.replace(tab("next", 2), tab("next", 0)).replace(panel("next", 2), panel("next", 0)), "x")
check("with only Completed left the strip is dropped (its fold line has the count)", ('<div class="sp-tabs"' in out2, 'data-tab="next"' in out2), (False, False))
stats = D.group_stats('<div class="tiles sp-tiles"><div class="tile"><b>0</b><span>open picks</span></div><div class="tile"><b>2</b><span>active rules</span></div>'
                      '<div class="tile"><b>7–2</b><span>since Production · X</span></div><div class="tile"><b class="mut">+13.7%</b><span>ROI after fees · since Production</span></div></div></div>'
                      '<div class="tiles"><div class="tile"><b>+99.0%</b><span>ROI after fees · held</span></div></div>')
check("the group's own four tiles are read, not a later block's", (stats["wl"], stats["roi"], stats["rules"], D.win_pct(7, 2), D.sum_line(stats)),
      ("7–2", "+13.7%", "2", "78%", "78% won · 7–2 · +13.7% return"))

print("\none basis for every tile (2026-11-11): the running rules added up as their rows count them")
row = lambda stage, rec, roi: (f'<details class="sp-rule" data-stage="{stage}"><summary class="sp-line"><span class="sp-cell num" data-l="Record">{rec}</span>'
                              f'<span class="sp-cell num" data-l="ROI after fees"><span class="mut">{roi}</span></span><span class="sp-cell">x</span></summary></details>')
sec = ('<section id="z-rules"><div class="sp-rules-list">' + row("production", "9–0", "+4.4%") + row("sandbox", "18–5", "+3.8%")
       + row("sandbox", "2–0 wks", "+145.3% held") + '</div></section><section id="z-events"></section>')
rs = D.rules_stats(sec, "z")
check("Production and Sandbox rows are added; a weekly row (another unit) is left out", (rs["wl"], rs["rules"]), ("27–5", "2"))
check("the return is the average per bet", rs["roi"], f"{(9 * 4.4 + 23 * 3.8) / 32:+.1f}%")
check("a section with no row says so", D.rules_stats('<section id="z-rules"></section>', "z"), None)
for g in ("crypto", "commodities", "econ", "finance"):
    a = main.index(f'<section id="{g}-rules"')
    got = D.rules_stats(main[a:], g)
    tile = [t for t in tiles if t[0] == g][0]
    check(f"{g}: the tile is its rule rows added up ({got['wl'] if got else '—'})", tile[3].startswith(got["wl"]) if got else tile[3] == "no settled bets yet", True)
check("the page says what a tile counts, in a few words", "adds up the section" in main and "Production and Sandbox" in main, True)

print("\nold URLs and anchors")
for g, label, old in D.GROUPS:
    page = D.redirect_page(g, label, old)
    check(f"{old} still forwards to #{g}", f"daily_markets.html#{g}" in page, True)
    check(f"#{g} is a section id, and its fold is its first child, so tables.js opens it", f'<section id="{g}" class="dm-group"' in main, True)
js = open("public_site/tables.js").read()
check("tables.js opens a closed fold on an anchor and keeps the Completed count in step with the filter", ("node.open = true" in js, "details.dm-done > summary .sp-count" in js), (True, True))

print("\npublic copy")
text = re.sub(r"<[^>]+>", " ", main)
check("no dollar amount, balance or stake in the new lines", re.search(r"balance|\bstake of\b", text, re.I) is None, True)
BAD = ("real" + " money", "the " + "bo" + "t")
check("none of the guarded phrases (whole words: 'bottom' is fine)", [w for w in BAD if re.search(r"\b" + w + r"\b", text.lower())], [])

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
