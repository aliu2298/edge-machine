"""Chaos lanes (2026-10-25): where lane configs plug into chaos_replay.py.

Phase 1 ships NO lane: LANES is empty, so nothing is replayed and the Sandbox's Chaos section says so.
Phase 2 sessions add a config here after the engine merges. Every lane starts a FRESH record from
its first replayed night (chaos_replay.lane_state): never inherit an old lane's rows, and never
edit or delete an old lane's rows or ledger (they stay archived as they are).

A chaos lane BUYS BEFORE THE EVENT STARTS (1 hour before, and a 24-hour variant) and rests a limit
sell at +20%, +30% or +50% ROI after fees from that moment; the in-play swings fill it or the
position settles. Nothing is bought during the event. The control is the same entry held to
settlement.

A lane config:

    id            "chaos_nba_ml"                      the lane's ledger key
    label         "NBA moneyline"                     shown on the page
    series        ["KXNBAGAME"]                       Kalshi series to replay (settled events)
    picker        chaos_replay.band_picker(0.70, 0.85)        which market and side to buy:
                  chaos_replay.any_side_picker()              any side of every market
                  chaos_replay.named_picker(table)            a named side from another lane's pick
                  or any callable(ctx) -> [(ticker, "yes"|"no")]; ctx has event, series, tickers,
                  markets, close_ts, minutes, hours and entry_view(ticker, side) (the side's quote
                  at the entry time being replayed, None if there is none)
    entry_hours   (1, 24)                             optional: hours before the start to buy
    start         callable(ctx) -> epoch seconds      optional: the lane's own kickoff / tip source
                  (the ESPN times the other lanes use). Without it the start is detected from the
                  price path (18 minutes of detection lag removed), else close minus duration_min
    duration_min  160                                 minutes from start to close (the fallback)
    since         "2026-10-26"                        optional first night (ISO date)
    note          one line: what the lane tests

Planned (Phase 2): tennis (KXATPMATCH / KXWTAMATCH / KXATPCHALLENGERMATCH, a favourite or an
underdog band), NBA moneyline (KXNBAGAME), cricket T20 (KXT20MATCH), NFL / CFB winners, NFL totals
(a 40-60c rung), NBA 1Q / 1H middle rungs, ATP total games middle rung.
"""
import datetime as dt
import json
import re
import subprocess
import urllib.request

import chaos_replay as C
import daily_track as D

ESPN_SITE = "https://site.web.api.espn.com/apis/site/v2/sports"
_BOARDS = {}


def _board(path, day):
    """ESPN scoreboard events for one day (cached); [] when ESPN is unreachable."""
    key = (path, day)
    if key not in _BOARDS:
        url = f"{ESPN_SITE}/{path}/scoreboard?dates={day:%Y%m%d}" + ("&groups=80&limit=300" if "college" in path else "")
        body = None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as f:
                body = f.read()
        except Exception:
            try:
                body = subprocess.run(["curl", "-s", "--max-time", "20", url], capture_output=True, timeout=30).stdout
            except Exception:
                body = None
        try:
            _BOARDS[key] = json.loads(body).get("events") or []
        except Exception:
            _BOARDS[key] = []
    return _BOARDS[key]


def espn_start(path):
    """A start(ctx) that finds the game on ESPN's scoreboard by the two team codes in the event
    ticker (KXNBAGAME-26OCT24HOUATL -> HOU, ATL) and returns its kickoff; None sends the engine to the
    price path."""
    def start(ctx):
        day = C.event_date(ctx["event"])
        code = re.sub(r"^.*?-\d\d[A-Z]{3}\d\d(?:\d{4})?", "", ctx["event"])
        if not day or not code:
            return None
        for d in (day - dt.timedelta(days=1), day, day + dt.timedelta(days=1)):
            for ev in _board(path, d):
                abbr = [(t.get("team") or {}).get("abbreviation", "") for c in (ev.get("competitions") or [])[:1]
                        for t in c.get("competitors") or []]
                if len(abbr) == 2 and all(a and a in code for a in abbr) and ev.get("date"):
                    try:
                        return int(dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).timestamp())
                    except ValueError:
                        return None
        return None
    return start


def winmargin_start(ctx):
    """The NBA win margin tracker's tip rule (nba_winmargin.py): the KXNBAGAME market's
    expected_expiration_time minus 3 hours, from the same game's moneyline event. None sends the engine to
    the price path."""
    import nba_winmargin as W
    suf = ctx["event"].split("-", 1)[1]
    fetch = ctx["fetch"]
    ms = D.pages(f"markets?limit=5&event_ticker=KXNBAGAME-{suf}", "markets", fetch) \
        or D.pages(f"historical/markets?limit=5&event_ticker=KXNBAGAME-{suf}", "markets", fetch)
    tip = next((x for x in (W._ts(m.get("expected_expiration_time")) for m in ms) if x), None)
    return None if tip is None else tip - W.TIP_BACK_H * 3600


def bucket_picker(buckets, lo, hi, spread):
    """YES of a win margin bucket (by its title: 1-5, 6-10) whose ask at the entry hour is lo-hi with a
    spread of `spread` or less, either team."""
    import nba_winmargin as W
    inner = C.band_picker(lo, hi, ("yes",), spread=spread)

    def pick(ctx):
        return [(t, s) for t, s in inner(ctx)
                if W.bucket_of((ctx["markets"].get(t) or {}).get("yes_sub_title")) in buckets]
    return pick


DOG = C.band_picker(0.10, 0.40, ("yes",))
FIRST_NIGHT = "2026-10-25"          # approved 2026-10-24: every record starts fresh from here

LANES = [
    # 2026-10-27 (Olu): the cheap-side split as the chaos standard. A Challenger player whose YES ask is
    # 0.15-0.30 (spread 5c or less) about an hour before the match, start found as for
    # challenger_dog_tp30 (the first in-play price movement); SPLIT half at 2x, half at 3x of the ask
    # (cap 0.98), filled only on a traded print, else held; HOLD on the same entries. Research (Olu,
    # real asks, 149 settled matches): 21 entries, 7 won, 14 reached 2x; split +43% (z 1.7, halves
    # +44% / +42%), hold +24%. 3-15c and the ATP main tour lost. Fresh record from 2026-10-26.
    # RETIRED 2026-10-31 (Olu): no new entries from that night on; its rows stay on the ledger as they are.
    dict(id="challenger_cheap_split", label="Challenger cheap side · split 2x / 3x", series=["KXATPCHALLENGERMATCH"],
         picker=C.band_picker(0.15, 0.30, ("yes",), spread=0.05), max_spread=0.05, entry_hours=(1,),
         exits=("hold", C.SPLIT), headline=C.SPLIT, first=True, since="2026-10-26", duration_min=120,
         retired=dict(on="2026-10-31", at="34 settled, 10 won; split +0.8%, hold +19.6%",
                      reason="decided at 34 settled: the split sell (+0.8%) lost to holding (+19.6%); the hold result is 10 cheap-underdog wins, not a proven edge"),
         note="A Challenger player priced 15-30c (spread 5c or less) an hour before the match, with a split resting sell: "
              "half at 2x, half at 3x of the ask paid. Start from the first in-play price movement, as challenger_dog_tp30."),
    # RETIRED 2026-10-27 (Olu): no new entries from that night on; its rows stay on the ledger as they are.
    dict(id="challenger_dog_tp30", label="Challenger underdog · sell +30%", series=["KXATPCHALLENGERMATCH"], picker=DOG,
         entry_hours=(1,), headline="tp30", since=FIRST_NIGHT, duration_min=120,
         retired=dict(on="2026-10-27", at="45 settled, 13 won; hold -3.2%, split -7.9%, every target exit negative",
                      reason="superseded by challenger_cheap_split (the 15-30c band)"),
         note="A Challenger player priced 10-40c an hour before the match, with a resting sell at +30%. Start from the first in-play price movement (Kalshi's occurrence time is near the END). 24h books are empty, so 1h only."),
    dict(id="cfb_dog_tp50", label="College football underdog · sell +50%", series=["KXNCAAFGAME"], picker=DOG,
         entry_hours=(1, 24), headline="tp50", since=FIRST_NIGHT, duration_min=210, start=espn_start("football/college-football"),
         note="A side priced 10-40c, bought 1h and 24h before kickoff, with a resting sell at +50%."),
    # RETIRED 2026-10-29 (Olu): no new entries from that night on; its rows stay on the ledger as they are.
    dict(id="atp_coinflip_tp30", label="ATP coin-flip · sell +30%", series=["KXATPMATCH"],
         picker=C.one_per_event(C.band_picker(0.40, 0.60, ("yes",))), entry_hours=(1,), headline="tp30", watch=True,
         since=FIRST_NIGHT, duration_min=120,
         retired=dict(on="2026-10-29", at="13 settled, 6 won; split -2.0%, hold -1.5%, every target exit (+20/+30/+50/+100%, with or without a stop) loses to hold by 2 to 29 points",
                      reason="every take-profit exit loses to holding"),
         note="One player (the cheaper ask) priced 40-60c an hour before the match, with a resting sell at +30%. Start from the first in-play price movement."),
    # RETIRED 2026-10-27 (Olu): no new entries from that night on; its rows stay on the ledger as they are.
    dict(id="nba_tt_cheap_tp30", label="NBA team-total cheap rungs · sell +30%", series=["KXNBATEAMTOTAL"], picker=DOG,
         entry_hours=(1, 24), headline="tp30", since=FIRST_NIGHT, duration_min=160, start=espn_start("basketball/nba"),
         retired=dict(on="2026-10-27", at="145 settled, 26 won; hold -29.4%, split -37.8%, +30% sell -38.8%, every exit negative",
                      reason="past 30 and losing under every exit"),
         note="Each team's rungs priced 10-40c, bought 1h and 24h before the tip, with a resting sell at +30%. A loss-cutter test for the failing NBA team-total lanes. Rungs of one game move together: z is clustered by night, which is at least as strict as by game."),
    # 2026-10-28 (Olu): the HEADLINE exit moves from +50% to the cheap-side split (half 2x, half 3x), on the
    # same entries: the record does NOT reset (every exit was tracked on them from the first night) and the
    # lane id stays nba_ml_dog_tp50 so the ledger history is continuous. At 12 settled (Oct 25-27): split
    # +15.2%, +30% +14.4%, hold +13.9%, +100% +10.6%, +20% +5.6%, +50% +0.7%, every -50% stop -15% to -26%;
    # the +50% sell capped the 4 outright winners (+146% to +228% held). Hold stays its comparison row and
    # every other exit is still tracked. SUB-BAND ask 10-30c: the same entries narrowed (the 37-40c entries
    # reached 2x hardest), split v hold, shown under the lane; the 10-40c population stays the lane.
    dict(id="nba_ml_dog_tp50", label="NBA moneyline underdog · split 2x / 3x", series=["KXNBAGAME"], picker=DOG,
         entry_hours=(1,), headline=C.SPLIT, since=FIRST_NIGHT, duration_min=160, start=espn_start("basketball/nba"),
         sub_bands=(dict(id="ask_10_30", label="ask 10-30c", lo=0.10, hi=0.30),),
         caution="Read the split against its hold row; the ask 10-30c row is the same entries narrowed, not a new lane. "
                 "Reviewed at 31: kept as paper (beats hold, not strong enough to promote).",
         note="A team priced 10-40c an hour before the tip, with a split resting sell: half at 2x, half at 3x of the "
              "ask paid. The headline exit was +50% until 2026-10-28; it moved to the split on the same entries, "
              "with no reset, and every other exit is still tracked."),
    # 2026-10-30 (Olu): the NBA win margin LANE, from the tracker's research (nba_winmargin.py: a 1-5 or 6-10
    # bucket at a cheap ask reaches 2x about 7 times in 10). YES of the 1-5 and 6-10 buckets, either team,
    # priced 10-20c (spread 5c or less) an hour before the tip (the tracker's tip rule: KXNBAGAME expiry
    # minus 3h); the split resting sell (half 2x, half 3x of the ask), a leg filling ONLY on a traded print
    # from the tip on, the rest held; the same entries held as the control. FRESH from 2026-10-30. The rule
    # was chosen on Oct 20-29 data, so that period is the separate in-sample row below, never the headline.
    dict(id="nba_winmargin_split", label="NBA win margin 1-5 / 6-10 · split 2x / 3x", series=["KXNBAWINMARGIN"],
         picker=bucket_picker(("1-5", "6-10"), 0.10, 0.20, 0.05), max_spread=0.05, entry_hours=(1,),
         exits=("hold", C.SPLIT, "tp50", "tp100", C.X2), headline=C.SPLIT, since="2026-10-30", start=winmargin_start,
         fill_from_start=True, fetch_before_h=6, duration_min=160,
         note="YES of the 1-5 or 6-10 win margin bucket (either team) priced 10-20c, spread 5c or less, an hour before the tip, "
              "with a split resting sell: half at 2x, half at 3x of the ask paid, filling only on a traded print from the tip on. "
              "The buckets of one game are not independent: z is clustered by night."),
    dict(id="nba_winmargin_split_insample", label="NBA win margin 1-5 / 6-10 · IN-SAMPLE backfill Oct 20-29", series=["KXNBAWINMARGIN"],
         picker=bucket_picker(("1-5", "6-10"), 0.10, 0.20, 0.05), max_spread=0.05, entry_hours=(1,),
         exits=("hold", C.SPLIT, "tp50", "tp100", C.X2), headline=C.SPLIT, since="2026-10-20", until="2026-10-29",
         start=winmargin_start, fill_from_start=True, fetch_before_h=6, duration_min=160, insample=True,
         note="The same rule replayed on Oct 20-29, the data it was chosen on: in-sample, so it is NOT evidence and is never the "
              "lane's headline. It stops on 2026-10-29; the lane's own record starts fresh on 2026-10-30."),
]

# A demo config for tests and dry runs (python3 chaos_replay.py --demo --out <scratch>); never registered.
DEMO = dict(id="demo_nba_ml_pre", label="Demo · NBA moneyline, bought before the tip", series=["KXNBAGAME"],
            picker=C.any_side_picker(), entry_hours=(1, 24), duration_min=160,
            note="Demo only: either side of every NBA game, bought 1h and 24h before the tip with a resting limit sell.")
