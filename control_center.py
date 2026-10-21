#!/usr/bin/env python3
"""control_center.py — the site root as a Research Control Center (redesign, phase 2).

The home page answers four questions in order: what is live (the tiles), how each
area is doing (one card per area), what needs a person (the attention list), and
what is running right now (the Running list and its rule cards, kept from the old
shell). Everything on it is read from the tracker's own state: the Sandbox ledger,
the stage file, the Production feed, the NBA pace board, the trading ledger, the
closing-price writers' files and, at build time, the last completed workflow runs.
Nothing is invented; a signal that cannot be read says so.

AREA STATUS, in this order of precedence:
  Waiting    the area has never been read: no stamp anywhere.
  Stale      no successful read inside the area's expected interval (EXPECTED). The
             tracker lanes (soccer, cricket, tennis) run every 3h and are stale past
             7h, the same bar page_freshness fails the pages on. Crypto reads once a
             day inside its close window: 30h. Commodities reads on trading days only,
             so its 30h are counted on trading days (weekends and US exchange holidays
             do not count). NBA is a daily board: 36h. Trading is scanned on weekdays:
             36h counted on weekdays.
  Attention  an item in the attention list names the area.
  Healthy    none of the above.

A "successful read" is the tracker run on which the lane's venue listing or any of
its rules reported rows (sandbox_track.lane_read_signal), stamped per sport into the
ledger's meta.lane_reads by the tracker. Before that stamp exists for a lane, the last
run's coverage decides, and failing that the newest row the lane ever logged.

THE STATUS FILE. data/status.json is the tracker's own statement of its run
(sandbox_track.build_status): per lane the last successful read, the open bets past
their allowed window, and the feeds it could not read. When the file describes the
ledger this page renders (its ledger_updated is the ledger's meta.updated), the page
reads those three from it: an area's last read includes its lanes' last_read, the
broken feeds are the file's, and the overdue bets are the file's, each aged to the
build's clock, plus any bet that crossed its window after the file was written. A
missing file, or one from another run, falls back to the ledger, and an out-of-date
file is itself an attention item.
"""
import datetime
import json
import os
import urllib.request
from datetime import timedelta, timezone

import fmt
import production
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import shell_build
import site_chrome
import sport_page as SP

ROOT = os.path.dirname(os.path.abspath(__file__))
NBA_PATH = os.path.join(ROOT, "data", "nba_pace.json")
STATUS_PATH = T.STATUS
MARKET_PATH = os.path.join(ROOT, "data", "market_ledger.json")
CLOSES_DIR = T.CLOSES_DIR
REPO = "aliu2298/edge-machine"
RUNS_URL = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=40&status=completed"
RUNS_TIMEOUT = 8

AREAS = (
    ("soccer", "Soccer", "./soccer.html"),
    ("cricket", "Cricket", "./cricket.html"),
    ("tennis", "Tennis", "./tennis.html"),
    ("crypto", "Crypto", "./crypto.html"),
    ("commodities", "Commodities", "./commodities.html"),
    ("nba", "NBA", "./nba.html"),
    ("trading", "Trading", "./trading.html"),
)
AREA_HREF = {key: href for key, _label, href in AREAS}
AREA_LABEL = {key: label for key, label, _href in AREAS}
# sandbox_build.family -> area key, for the lanes the Sandbox ledger carries.
FAMILY_AREA = {"Soccer": "soccer", "Cricket": "cricket", "Tennis": "tennis",
               "Crypto": "crypto", "Commodities": "commodities"}
# (hours, calendar). The calendar says which hours count toward the interval.
EXPECTED = {
    "soccer": (7, "always"),
    "cricket": (7, "always"),
    "tennis": (7, "always"),
    "crypto": (30, "always"),
    "commodities": (30, "trading_days"),
    "nba": (36, "always"),
    "trading": (36, "weekdays"),
    # Econ and Finance Daily scan on their own workflow (daily-research.yml). Listed here since
    # 2026-10-15: a stale Daily card looked its hours up in this table, found nothing, and the
    # KeyError took the whole page build down (Sandbox Tracker runs 11:09Z and 15:00Z).
    "econ_daily": (3, "always"),
    "finance_daily": (3, "always"),
}
# Closing-price writers and how often each is expected to write (hours). The VPS
# snapshots every 15 minutes, the watchdog hourly, the close job every 30 minutes,
# the boards refresh every 3 hours. A writer not named here is read on the default.
VENUE_WRITERS = {"vps": 2, "watchdog": 3, "close": 2, "boards": 7}
DEFAULT_WRITER_HOURS = 48
# A writer only rewrites its file when it snapshotted or pruned something (sandbox_close.main),
# so a quiet file is normal whenever no bet came due: overnight, or on a Sunday with nothing
# closing. A writer past its interval is listed only when a bet's deadline passed since its
# last write and the bet has no closing price from ANY writer (2026-10-19: "close" read "5h ago"
# on a Sunday night with nothing due while vps.json was 15 minutes old).
# Writers that no longer run are not watched at all. Their files stay: the tracker merges every
# file in data/sandbox_closes/, and their snapshots are already on the ledger's bets (close_at).
RETIRED_WRITERS = {
    # The Mac's launchd agent (scripts/com.aliu.edge-machine-closes.plist) is not loaded; edge-vps
    # runs the same local_closes.sh as writer "vps" since 2026-10-06. Last write 2026-10-06.
    "mac": "replaced by vps on 2026-10-06",
}
CLOSE_LEAD = timedelta(minutes=60)   # sandbox_close.CLOSE_WINDOW_MIN: a snapshot this close counts
# A Production pair this close to the stale-pair demotion is named.
NEAR_DEMOTION_DAYS = 7
LATE_LEAD_HOURS = 48          # a lead published too late to act on is listed this long after its kickoff
NEXT_HOURS = 24


def window_days():
    """The settled window, shell_build.SHELL_SETTLED_DAYS, read at call time."""
    return int(shell_build.SHELL_SETTLED_DAYS)
WORKFLOWS = ("Sandbox Tracker", "Refresh boards")
STATUS_LABEL = {"healthy": "Healthy", "stale": "Stale", "attention": "Attention", "waiting": "Waiting"}
STATUS_CHIP = {"healthy": "y", "stale": "w", "attention": "x", "waiting": "n"}
KIND_LABEL = {"overdue": "Open past start", "feed": "Feed", "paused": "Production pair",
              "quiet": "Production pair", "route": "Not tradeable", "late": "Published late",
              "run": "Workflow",
              "venue": "Closing prices"}
SECTIONS = (("overview", "Overview"), ("areas", "Areas"), ("attention", "Attention"),
            ("live", "Live now"), ("scorecard", "Rules"))
# The Rule scorecard's chips: (value, label). "records" is any settled result,
# "read" is the read floor (sport_page.EVIDENCE_FLOOR, 30) or over.
SCORECARD_FILTERS = (("all", "All"), ("production", "Production"), ("records", "With records"),
                     ("read", f"{SP.EVIDENCE_FLOOR}+"))

esc = site_chrome.esc


# ------------------------------------------------------------------ time helpers
def _utc(value):
    """A UTC datetime from an ISO string or a datetime, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        dt = value
    else:
        try:
            dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _counts(instant, calendar):
    """Does this hour count toward an interval on `calendar`?"""
    if calendar == "weekdays":
        return instant.weekday() < 5
    if calendar == "trading_days":
        return S.commod_fav_trading_day(instant.astimezone(S.COMMOD_FAV_TZ).date())
    return True


def deadline(last, hours, calendar="always"):
    """The instant a read made at `last` goes stale: `hours` counted on `calendar`.

    Hours on days the calendar excludes do not count, so a commodities read on a
    Thursday evening is not stale on Sunday. Walks hour by hour; the intervals here
    are a day or two, so the walk is short. A calendar that excludes every day
    for a long stretch is capped at 60 days.
    """
    at = last
    counted = 0.0
    steps = 0
    while counted < hours and steps < 24 * 60:
        at = at + timedelta(hours=1)
        steps += 1
        if _counts(at, calendar):
            counted += 1
    return at


def _hours(a, b):
    return (b - a).total_seconds() / 3600.0


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def closes_updated(directory=None):
    """{writer: updated} for every closing-price writer file on disk."""
    directory = directory or CLOSES_DIR
    out = {}
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        blob = _read_json(os.path.join(directory, name))
        if isinstance(blob, dict) and blob.get("updated"):
            out[name[:-5]] = str(blob["updated"])
    return out


def fetch_runs(opener=None, timeout=RUNS_TIMEOUT):
    """The last completed workflow runs on main, newest first, or None when unreadable.

    Public repository, public endpoint, no token. Each entry: name, conclusion, url,
    at. A failure to read is None, which the model reports as "not read", never as
    a passing or failing run.
    """
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(RUNS_URL, headers={"Accept": "application/vnd.github+json",
                                                    "User-Agent": "edge-machine-control-center"})
    try:
        with opener(req, timeout=timeout) as resp:
            blob = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    runs = []
    for run in (blob or {}).get("workflow_runs") or []:
        if not isinstance(run, dict) or run.get("head_branch") not in (None, "main"):
            continue
        runs.append({"name": str(run.get("name") or ""), "conclusion": str(run.get("conclusion") or ""),
                     "url": str(run.get("html_url") or ""), "at": str(run.get("updated_at") or "")})
    return runs


def inputs(runs=False, opener=None):
    """Everything the model reads beside the ledger, the stages and the feed."""
    return dict(nba=_read_json(NBA_PATH), market=_read_json(MARKET_PATH),
                closes=closes_updated(), runs=fetch_runs(opener) if runs else None,
                status=_read_json(STATUS_PATH), daily=_read_json(os.path.join(ROOT, 'data', 'daily_ledger.json')),
                culture=_read_json(os.path.join(ROOT, 'data', 'culture_ledger.json')))


def current_status(status, d):
    """(status, note): the status file when it describes this ledger, else (None, why).

    `why` is None when there is no file at all (a fixture build reads none), and a
    sentence when a file exists but cannot be used: it is then an attention item.
    """
    if status is None:
        return None, None
    if not isinstance(status, dict) or not isinstance(status.get("lanes"), dict):
        return None, "data/status.json could not be read; the Control Center read the ledger instead"
    ledger_at = ((d or {}).get("meta") or {}).get("updated")
    if not ledger_at or status.get("ledger_updated") != ledger_at:
        return None, (f"data/status.json describes the run of {status.get('ledger_updated') or 'an unknown time'}, "
                      f"not the ledger's {ledger_at or 'unstamped'} run; the Control Center read the ledger instead")
    return status, None


# ------------------------------------------------------------------ the model
def _bet_rows(d):
    return [q for q in T.bet_rows(d)
            if q.get("bet") and not S.removed_row(q) and not S.tennis_refused_row(q)]


def _in_window(start, now):
    return start is not None and now - timedelta(days=window_days()) <= start <= now


def _coverage_signal(cell):
    """True when the last run's coverage cell says the lane was read: a venue listing
    or a rule that saw rows, even when nothing qualified."""
    if not isinstance(cell, dict):
        return False
    for key, value in cell.items():
        if isinstance(value, dict):
            if (value.get("offered") or 0) > 0:
                return True
        elif key in ("kalshi_venue", "polymarket_us", "polymarket_us_listed", "polymarket_us_priced"):
            if (value or 0) > 0:
                return True
    return False


def _lane_last_read(sports, d, rows, now):
    """The newest successful read across `sports`, as a UTC datetime, or None."""
    meta = d.get("meta") or {}
    stamps = meta.get("lane_reads") or {}
    cov = d.get("coverage") or {}
    found = [_utc(stamps.get(sp)) for sp in sports if stamps.get(sp)]
    tracker_at = _utc(meta.get("updated"))
    if tracker_at is not None and any(_coverage_signal(cov.get(sp)) for sp in sports):
        found.append(tracker_at)
    found.append(max((_utc(q.get("logged")) for q in rows if _utc(q.get("logged"))), default=None))
    found = [f for f in found if f is not None]
    return max(found) if found else None


def _status_last_read(sports, status):
    """The newest lane last_read in the status file across `sports`, or None."""
    if not status:
        return None
    found = [_utc(lane.get("last_read")) for lane in (status.get("lanes") or {}).values()
             if isinstance(lane, dict) and lane.get("sport") in sports and lane.get("last_read")]
    found = [f for f in found if f is not None]
    return max(found) if found else None


def _lane_area(key, label, rows, pair_rows, d, now, status=None):
    sports = [sp for sp in S.SPORTS if B.family(sp) == label]
    mine = [q for q in rows if q.get("sport") in sports]
    starts = {id(q): production._kickoff(q) for q in mine}
    open_n = sum(1 for q in mine if q.get("status") == "open")
    settled = sum(1 for q in mine if q.get("status") in ("won", "lost", "settled")
                  and _in_window(starts[id(q)], now))
    next24 = sum(1 for q in mine if q.get("status") == "open" and starts[id(q)] is not None
                 and now < starts[id(q)] <= now + timedelta(hours=NEXT_HOURS))
    if key == "crypto":
        coverage = f"{len(S.COINS)} coins checked"
    elif key == "commodities":
        coverage = f"{len(S.COMMOD_FAV_SERIES)} series checked"
    else:
        lanes = [r for r in pair_rows if B.family(r["sport"]) == label]
        n_prod = sum(1 for r in lanes if r.get("prod"))
        coverage = f"{len(lanes)} rule{'s' if len(lanes) != 1 else ''} · {n_prod} in Production"
    reads = [r for r in (_lane_last_read(sports, d, mine, now), _status_last_read(sports, status))
             if r is not None]
    return dict(key=key, label=label, href=AREA_HREF[key], open=open_n, settled=settled,
                next24=next24, coverage=coverage, last_read=max(reads) if reads else None)


def _nba_area(nba, now):
    games = [g for g in ((nba or {}).get("games") or []) if isinstance(g, dict)]
    starts = {id(g): _utc(g.get("start")) for g in games}
    in_play = sum(1 for g in games if not g.get("completed") and starts[id(g)] is not None
                  and starts[id(g)] <= now)
    settled = sum(1 for g in games if g.get("completed") and _in_window(starts[id(g)], now))
    next24 = sum(1 for g in games if not g.get("completed") and starts[id(g)] is not None
                 and now < starts[id(g)] <= now + timedelta(hours=NEXT_HOURS))
    teams = (nba or {}).get("teams") or {}
    coverage = (f"{len(games)} game{'s' if len(games) != 1 else ''} · {len(teams)} teams"
                if games or teams else "no board read")
    return dict(key="nba", label="NBA", href=AREA_HREF["nba"], open=in_play, settled=settled,
                next24=next24, coverage=coverage, last_read=_utc((nba or {}).get("built")))


def _trading_area(market, now):
    trades = [t for t in ((market or {}).get("trades") or []) if isinstance(t, dict)]
    open_n = sum(1 for t in trades if t.get("status") == "open")
    cut = (now - timedelta(days=window_days())).date().isoformat()
    settled = sum(1 for t in trades if t.get("status") == "closed" and str(t.get("exit_day") or "") >= cut)
    rules = (market or {}).get("research") or {}
    coverage = (f"{len(rules)} rule{'s' if len(rules) != 1 else ''} under test" if rules else "no ledger read")
    return dict(key="trading", label="Trading", href=AREA_HREF["trading"], open=open_n, settled=settled,
                next24=None, coverage=coverage, last_read=_utc(((market or {}).get("meta") or {}).get("updated")))


def _status(area, now, flagged):
    last = area["last_read"]
    if last is None:
        return "waiting"
    hours, calendar = EXPECTED[area["key"]]
    if deadline(last, hours, calendar) < now:
        return "stale"
    if flagged:
        return "attention"
    return "healthy"


def _contest(q):
    """The bet's contest as the pages spell it: 'A vs B', never a bare 'A v B'."""
    if q.get("label"):
        return fmt.contest(q["label"])
    if q.get("side_a") and q.get("side_b"):
        return fmt.contest(f"{q['side_a']} v {q['side_b']}")
    return str(q.get("market_id") or q.get("id") or "a bet")


def _area_of_sport(sport):
    return FAMILY_AREA.get(B.family(sport))


def _overdue(d, now, status):
    """[(quote, hours past start)] for the attention list, oldest first.

    With a current status file: its overdue_open, each looked up in the ledger and
    aged to `now`, then any bet the ledger shows past its window that the file does
    not list (it crossed after the file was written). Without one: the ledger's.
    """
    live = T.overdue_bets(d, now)
    if not status:
        return live
    by_id = {q.get("id"): q for q in T.bet_rows(d) if q.get("id")}
    out, seen = [], set()
    for item in status.get("overdue_open") or []:
        if not isinstance(item, dict) or item.get("id") in seen:
            continue
        q = by_id.get(item.get("id"))
        if q is None or q.get("status") != "open":
            continue                      # settled since, or not in this ledger at all
        start = _utc(item.get("start") or q.get("start"))
        age = _hours(start, now) if start is not None else float(item.get("hours_past_start") or 0)
        seen.add(item.get("id"))
        out.append((q, age))
    out += [(q, age) for q, age in live if q.get("id") not in seen]
    out.sort(key=lambda qa: -qa[1])
    return out


def _broken_feeds(d, status):
    """[(source, label, reason)]: the status file's when it is current, else the ledger's."""
    if not status:
        return B.dark_feeds(d)
    return [(f.get("source"), f.get("label"), f.get("reason") or "")
            for f in status.get("broken_feeds") or [] if isinstance(f, dict) and f.get("source")]


def _attention(d, st, pairs, now, closes, runs, status=None, status_note=None, blob=None):
    items = []
    if status_note:
        items.append(dict(kind="status", area=None, text=status_note, href="./sandbox.html"))
    for q, age in _overdue(d, now, status):
        if S.tennis_refused_row(q):
            continue
        area = _area_of_sport(q.get("sport"))
        items.append(dict(kind="overdue", area=area,
                          text=f"{_contest(q)} is still open {int(age)}h past its start",
                          href=AREA_HREF.get(area, "./production.html")))
    for name, label, reason in _broken_feeds(d, status):
        sports = (S.SOURCES.get(name) or {}).get("sports") or []
        area = _area_of_sport(sports[0]) if sports else None
        items.append(dict(kind="feed", area=area,
                          text=f"{label} could not be read on the last run"
                               + (f" ({reason})" if reason else ""),
                          href="./sandbox.html"))
    for key, pair in sorted(pairs.items()):
        name, sport = key.split("|", 1)
        since = pair.get("promoted_at") or production.entered_at(pair)
        last = (T._last_logged(d, name, sport, since) if since else None) or since
        last_at = _utc(last)
        if last_at is None:
            continue
        demote_at = last_at + timedelta(days=T.STALE_DAYS)
        days_left = max(0, int(_hours(now, demote_at) // 24))
        rule = S.scoped_rule(name, sport)
        area = _area_of_sport(sport)
        when = fmt.day(demote_at)
        if S.lane_paused(name, sport):
            items.append(dict(kind="paused", area=area,
                              text=(f"{rule} is paused in PAUSED_LANES: it logs nothing"
                                    + (f" and the stale-pair net demotes it on {when} ({days_left} days)"
                                       if T.inactivity_demotes(sport) else "; Production rules must be active")),
                              href="./production.html"))
        elif T.inactivity_demotes(sport) and days_left <= NEAR_DEMOTION_DAYS:
            items.append(dict(kind="quiet", area=area,
                              text=f"{rule}: no new bet since {fmt.day(last_at)}; the stale-pair net "
                                   f"demotes it on {when} ({days_left} days)",
                              href="./production.html"))
    # Nothing in Production is observation only: a pair whose leads carry no market a
    # follower can buy, or whose bets in the window were all held back, is listed with the
    # feed's own reason (production.routing_problem).
    # A lead first published inside production.LATE_MIN of its kickoff could not be acted
    # on: the follower skips anything that close. Listed while its kickoff is recent.
    for lead in sorted(((blob or {}).get("leads") or {}).values(), key=lambda l: str(l.get("kickoff"))):
        ko = _utc(lead.get("kickoff"))
        if not production.late_issue_active(lead) or ko is None or ko < now - timedelta(hours=LATE_LEAD_HOURS):
            continue
        name, sport = str(lead.get("pair") or "|").split("|", 1)
        items.append(dict(kind="late", area=_area_of_sport(sport),
                          text=(f"{lead.get('match')} · {lead.get('headline')} ({S.scoped_rule(name, sport)}) "
                                f"was published {lead.get('published_min_before_kickoff')} min before kickoff "
                                f"— too close to kickoff to act on"),
                          href="./production.html"))
    feed_pairs = (blob or {}).get("pairs") or {}
    for key in sorted(pairs):
        problem = ((feed_pairs.get(key) or {}).get("routing") or {}).get("problem")
        if not problem:
            continue
        name, sport = key.split("|", 1)
        items.append(dict(kind="route", area=_area_of_sport(sport),
                          text=f"{S.scoped_rule(name, sport)} cannot be followed: {problem}",
                          href="./production.html"))
    if runs:
        seen = set()
        for run in runs:
            name = run.get("name")
            if name not in WORKFLOWS or name in seen:
                continue
            seen.add(name)
            if run.get("conclusion") != "success":
                at = _utc(run.get("at"))
                items.append(dict(kind="run", area=None,
                                  text=f"{name}: the last completed run {run.get('conclusion') or 'did not finish'}"
                                       + (f" ({fmt.when_relative(at, now)})" if at else ""),
                                  href=run.get("url") or "./production.html"))
    for writer, updated in sorted((closes or {}).items()):
        at = _utc(updated)
        if at is None or writer in RETIRED_WRITERS:
            continue
        allowed = VENUE_WRITERS.get(writer, DEFAULT_WRITER_HOURS)
        age = _hours(at, now)
        if age <= allowed:
            continue
        missed = missed_closes(d, at, now)
        if missed:
            items.append(dict(kind="venue", area=None,
                              text=f"closing prices from {writer} last written {_age_text(age)} ago "
                                   f"(expected within {allowed}h) · {len(missed)} bet{'s' if len(missed) != 1 else ''} "
                                   f"came due since with no closing price",
                              href="./sandbox.html"))
    return items


def missed_closes(d, since, now):
    """Bets whose close deadline fell in (since, now] with no snapshot from any writer inside
    CLOSE_LEAD of it (the tracker merges every writer's file into close_at)."""
    out = []
    for q in (d or {}).get("quotes") or []:
        if not q.get("bet") or not q.get("pick") or S.removed_row(q) or q.get("note") == T.KALSHI_UNPLACEABLE:
            continue
        dl = T.close_deadline(q)
        if dl is None or not since < dl <= now:
            continue
        got = _utc(q.get("close_at"))
        if got is not None and dl - CLOSE_LEAD <= got <= dl:
            continue
        out.append(q)
    return out


def _age_text(hours):
    if hours >= 48:
        return f"{int(hours // 24)}d"
    return f"{int(hours)}h"


def model(d, st, blob, now, nba=None, market=None, closes=None, runs=None, status=None, daily=None, culture=None):
    """The Control Center as data. Pure: everything it reads is an argument.

    `status` is data/status.json as read (inputs()); it is used only when it
    describes this ledger (current_status)."""
    now = _utc(now) or datetime.datetime.now(timezone.utc)
    status, status_note = current_status(status, d)
    rows = _bet_rows(d)
    pairs = {k: v for k, v in production.production_pairs(st).items() if not production._weather_pair(k)}
    pair_rows = [r for r in B.pair_list(d, st) if not B.eliminated(r)]
    attention = _attention(d, st, pairs, now, closes, runs, status=status, status_note=status_note,
                           blob=blob)
    flagged = {item["area"] for item in attention if item.get("area")}
    areas = []
    for key, label, _href in AREAS:
        if key == "nba":
            area = _nba_area(nba, now)
        elif key == "trading":
            area = _trading_area(market, now)
        else:
            area = _lane_area(key, label, rows, pair_rows, d, now, status=status)
        area["status"] = _status(area, now, key in flagged)
        area["items"] = [item for item in attention if item.get("area") == key]
        areas.append(area)
    if daily is not None:
        for key, label in (("econ_daily", "Econ Daily"), ("finance_daily", "Finance Daily")):
            lane = (daily.get('lanes') or {}).get(key) or {}
            picks = lane.get('picks') or []
            last = _utc(lane.get('last_success'))
            status_word = ('attention' if lane.get('error') else 'waiting' if last is None
                           else 'stale' if last < now - timedelta(hours=EXPECTED[key][0]) else 'healthy')
            daily_items = []
            if lane.get('error') or status_word == 'stale':
                item = dict(kind='feed', area=key, href='./'+key+'.html',
                            text=label+': '+(lane.get('error') or f'no successful paper scan in the last {EXPECTED[key][0]} hours'))
                attention.append(item)
                daily_items.append(item)
            areas.append(dict(key=key, label=label, href='./'+key+'.html',
                open=sum(x.get('status')=='open' for x in picks),
                settled=sum(x.get('status')!='open' and _in_window(_utc(x.get('settled')),now) for x in picks),
                next24=sum(x.get('status')=='open' and _utc(x.get('close')) is not None
                           and now < _utc(x['close']) <= now+timedelta(hours=NEXT_HOURS) for x in picks),
                coverage=f"{len(lane.get('catalog') or [])} series · "+("Production" if key=="econ_daily" else "paper only"), last_read=last,
                status=status_word, items=daily_items))
    live_d, live_st, live_blob = d, st, blob
    if daily is not None:
        import daily_production
        live_d, live_st, live_blob = daily_production.page_inputs(d, st, blob, daily, now=now)
    if culture is not None:
        import culture_production
        live_d, live_st, live_blob = culture_production.page_inputs(live_d, live_st, live_blob, culture, now=now)
    live = shell_build._running_body(live_d, live_st, live_blob, now)
    n_open, n_settled, n_won = live["roll_counts"]
    scorecard = scorecard_rows(pair_rows)
    healthy = sum(1 for a in areas if a["status"] == "healthy")
    return dict(
        now=now,
        tiles=dict(pairs=len(pairs)+(1 if daily is not None else 0)+(1 if culture is not None else 0), open=sum(1 for q in rows if q.get("status") == "open")
                   + sum(a['open'] for a in areas if a['key'] in ('econ_daily','finance_daily')),
                   landed=(n_won, n_settled), healthy=(healthy, len(areas)), attention=len(attention)),
        areas=areas, attention=attention, live=live, scorecard=scorecard,
        # Production outside the scorecard's pair rows: Econ Daily's favourite band publishes
        # through its own feed (daily_production), so it is in the tile's count and not a row.
        prod_outside=(["Econ Daily favourite band"] if daily is not None else [])
                     + (["Trump mentions"] if culture is not None else []),
        runs_read=runs is not None, status_read=status is not None,
    )


# ------------------------------------------------------------------ the rule scorecard
def _rule_href(sport):
    return AREA_HREF.get(FAMILY_AREA.get(B.family(sport)), "./sandbox.html")


def scorecard_rows(pair_rows):
    """Every rule on the pages, one entry each, in scorecard order: Production first, then
    the most evidence, then the best ROI after fees, then the name. Each entry keeps the
    Sandbox row it came from (`row`), so the badge, record and ROI are that row's own."""
    out = []
    for r in pair_rows:
        a = r.get("a") or {}
        n = int(a.get("n") or 0)
        n_price = int(a.get("n_price") or 0)
        unit = SP.settled_unit(r)
        out.append(dict(
            row=r, name=B.rule_name(r), sport=r["sport"],
            sport_label=B.side_label(r), href=_rule_href(r["sport"]),
            stage="production" if r.get("prod") else "sandbox",
            open=int(r.get("open") or 0), n=n, n_price=n_price, unit=unit,
            n_bets=int(a.get("n_bets") or n), won=int(a.get("won") or 0),
            expected=float(a.get("expected") or 0), z=a.get("z") if n else None,
            roi=a.get("roi_fee") if n else None,
            win_rate=(int(a.get("won") or 0) / n) if n else None,
            records=bool(n or n_price), read=n >= SP.EVIDENCE_FLOOR,
            verdict=r.get("v")))
    def order(e):
        roi = e["roi"] if e["roi"] is not None else float("-inf")
        return (e["stage"] != "production", -e["n"], -roi, e["name"].lower(), e["sport"])
    return sorted(out, key=order)


def scorecard_counts(entries):
    """{filter value: rows it shows}, for the chips."""
    return {"all": len(entries),
            "production": sum(1 for e in entries if e["stage"] == "production"),
            "records": sum(1 for e in entries if e["records"]),
            "read": sum(1 for e in entries if e["read"])}


# ------------------------------------------------------------------ the page
def _tile(value, label):
    return f'<div class="tile"><b>{value}</b><span>{esc(label)}</span></div>'


def _area_card(area, now):
    status = area["status"]
    chip = f'<span class="sig {STATUS_CHIP[status]}">{STATUS_LABEL[status]}</span>'
    last = area["last_read"]
    if last is None:
        read = "never read"
    else:
        read = f"last read {fmt.when_relative(last, now)}"
    next24 = "—" if area["next24"] is None else str(area["next24"])
    why = ""
    if status == "stale":
        # A card for an area this table does not list still renders, without the hours.
        hours, calendar = EXPECTED.get(area["key"], (None, "always"))
        why = ('<p class="cc-why sm">No successful read inside the expected interval.</p>' if hours is None else
               f'<p class="cc-why sm">No successful read inside {hours}h'
               f'{" of trading days" if calendar == "trading_days" else " of weekdays" if calendar == "weekdays" else ""}.</p>')
    elif area["items"]:
        why = '<ul class="cc-card-items sm">' + "".join(
            f'<li>{esc(item["text"])}</li>' for item in area["items"][:3]) + "</ul>"
    return f"""<article class="cc-card cc-{status}" data-area="{esc(area['key'])}" data-status="{status}">
<div class="cc-card-head"><h3>{esc(area['label'])}</h3>{chip}</div>
<dl class="cc-stats">
<div><dt>Open</dt><dd>{area['open']}</dd></div>
<div><dt>Settled · {window_days()}d</dt><dd>{area['settled']}</dd></div>
<div><dt>Next {NEXT_HOURS}h</dt><dd>{next24}</dd></div>
</dl>
<p class="cc-coverage sm">{esc(area['coverage'])}</p>
<p class="cc-read sm mut">{esc(read)}</p>
{why}
<a class="cc-open" href="{esc(area['href'])}">Open →</a>
</article>"""


def _scorecard_row(e):
    r, a = e["row"], e["row"].get("a") or {}
    settled = SP.unit_count(e["n"], e["unit"])
    if e["unit"] in ("market-day", "match") and e["n"]:
        settled += f'<div class="sm mut">{e["n_bets"]} bet{"" if e["n_bets"] == 1 else "s"}</div>'
    record = T.record_html(a)
    if e["win_rate"] is not None:
        record += f'<div class="sm mut cc-winrate">{e["win_rate"] * 100:.0f}% won</div>'
    wvp = esc(SP.won_v_priced(a))
    if e["z"] is not None:
        wvp += f'<div class="sm">z {float(e["z"]):+.2f}</div>'
    attrs = (f' data-stage="{e["stage"]}" data-records="{1 if e["records"] else 0}"'
             f' data-read="{1 if e["read"] else 0}" data-sport="{esc(e["sport"])}"')
    return (f'<tr class="cc-rule"{attrs}>'
            f'<td><a href="{esc(e["href"])}"><b>{esc(e["name"])}</b></a>'
            f'<div class="sm mut">{esc(e["sport_label"])}</div></td>'
            f'<td class="cc-stage">{SP.stage_badges(r)}</td>'
            f'<td class="num" data-v="{e["open"]}">{e["open"]}</td>'
            f'<td class="num" data-v="{e["n"]}">{settled}</td>'
            f'<td class="num">{record}</td>'
            f'<td class="num">{wvp}</td>'
            f'<td class="num">{SP.roi_html(r)}</td>'
            f'<td class="num" data-v="{e["n"]}">{esc(SP.evidence(a))}</td>'
            f'<td class="cc-verdict">{SP.verdict_badge(r)}</td></tr>')


def _scorecard_html(entries, outside=()):
    if not entries:
        return '<p class="shell-empty">No rule has a record yet.</p>'
    counts = scorecard_counts(entries)
    # The tile above counts every pair in Production; the chip counts the rows listed here.
    # Say what the difference is rather than leave two numbers to disagree.
    outside_note = (f'<p class="sm mut cc-prod-note">Production {counts["production"]} lists the sports pairs; '
                    f'{" and ".join(esc(x) for x in outside)} is also in Production through its own feed, '
                    f'which makes the {counts["production"] + len(outside)} in the tile above.</p>' if outside else "")
    chips = "".join(
        f'<button type="button" data-value="{key}" aria-pressed="{"true" if key == "all" else "false"}">'
        f'{esc(label)} <span class="count">{counts[key]}</span></button>'
        for key, label in SCORECARD_FILTERS)
    rows = "".join(_scorecard_row(e) for e in entries)
    return f"""<nav class="sp-filter cc-filter" aria-label="Rules" data-controls="scorecard-table">{chips}</nav>
{outside_note}
<div class="tbl"><table class="cc-scorecard" id="scorecard-table">
<thead><tr><th>Rule</th><th>Stage</th><th class="num">Open</th><th class="num">Settled</th>
<th class="num">Record</th><th class="num">Won v priced</th><th class="num">ROI after fees</th>
<th class="num">Evidence</th><th>Verdict</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="sp-empty cc-scorecard-empty" hidden></p>
<p class="sm mut cc-scorecard-note">Settled counts a market-day for Crypto and Commodities, a match
for the corners ladder, a basket for a combo, and a bet otherwise. Evidence is settled over the
read floor of {SP.EVIDENCE_FLOOR}. The verdict reads <i>Too early</i> under {SP.TOO_EARLY_N},
<i>Collecting n/{SP.EVIDENCE_FLOOR}</i> with its lean (<i>Promising</i> or <i>Behind</i>) up to
{SP.EVIDENCE_FLOOR}, then <i>Working</i>, <i>No edge</i> or <i>Proven</i>.</p>"""


def _attention_html(items):
    if not items:
        return '<div class="note">Nothing needs attention. Every open bet is inside its start, every feed read, every Production pair is logging.</div>'
    rows = []
    for item in items:
        area = item.get("area")
        tag = AREA_LABEL.get(area, "System")
        external = str(item.get("href") or "").startswith("http")
        link = (f'<a href="{esc(item["href"])}"{" rel=\"noopener\"" if external else ""}>'
                f'{"Open run →" if external else "Open →"}</a>')
        rows.append(f'<li class="cc-item cc-item-{esc(item["kind"])}" data-kind="{esc(item["kind"])}">'
                    f'<span class="sig x">{esc(tag)}</span> <span class="cc-item-text">{esc(item["text"])}</span> {link}</li>')
    return f'<ol class="cc-attention">{"".join(rows)}</ol>'


def page(now, d=None, st=None, blob=None, nba=None, market=None, closes=None, runs=None, extra=None,
         status=None, daily=None, culture=None):
    """public_site/index.html. `extra` is the dict `inputs()` returns, for the tracker build."""
    when = shell_build._now(now)
    d, st, blob = shell_build._load(d, st, blob)
    if extra:
        nba = extra.get("nba") if nba is None else nba
        market = extra.get("market") if market is None else market
        closes = extra.get("closes") if closes is None else closes
        runs = extra.get("runs") if runs is None else runs
        status = extra.get("status") if status is None else status
        daily = extra.get("daily") if daily is None else daily
        culture = extra.get("culture") if culture is None else culture
    m = model(d, st, blob, when, nba=nba, market=market, closes=closes, runs=runs, status=status, daily=daily,
              culture=culture)
    tiles = m["tiles"]
    n_won, n_settled = tiles["landed"]
    healthy, total = tiles["healthy"]
    parts = m["live"]
    caption = (f'<p class="settled-caption" id="settled-caption" hidden>'
               f'Last {window_days()} days · counts are paper bets, one contest can carry several</p>')
    runs_note = ("" if m["runs_read"] else
                 '<p class="sm mut cc-runs-note">Workflow run results were not read for this build.</p>')
    body = f"""<h1 class="sr-only">Edge Machine · Control Center</h1>
<section id="overview" class="cc-overview" aria-label="Overview">
<div class="tiles">
{_tile(tiles['pairs'], 'pairs in Production')}
{_tile(tiles['open'], 'open bets')}
{_tile(f'{n_won}/{n_settled}', f'landed · last {window_days()} days')}
{_tile(f'{healthy} of {total}', 'areas healthy')}
{_tile(tiles['attention'], 'needs attention')}
</div>
</section>

<section id="areas" aria-labelledby="areas-title">
<div class="pane-head"><h2 id="areas-title">Areas</h2></div>
<div class="cc-areas">
{"".join(_area_card(a, when) for a in m['areas'])}
</div>
</section>

<section id="attention" aria-labelledby="attention-title">
<div class="pane-head"><h2 id="attention-title">Needs attention</h2> <span class="mut sm">· {tiles['attention']}</span></div>
{_attention_html(m['attention'])}
{runs_note}
</section>

<section id="live" aria-labelledby="live-title" class="cc-live">
<div class="pane-head"><h2 id="live-title">Live now</h2> <span class="production-badge">Production</span></div>
<div class="desk-layout" data-layout="analyst-desk">
<div class="shell-columns">
<div class="desk-center">
<section class="shell-pane running-pane" id="running" aria-labelledby="running-title">
<div class="pane-head">
<div>
<h3 id="running-title">Running markets</h3>
<p class="shell-kicker">Production lanes · choose a market to inspect its rules</p>
</div>
</div>
<div class="running-filters" role="group" aria-label="Running filters">
{parts["filters"]}
</div>
<nav class="sports sport-filter" aria-label="Sport filter">{parts["sports"]}</nav>
{caption}
<div class="running-list" id="running-list">
{parts["groups"]}
</div>
{parts["empty"]}
</section>
</div>
<div class="desk-side">
<section class="shell-pane rules-pane" id="rules" aria-labelledby="rules-title">
<div class="pane-head">
<h3 id="rules-title">Rule cards</h3>
<a class="full-page" href="./production.html">Full page →</a>
</div>
<div class="rules-head" id="rules-head" hidden>
<p class="rules-line" id="rules-line"></p>
</div>
<p class="sr-only" id="rules-live" aria-live="polite"></p>
<h4 class="rules-section" id="rules-section" hidden></h4>
<div class="rules-cards" id="rules-cards" hidden></div>
<p class="shell-empty" id="rules-empty">Select a contest in Running.</p>
</section>
</div>
</div>
</div>
</section>

<section id="scorecard" aria-labelledby="scorecard-title" class="cc-scorecard-section">
<div class="pane-head"><h2 id="scorecard-title">Rule scorecard</h2> <span class="mut sm">· {len(m['scorecard'])} rules</span></div>
{_scorecard_html(m['scorecard'], m.get('prod_outside') or ())}
</section>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return site_chrome.document(
        "Home",
        "The Research Control Center: every area's state, what needs attention, and what is running now.",
        "index",
        SECTIONS,
        shell_build._stamp(now),
        body,
        script_src="./tables.js",
        extra_head='<link rel="stylesheet" href="./control.css">',
        scripts=("./shell.js",),
        body_class="analyst-desk control-center",
    )
