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


DOG = C.band_picker(0.10, 0.40, ("yes",))
FIRST_NIGHT = "2026-10-25"          # approved 2026-10-24: every record starts fresh from here

LANES = [
    dict(id="challenger_dog_tp30", label="Challenger underdog · sell +30%", series=["KXATPCHALLENGERMATCH"], picker=DOG,
         entry_hours=(1,), headline="tp30", since=FIRST_NIGHT, duration_min=120,
         note="A Challenger player priced 10-40c an hour before the match, with a resting sell at +30%. Start from the first in-play price movement (Kalshi's occurrence time is near the END). 24h books are empty, so 1h only."),
    dict(id="cfb_dog_tp50", label="College football underdog · sell +50%", series=["KXNCAAFGAME"], picker=DOG,
         entry_hours=(1, 24), headline="tp50", since=FIRST_NIGHT, duration_min=210, start=espn_start("football/college-football"),
         note="A side priced 10-40c, bought 1h and 24h before kickoff, with a resting sell at +50%."),
    dict(id="atp_coinflip_tp30", label="ATP coin-flip · sell +30%", series=["KXATPMATCH"],
         picker=C.one_per_event(C.band_picker(0.40, 0.60, ("yes",))), entry_hours=(1,), headline="tp30", watch=True,
         since=FIRST_NIGHT, duration_min=120,
         note="One player (the cheaper ask) priced 40-60c an hour before the match, with a resting sell at +30%. Start from the first in-play price movement."),
    dict(id="nba_tt_cheap_tp30", label="NBA team-total cheap rungs · sell +30%", series=["KXNBATEAMTOTAL"], picker=DOG,
         entry_hours=(1, 24), headline="tp30", since=FIRST_NIGHT, duration_min=160, start=espn_start("basketball/nba"),
         note="Each team's rungs priced 10-40c, bought 1h and 24h before the tip, with a resting sell at +30%. A loss-cutter test for the failing NBA team-total lanes. Rungs of one game move together: z is clustered by night, which is at least as strict as by game."),
    dict(id="nba_ml_dog_tp50", label="NBA moneyline underdog · sell +50%", series=["KXNBAGAME"], picker=DOG,
         entry_hours=(1,), headline="tp50", since=FIRST_NIGHT, duration_min=160, start=espn_start("basketball/nba"),
         caution="In the research HOLD beat the sell (+12% v +1%, n18): read this lane against its hold row.",
         note="A team priced 10-40c an hour before the tip, with a resting sell at +50%."),
]

# A demo config for tests and dry runs (python3 chaos_replay.py --demo --out <scratch>); never registered.
DEMO = dict(id="demo_nba_ml_pre", label="Demo · NBA moneyline, bought before the tip", series=["KXNBAGAME"],
            picker=C.any_side_picker(), entry_hours=(1, 24), duration_min=160,
            note="Demo only: either side of every NBA game, bought 1h and 24h before the tip with a resting limit sell.")
