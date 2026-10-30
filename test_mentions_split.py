#!/usr/bin/env python3
"""Offline checks for the cheap-YES split lane on the weekly Trump-mention market (mentions_split.py)."""
import datetime as dt
import re
import sys

import culture_build as KB
import mentions_split as M
import sandbox_audit
import site_chrome as C

FAILS = []
# The sections below test entry, fill and settlement mechanics on fakes that serve no event endpoint, so they
# run with the ask rule off; the rule (2026-10-30) has its own section at the end, with it on.
_run = M.run
M.run = lambda *a, **k: _run(*a, **dict(k, ask_rule=k.get("ask_rule", False)))
UTC = dt.timezone.utc
OPEN = dt.datetime(2026, 10, 26, 4, 0, tzinfo=UTC)
O = int(OPEN.timestamp())


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def mc(mins, bid, ask, vol=0, hi=None):
    """A candle ending `mins` minutes after the open."""
    c = dict(end_period_ts=O + mins * 60, volume_fp=str(vol),
             yes_bid=dict(close_dollars=str(bid), high_dollars=str(bid)), yes_ask=dict(close_dollars=str(ask)),
             price=dict(high_dollars=None if hi is None else str(hi)))
    return c


print("the rule's terms")
check("registered terms", (M.SERIES, M.BAND, M.MAX_SPREAD, M.ENTRY_WINDOW_H, M.LEGS, M.CAP, M.TAKER, M.MAKER,
                           M.START, M.REVIEW_AT, M.DECIDE_AT),
      ("KXTRUMPSAY", (0.03, 0.30), 0.05, 6, ((2.0, 0.5), (3.0, 0.5)), 0.98, 0.07, 0.0175,
       "2026-10-26T04:00:00+00:00", 10, 30))
check("targets at 2x and 3x, capped at 0.98", [M.targets(p) for p in (0.23, 0.30, 0.40)],
      [[(2.0, 0.5, 0.46), (3.0, 0.5, 0.69)], [(2.0, 0.5, 0.6), (3.0, 0.5, 0.9)], [(2.0, 0.5, 0.8), (3.0, 0.5, 0.98)]])

print("\nentry: the first quote with a 5c spread inside 6h")
cs = [mc(10, 0.10, 0.20, vol=4), mc(30, 0.17, 0.21, vol=6), mc(40, 0.18, 0.20, vol=9)]
check("wide quotes are passed over; the first tight one, with the contracts traded up to it",
      M.entry_quote(cs, O), (O + 30 * 60, 0.17, 0.21, 10.0))
check("exactly 5c is tight", M.entry_quote([mc(5, 0.10, 0.15)], O)[2], 0.15)
check("nothing tight inside 6h: no entry (a tight quote at 6h01 is too late)",
      (M.entry_quote([mc(10, 0.1, 0.3), mc(361, 0.1, 0.12)], O), M.entry_quote([mc(360, 0.1, 0.12)], O)[0] - O),
      (None, 360 * 60))
check("a candle at the open itself is not after it", M.entry_quote([mc(0, 0.1, 0.12)], O), None)

print("\nfills: a trade at or above the target, never the bid")
leg_c = [mc(30, 0.40, 0.42, hi=0.50), mc(120, 0.40, 0.45, hi=0.45), mc(180, 0.47, 0.49, hi=None),
         mc(240, 0.30, 0.31, hi=0.46)]
entry_ts = O + 30 * 60
check("the entry's own candle does not count; a bid at 0.47 is not a fill; a 0.46 print is",
      M.fill_of(leg_c, entry_ts, 0.46), (O + 240 * 60, 0.46))
check("nothing printed at 0.69: unfilled", M.fill_of(leg_c, entry_ts, 0.69), None)
book = {"orderbook_fp": {"no_dollars": [["0.7500", "10"], ["0.7700", "5.5"], ["0.8000", "3"]], "yes_dollars": []}}
check("book size: YES offered at or under 0.23 = NO bids at 0.77 or more", M.book_size(book, 0.23), 8.5)

print("\ngrading: split, held and 2x only, after fees")
fin = lambda p: p + 0.07 * p * (1 - p)
out = lambda t: t - 0.0175 * t * (1 - t)


def ent(price, f2=None, f3=None, payout=None):
    e = dict(price=price, legs=[dict(multiple=m, share=w, target=t) for m, w, t in M.targets(price)], payout=payout)
    for leg, f in zip(e["legs"], (f2, f3)):
        if f:
            leg["filled_at"], leg["fill_px"] = f, leg["target"]
        elif payout is not None:
            leg["settled_px"] = payout
    return M.grade(e)


a = ent(0.23, "2026-10-27T05:00:00+00:00", "2026-10-28T05:00:00+00:00")
check("both legs filled before settlement: graded, held waits for the settlement",
      (a["status"], round(a["pnl"], 4), "roi_held" in a, round(a["roi_2x"], 4)),
      ("filled", round(0.5 * out(0.46) + 0.5 * out(0.69) - fin(0.23), 4), False,
       round((out(0.46) - fin(0.23)) / fin(0.23), 4)))
b = ent(0.23, "2026-10-27T05:00:00+00:00", None, payout=0.0)
check("2x filled, 3x held to a NO: half the stake back at 0.46, half lost; held -100%",
      (b["status"], round(b["pnl"], 4), b["roi_held"]), ("settled", round(0.5 * out(0.46) - fin(0.23), 4), -1.0))
c = ent(0.10, None, None, payout=1.0)
check("neither filled and the word was said: both legs paid at 1", round(c["roi"], 4), round((1 - fin(0.10)) / fin(0.10), 4))
d = ent(0.10)
check("an unresolved leg leaves it open, with no P/L", (d["status"], d.get("pnl")), ("open", None))
rec = M.record([a, b, c, d])
check("the record: 4 entries, 3 resolved, legs 2/1, the held figure over the 2 settled only",
      (rec["entries"], rec["resolved"], rec["filled_2x"], rec["filled_3x"], rec["n_held"]), (4, 3, 2, 1, 2))
check("ROI is the mean over resolved entries (equal stake)", round(rec["roi"], 6), round((a["roi"] + b["roi"] + c["roi"]) / 3, 6))

print("\nthe run: backfill, skips, the live book read, settlement")


def word(code, word_, status="active", result="", opened=OPEN):
    return dict(ticker=f"KXTRUMPSAY-26NOV02-{code}", open_time=opened.isoformat(), status=status, result=result,
                custom_strike={"Word": word_})


MKTS = [word("PEAC", "Peace"), word("CHEA", "Cheap"), word("PENY", "Penny"), word("WIDE", "Wide"), word("DEAR", "Dear"),
        word("LATE", "Late", opened=OPEN + dt.timedelta(hours=30))]
MIN = {"KXTRUMPSAY-26NOV02-PEAC": [mc(10, 0.10, 0.30), mc(93, 0.19, 0.23, vol=2)],
       "KXTRUMPSAY-26NOV02-CHEA": [mc(5, 0.03, 0.05)],
       "KXTRUMPSAY-26NOV02-PENY": [mc(5, 0.01, 0.02)],
       "KXTRUMPSAY-26NOV02-WIDE": [mc(5, 0.10, 0.25)],
       "KXTRUMPSAY-26NOV02-DEAR": [mc(5, 0.29, 0.31)]}
HOUR = {"KXTRUMPSAY-26NOV02-PEAC": [mc(120, 0.4, 0.45, hi=0.46), mc(600, 0.6, 0.7, hi=0.70)],
        "KXTRUMPSAY-26NOV02-CHEA": [mc(60, 0.04, 0.05, hi=0.09)]}
OLD = dict(event_ticker="KXTRUMPSAY-26OCT26", markets=[dict(ticker="KXTRUMPSAY-26OCT26-X", open_time="2026-10-19T04:00:00Z",
                                                            status="finalized", result="yes")])
calls = []


def fake(path, mkts=None):
    calls.append(path)
    if path.startswith("events?"):
        assert "series_ticker=KXTRUMPSAY&" in path
        return {"events": [dict(event_ticker="KXTRUMPSAY-26NOV02", markets=mkts or MKTS), OLD], "cursor": ""}
    if "candlesticks" in path:
        src = MIN if path.endswith("period_interval=1") else HOUR
        end = int(path.split("end_ts=")[1].split("&")[0])
        return {"market_tickers": list(src), "market_candlesticks": [[c for c in v if c["end_period_ts"] <= end]
                                                                      for v in src.values()]}
    if path.endswith("/orderbook"):
        return book
    raise AssertionError(path)


st = M.load("/nonexistent/ledger.json")
EARLY = OPEN + dt.timedelta(hours=2)
M.run(st, now=EARLY, fetch=fake)
check("2h after the open: PEAC (0.23) and CHEA (0.05) entered; the late-opening word not yet open",
      sorted((e["word"], e["price"]) for e in st["entries"]), [("Cheap", 0.05), ("Peace", 0.23)])
check("an entry read within 2h carries the book at the entry price (none offered at 0.05), and the contracts traded to it",
      [(e["word"], e.get("book_size"), e["traded_to_entry"]) for e in sorted(st["entries"], key=lambda e: e["word"])],
      [("Cheap", 0.0, 0.0), ("Peace", 8.5, 2.0)])
check("outside the band is skipped at once (0.02 and 0.31); a wide quote waits for the window",
      (sorted((v["word"], v["reason"]) for v in st["skips"].values()), st["observations"]["waiting"]),
      ([("Dear", "YES ask 0.31 outside 0.03-0.30"), ("Penny", "YES ask 0.02 outside 0.03-0.30")], 1))
check("the earlier week (opened before the lane's start) is never touched",
      any("26OCT26" in c for c in calls), False)
check("fills read off the traded high: PEAC 2x filled in the 2h candle, CHEA's 0.09 print below its 0.10",
      [(e["word"], [bool(l.get("filled_at")) for l in e["legs"]]) for e in sorted(st["entries"], key=lambda e: e["word"])],
      [("Cheap", [False, False]), ("Peace", [True, False])])
LATER = OPEN + dt.timedelta(hours=12)
M.run(st, now=LATER, fetch=fake)
check("12h on: PEAC's 3x (0.69) filled by the 0.70 print; the wide word skipped after 6h; entries never re-made",
      ([bool(l.get("filled_at")) for l in next(e for e in st["entries"] if e["word"] == "Peace")["legs"]],
       st["skips"]["KXTRUMPSAY-26NOV02-WIDE"]["reason"], len(st["entries"])),
      ([True, True], "no quote with a 5c spread inside 6h", 2))
calls.clear()
SETTLED = [dict(m, status="finalized", result="no") if m["ticker"].endswith(("PEAC", "CHEA")) else m for m in MKTS]
M.run(st, now=OPEN + dt.timedelta(days=7), fetch=lambda p: fake(p, SETTLED))
pe, ch = (next(e for e in st["entries"] if e["word"] == w) for w in ("Peace", "Cheap"))
check("settled NO: PEAC keeps both fills (held would have lost); CHEA held both legs to 0",
      (pe["status"], pe["roi_held"], ch["status"], ch["roi"], [l.get("settled_px") for l in ch["legs"]]),
      ("settled", -1.0, "settled", -1.0, [0.0, 0.0]))
check("no book is read for an entry made long after its time", calls.count("markets/KXTRUMPSAY-26NOV02-LATE/orderbook"), 0)

print("\nthe Culture page card")
h = KB.build(split_state=st)
card = h[h.find('id="mentions-split"'):h.find('<section id="models"')]
t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", card))
check("it sits on the Culture page before the Model lanes, with the review note and the same tiles as every card",
      (bool(card), "review at 10, decide at 30" in t, "ROI after fees · held" in t, "2x only" in t,
       "legs filled 2x / 3x" in t, "ROI after fees · split" in t), (True, True, True, True, True, True))
check("per-week row and the trade list name the words, the entry price and the size",
      ("KXTRUMPSAY-26NOV02 2 1 1 2" in t, "Peace" in t, "0.23" in t, "2 traded to entry · 8.5 on the book" in t), (True, True, True, True))
check("an empty ledger renders", "No entry yet." in M.section(M.load("/nonexistent/x.json"), C.esc), True)
check("no guarded public phrase on the card or in the module", sandbox_audit.COPY_RE.findall(card + open("mentions_split.py").read()), [])

print("\nthe wide twin (2026-10-27): spread 10c or less AND an ask of 0.03-0.30, at the ask paid")


def tc(mins, bid, ask, px=None, vol=0):
    c = mc(mins, bid, ask, vol=vol)
    c["price"] = dict(close_dollars=None if px is None else str(px), high_dollars=None if px is None else str(px))
    return c


W = M.WIDE
check("its terms differ from the strict lane's only in the entry",
      (W["lane"], W["spread"], W["band_in_quote"], W["last_trade"], W["path"].endswith("mentions_split_wide_ledger.json"),
       M.STRICT["spread"], M.STRICT["band_in_quote"], M.STRICT["path"] == M.PATH),
      ("mentions_cheap_yes_split_wide", 0.10, True, True, True, 0.05, False, True))
seq = [tc(3, 0.05, 0.25, px=0.20, vol=2), tc(5, 0.10, 0.18, vol=1), tc(9, 0.19, 0.21)]
check("an 8c quote at 0.18 is the wide entry; the strict lane waits for the 2c one",
      (M.entry_quote(seq, O, W, detail=True), M.entry_quote(seq, O)),
      ((O + 300, 0.10, 0.18, 3.0, (0.20, O + 180)), (O + 540, 0.19, 0.21, 3.0)))
check("exactly 10c is in; 11c is not",
      (M.entry_quote([tc(5, 0.08, 0.18)], O, W) is not None, M.entry_quote([tc(5, 0.07, 0.18)], O, W)), (True, None))
out_band = [tc(5, 0.30, 0.35, px=0.33), tc(7, 0.22, 0.30)]
check("a tight quote outside the band is passed over (the strict lane would skip the word on it)",
      (M.entry_quote(out_band, O, W, detail=True)[:3], M.entry_quote(out_band, O)[2]), ((O + 420, 0.22, 0.30), 0.35))
check("no trade yet: the last trade is (None, None)", M.entry_quote([tc(5, 0.10, 0.18)], O, W, detail=True)[4], (None, None))

WMIN = {"KXTRUMPSAY-26NOV02-PEAC": [tc(10, 0.10, 0.30), tc(20, 0.14, 0.22, px=0.25, vol=3), tc(93, 0.19, 0.23)],
        "KXTRUMPSAY-26NOV02-CHEA": [tc(5, 0.03, 0.05)],
        "KXTRUMPSAY-26NOV02-WIDE": [tc(5, 0.10, 0.25, px=0.12), tc(9, 0.15, 0.24)],
        "KXTRUMPSAY-26NOV02-DEAR": [tc(5, 0.29, 0.31), tc(8, 0.25, 0.32)]}


def wfake(path):
    if "candlesticks" in path and path.endswith("period_interval=1"):
        return {"market_tickers": list(WMIN), "market_candlesticks": list(WMIN.values())}
    return fake(path)


ws = M.load("/nonexistent/wide.json", cfg=W)
M.run(ws, now=OPEN + dt.timedelta(hours=7), fetch=wfake, cfg=W)
got = sorted((e["word"], e["price"], e["spread"], e.get("last_trade"), e.get("spread_cost")) for e in ws["entries"])
check("backfill: PEAC at 0.22 (8c, last trade 0.25), CHEA, WIDE at 0.24 (9c, last trade 0.12, the spread cost 12c)",
      got, [("Cheap", 0.05, 0.02, None, None), ("Peace", 0.22, 0.08, 0.25, -0.03), ("Wide", 0.24, 0.09, 0.12, 0.12)])
check("legs at 2x and 3x of the ask paid", [l["target"] for l in next(e for e in ws["entries"] if e["word"] == "Wide")["legs"]],
      [0.48, 0.72])
check("DEAR never quoted inside the band within 10c: skipped with the wide reason; PENY too",
      sorted((v["word"], v["reason"]) for v in ws["skips"].values())[:1],
      [("Dear", "no quote with a 10c spread and a YES ask of 0.03-0.30 inside 6h")])
check("the strict lane's entries are not the wide lane's (separate ledgers)", ws["lane"], "mentions_cheap_yes_split_wide")
wh = KB.build(split_state=st, wide_state=ws)
wt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", wh))
check("the page: both cards, the wide one after the strict one, and the comparison line between",
      (wh.find('id="mentions-split"') < wh.find('id="mentions-split-compare"') < wh.find('id="mentions-split-wide"')
       < wh.find('<section id="models"'), "Cost of the spread" in wt, "Last trade" in wt),
      (True, True, True))
check("the comparison: entries, ROI after fees and the average spread paid, strict v wide",
      re.search(r"Strict v wide · strict \(5c\): 2 entries, ROI after fees [^,]+ \(2 resolved\), average spread paid 0\.03 · "
                r"wide \(10c\): 3 entries, ROI after fees pending \(0 resolved\), average spread paid 0\.06", wt) is not None, True)
check("the wide card names its own rule and the review note",
      ("whose spread is 10c or less and whose YES ask is 0.03-0.30" in wt and wt.count("review at 10, decide at 30") >= 6), True)
check("no guarded public phrase on the page cards", sandbox_audit.COPY_RE.findall(
      wh[wh.find('id="mentions-split"'):wh.find('<section id="models"')]), [])

print("\nthe monthly market (2026-10-27): both lanes on KXTRUMPSAYMONTH, separate records")
check("monthly lanes: their own ids, ledgers, series and start; the same entry rules as the weekly twins",
      [(c["lane"], c["series"], c["start"], c["spread"], c["band_in_quote"], c["last_trade"], c["path"].rsplit("/", 1)[-1])
       for c in (M.MONTH, M.MONTH_WIDE)],
      [("mentions_month_split", "KXTRUMPSAYMONTH", "2026-10-01T14:00:00+00:00", 0.05, False, False, "mentions_month_split_ledger.json"),
       ("mentions_month_split_wide", "KXTRUMPSAYMONTH", "2026-10-01T14:00:00+00:00", 0.10, True, True,
        "mentions_month_split_wide_ledger.json")])
check("six lanes (four mention, two album), and no company series anywhere",
      ([c["lane"] for c in M.LANES], any("COMPANY" in c["series"] for c in M.LANES)),
      (["mentions_cheap_yes_split", "mentions_cheap_yes_split_wide", "mentions_month_split", "mentions_month_split_wide",
        "album_cheap_rungs", "album_cheap_no"], False))
check("the weekly lanes still read KXTRUMPSAY from 2026-10-26", (M.STRICT["series"], M.WIDE["series"], M.STRICT["start"]),
      ("KXTRUMPSAY", "KXTRUMPSAY", "2026-10-26T04:00:00+00:00"))
check("the monthly rule text names its own series and a month", ("Monthly KXTRUMPSAYMONTH only." in M.MONTH["rule"],
      "per word per month" in M.MONTH_WIDE["rule"], "Weekly" in M.MONTH["rule"]), (True, True, False))
MOPEN = dt.datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
MO = int(MOPEN.timestamp())
mcalls = []
MM = [dict(ticker="KXTRUMPSAYMONTH-26NOV01-UFO", open_time=MOPEN.isoformat(), status="active", result="",
           custom_strike={"Word": "UFO"})]


def mfake(path):
    mcalls.append(path)
    if path.startswith("events?"):
        return {"events": [dict(event_ticker="KXTRUMPSAYMONTH-26NOV01", markets=MM)], "cursor": ""}
    if "candlesticks" in path:
        c = dict(end_period_ts=MO + 600, volume_fp="4", yes_bid=dict(close_dollars="0.10"), yes_ask=dict(close_dollars="0.14"),
                 price=dict(close_dollars="0.12", high_dollars="0.12"))
        later = dict(c, end_period_ts=MO + 7200, price=dict(close_dollars="0.30", high_dollars="0.30"))
        return {"market_tickers": ["KXTRUMPSAYMONTH-26NOV01-UFO"], "market_candlesticks": [[c, later]]}
    if path.endswith("/orderbook"):
        return book
    raise AssertionError(path)


for cfg in (M.MONTH, M.MONTH_WIDE):
    ms_ = M.load("/nonexistent/m.json", cfg=cfg)
    M.run(ms_, now=MOPEN + dt.timedelta(days=3), fetch=mfake, cfg=cfg)
    e0 = ms_["entries"][0]
    check(f"{cfg['lane']}: reads the monthly series and enters UFO at 0.14 (2x 0.28 filled by the 0.30 print)",
          (e0["id"], e0["price"], e0["legs"][0].get("fill_px"), e0.get("last_trade"), ms_["lane"]),
          ("KXTRUMPSAYMONTH-26NOV01-UFO", 0.14, 0.28, 0.12 if cfg["last_trade"] else None, cfg["lane"]))
check("every call went to the monthly series, none to the weekly or company one",
      (all("KXTRUMPSAYMONTH" in c for c in mcalls if "series" in c), any("COMPANY" in c for c in mcalls)), (True, False))
mh = KB.build(split_state=st, wide_state=ws, month_state=ms_, month_wide_state=ms_)
order = [mh.find(f'id="{a}"') for a in ("mentions-split", "mentions-split-compare", "mentions-split-wide", "mentions-month-split",
                                        "mentions-month-split-compare", "mentions-month-split-wide")] + [mh.find('<section id="models"')]
mt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", mh))
check("the page: weekly cards, then the monthly strict card, its comparison line and the monthly wide card",
      (all(x > 0 for x in order), order == sorted(order), "Monthly · strict v wide" in mt,
       "KXTRUMPSAYMONTH-26NOV01 (October, opened 2026-10-01 14:00Z)" in mt), (True, True, True, True))

print("\nalbum sales (2026-10-27): album_cheap_rungs on KXALBUMEQUIV, HOLD v SPLIT on the same entries")
A = M.ALBUM
check("its terms: 5c spread, YES ask 0.03-0.15 in the quote, its own series and ledger, backfills open events",
      (A["lane"], A["series"], A["spread"], A["band"], A["band_in_quote"], A["backfill_open"], A["hold_variant"],
       A["path"].rsplit("/", 1)[-1], A in M.LANES),
      ("album_cheap_rungs", "KXALBUMEQUIV", 0.05, (0.03, 0.15), True, True, True, "album_cheap_rungs_ledger.json", True))
check("0.15-0.30 is never entered: a tight 0.20 is passed over for a later tight 0.12; 0.15 itself is in",
      (M.entry_quote([tc(5, 0.17, 0.20), tc(9, 0.08, 0.12)], O, A)[2], M.entry_quote([tc(5, 0.11, 0.15)], O, A)[2],
       M.entry_quote([tc(5, 0.12, 0.16)], O, A)), (0.12, 0.15, None))
check("a 6c spread at 0.10 is not tight enough", M.entry_quote([tc(5, 0.04, 0.10)], O, A), None)
AOLD = dt.datetime(2026, 10, 20, 20, 0, tzinfo=UTC)
AO = int(AOLD.timestamp())
acalls = []
OPEN_EV = dict(event_ticker="KXALBUMEQUIV-FRE26NOV12", markets=[
    dict(ticker="KXALBUMEQUIV-FRE26NOV12-300K", open_time=AOLD.isoformat(), status="active", result="", yes_sub_title="Above 300K"),
    dict(ticker="KXALBUMEQUIV-FRE26NOV12-400K", open_time=(AOLD + dt.timedelta(days=2)).isoformat(), status="active", result="",
         yes_sub_title="Above 400K")])
DONE_EV = dict(event_ticker="KXALBUMEQUIV-OLD26OCT22", markets=[
    dict(ticker="KXALBUMEQUIV-OLD26OCT22-10K", open_time=AOLD.isoformat(), status="finalized", result="no", yes_sub_title="Above 10K")])


def afake(path, evs=None):
    acalls.append(path)
    if path.startswith("events?"):
        assert "series_ticker=KXALBUMEQUIV&" in path
        return {"events": evs or [OPEN_EV, DONE_EV], "cursor": ""}
    if "candlesticks" in path:
        st_ = int(path.split("start_ts=")[1].split("&")[0])
        if path.endswith("period_interval=1"):
            q = {AO: ("KXALBUMEQUIV-FRE26NOV12-300K", tc(30, 0.02, 0.06, px=0.04, vol=12)),
                 AO + 2 * 86400: ("KXALBUMEQUIV-FRE26NOV12-400K", dict(tc(30, 0.17, 0.20), end_period_ts=AO + 2 * 86400 + 1800))}
            t_, c_ = q[st_]
            c_ = dict(c_, end_period_ts=st_ + 1800)
            return {"market_tickers": [t_], "market_candlesticks": [[c_]]}
        later = dict(end_period_ts=AO + 7200, price=dict(high_dollars="0.13"))
        return {"market_tickers": ["KXALBUMEQUIV-FRE26NOV12-300K"], "market_candlesticks": [[later]]}
    if path.endswith("/orderbook"):
        return book
    raise AssertionError(path)


als = M.load("/nonexistent/album.json", cfg=A)
M.run(als, now=dt.datetime(2026, 10, 27, 3, 30, tzinfo=UTC), fetch=afake, cfg=A)
check("backfill: the still-open event is replayed, the settled one is not touched",
      (sorted(als["events"]), any("OLD26OCT22" in c for c in acalls if "candlesticks" in c)),
      (["KXALBUMEQUIV-FRE26NOV12"], False))
check("minute candles are read per opening time (two rungs opened two days apart: two reads)",
      sum(1 for c in acalls if c.endswith("period_interval=1")), 2)
check("the 300K rung entered at 0.06 with its size and last trade; the 400K rung (tight only at 0.20) skipped",
      ([(e["word"], e["price"], e["traded_to_entry"], e["last_trade"]) for e in als["entries"]], sorted(als["skips"])),
      ([("Above 300K", 0.06, 12.0, 0.04)], ["KXALBUMEQUIV-FRE26NOV12-400K"]))
check("SPLIT legs at 0.12 (filled by the 0.13 print) and 0.18 (resting)",
      [(l["target"], bool(l.get("filled_at"))) for l in als["entries"][0]["legs"]], [(0.12, True), (0.18, False)])
SETTLED_EV = dict(OPEN_EV, markets=[dict(m, status="finalized", result="yes") for m in OPEN_EV["markets"]])
M.run(als, now=dt.datetime(2026, 11, 20, tzinfo=UTC), fetch=lambda p: afake(p, [SETTLED_EV, DONE_EV]), cfg=A)
e0 = als["entries"][0]
check("once tracked it is kept after it settles: won, HOLD and SPLIT both graded on the same entry",
      (e0["payout"], e0["roi_held"] > e0["roi"] > 0, M.record(als["entries"])["won"], M.record(als["entries"])["settled"]),
      (1.0, True, 1, 1))
ah = KB.build(split_state=st, wide_state=ws, month_state=ms_, month_wide_state=ms_, album_state=als)
card_a = ah[ah.find('id="album-cheap-rungs"'):ah.find('<section id="models"')]
at = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", card_a))
check("the album card: entries, won, HOLD v SPLIT, per-event rows and the trade list, review at 10",
      (bool(card_a), "ROI after fees · held" in at, "ROI after fees · split" in at, " won" in at, "Event" in at,
       "Rung" in at, "KXALBUMEQUIV-FRE26NOV12" in at, "Above 300K" in at, "review at 10, decide at 30" in at),
      (True,) * 9)
check("no guarded public phrase on the album card", sandbox_audit.COPY_RE.findall(card_a), [])

print("\ncheap NO on the album ladders (2026-10-27): album_cheap_no, a separate record")
N = M.ALBUM_NO
check("its terms: the NO side, 10c spread, NO ask 0.03-0.15, its own ledger and lane id",
      (N["lane"], N["side"], N["spread"], N["band"], N["series"], N["path"].rsplit("/", 1)[-1], N in M.LANES, M.ALBUM.get("side", "yes")),
      ("album_cheap_no", "no", 0.10, (0.03, 0.15), "KXALBUMEQUIV", "album_cheap_no_ledger.json", True, "yes"))
# YES 0.88/0.94 -> NO bid 0.06, NO ask 0.12 (6c spread); YES 0.70/0.78 -> NO ask 0.30 (out of band).
q = M.entry_quote([tc(4, 0.70, 0.78, px=0.75), tc(8, 0.88, 0.94, px=0.90, vol=5)], O, N, detail=True)
check("the NO ask is 1 - the YES bid, the NO bid 1 - the YES ask; the last trade in NO terms; 0.30 passed over",
      q, (O + 480, 0.06, 0.12, 5.0, (0.1, O + 480)))
check("an 11c spread is too wide; a NO ask of 0.16 is out of band",
      (M.entry_quote([tc(5, 0.87, 0.98)], O, N), M.entry_quote([tc(5, 0.84, 0.90)], O, N)), (None, None))
lows = [dict(end_period_ts=O + 600, price=dict(low_dollars="0.60")), dict(end_period_ts=O + 7200, price=dict(low_dollars="0.75")),
        dict(end_period_ts=O + 9000, price=dict(low_dollars="0.74"))]
check("a NO leg at 0.26 fills when the YES traded low is 0.74 or under, after the entry (not on the YES high)",
      (M.fill_of(lows, O + 600, 0.26, "no"), M.fill_of(lows, O + 600, 0.26)), ((O + 9000, 0.26), None))
nb = {"orderbook_fp": {"yes_dollars": [["0.8500", "4"], ["0.8800", "6"], ["0.9000", "2"]], "no_dollars": []}}
check("NO offered at or under 0.12 = YES bids at 0.88 or more", M.book_size(nb, 0.12, "no"), 8.0)
check("settlement pays the NO on a 'no' result", (M.settled_payout(dict(status="finalized", result="no"), "no"),
      M.settled_payout(dict(status="finalized", result="yes"), "no")), (1.0, 0.0))
NOEV = dict(event_ticker="KXALBUMEQUIV-FRE26NOV12", markets=[
    dict(ticker="KXALBUMEQUIV-FRE26NOV12-60K", open_time=AOLD.isoformat(), status="active", result="", yes_sub_title="Above 60K")])


def nfake(path, evs=None):
    if path.startswith("events?"):
        return {"events": evs or [NOEV], "cursor": ""}
    if "candlesticks" in path:
        if path.endswith("period_interval=1"):
            return {"market_tickers": ["KXALBUMEQUIV-FRE26NOV12-60K"],
                    "market_candlesticks": [[dict(tc(30, 0.93, 0.97), end_period_ts=AO + 1800)]]}
        return {"market_tickers": ["KXALBUMEQUIV-FRE26NOV12-60K"],
                "market_candlesticks": [[dict(end_period_ts=AO + 7200, price=dict(low_dollars="0.86"))]]}
    if path.endswith("/orderbook"):
        return nb
    raise AssertionError(path)


ns = M.load("/nonexistent/no.json", cfg=N)
M.run(ns, now=dt.datetime(2026, 10, 27, 3, 0, tzinfo=UTC), fetch=nfake, cfg=N)
n0 = ns["entries"][0]
check("the run: NO bought at 0.07 (YES bid 0.93), 2x leg (0.14) filled by the YES low 0.86, 3x (0.21) resting",
      (n0["side"], n0["price"], [(l["target"], bool(l.get("filled_at"))) for l in n0["legs"]]),
      ("no", 0.07, [(0.14, True), (0.21, False)]))
M.run(ns, now=dt.datetime(2026, 11, 20, tzinfo=UTC), cfg=N,
      fetch=lambda p: nfake(p, [dict(NOEV, markets=[dict(NOEV["markets"][0], status="finalized", result="no")])]))
check("settled NO: won, HOLD and SPLIT graded", (n0["payout"], n0["roi_held"] > 0, n0["roi"] > 0, M.record(ns["entries"])["won"]),
      (1.0, True, True, 1))
nh = KB.build(split_state=st, wide_state=ws, month_state=ms_, month_wide_state=ms_, album_state=als, album_no_state=ns)
nt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", nh))
check("the page: the summary has cheap YES and cheap NO as separate rows; the note, then each card",
      ("Album ladders tested too confident: both tails won more than priced." in nt,
       "Album · cheap YES 1 0 1 1" in nt, "Album · cheap NO 1 0 1 1" in nt,
       nh.find('id="album-note"') < nh.find('id="album-cheap-rungs"') < nh.find('id="album-cheap-no"') < nh.find('<section id="models"'),
       "NO ask paid" in nt), (True, True, True, True, True))
check("no guarded public phrase on the album cards", sandbox_audit.COPY_RE.findall(
      nh[nh.find('id="album-note"'):nh.find('<section id="models"')]), [])

print("\ncommodities (2026-10-27): wti_cheap_yes and gas_cheap_no on the same engine")
WT, GS = M.WTI, M.GAS
check("their terms: KXWTI YES / KXAAAGASD NO, 15-30c, 5c spread, open events only, 7-day backfill, own ledgers",
      [(c["lane"], c["series"], c.get("side", "yes"), c["band"], c["spread"], c["open_only"], c["backfill_days"],
        c["path"].rsplit("/", 1)[-1]) for c in (WT, GS)],
      [("wti_cheap_yes", "KXWTI", "yes", (0.15, 0.30), 0.05, True, 7, "wti_cheap_yes_ledger.json"),
       ("gas_cheap_no", "KXAAAGASD", "no", (0.15, 0.30), 0.05, True, 7, "gas_cheap_no_ledger.json")])
check("the groups: culture runs the six culture lanes, commodities the commodity lanes",
      ([c["lane"] for c in M.GROUPS["commodities"]], WT in M.GROUPS["culture"], len(M.GROUPS["culture"])),
      (["wti_cheap_yes", "gas_cheap_no", "gas_week_cheap_no"], False, 6))
check("never under 0.15: a tight 0.12 is passed over for a tight 0.18; 0.30 is in, 0.31 out",
      (M.entry_quote([tc(3, 0.09, 0.12), tc(6, 0.14, 0.18)], O, WT)[2], M.entry_quote([tc(3, 0.26, 0.30)], O, WT)[2],
       M.entry_quote([tc(3, 0.27, 0.31)], O, WT)), (0.18, 0.30, None))
check("gas NO: YES 0.80/0.83 is a NO ask of 0.20 (3c spread)", M.entry_quote([tc(3, 0.80, 0.83)], O, GS)[1:3], (0.17, 0.2))
COPEN = dt.datetime(2026, 10, 26, 23, 30, tzinfo=UTC)
CO = int(COPEN.timestamp())
ccalls = []
WEV = dict(event_ticker="KXWTI-26OCT2814", markets=[dict(ticker="KXWTI-26OCT2814-T104", open_time=COPEN.isoformat(),
                                                        status="active", result="", yes_sub_title="Above $104")])
OLDW = dict(event_ticker="KXWTI-26NOV03", markets=[dict(ticker="KXWTI-26NOV03-T60", open_time="2026-05-06T14:00:00Z",
                                                       status="active", result="", yes_sub_title="Above $60")])


def cfake(path, listed=None, single=None):
    ccalls.append(path)
    if path.startswith("events?"):
        assert "series_ticker=KXWTI&status=open&" in path
        return {"events": [WEV, OLDW] if listed is None else listed, "cursor": ""}
    if path.startswith("events/"):
        return {"event": dict(event_ticker=path.split("/")[1].split("?")[0]), "markets": single["markets"]}
    if "candlesticks" in path:
        if path.endswith("period_interval=1"):
            return {"market_tickers": ["KXWTI-26OCT2814-T104"],
                    "market_candlesticks": [[dict(tc(1, 0.17, 0.21, px=0.20, vol=3), end_period_ts=CO + 60)]]}
        return {"market_tickers": ["KXWTI-26OCT2814-T104"],
                "market_candlesticks": [[dict(end_period_ts=CO + 7200, price=dict(high_dollars="0.42"))]]}
    if path.endswith("/orderbook"):
        return book
    raise AssertionError(path)


cs_ = M.load("/nonexistent/wti.json", cfg=WT)
M.run(cs_, now=COPEN + dt.timedelta(hours=1), fetch=cfake, cfg=WT)
check("WTI: only the open events are listed; the May event is past the 7-day backfill; T104 entered at 0.21",
      (sorted(cs_["events"]), [(e["word"], e["price"], e["last_trade"]) for e in cs_["entries"]]),
      (["KXWTI-26OCT2814"], [("Above $104", 0.21, 0.2)]))
check("its legs rest: the 0.42 print lies after this read (a candle past now is never used)",
      [bool(l.get("filled_at")) for l in cs_["entries"][0]["legs"]], [False, False])
done_ev = dict(WEV, markets=[dict(WEV["markets"][0], status="finalized", result="yes")])
ccalls.clear()
M.run(cs_, now=COPEN + dt.timedelta(days=2), fetch=lambda p: cfake(p, listed=[], single=done_ev), cfg=WT)
check("once the event leaves the open list, the held entry's event is read on its own and settles",
      ("events/KXWTI-26OCT2814?with_nested_markets=true" in ccalls, cs_["entries"][0]["payout"],
       cs_["entries"][0]["roi_held"] > 0, [bool(l.get("filled_at")) for l in cs_["entries"][0]["legs"]]),
      (True, 1.0, True, [True, False]))
import commodities_build as CB
gh_ = CB.build()
sec = gh_[gh_.find('id="cheap-side"'):gh_.find('<section id="events"')]
stx = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sec))
check("the Commodities page: the cheap-side section before the Events, the summary and both cards, phone labels",
      (bool(sec), "Cheap side + resting take-profit" in stx, "WTI oil · cheap YES (15-30c)" in stx,
       "AAA gas · cheap NO (15-30c)" in stx, 'id="wti-cheap-yes"' in sec, 'id="gas-cheap-no"' in sec,
       'data-l="Split ROI"' in sec, "review at 10, decide at 30" in stx), (True,) * 8)
check("the existing commodities rules are still on the page", all(n in gh_ for n in CB.RULE_NAMES.values()), True)
check("no guarded public phrase in the commodities section", sandbox_audit.COPY_RE.findall(stx), [])

print("\nthe weekly gas lane (2026-10-27): gas_week_cheap_no on KXAAAGASW, the wide rule")
GW = M.GAS_WEEK
check("its terms: KXAAAGASW, NO, 15-30c, 10c spread, open events only, own ledger, third commodity lane",
      (GW["lane"], GW["series"], GW["side"], GW["band"], GW["spread"], GW["open_only"], GW["path"].rsplit("/", 1)[-1],
       [c["lane"] for c in M.GROUPS["commodities"]]),
      ("gas_week_cheap_no", "KXAAAGASW", "no", (0.15, 0.30), 0.10, True, "gas_week_cheap_no_ledger.json",
       ["wti_cheap_yes", "gas_cheap_no", "gas_week_cheap_no"]))
check("the wide rule: a 10c spread at NO 0.23 enters (the daily gas lane, 5c, would not)",
      (M.entry_quote([tc(3, 0.77, 0.87)], O, GW)[1:3], M.entry_quote([tc(3, 0.77, 0.87)], O, M.GAS)), ((0.13, 0.23), None))
check("its rule text says 10c and that it is small and slow",
      ("a spread of 10c or less" in GW["rule"], "about 3 entries a week" in GW["rule"], "5c" in GW["rule"]), (True, True, False))
gw_h = CB.build()
gsec = gw_h[gw_h.find('id="cheap-side"'):gw_h.find('<section id="events"')]
gtx = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", gsec))
check("the Commodities page: a summary row and its card after gas_cheap_no, with the small-and-slow note",
      ("AAA gas weekly · cheap NO (15-30c, 10c spread)" in gtx,
       gsec.find('id="gas-cheap-no"') < gsec.find('id="gas-week-note"') < gsec.find('id="gas-week-cheap-no"'),
       "about 3 entries a week, all on one weekly event, so 10 settled events takes about ten weeks. Review at 10, decide at 30." in gtx), (True, True, True))

print("\nthe outcome unit is the Kalshi event, not the rung (2026-10-29)")
# A WTI-like ladder: 3 trading days, 13 settled rungs, plus a 4th day still open. Rungs of one day move together.
_days = (("KXWTI-26OCT27", 5, 0.0), ("KXWTI-26OCT28", 4, 0.0), ("KXWTI-26OCT29", 4, 1.0))
_ladder = []
for _ev, _n, _pay in _days:
    for _i in range(_n):
        _ladder.append(M.grade(dict(id=f"{_ev}-T{_i}", event=_ev, price=0.20, payout=_pay,
                                    legs=[dict(target=0.40, share=0.5, settled_px=_pay), dict(target=0.60, share=0.5, settled_px=_pay)])))
_ladder += [dict(id=f"KXWTI-26OCT30-T{_i}", event="KXWTI-26OCT30", price=0.20, payout=None, legs=[dict(target=0.40, share=0.5),
            dict(target=0.60, share=0.5)]) for _i in range(3)]
# A day with one rung settled and one still open is not a settled event yet.
_ladder += [M.grade(dict(id="KXWTI-26OCT31-T0", event="KXWTI-26OCT31", price=0.20, payout=1.0,
                         legs=[dict(target=0.40, share=0.5, settled_px=1.0), dict(target=0.60, share=0.5, settled_px=1.0)])),
            dict(id="KXWTI-26OCT31-T1", event="KXWTI-26OCT31", price=0.20, payout=None,
                 legs=[dict(target=0.40, share=0.5), dict(target=0.60, share=0.5)])]
for _e in _ladder:
    _e.update(entry_at=_e["event"][-5:] + "T04:00:00+00:00", word=_e["id"].rsplit("-", 1)[-1], side="yes")
_r = M.record(_ladder)
check("18 entries, 14 settled entries, 5 events, only the 3 fully settled days are settled events",
      (_r["entries"], _r["settled"], _r["events"], _r["settled_events"]), (18, 14, 5, 3))
check("the status counts settled events, so 14 settled rungs are not a review", M.status(_r["settled_events"]),
      "3 settled events · review at 10, decide at 30")
_win = (1 - M.fee(0.20, M.TAKER) - 0.20) / (0.20 + M.fee(0.20, M.TAKER))
check("the ROI columns stay the mean per entry; the event ROI is the mean of each settled day's mean",
      (round(_r["roi"], 4), round(_r["roi_event"], 4)),
      (round((9 * -1.0 + 5 * _win) / 14, 4), round((-1.0 - 1.0 + _win) / 3, 4)))
_cfg = dict(M.WTI)
_html = M.summary([_cfg], {_cfg["lane"]: dict(entries=_ladder)}, M._esc)
_row = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html.split("<tbody>", 1)[1].split("</tbody>", 1)[0])).strip()
check("the summary row: entries, unverified asks, settled entries, settled events side by side, the status from events",
      _row.startswith("WTI oil · cheap YES (15-30c) 18 0 14 3 ") and _row.endswith("3 settled events · review at 10, decide at 30"), True)
_card = M.section(dict(entries=_ladder), M._esc, _cfg)
check("the card's header and tiles read events",
      ("review at 10 settled events, decide at 30" in _card, "3 settled events · review at 10, decide at 30" in _card,
       '<b>3 of 5</b><span>settled events</span>' in _card, "<span>split ROI per event</span>" in _card), (True, True, True, True))
check("ten settled days reach review whatever the rung count", M.status(10), "10 settled events · review due (10 reached) · decide at 30")
check("public copy passes the guard", sandbox_audit.COPY_RE.search(re.sub(r"<[^>]+>", " ", _card + _html)), None)

print("\nno ROI headline before the first settled event (2026-10-30)")
# An album-like ladder: 5 rungs bought at 4c, every leg filled at 8c / 12c, nothing settled yet.
_open = [M.grade(dict(id=f"KXALBUMEQUIV-X-{_i}", event="KXALBUMEQUIV-X", price=0.04, payout=None, word=f"R{_i}",
                      entry_at="2026-10-29T04:00:00+00:00", side="yes",
                      legs=[dict(target=0.08, share=0.5, filled_at="2026-10-29T05:00:00+00:00"),
                            dict(target=0.12, share=0.5, filled_at="2026-10-29T06:00:00+00:00")])) for _i in range(5)]
_ro = M.record(_open)
check("every leg filled, so the split is resolved, but no event has settled", (_ro["resolved"], _ro["settled_events"], _ro["roi"] > 1),
      (5, 0, True))
_acfg = dict(M.ALBUM)
_ah = M.summary([_acfg], {_acfg["lane"]: dict(entries=_open)}, M._esc)
_arow = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _ah.split("<tbody>", 1)[1].split("</tbody>", 1)[0])).strip()
check("the summary shows pending for split and hold ROI, never the +130% the open legs imply",
      (_arow.startswith("Album · cheap YES 5 0 0 0 0 pending pending 5 / 5"), "%" in _arow), (True, False))
_ac = M.section(dict(entries=_open), M._esc, _acfg)
_tiles = dict((k, v) for v, k in re.findall(r'<div class="tile"><b>([^<]*)</b><span>([^<]+)</span>', _ac))
check("the card's ROI tiles and its event row read pending; the trade list keeps each entry's own figures",
      (_tiles["ROI after fees · split"], _tiles["ROI after fees · held"], _tiles["split ROI per event"],
       "<td>KXALBUMEQUIV-X</td><td class=\"num\">5</td>" in _ac and _ac.count(">pending</td>") == 3, "+130.6%" in _ac),
      ("pending", "pending", "pending", True, True))
_one = _open + [M.grade(dict(id="KXALBUMEQUIV-Y-0", event="KXALBUMEQUIV-Y", price=0.04, payout=0.0, word="R0",
                             entry_at="2026-10-28T04:00:00+00:00", side="yes",
                             legs=[dict(target=0.08, share=0.5, settled_px=0.0), dict(target=0.12, share=0.5, settled_px=0.0)]))]
check("from the first settled event the ROI shows again", M._headline(M.record(_one)["roi"], M.record(_one)) != "pending", True)
check("a lane with no entry still shows —", M._headline(None, M.record([])), "—")

print("\nentry validity: the ask must have been there (2026-10-30, option A + the book at entry)")


def pc(mins, vol=0, lo=None, hi=None, close=None):
    """A minute candle `mins` after the open with a traded low / high / close."""
    return dict(end_period_ts=O + mins * 60, volume_fp=str(vol),
                price=dict(low_dollars=None if lo is None else str(lo), high_dollars=None if hi is None else str(hi),
                           close_dollars=None if close is None else str(close)))


def ve(price, mins=20, side="yes", **k):
    return dict(dict(id="KX-T", event="KX", price=price, side=side, entry_at=M._iso(O + mins * 60)), **k)


AFTER = O + 3 * 3600
check("its terms: 10 contracts, 60 minutes, half the last trade, first 5 minutes flagged",
      (M.MIN_SIZE, M.PRINT_WINDOW_MIN, M.LAST_TRADE_FLOOR, M.FIRST_QUOTES_MIN), (10, 60, 0.5, 5))
snap = M.book_snapshot({"orderbook_fp": {"no_dollars": [["0.75", "10"], ["0.77", "5.5"], ["0.80", "3"]],
                                         "yes_dollars": [["0.20", "40"], ["0.18", "7"]]}}, 0.23, "yes", "2026-10-26T04:21:00+00:00")
check("the book snapshot at entry: best bid / ask with sizes, depth, and the contracts at or under the price paid",
      (snap["best_bid"], snap["bid_size"], snap["best_ask"], snap["ask_size"], snap["at_or_under"], snap["ask_depth"], snap["bid_levels"]),
      (0.2, 40.0, 0.2, 3.0, 8.5, 18.5, 2))
live = lambda n: dict(book=dict(at=M._iso(O + 25 * 60), at_or_under=n))
check("a live book of 10+ at or under the ask verifies the entry, with no print needed",
      M.ask_check(ve(0.23, **live(12)), [], None, AFTER)["status"] + " " + M.ask_check(ve(0.23, **live(12)), [], None, AFTER)["how"],
      "verified book")
check("a book read hours after the entry is not live: the print rule decides",
      M.ask_check(ve(0.23, book=dict(at=M._iso(O + 5 * 3600), at_or_under=500)), [pc(30, 3, lo=0.22)], None, AFTER + 7200)["source"],
      "replayed")
c_ok = M.ask_check(ve(0.23, **live(8.5)), [pc(30, 6, lo=0.22), pc(50, 5, lo=0.23), pc(90, 50, lo=0.20), pc(40, 9, lo=0.25)], None, AFTER)
check("under 10 on the book: verified by 10+ traded at or through the ask within 60 min (a 0.25 low and the 90th minute, after the window, do not count)",
      (c_ok["status"], c_ok["how"], c_ok["printed"]), ("verified", "print", 11.0))
c_bad = M.ask_check(ve(0.04, mins=19), [pc(19, 0), pc(25, 0, lo=0.08, hi=0.12)], O - 60, AFTER)
check("a 4c ask nothing traded through is an unverified ask; the reason names the count",
      (c_bad["status"], c_bad["reason"]), ("unverified", "0 contracts traded at or through the ask within 60 minutes (under 10)"))
c_last = M.ask_check(ve(0.04, mins=30), [pc(25, 3, close=0.40), pc(40, 50, lo=0.04)], None, AFTER)
check("an ask under half the last trade before the entry is unverified, prints or not",
      (c_last["status"], c_last["reason"], c_last["last_trade"]), ("unverified", "ask 0.04 under half the last trade 0.40", 0.4))
check("a NO reads the YES side: last YES trade 0.60 makes the last NO trade 0.40; a YES traded high of 0.96+ prints through a 0.04 NO",
      (M.ask_check(ve(0.04, side="no"), [pc(10, 1, close=0.60)], None, AFTER)["reason"],
       M.ask_check(ve(0.04, side="no"), [pc(30, 12, hi=0.97)], None, AFTER)["status"]),
      ("ask 0.04 under half the last trade 0.40", "verified"))
check("inside the 60 minutes the entry is still checking; with no candles it keeps checking until they stop being served",
      (M.ask_check(ve(0.23), [], None, O + 40 * 60)["status"], M.ask_check(ve(0.23), [], None, AFTER)["status"],
       M.ask_check(ve(0.23), [], None, O + 8 * 86400)["reason"]),
      ("checking", "checking", "its minute candles are no longer served"))
check("an entry in the market's first 5 minutes is flagged, never rejected for that alone",
      (M.ask_check(ve(0.23, mins=4), [pc(30, 20, lo=0.2)], O, AFTER)["first_quotes"],
       M.ask_check(ve(0.23, mins=4), [pc(30, 20, lo=0.2)], O, AFTER)["status"],
       M.ask_check(ve(0.23, mins=6), [pc(30, 20, lo=0.2)], O, AFTER)["first_quotes"]), (True, "verified", False))

# A placeholder ladder (every rung at 4c, nothing traded, legs "filled" at 8c / 12c) beside one real rung.
LAD = "KXALBUMEQUIV-PH"
rungs = [dict(id=f"{LAD}-{k}", event=LAD, word=f"{k}K", side="yes", price=0.04, entry_at=M._iso(O + 20 * 60),
              logged=M._iso(O + 7200), legs=[dict(multiple=2.0, share=0.5, target=0.08, filled_at=M._iso(O + 3600)),
                                             dict(multiple=3.0, share=0.5, target=0.12, filled_at=M._iso(O + 3700))],
              payout=None) for k in (20, 40, 60)]
rungs.append(dict(id=f"{LAD}-80", event=LAD, word="80K", side="yes", price=0.10, entry_at=M._iso(O + 20 * 60),
                  logged=M._iso(O + 7200), legs=[dict(multiple=2.0, share=0.5, target=0.2), dict(multiple=3.0, share=0.5, target=0.3)],
                  payout=None))
for _e in rungs:
    M.grade(_e)
lad_c = {f"{LAD}-20": [pc(25, 0, lo=0.08, hi=0.12)], f"{LAD}-40": [pc(25, 0)], f"{LAD}-60": [pc(10, 2, close=0.30)],
         f"{LAD}-80": [pc(30, 25, lo=0.09)]}
lcalls = []


def lfake(path):
    lcalls.append(path)
    if path.startswith(f"events/{LAD}"):
        return {"event": {"markets": [dict(ticker=t, open_time=M._iso(O)) for t in lad_c]}}
    if "candlesticks" in path and path.endswith("period_interval=1"):
        return {"market_tickers": list(lad_c), "market_candlesticks": list(lad_c.values())}
    raise AssertionError(path)


lst = dict(lane="album_cheap_rungs", entries=rungs, skips={}, events={})
errs = M.check_asks(lst, dt.datetime.fromtimestamp(AFTER, UTC), lfake, dict(M.ALBUM))
check("one event request and one candle request for the whole ladder", (errs, len(lcalls)), ([], 2))
check("the placeholders fail (no print; under half the 0.30 last trade); the rung with 25 printed through its ask counts",
      [(e["word"], M.check_status(e)) for e in rungs],
      [("20K", "unverified"), ("40K", "unverified"), ("60K", "unverified"), ("80K", "verified")])
check("the voided figure keeps the record from before the rule (4 entries, the +130% split on open legs)",
      (lst["voided"]["entries"], round(lst["voided"]["roi"], 2) > 0.9, M.record(M.counted(lst))["entries"]), (4, True, 1))
vcard = M.section(lst, M._esc, dict(M.ALBUM))
vtxt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", vcard))
check("the card shows the voided figure once, the unverified count by reason, and the ask check per entry",
      ("Voided " in vtxt and vtxt.count("Voided ") == 1, "3 of those entries failed the ask check" in vtxt,
       "Skipped: unverified ask: 3 (ask under half the last trade: 1; under 10 traded at or through the ask in 60 min: 2)" in vtxt,
       "unverified, not counted: 0 contracts traded" in vtxt, "verified · print, 25 traded through the ask in 60 min" in vtxt),
      (True, True, True, True, True))
vsum = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", M.summary([dict(M.ALBUM)], {"album_cheap_rungs": lst}, M._esc)))
check("the summary counts the 1 verified entry and shows the 3 unverified asks beside it",
      "Album · cheap YES 1 3 0 0 0 pending pending 0 / 0" in vsum, True)
check("a second run leaves verified and unverified entries alone (nothing re-fetched)",
      (M.check_asks(lst, dt.datetime.fromtimestamp(AFTER + 3600, UTC), lfake, dict(M.ALBUM)), len(lcalls)), ([], 2))
check("with no entry failing, no voided line is shown", M.voided_line(dict(voided=lst["voided"], ask_rule_since="x", entries=[]), M._esc), "")
check("public copy passes the guard", sandbox_audit.COPY_RE.search(vtxt + vsum), None)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
