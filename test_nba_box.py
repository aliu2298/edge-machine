#!/usr/bin/env python3
"""Per-team 1Q/1H rolling rates and last-game top PRA on the NBA pace file.

No network. ESPN is a fixture, and the fetch is monkeypatched.

Fails on main before the data is added: the new per-game keys, the teams
object, and the box-score fetch do not exist yet.
"""
import contextlib
import http.client
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import urllib.error
import urllib.request
from collections import deque

import nba_pace

FAILS = []
PASSED = 0
ROOT = os.path.dirname(os.path.abspath(__file__))
LEGACY_PATH = os.path.join(ROOT, "fixtures", "nba_box_legacy_games.json")
REAL_PATH = os.path.join(ROOT, "fixtures", "espn_nba_summary_401918010.json")
NEW_KEYS = {
    "roll_home_O_q1", "roll_home_D_q1", "roll_home_O_h1", "roll_home_D_h1",
    "roll_away_O_q1", "roll_away_D_q1", "roll_away_O_h1", "roll_away_D_h1",
}

# Block live HTTP for the whole file. A unit test may install its own fake.
def _no_net(*_a, **_k):
    raise AssertionError("test_nba_box made a live HTTP call")


urllib.request.urlopen = _no_net


def ok(cond, why):
    global PASSED
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if cond:
        PASSED += 1
    else:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


@contextlib.contextmanager
def _patched(values):
    saved = []
    for name, value in values.items():
        had = hasattr(nba_pace, name)
        old = getattr(nba_pace, name, None)
        setattr(nba_pace, name, value)
        saved.append((name, had, old))
    try:
        yield
    finally:
        for name, had, old in reversed(saved):
            if had:
                setattr(nba_pace, name, old)
            elif hasattr(nba_pace, name):
                delattr(nba_pace, name)


def _state(spec):
    st = {}
    for team, periods in spec.items():
        st[team] = {
            p: deque([tuple(x) for x in periods[p]], maxlen=nba_pace.WINDOW)
            for p in nba_pace.PERIODS
        }
    return st


def _flat_window():
    return {
        "q1": [(10, 10)] * 5,
        "h1": [(20, 20)] * 5,
        "ft": [(100, 100)] * 5,
    }


def _box(sides, labels=None):
    labels = labels or ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST"]
    players = []
    for abbr, athletes in sides.items():
        players.append({
            "team": {"abbreviation": abbr},
            "statistics": [{"labels": list(labels), "athletes": athletes}],
        })
    return {"boxscore": {"players": players}}


def _line(name, pts, reb, ast, labels=None):
    labels = labels or ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST"]
    values = {"MIN": "10", "PTS": str(pts), "FG": "1-2", "3PT": "0-0",
              "FT": "0-0", "REB": str(reb), "AST": str(ast)}
    return {
        "athlete": {"displayName": name},
        "didNotPlay": False,
        "stats": [str(values.get(lab, "0")) for lab in labels],
    }


def _dnp(name, stats=None):
    return {
        "athlete": {"displayName": name},
        "didNotPlay": True,
        "stats": [] if stats is None else stats,
    }


def _run(spec, games, http, prior=None, entry="run", transport=None):
    """Run nba_pace against fixtures. Never touches data/nba_pace.json.

    `transport` is a urlopen stand-in. When it is set, the real `_http_get`
    runs, so timeout and decode failures are the production path.
    """
    info = {"calls": [], "sleeps": [], "keep": None, "error": None,
            "blob": None, "code": None, "tmp": False, "before": None, "after": None}
    tmp = tempfile.mkdtemp(prefix="nba-box-")
    path = os.path.join(tmp, "nba_pace.json")
    if prior is not None:
        text = prior if isinstance(prior, str) else json.dumps(prior) + "\n"
        with open(path, "w") as fh:
            fh.write(text)
        info["before"] = text

    def build_seed(log=print):
        return _state(spec), []

    def fetch_range(start, end, keep=None, log=print):
        info["keep"] = keep
        return [dict(g) for g in games]

    def http_wrap(url, timeout):
        info["calls"].append((url, timeout))
        return http(url, timeout)

    def sleep_wrap(seconds):
        info["sleeps"].append(seconds)

    patches = {
        "OUT": path,
        "build_seed": build_seed,
        "fetch_range": fetch_range,
        "_sleep": sleep_wrap,
    }
    if transport is None:
        patches["_http_get"] = http_wrap

    with _patched(patches):
        if hasattr(nba_pace, "_box_gap"):
            nba_pace._box_gap["sent"] = False
        if transport is not None:
            urllib.request.urlopen = transport
        try:
            if entry == "main":
                argv = sys.argv
                sys.argv = ["nba_pace.py", "--run"]
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        info["code"] = nba_pace.main()
                finally:
                    sys.argv = argv
            else:
                info["blob"] = nba_pace.run(log=lambda *_a, **_k: None)
        except Exception as exc:
            info["error"] = exc
        finally:
            info["after"] = open(path).read() if os.path.exists(path) else None
            info["tmp"] = os.path.exists(path + ".tmp")
            if transport is not None:
                urllib.request.urlopen = _no_net
    shutil.rmtree(tmp, ignore_errors=True)
    return info


def _last(blob, team):
    teams = blob.get("teams") if isinstance(blob, dict) else None
    if not isinstance(teams, dict) or team not in teams:
        return "MISSING"
    row = teams[team]
    if not isinstance(row, dict) or "last_game" not in row:
        return "MISSING"
    return row["last_game"]


# The hand fixture. Numbers below are computed from these rows, not copied
# out of run(). The legacy file is what main's run() loop wrote for them.
MATH_SPEC = {
    "BOS": {
        "q1": [(10, 20), (12, 22), (14, 18), (11, 19), (13, 21)],
        "h1": [(40, 50), (42, 48), (44, 46), (41, 49), (43, 47)],
        "ft": [(100, 110), (108, 102), (99, 111), (120, 115), (103, 107)],
    },
    "NY": {
        "q1": [(21, 11), (19, 15), (23, 13), (17, 16), (20, 15)],
        "h1": [(48, 40), (46, 44), (50, 42), (45, 43), (51, 41)],
        "ft": [(115, 100), (109, 108), (121, 99), (110, 104), (105, 114)],
    },
    "CHA": {
        "q1": [(8, 9), (10, 11), (12, 7), (9, 13), (11, 10)],
        "h1": [(30, 28), (31, 29), (29, 27), (32, 30), (28, 26)],
        "ft": [(101, 99), (100, 98), (102, 100), (99, 97), (103, 101)],
    },
}
MATH_GAMES = [
    dict(id="g1", day="2026-10-03", start="2026-10-03T23:00Z",
         home="BOS", away="NY", completed=True, season_type=1,
         q1_home=18, q1_away=16, q1=34,
         h1_home=40, h1_away=44, h1=84,
         ft_home=102, ft_away=110, ft=212),
    dict(id="g2", day="2026-10-05", start="2026-10-05T23:30Z",
         home="NY", away="BOS", completed=False, season_type=1),
    dict(id="g3", day="2026-10-06", start="2026-10-06T23:00Z",
         home="CHA", away="NY", completed=False, season_type=1),
    dict(id="skip", day="2026-10-12", start="2026-10-12T20:00Z",
         home="POR", away="LON", completed=False, season_type=1),
]
# g1 is before the window moves. g2 and g3 see the window after g1 only,
# because g2 is not completed. Means:
#   BOS q1 (12+14+11+13+18)/5 = 13.6, (22+18+19+21+16)/5 = 19.2
#   NY  q1 (19+23+17+20+16)/5 = 19.0, (15+13+16+15+18)/5 = 15.4
HAND_OD = {
    "g1": {
        "roll_home_O_q1": 12.0, "roll_home_D_q1": 20.0,
        "roll_home_O_h1": 42.0, "roll_home_D_h1": 48.0,
        "roll_away_O_q1": 20.0, "roll_away_D_q1": 14.0,
        "roll_away_O_h1": 48.0, "roll_away_D_h1": 42.0,
    },
    "g2": {
        "roll_home_O_q1": 19.0, "roll_home_D_q1": 15.4,
        "roll_home_O_h1": 47.2, "roll_home_D_h1": 42.0,
        "roll_away_O_q1": 13.6, "roll_away_D_q1": 19.2,
        "roll_away_O_h1": 42.0, "roll_away_D_h1": 46.8,
    },
    "g3": {
        "roll_home_O_q1": 10.0, "roll_home_D_q1": 10.0,
        "roll_home_O_h1": 30.0, "roll_home_D_h1": 28.0,
        "roll_away_O_q1": 19.0, "roll_away_D_q1": 15.4,
        "roll_away_O_h1": 47.2, "roll_away_D_h1": 42.0,
    },
}
HAND_ROLL = {
    "BOS": {"q1": (13.6, 19.2, 5), "h1": (42.0, 46.8, 5), "ft": (106.4, 109.0, 5)},
    "NY": {"q1": (19.0, 15.4, 5), "h1": (47.2, 42.0, 5), "ft": (111.0, 105.4, 5)},
    "CHA": {"q1": (10.0, 10.0, 5), "h1": (30.0, 28.0, 5), "ft": (101.0, 99.0, 5)},
}
MATH_BOX = _box({
    "BOS": [_line("Jalen Brown", 22, 5, 4), _line("Bench Guy", 10, 2, 1),
            _dnp("Injured Star")],
    "NY": [_line("Miles Bridge", 18, 7, 6)],
})


def _math_http(url, timeout):
    if "site.web.api.espn.com" not in url or "event=g1" not in url:
        raise AssertionError("unexpected box fetch " + url)
    return 200, json.dumps(MATH_BOX)


def test_top_pra_selection():
    print("\ntop PRA, ties, DNP, label columns")
    fn = getattr(nba_pace, "top_pra", None)
    if fn is None:
        ok(False, "top_pra is missing")
        return
    # PTS is not at index 1. A hardcoded ESPN column order would crown Trap.
    labels = ["MIN", "STL", "FG", "3PT", "FT", "BLK", "TO", "PTS", "REB", "AST"]
    trap = {lab: 0 for lab in labels}
    trap.update({"STL": 40, "BLK": 30, "TO": 20, "PTS": 2, "REB": 3, "AST": 4})
    star = {lab: 0 for lab in labels}
    star.update({"PTS": 10, "REB": 8, "AST": 7})
    scorer = {lab: 0 for lab in labels}
    scorer.update({"PTS": 18})
    mega = {lab: 99 for lab in labels}
    athletes = []
    for name, values in (("Trap", trap), ("Real Star", star), ("Scorer", scorer)):
        athletes.append({
            "athlete": {"displayName": name},
            "didNotPlay": False,
            "stats": [str(values[lab]) for lab in labels],
        })
    athletes.append(_dnp("Mega", [str(mega[lab]) for lab in labels]))
    athletes.append({"athlete": {"displayName": "Ghost"}, "didNotPlay": False, "stats": []})
    athletes.append({
        "athlete": {"displayName": "Blank"},
        "didNotPlay": False,
        "stats": [""] * len(labels),
    })
    payload = _box({"BOS": athletes}, labels=labels)
    got = fn(payload, "BOS")
    eq(got, {"name": "Real Star", "pts": 10, "reb": 8, "ast": 7, "pra": 25},
       "label columns, not position; DNP and empty lines skipped")

    # Same PRA: more points wins, and the winner is not the first row.
    points = _box({"NY": [
        _line("Bara", 8, 7, 0, labels=["PTS", "REB", "AST"]),
        _line("Cara", 10, 5, 0, labels=["PTS", "REB", "AST"]),
    ]}, labels=["PTS", "REB", "AST"])
    eq(fn(points, "NY")["name"], "Cara", "a PRA tie goes to more points")

    # Same PRA and the same points: alphabetical, even if that name is listed second.
    alpha = _box({"NY": [
        _line("Nina", 5, 5, 5, labels=["PTS", "REB", "AST"]),
        _line("Mina", 5, 5, 5, labels=["PTS", "REB", "AST"]),
    ]}, labels=["PTS", "REB", "AST"])
    eq(fn(alpha, "NY")["name"], "Mina", "a remaining tie goes to the name A to Z")

    with open(REAL_PATH) as fh:
        real = json.load(fh)
    eq(fn(real, "GS"), {"name": "Charles Bassey", "pts": 12, "reb": 8, "ast": 1, "pra": 21},
       "trimmed ESPN summary: GS top PRA is Charles Bassey, not the DNP")
    eq(fn(real, "LAC"), {"name": "Rui Hachimura", "pts": 21, "reb": 5, "ast": 0, "pra": 26},
       "trimmed ESPN summary: LAC top PRA is Rui Hachimura")

    try:
        fn(_box({"BOS": [_dnp("Only Out")]}), "BOS")
        ok(False, "a box with nobody who played raises")
    except Exception as exc:
        ok(type(exc).__name__ == "BoxScoreError",
           f"nobody-played raises BoxScoreError ({type(exc).__name__})")


def test_latest_is_season_agnostic():
    print("\nseason-agnostic last game")
    fn = getattr(nba_pace, "latest_completed", None)
    if fn is None:
        ok(False, "latest_completed is missing")
        return
    rows = [
        {"id": "pre-1", "completed": True, "start": "2026-10-01T00:00Z",
         "day": "2026-10-01", "home": "MIL", "away": "DAL", "season_type": 1},
        {"id": "reg-9", "completed": True, "start": "2026-10-20T00:00Z",
         "day": "2026-10-20", "home": "DAL", "away": "MIL", "season_type": 2},
        {"id": "", "completed": True, "start": "2026-10-21T00:00Z",
         "day": "2026-10-21", "home": "MIL", "away": "DAL", "season_type": 2},
        {"id": None, "completed": True, "start": "2026-10-21T01:00Z",
         "day": "2026-10-21", "home": "MIL", "away": "DAL"},
        {"id": "fut", "completed": False, "start": "2026-10-22T00:00Z",
         "day": "2026-10-22", "home": "MIL", "away": "DAL", "season_type": 2},
    ]
    eq(fn(rows, "MIL")["id"], "reg-9",
       "a later regular-season game is the last game; season_type is ignored")
    eq(fn(rows, "DAL")["id"], "reg-9", "the opponent gets the same game")
    eq(fn([{"id": None, "completed": True, "start": "2026-10-09T00:00Z",
            "home": "CHA", "away": "BOS"}], "CHA"), None,
       "a completed game without an id does not qualify")
    eq(fn(rows, "BKN"), None, "a team that never appears has no last game")


def test_period_rates_and_unchanged_keys():
    print("\nper-period rates and unchanged game keys")
    info = _run(MATH_SPEC, MATH_GAMES, _math_http)
    ok(info["error"] is None, f"fixture run completes ({info['error']})")
    blob = info["blob"] or {}
    ok("teams" in blob, "top-level teams object is present")
    games = {g["id"]: g for g in blob.get("games") or []}
    for gid, want in HAND_OD.items():
        got = {k: games.get(gid, {}).get(k, "MISSING") for k in NEW_KEYS}
        eq(got, want, f"{gid} 1Q/1H O and D match the hand window")
    if "teams" in blob:
        eq(set(blob["teams"]), set(MATH_SPEC), "every seeded team is in teams")
        for team, periods in HAND_ROLL.items():
            roll = blob["teams"].get(team, {}).get("roll", {})
            got = {p: (roll.get(p, {}).get("O"), roll.get(p, {}).get("D"),
                       roll.get(p, {}).get("n")) for p in ("q1", "h1", "ft")}
            eq(got, periods, f"{team} current roll matches the hand window")
        cha = blob["teams"].get("CHA", {})
        ok(blob.get("seed", {}).get("teams", {}).get("CHA", {}).get("ft"),
           "CHA still has a seed window")
        eq(cha.get("last_game", "MISSING"), None,
           "CHA last_game is null: scheduled only, seed is not a last game")
        bos = _last(blob, "BOS")
        eq(bos, {
            "id": "g1", "date": "2026-10-03", "opp": "NY", "home_away": "home",
            "top_pra": {"name": "Jalen Brown", "pts": 22, "reb": 5, "ast": 4, "pra": 31},
        }, "BOS last_game is the completed game, DNP ignored")
        ny = _last(blob, "NY")
        eq(isinstance(ny, dict) and ny.get("home_away"), "away", "NY was the away side")
        eq(isinstance(ny, dict) and ny.get("opp"), "BOS", "NY's opponent is BOS")
    else:
        ok(False, "CHA null last_game (teams missing)")
        ok(False, "BOS last_game (teams missing)")
    g1 = games.get("g1", {})
    eq(g1.get("roll_exp_q1"), 33.0, "hand check: g1 roll_exp_q1 stays 33.0")
    eq(g1.get("roll_exp_h1"), 90.0, "hand check: g1 roll_exp_h1 stays 90.0")
    eq(g1.get("roll_exp_ft"), 216.0, "hand check: g1 roll_exp_ft stays 216.0")
    eq((g1.get("err_q1"), g1.get("err_h1"), g1.get("err_ft")), (1.0, -6.0, -4.0),
       "hand check: g1 errors stay act minus roll_exp")
    with open(LEGACY_PATH) as fh:
        legacy = json.load(fh)
    eq([g["id"] for g in blob.get("games") or []], [g["id"] for g in legacy],
       "the fixture still emits the same games, in the same order")
    for want in legacy:
        got = games.get(want["id"], {})
        old = {k: got.get(k, "MISSING") for k in want}
        eq(old, want, f"{want['id']} pre-existing keys unchanged versus main")
        extra = set(got) - set(want)
        if want.get("skipped"):
            eq(extra, set(), f"{want['id']} skipped game gained no keys")
        else:
            eq(extra, NEW_KEYS, f"{want['id']} adds only the eight 1Q/1H rates")
    eq(info["keep"], (nba_pace.PRE,), "run() still fetches preseason only")
    eq(len(info["calls"]), 1, "the one completed game is fetched once")
    eq(info["sleeps"], [], "no pause before the only request")
    written = json.loads(info["after"]) if info["after"] else {}
    eq(written.get("games", [{}])[0].get("roll_home_O_q1"), 12.0,
       "the atomic write keeps roll_home_O_q1")
    eq((written.get("teams") or {}).get("CHA", {}).get("last_game", "MISSING"), None,
       "the written file stores CHA last_game as null")


def test_host_fallback_and_retry():
    print("\nhost fallback and one retry")
    eq(getattr(nba_pace, "BOX_TIMEOUT", None), 15, "box-score timeout is 15s")
    eq(getattr(nba_pace, "BOX_ATTEMPTS", None), 2, "one retry: two attempts per host")
    eq(getattr(nba_pace, "BOX_PAUSE", None), 1.0, "about 1s between box-score requests")
    hosts = getattr(nba_pace, "BOX_HOSTS", ())
    eq(tuple(hosts[:1]), ("site.web.api.espn.com",), "web host is tried first")
    eq(tuple(hosts[1:2]), ("site.api.espn.com",), "api host is the fallback")
    ua = getattr(nba_pace, "BOX_UA", "")
    ok(bool(ua) and "Mozilla" not in ua and "Chrome" not in ua,
       f"User-Agent is a plain identifier ({ua!r})")

    if not hasattr(nba_pace, "_http_get"):
        ok(False, "box-score GET helper is missing")
        return
    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def fake_open(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["timeout"] = timeout
        captured["ua"] = req.get_header("User-agent")
        captured["data"] = req.data
        captured["unredirected"] = dict(req.unredirected_hdrs)
        return _Resp()

    urllib.request.urlopen = fake_open
    try:
        status, text = nba_pace._http_get("https://site.web.api.espn.com/x", 15)
    finally:
        urllib.request.urlopen = _no_net
    eq(status, 200, "GET helper returns the status")
    eq(text, '{"ok": true}', "GET helper returns the body")
    eq(captured.get("method"), "GET", "box score uses GET")
    eq(captured.get("ua"), nba_pace.BOX_UA, "box score sends the plain User-Agent")
    eq(captured.get("timeout"), 15, "GET helper honours the 15s timeout")
    eq(captured.get("data"), None, "GET carries no body")
    ok("key" not in captured.get("url", "") and "Authorization" not in captured["unredirected"],
       "box score sends no key")

    def forbidden(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", None, io.BytesIO(b"no"))

    urllib.request.urlopen = forbidden
    try:
        status, text = nba_pace._http_get("https://site.web.api.espn.com/x", 15)
    finally:
        urllib.request.urlopen = _no_net
    eq((status, text), (403, None), "an HTTP 403 is a status, not a swallowed error")

    if not hasattr(nba_pace, "fetch_summary"):
        ok(False, "fetch_summary is missing")
        return
    nba_pace._box_gap["sent"] = False
    attempts = {"n": 0}

    def retry_http(url, timeout):
        attempts["n"] += 1
        eq(timeout, 15, "fetch passes the 15s timeout")
        if attempts["n"] == 1:
            return 503, None
        ok("site.web.api.espn.com" in url, "the retry stays on the first host")
        return 200, json.dumps(MATH_BOX)

    sleeps = []
    with _patched({"_http_get": retry_http, "_sleep": sleeps.append}):
        payload, host, status = nba_pace.fetch_summary("g1")
    eq(host, "site.web.api.espn.com", "a successful retry does not change host")
    eq(status, 200, "the retry returns 200")
    eq(attempts["n"], 2, "one failure then one retry")
    eq(sleeps, [1.0], "the retry waits about 1s")
    eq(nba_pace.top_pra(payload, "BOS")["name"], "Jalen Brown", "retried payload parses")

    with open(REAL_PATH) as fh:
        real_text = fh.read()
    spec = {"GS": _flat_window(), "LAC": _flat_window()}
    games = [dict(id="401918010", day="2026-10-04", start="2026-10-04T23:00Z",
                   home="LAC", away="GS", completed=True, season_type=1)]

    def fallback_http(url, timeout):
        if "site.web.api.espn.com" in url:
            return 403, None
        if "site.api.espn.com" in url:
            return 200, real_text
        raise AssertionError(url)

    info = _run(spec, games, fallback_http)
    ok(info["error"] is None, f"fallback run completes ({info['error']})")
    web = [u for u, _t in info["calls"] if "site.web.api.espn.com" in u]
    api = [u for u, _t in info["calls"] if "site.api.espn.com" in u and "site.web.api.espn.com" not in u]
    eq(len(web), 2, "the web host is tried, then retried, on 403")
    eq(len(api), 1, "the api host is used once the web host fails")
    ok(web and web[0].endswith("summary?event=401918010"),
       "the summary URL is the keyless event path")
    eq(info["sleeps"], [1.0, 1.0], "1s between the 403, the retry, and the fallback")
    eq([t for _u, t in info["calls"]], [15, 15, 15], "every attempt uses the 15s timeout")
    blob = info["blob"] or {}
    eq(_last(blob, "GS"), {
        "id": "401918010", "date": "2026-10-04", "opp": "LAC", "home_away": "away",
        "top_pra": {"name": "Charles Bassey", "pts": 12, "reb": 8, "ast": 1, "pra": 21},
    }, "GS last_game comes from the fallback host")
    lac = _last(blob, "LAC")
    eq(isinstance(lac, dict) and lac.get("top_pra", {}).get("name"), "Rui Hachimura",
       "LAC shares that one fetch")
    eq(isinstance(lac, dict) and lac.get("home_away"), "home", "LAC was home")


def test_fail_loud_does_not_rewrite():
    print("\nfail loud before the write")
    keep = '{"built": "keep-me"}\n'
    spec = {"BOS": _flat_window(), "NY": _flat_window()}
    games = [dict(id="boom", day="2026-10-04", start="2026-10-04T23:00Z",
                   home="BOS", away="NY", completed=True, season_type=1)]

    def both_fail(url, timeout):
        if "site.web.api.espn.com" in url:
            return 403, None
        return 500, None

    info = _run(spec, games, both_fail, prior=keep)
    ok(info["error"] is not None, "both hosts failing raises")
    if info["error"] is not None:
        msg = str(info["error"])
        ok("boom" in msg, "the error names the event id")
        ok("site.web.api.espn.com" in msg and "site.api.espn.com" in msg,
           "the error names both hosts")
        ok("403" in msg and "500" in msg, "the error names both statuses")
    eq(info["after"], keep, "a failed run does not rewrite the file")
    ok(not info["tmp"], "a failed run does not leave the temp file in place")

    def malformed(url, timeout):
        return 200, "{}"

    info = _run(spec, games, malformed, prior=keep)
    ok(info["error"] is not None, "a 200 without a boxscore raises")
    if info["error"] is not None:
        msg = str(info["error"])
        ok("boom" in msg and "missing boxscore" in msg and "200" in msg,
           "a malformed payload names the event, the reason and the status")
    eq(info["after"], keep, "a malformed payload does not rewrite the file")

    def only_dnp(url, timeout):
        body = _box({"BOS": [_dnp("Out A")], "NY": [_dnp("Out B")]})
        return 200, json.dumps(body)

    info = _run(spec, games, only_dnp, prior=keep)
    ok(info["error"] is not None, "a completed game with no countable player raises")
    eq(info["after"], keep, "that failure does not write last_game null")
    if info["after"]:
        ok("top_pra" not in info["after"], "no partial PRA line was written")

    info = _run(spec, games, both_fail, prior=keep, entry="main")
    failed = info["error"] is not None or info["code"] not in (None, 0)
    ok(failed, "nba_pace.py --run raises or exits non-zero")
    if info["error"] is not None:
        ok(type(info["error"]).__name__ == "BoxScoreError",
           f"--run lets BoxScoreError out ({type(info['error']).__name__})")
    eq(info["after"], keep, "--run leaves the previous file in place")


def test_no_refetch_of_resolved_last_game():
    print("\nno refetch of a resolved last_game")
    cached_bos = {
        "id": "g1", "date": "2026-10-03", "opp": "NY", "home_away": "home",
        "top_pra": {"name": "Cached BOS", "pts": 9, "reb": 8, "ast": 7, "pra": 24},
    }
    cached_ny = {
        "id": "g1", "date": "2026-10-03", "opp": "BOS", "home_away": "away",
        "top_pra": {"name": "Cached NY", "pts": 1, "reb": 2, "ast": 3, "pra": 6},
    }
    prior = {"teams": {"BOS": {"last_game": cached_bos}, "NY": {"last_game": cached_ny}}}

    def boom(url, timeout):
        raise AssertionError("refetched " + url)

    info = _run(MATH_SPEC, MATH_GAMES, boom, prior=prior)
    ok(info["error"] is None, f"a fully resolved pair does not fetch ({info['error']})")
    eq(info["calls"], [], "no HTTP at all when every latest game is already resolved")
    eq(info["sleeps"], [], "no pause when nothing is fetched")
    eq(_last(info["blob"] or {}, "BOS"), cached_bos, "BOS keeps the stored line")
    eq(_last(info["blob"] or {}, "NY"), cached_ny, "NY keeps the stored line")

    prior = {"teams": {"BOS": {"last_game": dict(cached_bos)}}}

    def fresh(url, timeout):
        box = _box({
            "BOS": [_line("Fresh BOS", 30, 1, 1)],
            "NY": [_line("Fresh NY", 11, 2, 3)],
        })
        return 200, json.dumps(box)

    info = _run(MATH_SPEC, MATH_GAMES, fresh, prior=prior)
    ok(info["error"] is None, f"the unresolved side can still fetch ({info['error']})")
    eq(len(info["calls"]), 1, "the shared game is fetched once, for the side that needs it")
    eq(_last(info["blob"] or {}, "BOS"), cached_bos,
       "the already-resolved side is not replaced by the new parse")
    ny = _last(info["blob"] or {}, "NY")
    eq(isinstance(ny, dict) and ny.get("top_pra", {}).get("name"), "Fresh NY",
       "the side without a stored line gets the new box")


def test_regular_season_game_in_the_file():
    print("\nregular-season game in games[]")
    spec = {"MIL": _flat_window(), "DAL": _flat_window()}
    games = [
        dict(id="pre-1", day="2026-10-01", start="2026-10-01T23:00Z",
             home="MIL", away="DAL", completed=True, season_type=1),
        dict(id="reg-9", day="2026-10-20", start="2026-10-20T23:00Z",
             home="DAL", away="MIL", completed=True, season_type=2),
        dict(id="", day="2026-10-21", start="2026-10-21T23:00Z",
             home="MIL", away="DAL", completed=True, season_type=2),
        dict(id="fut", day="2026-10-22", start="2026-10-22T23:00Z",
             home="MIL", away="DAL", completed=False, season_type=2),
    ]

    def http(url, timeout):
        if "event=reg-9" not in url:
            raise AssertionError("fetched something other than the latest game: " + url)
        box = _box({
            "MIL": [_line("Mil Top", 15, 4, 5)],
            "DAL": [_line("Dal Top", 12, 3, 2)],
        })
        return 200, json.dumps(box)

    info = _run(spec, games, http)
    ok(info["error"] is None, f"a games[] list with a regular-season row runs ({info['error']})")
    eq(info["keep"], (nba_pace.PRE,),
       "adding the row does not change the preseason fetch filter")
    blob = info["blob"] or {}
    ids = [g["id"] for g in blob.get("games") or []]
    ok("reg-9" in ids and "pre-1" in ids, "both the preseason and regular-season rows are kept")
    mil = _last(blob, "MIL")
    eq(isinstance(mil, dict) and mil.get("id"), "reg-9",
       "the last game is the regular-season row, not the earlier preseason one")
    eq(isinstance(mil, dict) and mil.get("date"), "2026-10-20", "date is the games[] day")
    eq(isinstance(mil, dict) and mil.get("home_away"), "away", "MIL was away on that day")
    eq(isinstance(mil, dict) and mil.get("opp"), "DAL", "MIL's opponent is DAL")
    eq(isinstance(mil, dict) and mil.get("top_pra"),
       {"name": "Mil Top", "pts": 15, "reb": 4, "ast": 5, "pra": 24},
       "PRA is taken from that regular-season box")
    dal = _last(blob, "DAL")
    eq(isinstance(dal, dict) and dal.get("home_away"), "home", "DAL was home")
    eq(len(info["calls"]), 1, "the older preseason game and the id-less game are not fetched")


def test_pause_between_games():
    print("\npause between newly fetched games")
    spec = {t: _flat_window() for t in ("BOS", "NY", "CHA", "MIL")}
    games = [
        dict(id="ea", day="2026-10-03", start="2026-10-03T23:00Z",
             home="BOS", away="NY", completed=True),
        dict(id="eb", day="2026-10-04", start="2026-10-04T23:00Z",
             home="CHA", away="MIL", completed=True),
    ]

    def http(url, timeout):
        if "event=ea" in url:
            sides = {"BOS": [_line("A", 10, 1, 1)], "NY": [_line("B", 9, 1, 1)]}
        elif "event=eb" in url:
            sides = {"CHA": [_line("C", 8, 1, 1)], "MIL": [_line("D", 7, 1, 1)]}
        else:
            raise AssertionError(url)
        return 200, json.dumps(_box(sides))

    info = _run(spec, games, http)
    ok(info["error"] is None, f"two new games complete ({info['error']})")
    eq(len(info["calls"]), 2, "one request per newly latest game")
    eq(info["sleeps"], [1.0], "about 1s between those requests, and not before the first")
    eq([t for _u, t in info["calls"]], [15, 15], "both requests use the 15s timeout")


class _Resp:
    """A urlopen result. `raw` is bytes. `boom` is raised from read()."""

    def __init__(self, raw=b"", status=200, boom=None):
        self.status = status
        self._raw = raw
        self._boom = boom

    def read(self):
        if self._boom is not None:
            raise self._boom
        return self._raw

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "fail", None, io.BytesIO(b""))


def _host_of(url):
    if "site.web.api.espn.com" in url:
        return "web"
    if "site.api.espn.com" in url:
        return "api"
    return "?"


KEEP_FILE = ('{"built":"keep-me","teams":{"PHI":{"last_game":{"id":"401914101"}}},'
             '"games":[{"id":"401914101"}]}\n')


def _failed(info):
    return info["error"] is not None or info["code"] not in (None, 0)


def _run_scoreboard(decide):
    """`nba_pace.py --run` with a fake scoreboard. `decide(url)` returns bytes or raises."""
    info = {"calls": [], "error": None, "code": None, "after": None, "tmp": False}
    tmp = tempfile.mkdtemp(prefix="nba-score-")
    path = os.path.join(tmp, "nba_pace.json")
    with open(path, "w") as fh:
        fh.write(KEEP_FILE)

    def urlopen(req, timeout=None):
        info["calls"].append((req.full_url, timeout, req.get_header("User-agent"),
                               req.get_method()))
        got = decide(req.full_url)
        if isinstance(got, BaseException):
            raise got
        return got

    urllib.request.urlopen = urlopen
    argv = sys.argv
    sys.argv = ["nba_pace.py", "--run"]
    try:
        with _patched({"OUT": path, "_sleep": lambda _s: None}):
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    info["code"] = nba_pace.main()
            except Exception as exc:
                info["error"] = exc
            info["after"] = open(path).read() if os.path.exists(path) else None
            info["tmp"] = os.path.exists(path + ".tmp")
    finally:
        sys.argv = argv
        urllib.request.urlopen = _no_net
        shutil.rmtree(tmp, ignore_errors=True)
    return info


def _day_hosts(info, ymd):
    return [_host_of(url) for url, _t, _ua, _m in info["calls"] if f"dates={ymd}" in url]


def test_scoreboard_day_fails_loud():
    print("\nscoreboard day fails before the write")
    eq(getattr(nba_pace, "SCORE_HOSTS", None), getattr(nba_pace, "BOX_HOSTS", None),
       "scoreboard uses the same host fallback as summaries")
    eq(getattr(nba_pace, "SCORE_ATTEMPTS", None), 2, "a failed scoreboard day is retried once")
    eq(getattr(nba_pace, "SCORE_TIMEOUT", None), 30, "scoreboard timeout stays 30s")

    def one_bad(url):
        # 29 Sep is the first preseason day, so the seed days have already succeeded.
        if "dates=20260929" in url:
            return _http_error(url, 503)
        if "scoreboard?dates=" not in url:
            raise AssertionError("not a scoreboard " + url)
        return _Resp(b'{"events":[]}')

    info = _run_scoreboard(one_bad)
    ok(_failed(info), "one failed scoreboard day exits non-zero")
    err = info["error"]
    ok(type(err).__name__ == "ScoreboardError",
       f"one failed day raises ScoreboardError ({type(err).__name__})")
    if err is not None:
        msg = str(err)
        ok("2026-09-29" in msg, "the error names the date")
        ok("site.web.api.espn.com" in msg and "site.api.espn.com" in msg,
           "the error names both hosts")
        ok("503" in msg, "the error names the status")
    eq(_day_hosts(info, "20260929"), ["web", "web", "api", "api"],
       "the failed day is retried, then the fallback host is retried")
    eq(info["after"], KEEP_FILE, "one failed day does not rewrite the file")
    ok(not info["tmp"], "one failed day does not leave a temp file")
    later = [url for url, _t, _ua, _m in info["calls"] if "dates=20260930" in url]
    eq(later, [], "days after the failure are not fetched and not written")

    def all_bad(url):
        return _http_error(url, 500)

    info = _run_scoreboard(all_bad)
    ok(_failed(info), "every scoreboard day failing exits non-zero")
    err = info["error"]
    ok(type(err).__name__ == "ScoreboardError",
       f"every day failing raises ScoreboardError ({type(err).__name__})")
    if err is not None:
        msg = str(err)
        ok("2026-03-25" in msg, "the first failed seed day is named")
        ok("500" in msg, "the status is named when every day fails")
    eq(len(info["calls"]), 4, "the run stops on the first day instead of writing teams={}")
    eq(_day_hosts(info, "20260325"), ["web", "web", "api", "api"],
       "the first day uses the retry and the fallback before giving up")
    eq(info["after"], KEEP_FILE, "every day failing leaves the last good file")
    ok(not info["tmp"], "every day failing does not leave a temp file")
    if info["calls"]:
        url, timeout, ua, method = info["calls"][0]
        ok("scoreboard?dates=" in url, "the request is the scoreboard path")
        eq(timeout, 30, "the scoreboard request uses the 30s timeout")
        eq(ua, nba_pace.UA, "the scoreboard request keeps its User-Agent")
        eq(method, "GET", "the scoreboard request is a GET")

    flaky = {"n": 0}

    def retry_ok(url):
        if "scoreboard?dates=" not in url:
            raise AssertionError(url)
        if "dates=20260929" in url:
            flaky["n"] += 1
            if _host_of(url) != "web" or flaky["n"] > 2:
                raise AssertionError("retry left the web host " + url)
            if flaky["n"] == 1:
                return _http_error(url, 503)
            body = json.dumps({"events": [{
                "id": "retry-game",
                "date": "2026-09-29T23:00Z",
                "season": {"year": 2027, "type": 1},
                "competitions": [{
                    "status": {"type": {"completed": False}},
                    "competitors": [
                        {"homeAway": "home", "team": {"abbreviation": "BOS", "id": "2"}},
                        {"homeAway": "away", "team": {"abbreviation": "NY", "id": "18"}},
                    ],
                }],
            }]}).encode()
            return _Resp(body)
        if _host_of(url) != "web":
            raise AssertionError("a healthy day does not need the fallback " + url)
        return _Resp(b'{"events":[]}')

    info = _run_scoreboard(retry_ok)
    ok(info["error"] is None and info["code"] == 0,
       f"a day that succeeds on retry exits 0 ({info['error']})")
    eq(flaky["n"], 2, "the flaky day is fetched, then retried once")
    eq(_day_hosts(info, "20260929"), ["web", "web"],
       "a successful retry stays on the first host")
    ok(info["after"] and info["after"] != KEEP_FILE, "a successful retry rewrites the file")
    written = json.loads(info["after"]) if info["after"] else {}
    ids = [g.get("id") for g in written.get("games") or []]
    eq(ids, ["retry-game"], "the retried day is in the written file")
    ok(not info["tmp"], "a successful write does not leave the temp file")
    healthy = _day_hosts(info, "20260325")
    eq(healthy, ["web"], "a healthy day is fetched once")


def test_stale_last_game_is_replaced():
    print("\nstale last_game is refetched")
    stale_bos = {
        "id": "old-1", "date": "2026-10-01", "opp": "NY", "home_away": "home",
        "top_pra": {"name": "Stale Star", "pts": 40, "reb": 10, "ast": 10, "pra": 60},
    }
    stale_ny = {
        "id": "old-1", "date": "2026-10-01", "opp": "BOS", "home_away": "away",
        "top_pra": {"name": "Stale NY", "pts": 30, "reb": 9, "ast": 8, "pra": 47},
    }
    prior = {"teams": {"BOS": {"last_game": stale_bos}, "NY": {"last_game": stale_ny}}}
    info = _run(MATH_SPEC, MATH_GAMES, _math_http, prior=prior)
    ok(info["error"] is None, f"a newer completed game replaces the stored line ({info['error']})")
    eq(len(info["calls"]), 1, "the newer event is fetched once")
    ok(info["calls"] and "event=g1" in info["calls"][0][0], "the fetch is the newer game, not old-1")
    bos = _last(info["blob"] or {}, "BOS")
    eq(isinstance(bos, dict) and bos.get("id"), "g1",
       "BOS last_game moves off the older stored id")
    eq(isinstance(bos, dict) and bos.get("top_pra"),
       {"name": "Jalen Brown", "pts": 22, "reb": 5, "ast": 4, "pra": 31},
       "BOS PRA is the new box, not the stored line")
    ny = _last(info["blob"] or {}, "NY")
    eq(isinstance(ny, dict) and ny.get("id"), "g1", "NY last_game moves off the older stored id")
    eq(isinstance(ny, dict) and (ny.get("top_pra") or {}).get("name"), "Miles Bridge",
       "NY PRA is the new box, not the stored line")


def _open_raising(exc):
    def urlopen(req, timeout=None):
        urlopen.calls.append((req.full_url, timeout))
        raise exc
    urlopen.calls = []
    return urlopen


def _open_body(raw):
    def urlopen(req, timeout=None):
        urlopen.calls.append((req.full_url, timeout))
        return _Resp(raw)
    urlopen.calls = []
    return urlopen


def test_transport_and_decode_use_retry_path():
    print("\ntransport and decode failures retry, then fall back")
    spec = {"BOS": _flat_window(), "NY": _flat_window()}
    games = [dict(id="boom", day="2026-10-04", start="2026-10-04T23:00Z",
                   home="BOS", away="NY", completed=True, season_type=1)]
    cases = [
        ("timeout", _open_raising(socket.timeout("timed out")), "TimeoutError"),
        ("URLError", _open_raising(urllib.error.URLError("connection refused")), "URLError"),
        ("IncompleteRead",
         _open_raising(http.client.IncompleteRead(b"abc", 20)), "IncompleteRead"),
        ("utf-8", _open_body(b"\xff"), "UnicodeDecodeError"),
        ("json", _open_body(b"{"), "malformed json"),
    ]
    # IncompleteRead is raised by read(), not by urlopen. The raiser above
    # fires before a response exists, which skips the real read() path.
    # Replace that one case with a response whose read() is truncated.
    def incomplete(req, timeout=None):
        incomplete.calls.append((req.full_url, timeout))
        return _Resp(boom=http.client.IncompleteRead(b"abc", 20))
    incomplete.calls = []
    cases[2] = ("IncompleteRead", incomplete, "IncompleteRead")

    for kind, transport, token in cases:
        info = _run(spec, games, None, prior=KEEP_FILE, entry="main", transport=transport)
        ok(_failed(info), f"{kind} exits non-zero")
        err = info["error"]
        got_type = type(err).__name__
        ok(got_type == "BoxScoreError",
           f"{kind} raises BoxScoreError" if got_type == "BoxScoreError"
           else f"{kind} raises BoxScoreError, not {got_type}")
        if err is not None:
            msg = str(err)
            ok("boom" in msg, f"{kind} names the event")
            ok(token in msg, f"{kind} records {token} — got {msg!r}")
            ok("site.web.api.espn.com" in msg and "site.api.espn.com" in msg,
               f"{kind} names both hosts")
        hosts = [_host_of(url) for url, _t in transport.calls]
        eq(hosts, ["web", "web", "api", "api"], f"{kind} retries, then falls back")
        eq([t for _u, t in transport.calls], [15, 15, 15, 15], f"{kind} keeps the 15s timeout")
        eq(info["sleeps"], [1.0, 1.0, 1.0], f"{kind} pauses between the four attempts")
        eq(info["after"], KEEP_FILE, f"{kind} does not rewrite the file")
        ok(not info["tmp"], f"{kind} does not leave a temp file")


def test_short_and_empty_windows():
    print("\nshort window and empty team")
    # 3 games: 74/3 = 24.666… → 24.67, which is 24.7 at 1 dp.
    # 31/3 = 10.333… → 10.33. 124/3 = 41.333… → 41.33. 151/3 = 50.333… → 50.33.
    # 305/3 = 101.666… → 101.67. 274/3 = 91.333… → 91.33.
    spec = {
        "SHORT": {
            "q1": [(24, 10), (25, 10), (25, 11)],
            "h1": [(40, 50), (41, 50), (43, 51)],
            "ft": [(100, 90), (101, 91), (104, 93)],
        },
        "EMPTY": {"q1": [], "h1": [], "ft": []},
    }
    games = [dict(id="short-1", day="2026-10-08", start="2026-10-08T23:00Z",
                   home="SHORT", away="EMPTY", completed=False, season_type=1)]

    def boom(url, timeout):
        raise AssertionError("unfinished game was fetched " + url)

    info = _run(spec, games, boom)
    ok(info["error"] is None, f"short and empty windows run ({info['error']})")
    blob = info["blob"] or {}
    teams = blob.get("teams") or {}
    short = (teams.get("SHORT") or {}).get("roll") or {}
    empty = (teams.get("EMPTY") or {}).get("roll") or {}
    eq({p: (short.get(p, {}).get("O"), short.get(p, {}).get("D"), short.get(p, {}).get("n"))
        for p in ("q1", "h1", "ft")},
       {"q1": (24.67, 10.33, 3), "h1": (41.33, 50.33, 3), "ft": (101.67, 91.33, 3)},
       "a 3-game window keeps n=3 and means at 2 dp")
    eq({p: (empty.get(p, {}).get("O"), empty.get(p, {}).get("D"), empty.get(p, {}).get("n"))
        for p in ("q1", "h1", "ft")},
       {"q1": (None, None, 0), "h1": (None, None, 0), "ft": (None, None, 0)},
       "a team with no games stores null O/D and n=0")
    game = {g["id"]: g for g in blob.get("games") or []}.get("short-1", {})
    eq({k: game.get(k, "MISSING") for k in (
        "roll_home_O_q1", "roll_home_D_q1", "roll_home_O_h1", "roll_home_D_h1",
        "roll_away_O_q1", "roll_away_D_q1", "roll_away_O_h1", "roll_away_D_h1",
    )}, {
        "roll_home_O_q1": 24.67, "roll_home_D_q1": 10.33,
        "roll_home_O_h1": 41.33, "roll_home_D_h1": 50.33,
        "roll_away_O_q1": None, "roll_away_D_q1": None,
        "roll_away_O_h1": None, "roll_away_D_h1": None,
    }, "per-game 1Q/1H rates use the short window, and the empty side is null")


def test_blank_stat_is_dnp():
    print("\nblank or unreadable stat is DNP")
    fn = getattr(nba_pace, "top_pra", None)
    if fn is None:
        ok(False, "top_pra is missing")
        return
    doc = fn.__doc__ or ""
    ok("didNotPlay" in doc and "unreadable" in doc,
       "top_pra docstring: didNotPlay, or empty or unreadable stats, means DNP")
    ok("minutes" in doc and "not DNP" in doc,
       "top_pra docstring: 0 or missing minutes is not DNP")
    labels = ["MIN", "PTS", "REB", "AST"]

    def athlete(name, stats):
        return {"athlete": {"displayName": name}, "didNotPlay": False, "stats": stats}

    # Each of these beats 5/1/1 if a blank cell is invented as 0.
    payload = _box({"BOS": [
        athlete("Blank PTS", ["32", "", "20", "20"]),
        athlete("Blank REB", ["32", "20", "", "20"]),
        athlete("Blank AST", ["32", "20", "20", ""]),
        athlete("Dash", ["10", "--", "9", "9"]),
        athlete("Float", ["10", "40.0", "9", "9"]),
        athlete("Spaces", ["10", "   ", "8", "8"]),
        athlete("None Cell", ["10", None, "8", "8"]),
        _line("Real Line", 5, 1, 1, labels=labels),
    ]}, labels=labels)
    got = fn(payload, "BOS")
    eq(got, {"name": "Real Line", "pts": 5, "reb": 1, "ast": 1, "pra": 7},
       "a blank or unreadable PTS/REB/AST is skipped, not read as zero")

    try:
        fn(_box({"BOS": [athlete("Only Blank", ["32", "", "20", "20"])]}, labels=labels), "BOS")
        ok(False, "a box whose only line is unreadable raises")
    except Exception as exc:
        ok(type(exc).__name__ == "BoxScoreError",
           f"unreadable-only box raises BoxScoreError ({type(exc).__name__})")

    zero_min = _box({"BOS": [
        athlete("Zero Min", ["0", "3", "2", "1"]),
        athlete("Missing Min", ["--", "1", "0", "0"]),
    ]}, labels=labels)
    eq(fn(zero_min, "BOS")["name"], "Zero Min",
       "0 minutes is counted, and missing minutes is not DNP")


if __name__ == "__main__":
    print("nba box")
    test_top_pra_selection()
    test_latest_is_season_agnostic()
    test_period_rates_and_unchanged_keys()
    test_host_fallback_and_retry()
    test_fail_loud_does_not_rewrite()
    test_no_refetch_of_resolved_last_game()
    test_regular_season_game_in_the_file()
    test_pause_between_games()
    test_scoreboard_day_fails_loud()
    test_stale_last_game_is_replaced()
    test_transport_and_decode_use_retry_path()
    test_short_and_empty_windows()
    test_blank_stat_is_dnp()
    print(f"\n{PASSED} passed, {len(FAILS)} failed")
    if FAILS:
        raise SystemExit(1)
    print("all passed")
