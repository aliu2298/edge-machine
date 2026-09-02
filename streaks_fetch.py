#!/usr/bin/env python3
"""streaks_fetch.py — pull recent + upcoming fixtures from ESPN into data/streaks_raw.json.

WHY ESPN AND NOT API-FOOTBALL
-----------------------------
API-Football's free plan hard-blocks the current season: the /leagues endpoint happily
LISTS 2026, but /fixtures answers "Free plans do not have access to this season, try from
2022 to 2024." Streaks are a statement about CURRENT form, so 2-4 year old data is worthless
here. ESPN's scoreboard is keyless, has today's results, supports date ranges, and is
already this repo's settlement source — one call per league covers both finished and
scheduled fixtures.

Fetch is separated from analysis (streaks_build.py) on purpose: the network is the slow,
flaky part, so a cached raw pull can be re-analysed many times without re-hitting ESPN.

Usage:  python3 streaks_fetch.py [--force]
"""
import json, os, sys, time, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "streaks_raw.json")

HOST = "https://site.web.api.espn.com"
# site.api.espn.com began 403-ing every request on 2026-08-08 (this machine AND the
# GitHub runner, any user-agent) — a server-side block. site.web.api still answers.
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")}

# ESPN slug -> display name. Slugs verified against live feeds (ksa.1 = Saudi Pro League).
LEAGUES = {
    "eng.1": "Premier League", "esp.1": "La Liga", "ger.1": "Bundesliga",
    "ita.1": "Serie A", "fra.1": "Ligue 1", "ned.1": "Eredivisie",
    "por.1": "Primeira Liga", "sco.1": "Scottish Premiership",
    "usa.1": "MLS", "ksa.1": "Saudi Pro League",
    "uefa.champions": "Champions League", "uefa.europa": "Europa League",
}

# FORM-ONLY feeds. These fill the gap for sides that have barely started their league
# season — a promoted team or a second-tier club drawn into a cup tie could show up with
# one game played, or none, and render blank. Preseason friendlies give them a form line.
#
# They are FORM ONLY, never a source of leads, and they are excluded from the population
# baselines: friendlies are higher-scoring and less serious than competitive fixtures, so
# letting them into the baseline would quietly shift the very yardstick the leads are
# judged against. Games from these feeds are flagged `competitive: False` and rendered
# differently, because a run resting on preseason is weaker evidence than a league run.
FORM_ONLY_LEAGUES = {
    "club.friendly": "Club Friendly",
    "uefa.super_cup": "UEFA Super Cup",
    "ger.super_cup": "German Supercup",
}

# Form history. 180 days comfortably covers a mid-season domestic run AND bridges the
# European summer gap, so early-season sides still have a usable sample.
HISTORY_DAYS = 180
# Upcoming window. Long enough to catch the next round in every competition.
HORIZON_DAYS = 14
CACHE_TTL_H = 6          # re-fetch at most this often unless --force


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as f:
                return json.load(f)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return {}


def parse_event(ev, league_slug, league_name, competitive=True):
    """One ESPN event -> a flat row, or None if it isn't usable.

    Only FULL_TIME games carry scores worth trusting; scheduled ones are kept without
    scores so we know who plays whom next. Anything mid-flight or postponed is dropped
    rather than guessed at.
    """
    try:
        comp = ev["competitions"][0]
        status = comp["status"]["type"]["name"]
        sides = comp["competitors"]
        home = next(c for c in sides if c["homeAway"] == "home")
        away = next(c for c in sides if c["homeAway"] == "away")
    except (KeyError, IndexError, StopIteration):
        return None

    if status == "STATUS_FULL_TIME":
        try:
            hs, as_ = int(home["score"]), int(away["score"])
        except (KeyError, TypeError, ValueError):
            return None
        played = True
    elif status == "STATUS_SCHEDULED":
        hs = as_ = None
        played = False
    else:
        return None      # in-progress, postponed, cancelled — not a fact yet

    return {
        "date": (ev.get("date") or "")[:10],
        "kickoff": ev.get("date"),
        "league": league_name,
        "league_slug": league_slug,
        "home": home["team"]["displayName"],
        "away": away["team"]["displayName"],
        "home_id": home["team"].get("id"),
        "away_id": away["team"].get("id"),
        "home_goals": hs,
        "away_goals": as_,
        "played": played,
        "competitive": competitive,
    }


def fetch():
    # UTC: ESPN stamps fixtures in UTC, and CI runs there too
    today = datetime.datetime.now(datetime.timezone.utc).date()
    start = (today - datetime.timedelta(days=HISTORY_DAYS)).strftime("%Y%m%d")
    end = (today + datetime.timedelta(days=HORIZON_DAYS)).strftime("%Y%m%d")

    rows, per_league = [], {}
    feeds = ([(s, n_, True) for s, n_ in LEAGUES.items()] +
             [(s, n_, False) for s, n_ in FORM_ONLY_LEAGUES.items()])
    for n, (slug, name, competitive) in enumerate(feeds):
        if n:
            time.sleep(0.4)            # be polite; ESPN has no documented limit
        url = (f"{HOST}/apis/site/v2/sports/soccer/{slug}/scoreboard"
               f"?dates={start}-{end}&limit=1000")
        try:
            data = get(url)
        except Exception as e:
            print(f"  {name}: FETCH FAILED ({e}) — skipped")
            per_league[name] = 0
            continue
        got = [r for r in (parse_event(e, slug, name, competitive)
                           for e in data.get("events", [])) if r]
        rows += got
        played = sum(1 for r in got if r["played"])
        per_league[name] = len(got)
        tag = "" if competitive else "  [form only]"
        print(f"  {name:18s} {len(got):4d} fixtures "
              f"({played} played, {len(got)-played} upcoming){tag}")

    # A club can appear in two feeds for the same match (a friendly relisted, a super cup
    # also carried elsewhere). Duplicates would double-count games and inflate every run,
    # so collapse on the fixture identity, preferring the COMPETITIVE copy.
    seen = {}
    for r in rows:
        k = (r["date"], r["home"], r["away"])
        if k not in seen or (r["competitive"] and not seen[k]["competitive"]):
            seen[k] = r
    if len(seen) != len(rows):
        print(f"  (collapsed {len(rows) - len(seen)} duplicate fixtures across feeds)")
    rows = list(seen.values())

    blob = {
        "fetched_at": datetime.datetime.now(datetime.timezone.utc)
                      .isoformat(timespec="seconds"),
        "window": {"from": start, "to": end},
        "per_league": per_league,
        "count": len(rows),
        "fixtures": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(blob, f, indent=1)
    print(f"wrote {OUT} ({len(rows)} fixtures, {os.path.getsize(OUT)/1024:.0f} KB)")
    return blob


def load_or_fetch(force=False):
    """Cached read. The build step calls this so a re-render doesn't re-hit the network."""
    if not force and os.path.exists(OUT):
        try:
            blob = json.load(open(OUT))
            age_h = (datetime.datetime.now(datetime.timezone.utc) -
                     datetime.datetime.fromisoformat(blob["fetched_at"])).total_seconds() / 3600
            if age_h < CACHE_TTL_H:
                print(f"  (streaks raw from cache: {blob['count']} fixtures, {age_h:.1f}h old)")
                return blob
        except Exception:
            pass
    return fetch()


if __name__ == "__main__":
    fetch() if "--force" in sys.argv else load_or_fetch()
