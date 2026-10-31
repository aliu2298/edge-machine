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
ids = ["standard", "lanes", "album-note", "album-cheap-rungs", "album-cheap-no", "models", "retired-cheap",
       "mentions-split", "mentions-split-compare", "mentions-split-wide", "mentions-month-split",
       "mentions-month-split-compare", "mentions-month-split-wide", "archive"]
pos = [h.find(f'id="{i}"') for i in ids]
check("standard, summary and the album cards, model lanes, the Retired fold (weekly then monthly mention cards), archive",
      (all(p > 0 for p in pos), pos == sorted(pos)), (True, True))
check("the standard, in Olu's words",
      all(x in t for x in ("Cheap side + resting take-profit.", "Buy cheap contracts at the event's open, at the real ask.",
                           "Rest a split sell: half at 2x, half at 3x.", "A fill counts only on a traded print.",
                           "Every lane is shown next to the same entries held.")), True)

print("\nthe summary table: one row per LIVE cheap-side lane (the album lanes); the retired mention lanes sit in their fold")
summ = h[h.find('class="culture-summary"'):h.find("</table>", h.find('class="culture-summary"'))]
retired_h = h[h.find('id="retired-cheap"'):h.find('id="archive"')]
rsumm = retired_h[retired_h.find('class="culture-summary"'):retired_h.find("</table>", retired_h.find('class="culture-summary"'))]
rows = re.findall(r"<tr>(.*?)</tr>", summ.split("<tbody>", 1)[1], re.S)
rrows = re.findall(r"<tr>(.*?)</tr>", rsumm.split("<tbody>", 1)[1], re.S)
check("the retired fold's summary lists the four mention lanes, in order",
      [re.sub(r"<[^>]+>", "", r.split("</td>")[0]).strip() for r in rrows],
      [_html.escape(c["label"], quote=False) for c in KB.GONE_CHEAP])
check("the page summary lists the two album lanes only", [text(r).split(" ", 1)[1].split(" 0 ")[0] if False else re.sub(r"<[^>]+>", "", r.split("</td>")[0]).strip()
                             for r in rows],
      [_html.escape(c["label"], quote=False) for c in KB.LIVE_CHEAP])
check("columns: entries, unverified asks, settled entries, settled events, won, split ROI, hold ROI, legs 2x / 3x, average spread paid, status",
      [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<th[^>]*>(.*?)</th>", rsumm)],
      ["Lane", "Entries", "Unverified asks", "Settled entries", "Settled events", "Won", "Split ROI", "Hold ROI", "Legs filled 2x / 3x", "Avg spread paid", "Status"])
w0 = text(rrows[0])
check("the weekly strict row: 2 entries, 2 settled, both in 1 event, 1 won, legs 1 / 0, 4c spread, the review status",
      ("2 0 2 1 1" in w0, "1 / 0" in w0, "0.04" in w0, "1 settled event · review at 10, decide at 30" in w0), (True, True, True, True))
check("strict v wide average spread paid, for the mention lanes",
      "Weekly mentions, strict v wide average spread paid 0.04 v 0.10. Monthly mentions, strict v wide average spread paid — v —." in t,
      True)
check("status moves at 10 and 30", (KB.status(9), KB.status(10), KB.status(30)),
      ("9 settled events · review at 10, decide at 30", "10 settled events · review due (10 reached) · decide at 30",
       "30 settled events · decide now (30 reached)"))

print("\nthe cards are consistent")
cards = re.findall(r'<section class="lane-card" id="([^"]+)">(.*?)</section>', h, re.S)
tiles = {i: re.findall(r'<div class="tile"><b>[^<]*</b><span>([^<]+)</span>', c) for i, c in cards}
check("six cards, every one with the same tiles", (len(cards), len({tuple(v) for v in tiles.values()}),
      next(iter(tiles.values()))),
      (6, 1, ["entries", "settled entries", "settled events", "won", "ROI after fees · split", "ROI after fees · held",
             "split ROI per event", "legs filled 2x / 3x"]))
heads = {i: tuple(re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<th[^>]*>(.*?)</th>", c)) for i, c in cards}
norm = {i: tuple(x for x in v if x not in ("Week", "Event", "Word", "Rung", "YES ask paid", "NO ask paid")) for i, v in heads.items()}
check("and the same columns (units and side aside)", len(set(norm.values())), 1)

print("\nmodel lanes and the archive")
models = text(h[h.find('id="models"'):h.find('id="retired-cheap"')])
check("rt_model under Model lanes, with its revival note", ("Rotten Tomatoes model" in models,
      "revived 2026-10-26 · fresh record · review at 10" in models), (True, True))
arch_h = h[h.find('id="archive"'):]
arch = text(arch_h)
check("the Archive is collapsed and holds the three old lanes, one line each",
      ('<details class="fold sec" id="archive">' in h, arch.count("(mentions_rate)"), arch.count("(culture_endgame)"),
       arch.count("(culture_fav_band)")), (True, 1, 1, 1))
outside = text(h[:h.find('id="archive"')])
check("the old lanes are not shown anywhere above the Archive",
      any(K.LANES[k] in outside for k in ("mentions_rate", "culture_endgame", "culture_fav_band")), False)
check("no leftover blocks of the old template (verdict chips, Events, Production list, Observing)",
      [x for x in ('data-verdict=', 'id="events"', 'data-list="production"', "Observing · paper", 'id="sandbox"')
       if x in h], [])
check("the ledger was not touched", ledger["lanes"]["mentions_rate"]["picks"], [])

print("\nthe document")
check("Culture is the active page in the site nav; the in-page links name the four parts",
      ('aria-current="page"' in h and "culture" in h, all(f'href="#{i}"' in h for i in ("standard", "lanes", "models", "archive"))),
      (True, True))
check("every table sits in a scroll wrapper and its cells carry phone labels",
      (h.count("<table") == h.count('<div class="tbl"><table'), 'data-l="Entries"' in h), (True, True))
check("no guarded public phrase on the page", sandbox_audit.COPY_RE.findall(t), [])
real = KB.build(now=NOW)
check("the live ledgers build", ('id="lanes"' in real, 'id="archive"' in real), (True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
