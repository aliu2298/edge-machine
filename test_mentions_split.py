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
card = h[h.find('<section id="mentions-split"'):h.find('<section id="method"')]
t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", card))
check("it sits on the Culture page before the Method, with the review note and the comparisons",
      (bool(card), "review at 10, decide at 30" in t, "same entries held" in t, "same entries, 2x leg only" in t,
       "2x legs filled" in t, "3x legs filled" in t), (True, True, True, True, True, True))
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
       < wh.find('<section id="method"'), "Cost of the spread" in wt, "Last trade" in wt),
      (True, True, True))
check("the comparison: entries, ROI after fees and the average spread paid, strict v wide",
      re.search(r"Strict v wide · strict \(5c\): 2 entries, ROI after fees [^,]+ \(2 resolved\), average spread paid 0\.03 · "
                r"wide \(10c\): 3 entries, ROI after fees — \(0 resolved\), average spread paid 0\.06", wt) is not None, True)
check("the wide card names its own rule and the review note",
      ("whose spread is 10c or less and whose YES ask is 0.03-0.30" in wt and wt.count("review at 10, decide at 30") == 4), True)
check("no guarded public phrase on the page cards", sandbox_audit.COPY_RE.findall(
      wh[wh.find('id="mentions-split"'):wh.find('<section id="method"')]), [])

print("\nthe monthly market (2026-10-27): both lanes on KXTRUMPSAYMONTH, separate records")
check("monthly lanes: their own ids, ledgers, series and start; the same entry rules as the weekly twins",
      [(c["lane"], c["series"], c["start"], c["spread"], c["band_in_quote"], c["last_trade"], c["path"].rsplit("/", 1)[-1])
       for c in (M.MONTH, M.MONTH_WIDE)],
      [("mentions_month_split", "KXTRUMPSAYMONTH", "2026-10-01T14:00:00+00:00", 0.05, False, False, "mentions_month_split_ledger.json"),
       ("mentions_month_split_wide", "KXTRUMPSAYMONTH", "2026-10-01T14:00:00+00:00", 0.10, True, True,
        "mentions_month_split_wide_ledger.json")])
check("four lanes, and no company series anywhere",
      ([c["lane"] for c in M.LANES], any("COMPANY" in c["series"] for c in M.LANES)),
      (["mentions_cheap_yes_split", "mentions_cheap_yes_split_wide", "mentions_month_split", "mentions_month_split_wide"], False))
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
                                        "mentions-month-split-compare", "mentions-month-split-wide")] + [mh.find('<section id="method"')]
mt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", mh))
check("the page: weekly cards, then the monthly strict card, its comparison line and the monthly wide card",
      (all(x > 0 for x in order), order == sorted(order), "Monthly · strict v wide" in mt,
       "KXTRUMPSAYMONTH-26NOV01 (October, opened 2026-10-01 14:00Z)" in mt), (True, True, True, True))

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
