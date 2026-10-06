"""The SofaScore-style shell.

The site root lands here with Production selected. Page pills go to the
existing Sandbox, Production, Trading, and Method pages. Sport pills stay
inert: they do not filter, navigate, or take focus.

Running rows are presentation. They reuse the Production feed and the same
quote gates that feed already uses. They do not settle, assess, or rewrite a
ledger. Page pills leave this page, so the list is Production lanes only; a
row's lane pill reads Production. One row per contest. Several Production
lanes on that contest show an N-lanes count.

Settled rows use production.KEEP_SETTLED_DAYS, the same kickoff cutoff as
production.build_feed, so this list matches the recent leads on
production.html. The clock is the `now` the caller passed, the same instant
as production.html.
"""
import datetime

import fmt
import production
import sandbox_build
import sandbox_sources as S
import sandbox_track as T
import site_chrome

SPORTS = (
    ("all", "All"),
    ("nba", "NBA"),
    ("soccer", "Soccer"),
    ("tennis", "Tennis"),
    ("cricket", "Cricket"),
    ("crypto", "Crypto"),
)
PAGES = (
    ("Sandbox", "./sandbox.html", False),
    ("Production", "./production.html", True),
    ("Trading", "./trading.html", False),
    ("Method", "./sandbox.html#method", False),
)
RUNNING = (("live", "Live", True), ("settled", "Settled", False), ("upcoming", "Upcoming", False))
_GROUP_ORDER = ("NBA", "Soccer", "Tennis", "Cricket", "Crypto", "Markets")
_STATUS = {
    "pending": "Open",
    "open": "Open",
    "hit": "W",
    "won": "W",
    "miss": "L",
    "lost": "L",
    "void": "Void",
    "price": "price result",
    "settled": "price result",
}
_EMPTY = {
    "live": "No live paper bets",
    "settled": "No settled paper bets",
    "upcoming": "No upcoming paper bets",
}
_QUOTE_SETTLED = ("won", "lost", "void", "settled")


def tiles_html(html):
    """Copy the Production headline strip out of a page that already built it."""
    start = html.find('<div class="tiles">')
    if start < 0:
        raise RuntimeError("Production board has no headline tiles")
    depth = 0
    i = start
    while i < len(html):
        if html.startswith("<div", i):
            depth += 1
            i = html.find(">", i) + 1
            continue
        if html.startswith("</div>", i):
            depth -= 1
            i += len("</div>")
            if depth == 0:
                return html[start:i]
            continue
        i += 1
    raise RuntimeError("Production headline tiles are not closed")


def production_summary(d, st, blob, now):
    """The four Production tiles. page() does the counting; this only displays it."""
    return tiles_html(production.page(d, st, blob, "", now=now))


def _load(d, st, blob):
    if d is None or st is None or blob is None:
        if d is None:
            d = T.load()
        if st is None:
            st = T.load_stages()
        if blob is None:
            blob = production.load_feed()
    return d, st, blob


def _now(now):
    if isinstance(now, datetime.datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=datetime.timezone.utc)
        return now.astimezone(datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def _stamp(now):
    if isinstance(now, datetime.datetime):
        return site_chrome.stamp(_now(now), machine=False)
    return site_chrome.esc(str(now))


def _page_pills():
    parts = []
    for label, href, current in PAGES:
        attr = ' aria-current="page"' if current else ""
        parts.append(f'<a href="{site_chrome.esc(href)}"{attr}>{site_chrome.esc(label)}</a>')
    return "".join(parts)


def _sport_pills():
    """Inert chrome. aria-disabled and out of the tab order, not a filter."""
    parts = []
    for key, label in SPORTS:
        parts.append(
            f'<button type="button" data-sport="{site_chrome.esc(key)}" '
            f'aria-disabled="true" tabindex="-1" aria-describedby="sports-soon">'
            f'{site_chrome.esc(label)}</button>')
    return "".join(parts)


def _running_filters(counts):
    parts = []
    for key, label, pressed in RUNNING:
        parts.append(
            f'<button type="button" data-filter="{site_chrome.esc(key)}" '
            f'aria-pressed="{"true" if pressed else "false"}">'
            f'{site_chrome.esc(label)} <span class="count">{int(counts.get(key, 0))}</span></button>')
    return "".join(parts)


def _sport_label(sport):
    try:
        return sandbox_build.family(sport or "")
    except Exception:
        text = S.SPORTS.get(sport, sport or "Other")
        return str(text).split(" · ")[0] or "Other"


def _status_label(status):
    return _STATUS.get(status, "Void")


def _in_window(instant, now):
    """True when `instant` is inside production's settled-lead cutoff.

    production.build_feed drops a settled bet when its kickoff is strictly
    older than `now - KEEP_SETTLED_DAYS`. Reading that name here, not a copy
    of the number, keeps the two windows the same if the feed's window moves.
    """
    if instant is None or now is None:
        return False
    try:
        return not instant < now - datetime.timedelta(days=production.KEEP_SETTLED_DAYS)
    except TypeError:
        return False


def _cents(price):
    try:
        return fmt.cents(price)
    except (TypeError, ValueError, OverflowError):
        return "—"


def _when_text(kickoff):
    if kickoff is None:
        return "—"
    try:
        return fmt.when(kickoff)
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def _time_text(bucket, kickoff, now):
    """Live, the kickoff clock on the build date, or a relative day."""
    if bucket == "live":
        return "Live"
    if kickoff is None:
        return "—"
    today = production._chicago_day(now)
    day = production._chicago_day(kickoff)
    if today is None or day is None:
        return "—"
    delta = (day - today).days
    if delta == -1:
        return "Yesterday"
    if delta == 0:
        try:
            return fmt.clock(kickoff)
        except (TypeError, ValueError, OverflowError, OSError):
            return "—"
    try:
        return production._day_label(day, today)
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def _lane_from_lead(lead, settled_at=None):
    if not isinstance(lead, dict):
        return None
    if S.removed_row(lead) or production._weather_pair(lead.get("pair") or ""):
        return None
    kickoff = production._one_instant(lead.get("kickoff"))
    home, away = lead.get("home"), lead.get("away")
    if home is not None:
        home = str(home)
    if away is not None:
        away = str(away)
    return {
        "pair": str(lead.get("pair") or ""),
        "quote_id": lead.get("sandbox_quote") or lead.get("id"),
        "sport": _sport_label(lead.get("sport")),
        "home": home,
        "away": away,
        "match": str(lead.get("match") or ""),
        "competition": str(lead.get("league") or ""),
        "kickoff": kickoff,
        "price": lead.get("price_at_log"),
        "status": _status_label(lead.get("status")),
        "lane": "Sandbox" if lead.get("lane") == "sandbox" else "Production",
        "settled_at": settled_at,
    }


def _keeps(lane, now):
    if lane["status"] == "Open":
        return True
    return _in_window(lane.get("kickoff"), now)


def _contest_key(lane):
    day = production._chicago_day(lane.get("kickoff"))
    day_key = day.isoformat() if day is not None else ""
    home, away = lane.get("home"), lane.get("away")
    if home and away:
        sides = tuple(sorted((home.casefold(), away.casefold())))
        return ("sides", lane["sport"], sides, day_key)
    return ("match", lane["sport"], (lane.get("match") or "").casefold(), day_key)


def _contest_bucket(items, now):
    opens = [lane for lane in items if lane["status"] == "Open"]
    if not opens:
        return "settled"
    started = [lane for lane in opens
               if lane.get("kickoff") is not None and lane["kickoff"] <= now]
    if started:
        return "live"
    return "upcoming"


def _contest_status(items):
    if any(lane["status"] == "Open" for lane in items):
        return "Open"
    labels = []
    for lane in items:
        if lane["status"] not in labels:
            labels.append(lane["status"])
    if len(labels) == 1:
        return labels[0]
    return items[0]["status"]


def _extra_quote_lanes(d, st, shown, now):
    """Live bets, and settled bets the feed no longer carries.

    Upcoming quotes stay on the feed. This does not widen placeable() or
    start_verified(); a quote those two already refuse stays off the list.
    """
    if not d or "quotes" not in d or not st:
        return []
    pairs = {key: pair for key, pair in production.production_pairs(st).items()
             if not production._weather_pair(key)}
    if not pairs:
        return []
    built = now.replace(microsecond=0).isoformat()
    out = []
    try:
        rows = T.bet_rows(d)
    except (KeyError, TypeError):
        return []
    for key, pair in pairs.items():
        source, sport = key.split("|", 1)
        if S.lane_removed(source, sport):
            continue
        entered = production.entered_at(pair)
        for quote in rows:
            if quote.get("source") != source or quote.get("sport") != sport or not quote.get("bet"):
                continue
            if S.removed_row(quote):
                continue
            qid = quote.get("id")
            if qid and qid in shown:
                continue
            try:
                kickoff = production._kickoff(quote)
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
            if kickoff is None:
                continue
            try:
                if kickoff.isoformat() < entered:
                    continue
            except TypeError:
                continue
            status = quote.get("status")
            settled_at = production._one_instant(quote.get("settled"))
            if status == "open":
                if kickoff > now:
                    continue
            elif status in _QUOTE_SETTLED:
                if not _in_window(kickoff, now):
                    continue
            else:
                continue
            if not T.placeable(quote) or not production.start_verified(quote):
                continue
            try:
                lead = production.lead_from_quote(quote, key, built)
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
            lane = _lane_from_lead(lead, settled_at=settled_at)
            if lane is None:
                continue
            out.append(lane)
            if qid:
                shown.add(qid)
    return out


def collect_lanes(d, st, blob, now):
    """Production lanes for the Running list. Display only."""
    lanes = []
    shown = set()
    for lead in ((blob or {}).get("leads") or {}).values():
        lane = _lane_from_lead(lead)
        if lane is None or not _keeps(lane, now):
            continue
        lanes.append(lane)
        if lane.get("quote_id"):
            shown.add(lane["quote_id"])
    lanes.extend(_extra_quote_lanes(d, st, shown, now))
    return lanes


def contests_from_lanes(lanes, now):
    """One contest per event. The representative lane is the first pair name."""
    grouped = {}
    for lane in lanes:
        grouped.setdefault(_contest_key(lane), []).append(lane)
    contests = []
    for items in grouped.values():
        items.sort(key=lambda lane: (lane.get("pair") or "", str(lane.get("quote_id") or "")))
        kickoff = min((lane["kickoff"] for lane in items if lane.get("kickoff") is not None),
                      default=None)
        rep = next((lane for lane in items if lane["status"] == "Open"), items[0])
        competition = next((lane["competition"] for lane in items if lane.get("competition")), "")
        contests.append({
            "sport": items[0]["sport"] or "Other",
            "match": rep.get("match") or items[0].get("match") or "",
            "competition": competition,
            "kickoff": kickoff,
            "price": rep.get("price"),
            "status": _contest_status(items),
            "bucket": _contest_bucket(items, now),
            "pill": "Production" if any(lane["lane"] == "Production" for lane in items) else "Sandbox",
            "lanes": len({lane["pair"] for lane in items if lane.get("pair")}) or len(items),
        })
    return contests


def _group_key(label):
    try:
        return (0, _GROUP_ORDER.index(label))
    except ValueError:
        return (1, label.lower())


def _row_html(contest, index, now):
    bucket = contest["bucket"]
    hidden = "" if bucket == "live" else " hidden"
    lanes = ""
    if contest["lanes"] > 1:
        lanes = f'<span class="lane-n">{int(contest["lanes"])} lanes</span>'
    competition = contest["competition"] or "—"
    name = contest["match"] or "—"
    kickoff = _when_text(contest["kickoff"])
    price = _cents(contest["price"])
    esc = site_chrome.esc
    return (
        f'<button type="button" class="running-row"'
        f' data-filter="{esc(bucket)}" data-contest="c{index}"'
        f' data-competition="{esc(competition)}" data-sport="{esc(contest["sport"])}"'
        f' data-name="{esc(name)}" data-kickoff="{esc(kickoff)}" data-price="{esc(price)}"'
        f' aria-pressed="false"{hidden}>'
        f'<span class="running-time">{esc(_time_text(bucket, contest["kickoff"], now))}</span>'
        f'<span class="running-contest">{esc(name)}</span>'
        f'<span class="running-price">{esc(price)}</span>'
        f'<span class="running-meta">'
        f'<span class="running-status" data-status="{esc(contest["status"])}">{esc(contest["status"])}</span>'
        f'<span class="running-pills"><span class="lane-pill">{esc(contest["pill"])}</span>{lanes}</span>'
        f'</span></button>'
    )


def _running_body(d, st, blob, now):
    contests = contests_from_lanes(collect_lanes(d, st, blob, now), now)
    by_sport = {}
    for contest in contests:
        by_sport.setdefault(contest["sport"], []).append(contest)
    counts = {key: 0 for key, _label, _pressed in RUNNING}
    for contest in contests:
        counts[contest["bucket"]] = counts.get(contest["bucket"], 0) + 1
    groups = []
    number = 0
    for label in sorted(by_sport, key=_group_key):
        items = sorted(by_sport[label],
                       key=lambda contest: (contest["kickoff"] is None,
                                            contest["kickoff"] or datetime.datetime.max.replace(
                                                tzinfo=datetime.timezone.utc)))
        rows = []
        for contest in items:
            rows.append(_row_html(contest, number, now))
            number += 1
        hidden = "" if any(contest["bucket"] == "live" for contest in items) else " hidden"
        groups.append(
            f'<section class="running-group" data-sport-group="{site_chrome.esc(label)}"{hidden}>'
            f'<h3>{site_chrome.esc(label)}</h3>'
            f'<div>{"".join(rows)}</div>'
            f'</section>')
    empty_hidden = "" if counts["live"] == 0 else " hidden"
    empty = (
        f'<p class="shell-empty" id="running-empty"{empty_hidden}'
        f' data-live="{site_chrome.esc(_EMPTY["live"])}"'
        f' data-settled="{site_chrome.esc(_EMPTY["settled"])}"'
        f' data-upcoming="{site_chrome.esc(_EMPTY["upcoming"])}">'
        f'{site_chrome.esc(_EMPTY["live"])}</p>'
    )
    return _running_filters(counts), "".join(groups), empty


def page(now, d=None, st=None, blob=None, tiles=None):
    """The shell document.

    Pass `tiles` to reuse a strip already computed for production.html. Omitting
    it builds that strip from `d`, `st`, and `blob` (the live board by default)
    for callers that are not the tracker build. Running rows use `now` either way
    and do not count the tiles again.
    """
    when = _now(now)
    if tiles is None:
        d, st, blob = _load(d, st, blob)
        summary = production_summary(d, st, blob, when)
    else:
        summary = tiles
        if d is None or st is None or blob is None:
            d, st, blob = _load(d, st, blob)
    filters, groups, empty = _running_body(d, st, blob, when)
    body = f"""<h1 class="sr-only">Edge Machine · Production</h1>
<section class="shell-summary" aria-label="Production totals" data-board="production">
{summary}
</section>
<div class="shell-columns">
<section class="shell-pane" aria-labelledby="running-title">
<h2 id="running-title">Running</h2>
<p class="shell-kicker">Production lanes</p>
<div class="running-filters" role="group" aria-label="Running filters">
{filters}
</div>
<div class="running-list" id="running-list">
{groups}
</div>
{empty}
</section>
<section class="shell-pane" aria-labelledby="rules-title">
<div class="pane-head">
<h2 id="rules-title">Rules applied</h2>
<a class="full-page" href="./production.html">Full page →</a>
</div>
<div class="rules-head" id="rules-head" hidden>
<p class="rules-line" id="rules-line"></p>
</div>
<p class="shell-empty" id="rules-empty">Select a contest in Running.</p>
</section>
</div>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine</title>
<meta name="description" content="Production headlines, and the paper bets on those lanes.">
<link rel="stylesheet" href="./site.css">
{site_chrome.CSP}
{site_chrome.REFERRER}
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header class="site">
<div class="bet-roll">
<p class="bet-roll-label">Open &amp; recent</p>
<div class="bet-roll-track">
<p class="bet-roll-empty">No open or recent paper bets yet.</p>
</div>
</div>
<div class="topbar">
<a class="brand" href="./index.html">Edge Machine</a>
<nav class="main" aria-label="Pages">{_page_pills()}</nav>
<p class="stamp">{_stamp(now)}</p>
</div>
<div class="sport-row">
<nav class="sports" aria-label="Sports" aria-describedby="sports-soon">{_sport_pills()}</nav>
<p id="sports-soon" class="sports-soon">Coming soon</p>
</div>
</header>
<main id="content" class="wrap">
{body}
</main>
<script src="./tables.js"></script>
<script src="./shell.js"></script>
</body>
</html>
"""
