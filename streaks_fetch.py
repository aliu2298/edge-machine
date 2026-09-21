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

# COMPETITIVE form feeds — real league football, but not a source of leads.
#
# The Champions and Europa Leagues drag in opponents from leagues we do not track, and
# those sides arrived with NO form at all: 21 teams in upcoming fixtures had zero games
# (Anderlecht, Dinamo Zagreb, AEK Athens, Sturm Graz, Bodo/Glimt...). find_leads skips a
# fixture when either side lacks form, so 48 of 273 upcoming fixtures could never produce
# a lead — silently, since a missing lead looks exactly like "no confluence today".
#
# These differ from FORM_ONLY_LEAGUES above in the way that matters: a Belgian league
# match is COMPETITIVE, so it counts as real form and belongs in the baselines. What it
# is not is a fixture this board has an opinion about — the tracked league list is
# deliberate, and quietly turning seven more leagues into lead sources would change the
# product rather than fix the gap. Hence `lead_source: False`.
#
# Only slugs ESPN actually serves are listed. Czech, Polish, Croatian, Ukrainian,
# Israeli, Bulgarian, Slovenian, Slovak, Azerbaijani and Armenian top flights were all
# probed and either 400 or return zero events, so a handful of European ties still have
# a one-sided form line. That is a data limit, not an oversight — see verify_coverage.py,
# which reports it rather than letting it pass as silence.
FORM_LEAGUES = {
    "bel.1": "Belgian Pro League", "nor.1": "Eliteserien", "gre.1": "Greek Super League",
    "aut.1": "Austrian Bundesliga", "den.1": "Danish Superliga",
    "cyp.1": "Cypriot First Division", "tur.1": "Turkish Super Lig",
}

# Form history. 180 days comfortably covers a mid-season domestic run AND bridges the
# European summer gap, so early-season sides still have a usable sample.
# CUPS and INTERNATIONALS (2026-09-19) — for the Sandbox's cup and international form-rule
# pairs, never for a lead or a Production pair. Cup ties are counted as competitive form for
# the clubs in them; the lower tiers are there so a cup opponent from League Two or the
# 2. Bundesliga has a form line at all. National teams count every international, friendlies
# included (without them only 29 of the 54 Nations League sides had 10 games in a year), over
# a two-year window. Extra-time and penalty games (STATUS_FINAL_AET / _PEN) are never parsed,
# so form is only ever counted from games decided in 90 minutes — how Kalshi settles.
CUP_LEAGUES = {
    "uefa.europa.conf": "UEFA Conference League", "eng.league_cup": "EFL Cup",
    "eng.fa": "FA Cup", "ger.dfb_pokal": "DFB Pokal", "ita.coppa_italia": "Coppa Italia",
    "por.taca.portugal": "Taça de Portugal", "ned.cup": "KNVB Cup", "sco.tennents": "Scottish Cup",
    "usa.open": "US Open Cup", "concacaf.leagues.cup": "Leagues Cup",
    "conmebol.libertadores": "Copa Libertadores", "conmebol.sudamericana": "Copa Sudamericana",
    "afc.champions": "AFC Champions League",
    # 2026-09-21. Copa del Rey's first round is the week of 2026-09-26. ESPN lists the Coupe
    # de France only once the professional clubs enter (mid-November); verified on 24 ties in
    # Jan-Feb 2026, so it is empty now and fills itself when those rounds arrive.
    "esp.copa_del_rey": "Copa del Rey", "fra.coupe_de_france": "Coupe de France",
}
CUP_FORM_LEAGUES = {
    "eng.2": "EFL Championship", "eng.3": "EFL League One", "eng.4": "EFL League Two",
    "ger.2": "2. Bundesliga", "ita.2": "Serie B", "esp.2": "LaLiga 2", "fra.2": "Ligue 2",
    "ned.2": "Eerste Divisie", "sco.2": "Scottish Championship", "bra.1": "Brasileirão",
    "arg.1": "Liga Profesional", "jpn.1": "J1 League", "mex.1": "Liga MX",
}
INTL_LEAGUES = {
    "uefa.nations": "UEFA Nations League", "fifa.friendly": "International Friendly",
    "fifa.worldq.uefa": "World Cup Qualifying (UEFA)", "fifa.worldq.conmebol": "World Cup Qualifying (CONMEBOL)",
    "fifa.worldq.concacaf": "World Cup Qualifying (Concacaf)", "fifa.worldq.caf": "World Cup Qualifying (CAF)",
    "fifa.worldq.afc": "World Cup Qualifying (AFC)", "fifa.world": "FIFA World Cup",
    "uefa.euro": "UEFA European Championship", "concacaf.nations.league": "Concacaf Nations League",
}
INTL_HISTORY_DAYS = 730

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
            if i == tries - 1 or (isinstance(e, urllib.error.HTTPError) and e.code == 400):
                raise
            time.sleep(1.5 * (i + 1))
    return {}


def parse_event(ev, league_slug, league_name, competitive=True, lead_source=True):
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

    def corners(c):
        for st in c.get("statistics") or []:
            if st.get("name") == "wonCorners":
                try:
                    return int(float(st.get("displayValue")))
                except (TypeError, ValueError):
                    return None
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
        # Corners won (ESPN wonCorners), for the Sandbox's corners rule. None when not reported.
        "home_corners": corners(home) if played else None,
        "away_corners": corners(away) if played else None,
        "played": played,
        "competitive": competitive,
        # Whether this board may form an opinion ABOUT this fixture. Form feeds are real
        # football (competitive=True) but carry no leads of their own.
        "lead_source": lead_source,
    }


MONTH_CAP = 100      # a month query returns at most this many events (dates=2026 gave exactly 100)


def fetch_range(slug, first, last):
    """Every event for `slug` between two dates, a MONTH at a time (dates=YYYYMM).

    Since 2026-09-15 ESPN answers 400 ("Failed to get events endpoint") to nearly every
    dates=START-END range, so one 194-day query per league came back empty and the board
    published 0 leads. Month and single-day queries still work. A month that hits the result
    cap is re-read day by day, so a busy month is never silently truncated."""
    events, seen = [], set()

    def take(data, keep_all=False):
        for ev in data.get("events", []):
            day = (ev.get("date") or "")[:10]
            if ev.get("id") in seen or not (first.isoformat() <= day <= last.isoformat()):
                continue
            seen.add(ev.get("id"))
            events.append(ev)

    base = f"{HOST}/apis/site/v2/sports/soccer/{slug}/scoreboard?dates="
    month = first.replace(day=1)
    cache = _load_history(slug)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    while month <= last:
        key = month.strftime("%Y%m")
        nxt = (month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        # A month that ended more than HISTORY_SETTLE_DAYS ago cannot change: read it from
        # the committed cache instead of ESPN, so two years of internationals cost nothing
        # after the first run.
        closed = nxt <= today - datetime.timedelta(days=HISTORY_SETTLE_DAYS)
        if closed and key in cache:
            take({"events": cache[key]}, keep_all=True)
            month = nxt
            continue
        n_before = len(events)
        data = get(base + key)
        if len(data.get("events", [])) >= MONTH_CAP:
            day = max(first, month)
            nxt = (month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
            while day < nxt and day <= last:
                take(get(base + day.strftime("%Y%m%d")))
                day += datetime.timedelta(days=1)
                time.sleep(0.1)
        else:
            take(data)
        if closed:
            cache[key] = [_trim(e) for e in events[n_before:]]
            _save_history(slug, cache)
        month = nxt
        time.sleep(0.2)
    return events


HISTORY_DIR = os.path.join(ROOT, "data", "espn_history")
HISTORY_SETTLE_DAYS = 7


def _trim(ev):
    """Only what parse_event reads — a month of ESPN events is ~1 MB untrimmed."""
    comp = (ev.get("competitions") or [{}])[0]
    return {"id": ev.get("id"), "date": ev.get("date"),
            "competitions": [{"status": {"type": {"name": ((comp.get("status") or {}).get("type") or {}).get("name")}},
                              "competitors": [{"homeAway": c.get("homeAway"), "score": c.get("score"),
                                               "team": {"displayName": (c.get("team") or {}).get("displayName"),
                                                        "id": (c.get("team") or {}).get("id")},
                                               "statistics": [x for x in c.get("statistics") or []
                                                              if x.get("name") == "wonCorners"]}
                                              for c in comp.get("competitors") or []]}]}


HISTORY_VERSION = 2     # 2: trimmed events keep wonCorners (the corners rule, 2026-09-19)


def _load_history(slug):
    try:
        with open(os.path.join(HISTORY_DIR, f"{slug}.json")) as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return {}
    # A cache written by an older trim lacks fields a newer parse needs: re-read it once.
    return blob if blob.get("_v") == HISTORY_VERSION else {}


def _save_history(slug, cache):
    cache["_v"] = HISTORY_VERSION
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(os.path.join(HISTORY_DIR, f"{slug}.json"), "w") as f:
        json.dump(cache, f, separators=(",", ":"), sort_keys=True)


def fetch():
    # UTC: ESPN stamps fixtures in UTC, and CI runs there too
    today = datetime.datetime.now(datetime.timezone.utc).date()
    start = (today - datetime.timedelta(days=HISTORY_DAYS)).strftime("%Y%m%d")
    end = (today + datetime.timedelta(days=HORIZON_DAYS)).strftime("%Y%m%d")

    rows, per_league = [], {}
    feeds = ([(s, n_, True, True, HISTORY_DAYS, "league") for s, n_ in LEAGUES.items()] +
             [(s, n_, True, False, HISTORY_DAYS, "league") for s, n_ in FORM_LEAGUES.items()] +
             [(s, n_, False, False, HISTORY_DAYS, "league") for s, n_ in FORM_ONLY_LEAGUES.items()] +
             [(s, n_, True, False, HISTORY_DAYS, "cup") for s, n_ in CUP_LEAGUES.items()] +
             [(s, n_, True, False, HISTORY_DAYS, "league") for s, n_ in CUP_FORM_LEAGUES.items()] +
             [(s, n_, True, False, INTL_HISTORY_DAYS, "intl") for s, n_ in INTL_LEAGUES.items()])
    for n, (slug, name, competitive, lead_source, days, comp) in enumerate(feeds):
        if n:
            time.sleep(0.4)            # be polite; ESPN has no documented limit
        try:
            events = fetch_range(slug, today - datetime.timedelta(days=days),
                                 today + datetime.timedelta(days=HORIZON_DAYS))
        except Exception as e:
            print(f"  {name}: FETCH FAILED ({e}) — skipped")
            per_league[name] = 0
            continue
        got = [dict(r, comp=comp) for r in (parse_event(e, slug, name, competitive, lead_source)
                                            for e in events) if r]
        rows += got
        played = sum(1 for r in got if r["played"])
        per_league[name] = len(got)
        tag = ("" if lead_source else
               ("  [form only]" if competitive else "  [form only, non-competitive]"))
        print(f"  {name:18s} {len(got):4d} fixtures "
              f"({played} played, {len(got)-played} upcoming){tag}")

    # A club can appear in two feeds for the same match (a friendly relisted, a super cup
    # also carried elsewhere). Duplicates would double-count games and inflate every run,
    # so collapse on the fixture identity, preferring the COMPETITIVE copy.
    seen = {}
    for r in rows:
        k = (r["date"], r["home"], r["away"])
        if k not in seen or (r["lead_source"] and not seen[k].get("lead_source", True)) \
                or (r["competitive"] and not seen[k]["competitive"]):
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
