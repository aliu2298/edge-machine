#!/usr/bin/env python3
"""Offline checks for the Fights lanes (fights_split.py: boxing_cheap_dog, ufc_dog) and the Fights page."""
import copy
import datetime as dt
import re
import sys

import fights_build as FB
import fights_split as FS
import mentions_split as MS
import sandbox_audit
import site_chrome as C

FAILS = []
UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 31, 21, 0, tzinfo=UTC)
S0 = int(START.timestamp())
LO = S0 - 3600                         # 20:00, an hour before the start


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


def mc(ts, bid, ask, last=None, hi=None, lo=None, vol=0, bid_hi=None):
    """A minute candle ending at epoch `ts`."""
    return dict(end_period_ts=ts, volume_fp=str(vol),
                yes_bid=dict(close_dollars=str(bid), high_dollars=str(bid if bid_hi is None else bid_hi)),
                yes_ask=dict(close_dollars=str(ask)),
                price=dict(close_dollars=None if last is None else str(last),
                           high_dollars=None if hi is None else str(hi), low_dollars=None if lo is None else str(lo)))


m = lambda mins: LO + mins * 60        # minutes after the "one hour before" mark
fin = lambda p: p + 0.07 * p * (1 - p)
out = lambda t: t - 0.0175 * t * (1 - t)

print("the lanes' registered terms")
check("boxing", (FS.BOXING["lane"], FS.BOXING["series"], FS.BOXING["band"], FS.BOXING["spread"]),
      ("boxing_cheap_dog", "KXBOXING", (0.03, 0.15), 0.05))
check("ufc", (FS.UFC["lane"], FS.UFC["series"], FS.UFC["band"], FS.UFC["spread"]), ("ufc_dog", "KXUFCFIGHT", (0.15, 0.30), 0.05))
check("entry one hour before, within 15 minutes; split legs 2x and 3x capped at 0.98; fees",
      (FS.ENTRY_LEAD_MIN, FS.ENTRY_GRACE_MIN, MS.LEGS, MS.CAP, MS.TAKER, MS.MAKER), (60, 15, ((2.0, 0.5), (3.0, 0.5)), 0.98, 0.07, 0.0175))
check("separate ledgers", sorted({c["path"].rsplit("/", 1)[-1] for c in FS.LANES}), ["boxing_cheap_dog_ledger.json", "ufc_dog_ledger.json"])
check("targets: 2x and 3x of the ask, capped at 0.98", [MS.targets(p) for p in (0.10, 0.30, 0.40)],
      [[(2.0, 0.5, 0.2), (3.0, 0.5, 0.3)], [(2.0, 0.5, 0.6), (3.0, 0.5, 0.9)], [(2.0, 0.5, 0.8), (3.0, 0.5, 0.98)]])

print("\nentry: the first tight, in-band minute in the 15 after (start - 60 minutes)")
ent = lambda cs, cfg=FS.BOXING: FS.entry_for(cs, S0, cfg)
check("a wide quote is passed over; the first tight in-band one is the entry",
      ent([mc(m(2), 0.05, 0.20, vol=3), mc(m(4), 0.09, 0.12, last=0.11, vol=7)])[:4], (m(4), 0.09, 0.12, 10.0))
check("the entry's last trade comes with it", ent([mc(m(3), 0.09, 0.12, last=0.10, vol=2), mc(m(6), 0.09, 0.12)])[4], (0.10, m(3)))
check("exactly 5c wide is tight; 6c is not", (ent([mc(m(2), 0.07, 0.12)])[2], ent([mc(m(2), 0.06, 0.12)])), (0.12, None))
check("boxing band 0.03-0.15 inclusive: 0.03 and 0.15 in, 0.02 and 0.16 out",
      [bool(ent([mc(m(2), a - 0.01, a)])) for a in (0.03, 0.15, 0.02, 0.16)], [True, True, False, False])
check("ufc band 0.15-0.30 inclusive: 0.15 and 0.30 in, 0.14 and 0.31 out",
      [bool(ent([mc(m(2), a - 0.02, a)], FS.UFC)) for a in (0.15, 0.30, 0.14, 0.31)], [True, True, False, False])
check("a candle ending exactly at the one-hour mark is not after it; one past the 15 minutes is too late",
      (ent([mc(m(0), 0.09, 0.12)]), ent([mc(m(16), 0.09, 0.12)])), (None, None))
check("the window's last minute (15) still counts", ent([mc(m(15), 0.09, 0.12)])[0], m(15))
check("no candle in the window, no entry", ent([]), None)
check("only candles up to the window are read: a better quote at minute 20 changes nothing",
      ent([mc(m(3), 0.09, 0.12), mc(m(20), 0.10, 0.11)])[2], 0.12)
check("a window never reaches the start itself (a start 10 minutes away)",
      FS.entry_for([mc(S0 - 540, 0.09, 0.12)], S0 - 600 + 3600 - 3600 + 600, FS.BOXING), None)

print("\nfills: a TRADE at or above the target, never the bid")
E = m(4)
cs = [mc(E, 0.09, 0.12, last=0.11),
      mc(E + 60, 0.60, 0.62, hi=0.20, vol=5),                  # the bid sits at 0.60 (2x is 0.24): not a fill
      mc(E + 120, 0.10, 0.13, hi=0.23, vol=9),                 # a print under 0.24
      mc(E + 180, 0.12, 0.14, hi=0.24, vol=31.5),              # a print AT 0.24: the 2x leg fills
      mc(E + 240, 0.30, 0.35, hi=0.40, vol=2)]                 # 0.36 (3x) not printed
lo2, lo3 = MS.fill_of(cs, E, 0.24, "yes", detail=True), MS.fill_of(cs, E, 0.36, "yes", detail=True)
check("the bid high never fills; the 0.24 print does, with the minute's traded volume", (lo2, lo3), ((E + 180, 0.24, 31.5), (E + 240, 0.36, 2.0)))
check("a print under the target (0.23) does not fill 0.24", MS.fill_of(cs[:3], E, 0.24, "yes", detail=True), None)
check("the entry's own minute does not count", MS.fill_of([mc(E, 0.09, 0.12, hi=0.90)], E, 0.24), None)
check("without detail the engine's own two-item answer is unchanged", MS.fill_of(cs, E, 0.24), (E + 180, 0.24))

# ----------------------------------------------------------------------------- a fake API

SERIES = "KXBOXING"
EV = "KXBOXING-26OCT31AAABBB"
DOG, FAV = EV + "-AAA", EV + "-BBB"


def world(start=START, series=SERIES, result=None, open_=True, with_milestone=True):
    ms = [dict(ticker=DOG, yes_sub_title="Dave Dog", status="active", result=""),
          dict(ticker=FAV, yes_sub_title="Frank Favourite", status="active", result="")]
    if result:
        for mk in ms:
            mk.update(status="finalized", result="yes" if mk["ticker"] == result else "no")
    w = dict(events={EV: dict(event_ticker=EV, markets=ms)}, open=[EV] if open_ else [], series=series,
             milestones={EV: [dict(type="boxing_match", start_date=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                   related_event_tickers=[EV], primary_event_tickers=[EV])]} if with_milestone else {},
             candles={DOG: [], FAV: []}, books={}, calls=[])
    return w


def fetcher(w):
    def fetch(path):
        w["calls"].append(path)
        if path.startswith("events?series_ticker="):
            ser = path.split("series_ticker=")[1].split("&")[0]
            keys = w["open"] if "status=open" in path else w.get("recent", [])
            return {"events": [w["events"][t] for t in keys] if ser == w["series"] else [], "cursor": ""}
        if path.startswith("milestones?related_event_ticker="):
            return {"milestones": w["milestones"].get(path.split("ticker=")[1].split("&")[0], [])}
        if "/candlesticks?" in path:
            a = int(re.search(r"start_ts=(\d+)", path).group(1))
            b = int(re.search(r"end_ts=(\d+)", path).group(1))
            tk = sorted(w["candles"])
            return {"market_tickers": tk, "market_candlesticks": [[c for c in w["candles"][t] if a <= c["end_period_ts"] <= b] for t in tk]}
        if path.startswith("markets/") and path.endswith("/orderbook"):
            return w["books"].get(path.split("/")[1], {"orderbook_fp": {"no_dollars": [], "yes_dollars": []}})
        if path.startswith("events/"):
            return {"event": w["events"][path.split("/")[1].split("?")[0]]}
        raise AssertionError("unexpected path " + path)
    return fetch


def at(mins_after_start):
    return START + dt.timedelta(minutes=mins_after_start)


def lane_state(cfg=FS.BOXING):
    st = MS.load(path="/nonexistent/none.json", cfg=cfg)
    st.setdefault("starts", {})
    return st


W = world()
# the dog trades a tight 9/12 an hour before; the favourite sits at 0.85 (outside the band)
W["candles"][DOG] = [mc(m(1), 0.04, 0.20, vol=3), mc(m(3), 0.09, 0.12, last=0.11, vol=40),
                     mc(S0 + 600, 0.10, 0.13, hi=0.20, vol=4),                 # in the fight: below the 2x target of 0.24
                     mc(S0 + 1200, 0.12, 0.16, hi=0.24, vol=77.5),             # a trade at 0.24: the 2x leg fills
                     mc(S0 + 1800, 0.01, 0.02, hi=0.03, vol=2)]
W["candles"][FAV] = [mc(m(3), 0.84, 0.85, last=0.85, vol=60)]
W["books"][DOG] = {"orderbook_fp": {"no_dollars": [["0.8800", "20"], ["0.9100", "5"]], "yes_dollars": []}}
F = fetcher(W)

print("\nthe run: schedule from the milestone, entry only once the window has passed")
st = lane_state()
FS.run(st, now=at(-120), fetch=F, cfg=FS.BOXING)
check("two hours before the start: the schedule is read, nothing is entered, the window is waited for",
      (len(st["entries"]), st["starts"], st["observations"]["waiting"]), (0, {EV: "2026-10-31T21:00:00+00:00"}, 1))
check("no candle was fetched yet", [p for p in W["calls"] if "candlesticks" in p], [])
st = lane_state()
FS.run(st, now=at(-50), fetch=F, cfg=FS.BOXING)
check("50 minutes before: the 15-minute window is still open (it closes at 45): waiting", (len(st["entries"]), st["observations"]["waiting"]), (0, 1))

st = lane_state()
FS.run(st, now=at(-30), fetch=F, cfg=FS.BOXING)
e = st["entries"][0]
check("30 minutes before: the dog is bought at the 0.12 ask, not the wide minute-1 quote",
      (len(st["entries"]), e["word"], e["price"], e["bid"], e["spread"], e["entry_at"]),
      (1, "Dave Dog", 0.12, 0.09, 0.03, "2026-10-31T20:03:00+00:00"))
check("recorded: minutes to the start, last trade, cost of the spread, size traded to the entry, size on the book",
      (e["minutes_to_start"], e["last_trade"], e["spread_cost"], e["traded_to_entry"], e["book_size"], e["fight_start"]),
      (57.0, 0.11, 0.01, 43.0, 25.0, "2026-10-31T21:00:00+00:00"))
check("legs rest at 2x and 3x of the ask paid", [(l["multiple"], l["target"]) for l in e["legs"]], [(2.0, 0.24), (3.0, 0.36)])
check("the favourite at 0.85 is skipped, with the reason", (list(st["skips"]), st["skips"][FAV]["reason"]),
      ([FAV], FS.BOXING["skip"]))
check("one entry only, status open (the fight has not been fought)", (e["status"] if "status" in e else "open", e["payout"]), ("open", None))

FS.run(st, now=at(-20), fetch=F, cfg=FS.BOXING)
check("a second read inside the window adds nothing (one entry per fighter per fight)", (len(st["entries"]), len(st["skips"])), (1, 1))

print("\nthe run: fills on trade prints, volume per fill, settlement, hold on the same entry")
st = lane_state()
FS.run(st, now=at(5), fetch=F, cfg=FS.BOXING)
e = st["entries"][0]
check("read 5 minutes into the fight (a $0.20 print only): no fill, the book is not read once it has started",
      ([bool(l.get("filled_at")) for l in e["legs"]], e.get("book_size")), ([False, False], None))
FS.run(st, now=at(25), fetch=F, cfg=FS.BOXING)
e = st["entries"][0]
check("25 minutes in: the 0.24 print fills the 2x leg and records that minute's 77.5 contracts; 3x rests",
      (e["legs"][0].get("filled_at"), e["legs"][0].get("fill_volume"), e["legs"][1].get("filled_at"), e["legs"][1].get("fill_volume")),
      ("2026-10-31T21:20:00+00:00", 77.5, None, None))
check("the bid sitting under it never filled anything and the entry is not graded yet", (e.get("roi"), e["payout"]), (None, None))

W["events"][EV]["markets"][0].update(status="finalized", result="no")          # the dog lost
W["events"][EV]["markets"][1].update(status="finalized", result="yes")
W["open"] = []                                                                   # off the open list: read as held
FS.run(st, now=at(300), fetch=F, cfg=FS.BOXING)
e = st["entries"][0]
cost = fin(0.12)
split = 0.5 * out(0.24) + 0.5 * 0.0 - cost
check("settled: the filled 2x leg paid a maker fee, the unfilled 3x leg was held to settlement and lost",
      (e["payout"], e["legs"][1]["settled_px"], round(e["pnl"], 4), round(e["roi"], 4)),
      (0.0, 0.0, round(split, 4), round(split / cost, 4)))
check("HOLD is recorded on the same entry: the dog lost, so -100%", e["roi_held"], -1.0)
check("2x only is recorded too", round(e["roi_2x"], 4), round((out(0.24) - cost) / cost, 4))
check("the record over this lane: 1 entry, 1 won-or-lost settled, 0 won, 1 leg filled at 2x",
      (lambda r: (r["entries"], r["settled"], r["won"], r["filled_2x"], r["filled_3x"]))(MS.record(st["entries"])), (1, 1, 0, 1, 0))

print("\nthe run: a winning hold, and the schedule edge cases")
W2 = world(result=DOG, open_=False)
W2["candles"][DOG] = copy.deepcopy(W["candles"][DOG])[:3]
W2["candles"][FAV] = copy.deepcopy(W["candles"][FAV])
W2["open"] = [EV]
st2 = lane_state()
FS.run(st2, now=at(30), fetch=fetcher(W2), cfg=FS.BOXING)       # entered while open
W2["open"] = []
FS.run(st2, now=at(400), fetch=fetcher(W2), cfg=FS.BOXING)       # settled, off the list
e2 = st2["entries"][0]
check("the dog won: an unfilled split pays 1 on both legs, hold the same", (e2["payout"], round(e2["roi"], 4), round(e2["roi_held"], 4)),
      (1.0, round((1 - cost) / cost, 4), round((1 - cost) / cost, 4)))

Wn = world(with_milestone=False)
stn = lane_state()
FS.run(stn, now=at(-30), fetch=fetcher(Wn), cfg=FS.BOXING)
check("no milestone, no scheduled start: no entry and it is counted", (len(stn["entries"]), stn["observations"]["no_start"]), (0, 1))
Wd = world()
Wd["milestones"][EV] = Wd["milestones"][EV] * 2
check("two milestones for one fight are ambiguous: no start", FS.milestone_start(EV, fetcher(Wd)), None)
Wt = world()
Wt["milestones"][EV][0]["type"] = "cricket_match"
check("a milestone of another type is not a fight's", FS.milestone_start(EV, fetcher(Wt)), None)

Wr = world()
fr = fetcher(Wr)
st3 = lane_state()
st3["starts"][EV] = "2026-10-31T21:00:00+00:00"
Wr["milestones"][EV][0]["start_date"] = "2026-10-31T22:30:00Z"                    # the fight moved back 90 minutes
n0 = len([p for p in Wr["calls"] if p.startswith("milestones")])
FS.fight_start(st3, EV, S0 - 6 * 3600, fr)
check("a fight more than 4 hours away is not re-read", len([p for p in Wr["calls"] if p.startswith("milestones")]) - n0, 0)
check("within 4 hours and before its entry window: re-read, the new start wins",
      (FS.fight_start(st3, EV, S0 - 3 * 3600, fr), st3["starts"][EV]), (S0 + 5400, "2026-10-31T22:30:00+00:00"))
n1 = len([p for p in Wr["calls"] if p.startswith("milestones")])
FS.fight_start(st3, EV, S0 + 5400 - 40 * 60, fr)
check("once its entry window is past it is never re-read", len([p for p in Wr["calls"] if p.startswith("milestones")]) - n1, 0)
check("an entered fight keeps its start", FS.fight_start(st3, EV, S0 - 3 * 3600, fr, entered=True), S0 + 5400)

print("\nbackfill: a fight still open at the first run is replayed if its entry minute is within six days")
Wb = world(start=START - dt.timedelta(days=3))
Wb["candles"][DOG] = [mc(S0 - 3 * 86400 - 3600 + 180, 0.09, 0.12, last=0.11, vol=10)]
stb = lane_state()
FS.run(stb, now=START, fetch=fetcher(Wb), cfg=FS.BOXING)
check("three days old, still open: entered from its candles", (len(stb["entries"]), stb["entries"][0]["price"]), (1, 0.12))
Wo = world(start=START - dt.timedelta(days=9))
sto = lane_state()
FS.run(sto, now=START, fetch=fetcher(Wo), cfg=FS.BOXING)
check("nine days old: its minute candles are gone, so it is not replayed", (len(sto["entries"]), len(sto["skips"]), sto["observations"]["events"]),
      (0, 0, 0))
Wc = world()
stc = lane_state()
FS.run(stc, now=at(-30), fetch=fetcher(Wc), cfg=FS.BOXING)           # no candles at all just after the window
check("no candles served yet right after the window: wait, never skip", (len(stc["entries"]), len(stc["skips"])), (0, 0))
FS.run(stc, now=at(-30 + 80), fetch=fetcher(Wc), cfg=FS.BOXING)
check("still none an hour later: skipped, with the reason", (len(stc["skips"]), stc["skips"][DOG]["reason"]), (2, FS.BOXING["skip"]))

print("\nthe ufc lane is the same engine on KXUFCFIGHT and its own band")
Wu = world(series="KXUFCFIGHT")
Wu["candles"][DOG] = [mc(m(3), 0.17, 0.21, last=0.20, vol=12)]
Wu["candles"][FAV] = [mc(m(3), 0.77, 0.79)]
stu = lane_state(FS.UFC)
FS.run(stu, now=at(-30), fetch=fetcher(Wu), cfg=FS.UFC)
check("a 0.21 ask is inside 0.15-0.30 and is bought; the lane ledger is its own", (len(stu["entries"]), stu["entries"][0]["price"], stu["lane"]),
      (1, 0.21, "ufc_dog"))
sts = lane_state(FS.BOXING)
FS.run(sts, now=at(-30), fetch=fetcher(Wu), cfg=FS.BOXING)
check("the boxing lane never reads a UFC series", (len(sts["entries"]), sts["observations"]["events"]), (0, 0))

print("\nthe page")
html = FB.build(states={"boxing_cheap_dog": st, "ufc_dog": stu}, now=at(300))
check("title, heading, the standard", ("Edge Machine · Fights" in html, "<h1>Fights</h1>" in html, "Cheap side + resting take-profit" in html),
      (True, True, True))
check("a summary table row per lane and the review rule", (html.count("Boxing · cheap dog (3-15c)") >= 2, "UFC · dog (15-30c)" in html,
                                                           "review at 10, decide at 30" in html), (True, True, True))
check("the summary's columns", all(x in html for x in ("Entries", "Settled", "Won", "Split ROI", "Hold ROI", "Legs filled 2x / 3x", "Avg spread paid")), True)
check("both lane cards, with their research notes", ("boxing-cheap-dog" in html and "ufc-dog" in html, "134 matches" in html, "169 fights" in html),
      (True, True, True))
check("a filled leg shows the minute's traded volume", "77.5 traded that minute" in html, True)
check("the trade list names the fighter, the ask paid, the last trade and the cost of the spread",
      ("Dave Dog" in html, "Fighter" in html, "Cost of the spread" in html, "Last trade" in html), (True, True, True, True))
check("phone layout: every body cell is labelled for its column (data-l)", ('data-l="Fighter"' in html, 'data-l="ROI"' in html), (True, True))
check("skipped fighters are counted with the lane's own reason", ("Fighters skipped: 1" in html, FS.BOXING["skip"] in html), (True, True))
check("the Fights link is in the nav on its own page and on another page",
      ('href="./fights.html"' in html, 'href="./fights.html"' in C.nav("culture"), ">Fights<" in C.nav("culture")), (True, True, True))
check("it sits in the Markets menu", "fights" in C.MARKET_GROUP, True)
check("the page file name is registered", C.PAGE_FILES["fights"], "fights.html")
check("an empty ledger renders both cards", all(x in FB.build(states={c["lane"]: lane_state(c) for c in FS.LANES}, now=at(0))
                                                for x in ("No entry yet", "Not read yet")), True)
check("no guarded public phrase on the page or in the rules", sandbox_audit.COPY_RE.findall(html + " ".join(c["rule"] for c in FS.LANES)), [])

print("\nthe shared engine is unchanged for its other lanes")
dflt = MS.section(MS.load(path="/nonexistent/none.json", cfg=MS.STRICT), C.esc)
check("the Culture card still says Words skipped and keeps its YES-ask wording", ("Words skipped" in dflt,), (True,))
check("the engine's hourly fill still returns its two-item answer", MS.fill_of([mc(E + 60, 0.4, 0.5, hi=0.9)], E, 0.5), (E + 60, 0.5))

print("\nthe workflows and the build")
wf = open("/".join([FS.ROOT, ".github", "workflows", "fights.yml"])).read()
check("fights.yml runs hourly, the tests, the script, saves both ledgers and asks for the page build",
      ("cron: '23 * * * *'" in wf, "python3 test_fights_split.py" in wf, "python3 fights_split.py" in wf,
       "git add data/boxing_cheap_dog_ledger.json data/ufc_dog_ledger.json" in wf, "gh workflow run sandbox-tracker.yml" in wf),
      (True, True, True, True, True))
tr = open("/".join([FS.ROOT, ".github", "workflows", "sandbox-tracker.yml"])).read()
check("the Sandbox Tracker stages the Fights page", "git add public_site/fights.html" in tr, True)
sb = open("/".join([FS.ROOT, "sandbox_build.py"])).read()
check("the Sandbox build writes fights.html", "fights_build.build(now=now)" in sb, True)

print("\na fight that opens and settles between two runs is still entered (2026-11-01: 11 fights missed)")
WS = world(result=DOG, open_=False)
WS["recent"] = [EV]                                    # settled: off the open list, on the recently settled one
WS["candles"][DOG] = list(W["candles"][DOG]) + [mc(m(10), 0.09, 0.12, last=0.12, lo=0.11, vol=25)]   # 25 traded through the ask
WS["candles"][FAV] = list(W["candles"][FAV])
FSet = fetcher(WS)
st = lane_state()
FS.run(st, now=at(600), fetch=FSet, cfg=FS.BOXING)     # the first run since before the fight: it is already final
e = st["entries"][0] if st["entries"] else {}
check("the settled fight is listed through the closed/settled query, not only the open one",
      any("status=closed,settled" in p and "min_close_ts=" in p for p in WS["calls"]), True)
check("it is entered from the minute candles at the 0.12 ask, the favourite skipped",
      (len(st["entries"]), e.get("price"), e.get("entry_at"), list(st["skips"])), (1, 0.12, "2026-10-31T20:03:00+00:00", [FAV]))
check("its 2x leg fills on the 0.24 print, and it is settled (the dog won)",
      (e["legs"][0].get("filled_at"), e["payout"], e.get("roi") is not None), ("2026-10-31T21:20:00+00:00", 1.0, True))
check("the 10+ traded-through rule verifies it (no pre-fight book on a replay)", (MS.check_status(e), e.get("book_size")), ("verified", None))
FS.run(st, now=at(660), fetch=FSet, cfg=FS.BOXING)
check("a second run adds nothing: no double entry, one event on file", (len(st["entries"]), len(st["skips"]), list(st["events"])), (1, 1, [EV]))

old_start = START - dt.timedelta(days=FS.BACKFILL_DAYS + 2)
WO = world(start=old_start, result=DOG, open_=False)
WO["recent"] = [EV]
WO["candles"][DOG] = [mc(int(old_start.timestamp()) - 3600 + 180, 0.09, 0.12, last=0.11, vol=40)]
st = lane_state()
FS.run(st, now=at(600), fetch=fetcher(WO), cfg=FS.BOXING)
check("a fight whose entry minute is older than BACKFILL_DAYS is not entered (its candles are gone)", len(st["entries"]), 0)

before = START.replace(day=20)
WB = world(start=before, result=DOG, open_=False)
WB["recent"] = [EV]
WB["candles"][DOG] = [mc(int(before.timestamp()) - 3600 + 180, 0.09, 0.12, last=0.11, vol=40)]
st = lane_state()
FS.run(st, now=before + dt.timedelta(hours=5), fetch=fetcher(WB), cfg=FS.BOXING)
check("a fight from before the lane was registered is not entered, whatever the window", len(st["entries"]), 0)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
