#!/usr/bin/env python3
"""Last season's NBA team-total and PRA prices, from The Odds API's historical snapshots.

WHY THIS EXISTS. Neither venue the bot can reach holds any NBA price history. Every NBA
market Kalshi serves is `active` and closes this month; asked for the window Oct 2025 to
Jul 2026 it returns nothing on the game, team-total and PRA series alike, and the two
markets wanted here -- KXNBATEAMTOTAL and KXNBAPRA -- hold no markets at all. Polymarket US
lists only winner, spread and game total per NBA event, so it has no team total and no
player prop to have a history of. ESPN carries 23 seasons of RESULTS and no odds at all.

So a team-total or PRA rule cannot be built the way the Turkey, Eredivisie and Bundesliga
lanes were -- a multi-season study measured against each contest's own closing price --
because for NBA no such closing price is held anywhere this project can read. The only
route to last season's lines is a vendor snapshot, and this reads one.

WHAT IT COSTS, stated up front because the budget is small. The Odds API charges 10 credits
per region per market on every historical endpoint, against a 500-credit monthly free tier
that the Pinnacle lane already paces itself inside. So:

  --probe              10 credits. One featured-market historical call. Settles the only
                       open question: the pricing table lists "Historical Odds" under the
                       free Starter plan while the historical-data page says "Historical
                       data is only available on paid usage plans". Those cannot both be
                       true. This asks the API instead of guessing, and spends the least
                       that can produce an answer.
  --pull N             20 credits per game (team_totals + player_points_rebounds_assists,
                       one region), plus the historical event list. N=10 is 200 credits.

COVERAGE. Featured markets go back to 2020-06-06. Additional markets -- which is where both
team totals and every player prop live -- start 2023-05-03 at 5-minute snapshots, so last
season is inside the window and the 2023-24 season is the earliest usable one.

EACH GAME IS PRICED AT ITS OWN LEAD, not at one clock for the night. A 9-game slate tips
across five hours, so a single snapshot would price the late games three hours out and the
early ones at the buzzer. Every call asks for that event's own commence_time minus
LEAD_MINUTES, which is the same discipline the Sandbox uses on a live board and the reason
its prices are comparable to each other at all.

THE KEY never appears in output. It travels in the query string, so this calls the adapter
in sandbox_sources that reports failures by status code and never by URL.

Usage:
  python3 nba_odds_probe.py --probe
  python3 nba_odds_probe.py --pull 10 --date 2026-01-17
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import sandbox_sources as S

SPORT = "basketball_nba"
REGION = "us"
# Both markets the review asked for. team_totals is the per-team points line; the PRA key is
# the one The Odds API documents for NBA, NCAAB and WNBA.
MARKETS = ("team_totals", "player_points_rebounds_assists")
# Minutes before tip-off that each game is priced at. 30 matches the Sandbox's own floor for
# a price that is still pre-match, and the snapshots are 5 minutes apart so it resolves
# cleanly to the last one before that instant.
LEAD_MINUTES = 30
# Never spend below this. The Pinnacle lane budgets against the same balance and would
# otherwise find it gone.
RESERVE = 60
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nba_probe")


def _remaining(headers):
    """Credits left after a call, or None when the header is absent."""
    for name, val in headers.items():
        if name.lower() == "x-requests-remaining":
            try:
                return int(float(val))
            except ValueError:
                return None
    return None


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def probe(date):
    """One cheap historical call. Returns (ok, remaining, note)."""
    try:
        data, headers = S._odds_get(
            f"/historical/sports/{SPORT}/odds",
            dict(regions=REGION, markets="totals", oddsFormat="decimal", date=_iso(date)))
    except RuntimeError as e:
        # 401/403 is the plan refusing historical; 422 is a bad date; anything else is noise.
        return False, None, str(e)
    rows = (data or {}).get("data") or []
    return True, _remaining(headers), (f"snapshot {(data or {}).get('timestamp')} "
                                       f"with {len(rows)} events")


def historical_events(date):
    """Every NBA event in the snapshot at `date`, as the vendor saw it then."""
    data, headers = S._odds_get(f"/historical/sports/{SPORT}/events",
                                dict(date=_iso(date)))
    return ((data or {}).get("data") or []), _remaining(headers)


def event_odds(event_id, date):
    """One event's team totals and PRA at one instant. 10 credits per market per region."""
    data, headers = S._odds_get(
        f"/historical/sports/{SPORT}/events/{event_id}/odds",
        dict(regions=REGION, markets=",".join(MARKETS), oddsFormat="decimal",
             date=_iso(date)))
    return (data or {}), _remaining(headers)


def summarise(blob):
    """What a pulled event actually contains, so an empty market is visible as empty."""
    ev = blob.get("data") or {}
    out = {m: 0 for m in MARKETS}
    books = set()
    for bk in ev.get("bookmakers") or []:
        books.add(bk.get("key"))
        for mk in bk.get("markets") or []:
            if mk.get("key") in out:
                out[mk["key"]] += len(mk.get("outcomes") or [])
    return dict(home=ev.get("home_team"), away=ev.get("away_team"),
                commence=ev.get("commence_time"), snapshot=blob.get("timestamp"),
                bookmakers=sorted(books), outcomes=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true",
                    help="one 10-credit call to test historical access")
    ap.add_argument("--pull", type=int, default=0, metavar="N",
                    help="pull N games (20 credits each)")
    ap.add_argument("--date", default="2026-01-17",
                    help="slate date, YYYY-MM-DD (default a 9-game night last season)")
    a = ap.parse_args()

    if not S._odds_key():
        print("no ODDS_API_KEY in the environment — nothing was called", file=sys.stderr)
        return 2
    try:
        day = datetime.strptime(a.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print(f"--date {a.date!r} is not YYYY-MM-DD", file=sys.stderr)
        return 2

    # Noon UTC on the slate date is before every NBA tip-off (the earliest are 17:00Z), so
    # the event list is the full slate and nothing has started.
    listing_at = day + timedelta(hours=12)

    if a.probe:
        ok, left, note = probe(listing_at)
        print(f"historical access: {'YES' if ok else 'NO'} — {note}")
        if left is None:
            # A refusal returns no usage header, so the balance is read from the free
            # /v4/sports endpoint instead. This matters: the point of a 10-credit probe is
            # to spend little, and the run should be able to show that it did.
            try:
                _, h = S._odds_get("/sports", {})
                left = _remaining(h)
            except RuntimeError:
                left = None
        if left is not None:
            print(f"credits remaining: {left}")
        if not ok:
            print("the free tier does not serve historical odds. A 401 is refused at auth, "
                  "before billing, so this cost nothing. The 20K plan at $30/mo is the "
                  "cheapest that serves it.")
        return 0 if ok else 1

    if a.pull <= 0:
        print("nothing to do: pass --probe or --pull N")
        return 0

    events, left = historical_events(listing_at)
    print(f"{len(events)} NBA events in the {a.date} snapshot" +
          (f" | credits remaining {left}" if left is not None else ""))
    if not events:
        print("no events in that snapshot — try another date")
        return 1

    events = sorted(events, key=lambda e: str(e.get("commence_time")))[:a.pull]
    os.makedirs(OUT, exist_ok=True)
    kept, index = 0, []
    for e in events:
        if left is not None and left - 20 < RESERVE:
            print(f"stopping at {kept} games: {left} credits left and the reserve is "
                  f"{RESERVE}")
            break
        try:
            tip = datetime.fromisoformat(str(e["commence_time"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            print(f"  skipped {e.get('id')}: unreadable commence_time")
            continue
        try:
            blob, left = event_odds(e["id"], tip - timedelta(minutes=LEAD_MINUTES))
        except RuntimeError as err:
            print(f"  {e.get('away_team')} @ {e.get('home_team')}: {err}")
            continue
        path = os.path.join(OUT, f"{a.date}_{e['id']}.json")
        _write(path, blob)
        s = summarise(blob)
        index.append(dict(s, id=e["id"], file=os.path.basename(path)))
        kept += 1
        print(f"  {s['away']} @ {s['home']}  tip {s['commence']}  snap {s['snapshot']}  "
              f"books {len(s['bookmakers'])}  "
              + "  ".join(f"{k}={v}" for k, v in s["outcomes"].items())
              + (f"  | credits {left}" if left is not None else ""))
    if index:
        _write(os.path.join(OUT, f"index_{a.date}.json"),
               dict(date=a.date, lead_minutes=LEAD_MINUTES, region=REGION,
                    markets=list(MARKETS), games=index))
    print(f"\n{kept} game(s) written to data/nba_probe/")
    return 0


def _write(path, blob):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


if __name__ == "__main__":
    sys.exit(main())
