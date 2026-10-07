#!/usr/bin/env python3
"""Pre-flight for the ten league lanes, from their own series constants.

Each lane reads one or two Kalshi series (a total or BTTS contract, and the
three-way board it joins). Those tickers live on sandbox_sources — ERE_DRAW_SERIES,
ERE_O15_TOTAL, and the rest — and this script reads those names, so a renamed
constant cannot drift away from the check.

For every lane and series, Kalshi's public API (no key) is one of:

  listed
      Open markets exist and the same fetch that fills the board keeps at
      least one of them. fetch_kalshi_venue for a three-way series,
      fetch_kalshi_goals for a total or a +0.5, fetch_kalshi_btts for BTTS.
  exists but no open markets
      The series ticker is real and the book is empty. A warning. Goals
      markets show up 38-95 hours before kickoff, so an empty book on a
      weekday is normal.
  never seen
      Kalshi returns 404 for the series ticker. A typo or a renamed series.
      This fails the run.

Open markets that the board's own fetch then drops are "listed but not on
the board", and that is a failure: the 38-95h pattern explains an empty
book, not a book the lane cannot see. The one exception is the board's own
horizon. A game that is open but outside that window is the same calendar
fact as the listing lag, so it warns and does not fail. A series the fetch
never requests, or a contract shape the parser drops on any horizon, fails.

The goals and BTTS fetches join an ESPN fixture before a row is kept. This
check does not call ESPN. It builds that fixture from the Kalshi event title
and puts kickoff at noon UTC on the ticker date, then asks the real fetch
whether it would keep the row. Noon is early enough that a ticker date
inside the horizon is not rejected for the hour we guessed.

A Kalshi title is percent-encoded before it is printed on a ::warning:: or
::error:: line, so a newline in that title cannot emit its own workflow
command. The same list is written to GITHUB_STEP_SUMMARY when that file is
set, because GitHub shows only ten annotations on a step.

Usage:  python3 lane_preflight.py
"""
import http.client
import inspect
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import sandbox_sources as S

# The board fetches default to the same horizon. Reading it off the signature
# means a change there moves this check with it.
BOARD_HORIZON = {
    "three_way": inspect.signature(S.fetch_kalshi_venue).parameters["horizon_days"].default,
    "total": inspect.signature(S.fetch_kalshi_goals).parameters["horizon_days"].default,
    "btts": inspect.signature(S.fetch_kalshi_btts).parameters["horizon_days"].default,
    "p05": inspect.signature(S.fetch_kalshi_goals).parameters["horizon_days"].default,
}
# How far past the board's horizon an open market can sit and still be "the
# window" rather than a contract the parser cannot read.
_WIDE = 40
# A game that has already started is not a typo. Look back this far before
# calling an open-but-unreadable book a parser failure.
_LOOKBACK_DAYS = 7
# _kalshi_open pages this many times. The events fetch the goals board uses
# does not: it reads one page. Match each board.
_MARKET_PAGES = 10
_HOST = "api.elections.kalshi.com"
_MAX_BODY = 8 * 1024 * 1024
_TIMEOUT = 30
# 429 and 5xx are retried this many times. The pause is capped so a burst
# of them stays well inside the 5-minute job.
_RETRY_ATTEMPTS = 3
_RETRY_PAUSE = 0.5

_API = S.KALSHI_API.rsplit("/", 1)[0]


class ProbeError(RuntimeError):
    """Kalshi did not answer. Not a verdict about the series."""


def checks():
    """(lane, series, kind) for the ten lanes, from the module constants.

    kind is which board that series has to reach:
      three_way  the soccer moneyline fetch_kalshi_venue fills
      total      a goals line on the sport the lane is registered on
      btts       the both-teams board
      p05        the side-win / +0.5 board mls_fade_home reads
    """
    return (
        ("ere_draw", S.ERE_DRAW_SERIES, "three_way"),
        ("ere_o15", S.ERE_O15_TOTAL, "total"),
        ("ere_o15", S.ERE_O15_GAME, "three_way"),
        ("bund_o35", S.BUND_O35_TOTAL, "total"),
        ("bund_o35", S.BUND_O35_GAME, "three_way"),
        ("bund_o35_fav", S.BUND_O35_TOTAL, "total"),
        ("bund_o35_fav", S.BUND_O35_GAME, "three_way"),
        ("liga_btts_even", S.LIGA_BTTS, "btts"),
        ("liga_btts_even", S.LIGA_GAME, "three_way"),
        ("liga_u15_dog", S.LIGA_TOTAL, "total"),
        ("liga_u15_dog", S.LIGA_GAME, "three_way"),
        ("turkey_o25_dog", S.TURKEY_TOTAL, "total"),
        ("turkey_o25_dog", S.TURKEY_GAME, "three_way"),
        ("turkey_btts_dog", S.TURKEY_BTTS, "btts"),
        ("turkey_btts_dog", S.TURKEY_GAME, "three_way"),
        ("mls_away_band", S.MLS_GAME, "three_way"),
        ("mls_fade_home", S.MLS_GAME, "three_way"),
        ("mls_fade_home", S.MLS_GAME, "p05"),
    )


def board_sport(lane, kind):
    """The universe key the lane reads for this kind of series."""
    if kind == "three_way":
        return "soccer"
    return S.SOURCES[lane]["sports"][0]


def _series_url(ticker):
    return f"{_API}/series/{ticker}"


def _markets_url(ticker, cursor=""):
    url = f"{S.KALSHI_API}?limit=200&status=open&series_ticker={ticker}"
    if cursor:
        url += "&cursor=" + urllib.parse.quote(cursor, safe="")
    return url


def _events_url(ticker):
    # Same query _kalshi_open_events uses, including the single page.
    return (f"{_API}/events?series_ticker={ticker}&status=open&limit=200"
            f"&with_nested_markets=true")


def kalshi_https(url):
    """True only for https://api.elections.kalshi.com."""
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "") == _HOST


class _StayOnKalshi(urllib.request.HTTPRedirectHandler):
    """Redirects stay on the Kalshi host. Anywhere else is a probe error."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not kalshi_https(newurl):
            raise ProbeError("refusing a redirect off the Kalshi host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_StayOnKalshi)


def read_capped(resp, limit=_MAX_BODY):
    """Response bytes, or ProbeError once `limit` is passed."""
    chunks, total = [], 0
    while True:
        block = resp.read(65536)
        if not block:
            break
        total += len(block)
        if total > limit:
            raise ProbeError(f"response larger than {limit} bytes")
        chunks.append(block)
    return b"".join(chunks)


def _json_object(raw):
    if not raw:
        return {}
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ProbeError(str(exc)) from exc
    if not isinstance(body, dict):
        raise ProbeError("Kalshi JSON was not an object")
    return body


def live_get(url):
    """(status, json) from Kalshi's public API. Raises ProbeError on transport."""
    if not kalshi_https(url):
        raise ProbeError("refusing a request that is not the Kalshi host")
    req = urllib.request.Request(url, headers={"User-Agent": S.UA, "Accept": "application/json"})
    try:
        with _OPENER.open(req, timeout=_TIMEOUT) as resp:
            return resp.status, _json_object(read_capped(resp))
    except urllib.error.HTTPError as exc:
        try:
            raw = read_capped(exc)
        except ProbeError:
            raise
        except (http.client.HTTPException, OSError, UnicodeError, ValueError) as inner:
            raise ProbeError(str(inner)) from inner
        try:
            body = _json_object(raw)
        except ProbeError:
            body = {}
        return exc.code, body
    except ProbeError:
        raise
    except (http.client.HTTPException, OSError, UnicodeError, ValueError) as exc:
        raise ProbeError(str(exc)) from exc


def _retryable(status):
    return status == 429 or (isinstance(status, int) and status >= 500)


def _call(get, url, attempts, pause):
    last = ProbeError(f"no response for {url}")
    tries = max(1, attempts)
    gap = min(float(pause or 0), 1.0)
    for i in range(tries):
        try:
            status, body = get(url)
        except ProbeError as exc:
            last = exc
        except http.client.HTTPException as exc:
            last = ProbeError(str(exc))
        else:
            if _retryable(status):
                last = ProbeError(f"HTTP {status}")
            else:
                return status, body
        if i + 1 < tries and gap:
            time.sleep(gap)
    raise last


def _paged_markets(get, ticker, attempts, pause):
    out, cursor = [], ""
    for _ in range(_MARKET_PAGES):
        status, body = _call(get, _markets_url(ticker, cursor), attempts, pause)
        if status != 200 or not isinstance(body, dict) or "markets" not in body:
            raise ProbeError(f"HTTP {status} for {ticker} markets")
        batch = body.get("markets") or []
        out.extend(batch)
        cursor = body.get("cursor") or ""
        if not cursor or not batch:
            break
    return out


def _open_events(get, ticker, attempts, pause):
    status, body = _call(get, _events_url(ticker), attempts, pause)
    if status != 200 or not isinstance(body, dict) or "events" not in body:
        raise ProbeError(f"HTTP {status} for {ticker} events")
    return body.get("events") or []


def _load(ticker, kinds, get, attempts, pause):
    """One series probe, then the book each kind needs. Failures stay on the dict."""
    try:
        status, body = _call(get, _series_url(ticker), attempts, pause)
    except ProbeError as exc:
        return {"probe_error": str(exc)}
    if status == 404:
        return {"exists": False}
    series = body.get("series") if isinstance(body, dict) else None
    if status != 200 or not isinstance(series, dict) or series.get("ticker") != ticker:
        return {"probe_error": f"HTTP {status} for series {ticker}"}
    info = {"exists": True, "title": series.get("title") or ""}
    if "three_way" in kinds:
        try:
            info["markets"] = _paged_markets(get, ticker, attempts, pause)
        except ProbeError as exc:
            info["markets_error"] = str(exc)
    if kinds & {"total", "btts", "p05"}:
        try:
            info["events"] = _open_events(get, ticker, attempts, pause)
        except ProbeError as exc:
            info["events_error"] = str(exc)
    return info


def _wired(series, kind):
    """True when the fetch that fills this board requests this series."""
    if kind == "three_way":
        return series in (S.KALSHI_VENUE_SERIES.get("soccer") or [])
    suffix = {"total": "TOTAL", "btts": "BTTS", "p05": "GAME"}[kind]
    return any(series == f"KX{frag}{suffix}" for frag in S.BTTS_LEAGUES)


def _objects(items, what):
    """A list of dicts, or ProbeError. None is an empty list."""
    if items is None:
        return []
    if not isinstance(items, list):
        raise ProbeError(f"{what} was not a list")
    for item in items:
        if not isinstance(item, dict):
            raise ProbeError(f"{what} contained a non-object")
    return items


def _count_open(kind, info):
    if kind == "three_way":
        return len(_objects(info.get("markets") or [], "markets"))
    n = 0
    for ev in _objects(info.get("events") or [], "events"):
        raw = ev.get("markets")
        markets = _objects(raw, "nested markets") if raw else []
        # An open event with no nested legs still counts as 1. The events
        # call asked for status=open, and the legs are often listed later.
        n += len(markets) if markets else 1
    return n


def _shell_only(kind, info):
    """True when every open event has no nested markets."""
    if kind == "three_way":
        return False
    events = info.get("events") or []
    if not events:
        return False
    for ev in events:
        if not isinstance(ev, dict) or ev.get("markets"):
            return False
    return True


def _fixtures_from(events):
    """A league fixture per event, noon UTC on the ticker date, same club names."""
    out = []
    for ev in events or []:
        title = str(ev.get("title") or "").split(":")[0]
        parts = [p.strip() for p in title.replace(" vs. ", " vs ").split(" vs ")]
        if len(parts) != 2:
            continue
        date = S.kalshi_date(ev.get("event_ticker") or "")
        if not date:
            continue
        try:
            datetime.fromisoformat(date + "T12:00:00+00:00")
        except ValueError:
            continue
        out.append(dict(
            home=parts[0], away=parts[1], kickoff=date + "T12:00Z",
            played=False, home_goals=None, away_goals=None,
            comp="league", competitive=True,
        ))
    return out


def _three_way_rows(series, markets, now, horizon):
    """Rows fetch_kalshi_venue would keep for this one series. No other series is fetched."""
    if series not in (S.KALSHI_VENUE_SERIES.get("soccer") or []):
        return []
    saved_list = S.KALSHI_VENUE_SERIES["soccer"]
    saved_cache = S._kalshi_open_cache
    try:
        S.KALSHI_VENUE_SERIES["soccer"] = [series]
        S._kalshi_open_cache = {series: list(markets or [])}
        return S.fetch_kalshi_venue("soccer", horizon_days=horizon, now=now)
    finally:
        S.KALSHI_VENUE_SERIES["soccer"] = saved_list
        S._kalshi_open_cache = saved_cache


def _on_board(series, kind, sport, info, now, horizon):
    if kind == "three_way":
        rows = _three_way_rows(series, info.get("markets"), now, horizon)
    elif kind == "btts":
        rows = S.fetch_kalshi_btts(
            horizon_days=horizon, fixtures=_fixtures_from(info.get("events")), now=now,
            events_by_series={series: info.get("events") or []})
    else:
        got = S.fetch_kalshi_goals(
            horizon_days=horizon, fixtures=_fixtures_from(info.get("events")), now=now,
            events_by_series={series: info.get("events") or []})
        rows = got.get(sport) or []
    return sum(1 for r in rows if str(r.get("market_id") or "").startswith(series))


def _result(lane, series, kind, state, level, detail):
    return dict(lane=lane, series=series, kind=kind, state=state, level=level, detail=detail)


def _judge(lane, series, kind, info, now):
    sport = board_sport(lane, kind)
    if info.get("probe_error"):
        return _result(lane, series, kind, "could not check", "error",
                       f"Kalshi request failed ({info['probe_error']})")
    if not info.get("exists"):
        return _result(lane, series, kind, "never seen", "error",
                       "Kalshi has no such series ticker")
    side_error = info.get("markets_error") if kind == "three_way" else info.get("events_error")
    if side_error:
        return _result(lane, series, kind, "could not check", "error",
                       f"Kalshi request failed ({side_error})")
    try:
        n = _count_open(kind, info)
    except ProbeError as exc:
        return _result(lane, series, kind, "could not check", "error",
                       f"Kalshi response was not usable ({exc})")
    title = info.get("title") or ""
    known = "Kalshi knows the series" + (f" ({title})" if title else "")
    if n == 0:
        return _result(lane, series, kind, "exists but no open markets", "warning", known)
    if not _wired(series, kind):
        return _result(lane, series, kind, "listed but not on the board", "error",
                       f"the {sport} board's fetch does not request this series")
    if _shell_only(kind, info):
        noun = "event" if n == 1 else "events"
        return _result(lane, series, kind, "listed but not on the board", "warning",
                       f"{n} open {noun}, no nested markets")
    horizon = BOARD_HORIZON[kind]
    on = _on_board(series, kind, sport, info, now, horizon)
    if on:
        return _result(lane, series, kind, "listed", "ok",
                       f"{n} open, {on} on the {sport} board")
    earlier = now - timedelta(days=_LOOKBACK_DAYS)
    if (_on_board(series, kind, sport, info, now, _WIDE)
            or _on_board(series, kind, sport, info, earlier, _WIDE)):
        return _result(lane, series, kind, "listed but not on the board", "warning",
                       f"{n} open, none inside the window the {sport} board reads")
    return _result(lane, series, kind, "listed but not on the board", "error",
                   f"the {sport} board drops every open market")


def encode_workflow(text, for_property=False):
    """Percent-encode workflow-command data. % first, then CR and LF.

    Property values also encode ':' and ',' so a title cannot close the
    property list or start the message early.
    """
    out = str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if for_property:
        out = out.replace(":", "%3A").replace(",", "%2C")
    return out


def workflow_command(level, message, **properties):
    """One ::level:: line. Kalshi text cannot break out of it."""
    head = f"::{level}"
    if properties:
        bits = [encode_workflow(key, for_property=True) + "="
                + encode_workflow(value, for_property=True)
                for key, value in properties.items()]
        head += " " + ",".join(bits)
    return head + "::" + encode_workflow(message)


def evaluate(get, now=None, attempts=_RETRY_ATTEMPTS, pause=_RETRY_PAUSE):
    """One result per lane series. `get` is live_get or a stub of the same shape."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    needed = {}
    order = checks()
    for _lane, series, kind in order:
        needed.setdefault(series, set()).add(kind)
    loaded = {series: _load(series, kinds, get, attempts, pause)
              for series, kinds in needed.items()}
    return [_judge(lane, series, kind, loaded[series], now) for lane, series, kind in order]


def format_result(row):
    line = f"{row['lane']} {row['series']} {row['state']}"
    if row.get("detail"):
        line += f" - {row['detail']}"
    return line


def render(results, now):
    """(text, exit code). Never-seen, an unreadable open book, and a failed
    request are exit 1. An empty book, a window miss, and an event that is
    open before its legs are listed are warnings."""
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    lines = [f"{stamp} lane pre-flight"]
    failed = []
    for row in results:
        raw = format_result(row)
        safe = encode_workflow(raw)
        lines.append(safe)
        if row["level"] == "error":
            lines.append(workflow_command("error", raw))
            failed.append(safe)
        elif row["level"] == "warning":
            lines.append(workflow_command("warning", raw))
    if failed:
        lines.append(f"FAILED: {len(failed)} lane series")
        for line in failed:
            lines.append("  " + line)
        return "\n".join(lines) + "\n", 1
    lines.append(f"ok: {len(results)} lane series")
    return "\n".join(lines) + "\n", 0


def summary_text(results, now):
    """The full list, one lane a line. The step log only shows ten annotations."""
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    lines = [f"### Lane pre-flight {stamp}", ""]
    for row in results:
        flat = format_result(row).replace("\r", " ").replace("\n", " ")
        lines.append("- " + flat)
    failed = [row for row in results if row["level"] == "error"]
    lines.append("")
    if failed:
        lines.append(f"FAILED: {len(failed)} lane series")
    else:
        lines.append(f"ok: {len(results)} lane series")
    return "\n".join(lines) + "\n"


def write_step_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)


STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                     "lane_preflight.json")


def save(results, now, path=STATE):
    """Persist the last verdict per lane series, for the Soccer page to render.

    The page cannot call Kalshi itself: it is rebuilt every three hours by the tracker,
    and a live venue call there would turn a Kalshi hiccup into a failed publish. This
    file is written by THIS job, which is allowed to go red on its own without taking
    anything else down, and the page reads it and says how old it is.
    """
    blob = dict(checked=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                lanes=[{k: r.get(k) for k in ("lane", "series", "kind", "state", "detail")}
                       for r in results])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
    return blob


def main():
    now = datetime.now(timezone.utc)
    results = evaluate(live_get, now=now)
    text, code = render(results, now)
    sys.stdout.write(text)
    write_step_summary(summary_text(results, now))
    try:
        save(results, now)
    except OSError as e:
        # Never fail the pre-flight over a file: its job is to report on Kalshi.
        print(f"::warning::could not write {STATE} ({type(e).__name__})")
    return code


if __name__ == "__main__":
    sys.exit(main())
