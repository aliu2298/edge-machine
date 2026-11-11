#!/usr/bin/env python3
"""The Culture page redone (2026-10-27): the cheap-side standard first, the old lanes in the Archive."""
import datetime as dt
import html as _html
import re
import sys

import culture_build as KB
import culture_track as K
import mentions_split as M
import sandbox_audit

FAILS = []
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 27, 6, 0, tzinfo=UTC)


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html.unescape(h)))


def entry(ev, word, price, settled=None, f2=False, f3=False, spread=0.04):
    e = dict(id=f"{ev}-{word}", event=ev, word=word, side="yes", entry_at="2026-10-26T05:33:00+00:00", price=price,
             bid=round(price - spread, 2), spread=spread, traded_to_entry=0.0,
             legs=[dict(multiple=m, share=w, target=t) for m, w, t in M.targets(price)], payout=settled)
    for leg, f in zip(e["legs"], (f2, f3)):
        if f:
            leg["filled_at"], leg["fill_px"] = "2026-10-26T09:00:00+00:00", leg["target"]
        elif settled is not None:
            leg["settled_px"] = settled
    return M.grade(e)


ledger = {"lanes": {k: {"picks": [], "observations": {}, "error": None} for k in K.LANES}, "words": {}}
weekly = {"entries": [entry("KXTRUMPSAY-26NOV02", "A", 0.20, settled=0.0, f2=True),
                      entry("KXTRUMPSAY-26NOV02", "B", 0.10, settled=1.0)], "skips": {}, "events": {}}
wide = {"entries": [entry("KXTRUMPSAY-26NOV02", "C", 0.18, spread=0.10)], "skips": {}, "events": {}}
empty = {"entries": [], "skips": {}, "events": {}}
h = KB.build(ledger, NOW, split_state=weekly, wide_state=wide, month_state=empty, month_wide_state=empty,
             album_state=empty, album_no_state=empty)
t = text(h)

print("the order, top to bottom")
ids = ["standard", "lanes", "dip-hold-row", "album-cheap-rungs-row", "album-cheap-no-row", "rt-model-row", "retired", "retired-cheap", "archive"]
pos = [h.find(f'id="{i}"') for i in ids]
check("standard, the lane rows (dip bid, the album lanes, the model lane), one Retired block holding the mention lanes and the archive",
      (all(p > 0 for p in pos), pos == sorted(pos)), (True, True))
check("the standard, in Olu's words",
      all(x in t for x in ("Cheap side + resting take-profit.", "Buy cheap contracts at the event's open, at the real ask.",
                           "Rest a split sell: half at 2x, half at 3x.", "A fill counts only on a traded print.",
                           "Every lane is shown next to the same entries held.")), True)

print("\nthe lanes: one closed row per LIVE lane (2026-11-11, Olu)")
lanes_h = h[h.find('id="lanes"'):h.find('id="retired"')]
names = [_html.unescape(x) for x in re.findall(r'<b class="sp-name"[^>]*>(.*?)</b>', lanes_h)]
check("the rows, in order: the dip bid, the two album lanes, the model lane", names,
      ["Trump mentions · 10c dip bid, hold"] + [c["label"] for c in KB.LIVE_CHEAP] + [K.LANES["rt_model"]])
check("every row is closed on load, and no fold is open", ("<details open" in h, re.findall(r"<details[^>]* open[ >]", h)), (False, []))
head_ = lanes_h[lanes_h.find("sp-head-line"):lanes_h.find("</div>", lanes_h.find("sp-head-line"))]
check("the columns: lane, market, record, entries, ROI after fees, comparison, won v priced, evidence, verdict",
      re.findall(r'<span class="sp-cell[^"]*">([^<]*)</span>', head_),
      ["Lane", "Market", "Record (events)", "Entries", "ROI after fees", "Comparison", "Won v priced", "Evidence", "Verdict"])
tl = re.findall(r'<div class="tile"><b>([^<]*)</b><span>([^<]+)</span>', h.split('id="lanes"')[0].split('id="standard"')[1])
rowsum = lambda key: sum(int(x) for x in re.findall(rf'data-l="{key}">(\d+)', lanes_h))
check("the header tiles agree with the rows: lanes and entries", (dict((k, v) for v, k in tl)["active lanes"], dict((k, v) for v, k in tl)["entries"]),
      (str(len(names)), str(rowsum("Entries"))))
check("status moves at 10 and 30", (KB.status(9), KB.status(10), KB.status(30)),
      ("9 settled events · review at 10, decide at 30", "10 settled events · review due (10 reached) · decide at 30",
       "30 settled events · decide now (30 reached)"))

print("\nthe retired mention lanes: ONE line in the collapsed Retired fold (2026-11-06, Olu)")
retired_h = h[h.find('id="retired-cheap"'):h.find('id="archive"')]
rt = text(retired_h)
check("collapsed, one line, no cards, tables or tiles left",
      ('<details class="fold sec" id="retired-cheap">' in h, retired_h.count("<li>"), "<table" in retired_h,
       'class="tile"' in retired_h, "lane-card" in retired_h), (True, 1, False, False, False))
check("the line: the four names, retired date, final record, reason",
      ("Weekly strict 5c, Weekly wide 10c, Monthly strict 5c, Monthly wide 10c" in rt, "retired 2026-10-31" in rt,
       "final record 3 valid entries since 2026-10-27, 1 won" in rt, "books too thin to pass the spread + ask check" in rt),
      (True, True, True, True))
check("no lane id in the line", [c["lane"] for c in KB.GONE_CHEAP if c["lane"] in retired_h], [])
none = KB.build(ledger, NOW, split_state=empty, wide_state=empty, month_state=empty, month_wide_state=empty,
                album_state=empty, album_no_state=empty)
check("with no valid entry: 0 valid entries since 2026-10-27, nothing open",
      ("final record 0 valid entries since 2026-10-27; books too thin" in text(none), "still settling" in text(none)), (True, False))
opened = {"entries": [entry("KXTRUMPSAY-26NOV09", "D", 0.12)], "skips": {}, "events": {}}
check("an open entry still shows, settling",
      "1 open entry still settling" in text(KB.build(ledger, NOW, split_state=opened, wide_state=empty, month_state=empty,
                                                      month_wide_state=empty, album_state=empty, album_no_state=empty)), True)

print("\nthe cards are consistent")
cards = re.findall(r'<section class="lane-card" id="([^"]+)">(.*?)</section>', h, re.S)
tiles = {i: re.findall(r'<div class="tile"><b>[^<]*</b><span>([^<]+)</span>', c) for i, c in cards}
check("two cards (the album lanes), with the same tiles", (sorted(tiles), len({tuple(v) for v in tiles.values()}),
      next(iter(tiles.values()))),
      (["album-cheap-no", "album-cheap-rungs"], 1, ["entries", "settled entries", "settled events", "won", "ROI after fees · split",
                                                   "ROI after fees · held", "split ROI per event", "legs filled 2x / 3x"]))
heads = {i: tuple(re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<th[^>]*>(.*?)</th>", c)) for i, c in cards}
norm = {i: tuple(x for x in v if x not in ("Week", "Event", "Word", "Rung", "YES ask paid", "NO ask paid")) for i, v in heads.items()}
check("and the same columns (units and side aside)", len(set(norm.values())), 1)

print("\nmodel lanes and the archive")
models = text(h[h.find('id="rt-model-card"'):h.find('id="retired"')])
check("rt_model is a row, with its revival note in its closed details", ("Rotten Tomatoes model" in models,
      "revived 2026-10-26 · fresh record · review at 10" in models), (True, True))
arch_h = h[h.find('id="archive"'):]
arch = text(arch_h)
check("the Archive is collapsed and holds the three old lanes, one line each",
      ('<details class="fold sec" id="archive">' in h, arch.count("(mentions_rate)"), arch.count("(culture_endgame)"),
       arch.count("(culture_fav_band)")), (True, 1, 1, 1))
above = h[:h.find('id="retired"')]
outside = text(above)
check("the old lanes are not shown anywhere above the Archive",
      (any(K.LANES[k] in outside for k in ("culture_endgame", "culture_fav_band")), "(mentions_rate)" in outside), (False, False))
check("no leftover blocks of the old template (verdict chips, Events, Production list, Observing)",
      [x for x in ('id="events"', 'data-list="production"', "Observing · paper", 'id="sandbox"')
       if x in h], [])
check("the ledger was not touched", ledger["lanes"]["mentions_rate"]["picks"], [])

print("\nthe document")
check("Culture is the active page in the site nav; the in-page links name the two parts",
      ('aria-current="page"' in h and "culture" in h, all(f'href="#{i}"' in h for i in ("lanes", "retired"))),
      (True, True))
check("every table sits in a scroll wrapper and its cells carry phone labels",
      (h.count("<table") == h.count('<div class="tbl"><table'), 'data-l="Entries"' in h), (True, True))
check("no guarded public phrase on the page", sandbox_audit.COPY_RE.findall(t), [])
real = KB.build(now=NOW)
check("the live ledgers build", ('id="lanes"' in real, 'id="retired"' in real), (True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
