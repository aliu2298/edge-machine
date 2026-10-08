"""The Analyst Desk production shell.

The site root. It wears the same header as every other page. Sport pills
inside the Running pane filter the list in place. They do not navigate, and
All starts pressed; a sport with no lane on the list has no pill.

Running rows are presentation. They reuse the Production feed and the same
quote gates that feed already uses. They do not settle, assess, or rewrite a
ledger. Page pills leave this page, so the list is Production lanes only; a
row's lane pill reads Production. One row per contest. Several bets on that
contest show an N-lanes count and, on the right, one Rules-applied card each.
Card verdicts, ROI, and records come from the helpers the sport pages already
call. This file does not compute a new one.

Settled rows cover SHELL_SETTLED_DAYS Chicago dates, today included. Days
still inside production.KEEP_SETTLED_DAYS come from the same feed
production.html uses. Older days inside this window come from the quote
ledger, through the same status and price path. The clock is the `now`
the caller passed, the same instant as production.html.
"""
import datetime
import json
import re

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
    ("commodities", "Commodities"),
)
RUNNING = (("live", "Live", True), ("settled", "Settled", False), ("upcoming", "Upcoming", False))
_GROUP_ORDER = ("NBA", "Soccer", "Tennis", "Cricket", "Crypto", "Commodities", "Markets")
PRICE_LABEL = "No result · paid 50¢"
# Chicago dates on the Running Settled list, today included. Not
# production.KEEP_SETTLED_DAYS: that cutoff still belongs to production.html.
SHELL_SETTLED_DAYS = 14
_STATUS = {
    "pending": "Open",
    "open": "Open",
    "hit": "W",
    "won": "W",
    "miss": "L",
    "lost": "L",
    "void": "Void",
    "price": PRICE_LABEL,
    "settled": PRICE_LABEL,
}
_EMPTY = {
    "live": "No paper bet is in play right now. Settled and upcoming bets sit under the other two filters.",
    "settled": f"Nothing settled in the last {SHELL_SETTLED_DAYS} days.",
    "upcoming": "No paper bet is waiting on a start time. New leads appear here when a Production lane fires.",
}
# A bet the venue paid out at a price instead of a win or a loss (an
# abandoned match, for example). The ledger stores it as "price"/"settled".
PRICE_TOKEN = "price"
_STATUS_TOKEN = {
    "Open": "Open",
    "W": "W",
    "L": "L",
    "Void": "Void",
    PRICE_LABEL: PRICE_TOKEN,
    "Awaiting result": "awaiting",
    "mixed": "mixed",
}
_QUOTE_SETTLED = ("won", "lost", "void", "settled")
# An open bet still ungraded this long after kickoff stays in Live, but the
# row says "Awaiting result" instead of Open. The name is read on each call.
SHELL_AWAIT_HOURS = 6
# Sport pages that already exist. Anything else stays on the Production board.
_SPORT_PAGES = {
    "soccer": "./soccer.html",
    "tennis": "./tennis.html",
    "cricket": "./cricket.html",
    "nba": "./nba.html",
    "crypto": "./crypto.html",
    # The favourite-band lane only. The commodity price baseline and the gasoline
    # rule trade the `commodities` domain and file under Markets, so a prefix that
    # caught them would send their rows to a page they are not on.
    "commodities_fav": "./commodities.html",
}


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


def _sport_pills(present=None):
    """Filter the Running list. All starts pressed. The choice is not stored.

    `present` is the set of sport labels with at least one lane on the list.
    A sport with nothing to show gets no pill: a filter that empties every
    bucket is a dead control. All is always there. None keeps every pill.
    """
    parts = []
    for key, label in SPORTS:
        if present is not None and key != "all" and label not in present:
            continue
        pressed = "true" if key == "all" else "false"
        parts.append(
            f'<button type="button" data-sport="{site_chrome.esc(key)}" '
            f'aria-pressed="{pressed}">'
            f'{site_chrome.esc(label)}</button>')
    return "".join(parts)


def _running_filters(counts):
    """Live / Settled / Upcoming. Each count is paper bets (lanes), not contests."""
    parts = []
    for key, label, pressed in RUNNING:
        described = ' aria-describedby="settled-caption"' if key == "settled" else ""
        parts.append(
            f'<button type="button" data-filter="{site_chrome.esc(key)}" '
            f'aria-pressed="{"true" if pressed else "false"}"{described}>'
            f'{site_chrome.esc(label)} <span class="count">{int(counts.get(key, 0))}</span>'
            f'<span class="sr-only"> paper bets</span></button>')
    return "".join(parts)


def _sport_label(sport):
    try:
        return sandbox_build.family(sport or "")
    except Exception:
        text = S.SPORTS.get(sport, sport or "Other")
        return str(text).split(" · ")[0] or "Other"


def _status_token(label):
    """The short data-status value a style or a test can hook. Unknown labels pass through."""
    return _STATUS_TOKEN.get(label, label)


def _status_html(cls, label, spoken, token):
    """A status with its spoken form. The spoken line is only added when it differs,
    so assistive tech never reads the same words twice."""
    esc = site_chrome.esc
    inner = esc(label)
    if spoken and spoken != label:
        inner = f'<span aria-hidden="true">{esc(label)}</span><span class="sr-only">{esc(spoken)}</span>'
    return f'<span class="{esc(cls)}" data-status="{esc(token)}">{inner}</span>'


def _status_label(status):
    """Open / W / L / Void / No result · paid 50¢. Anything else stays neutral.

    A status this map does not know is not a void. A real string is shown as
    itself (escaped at render). Missing statuses read Unknown.
    """
    if status in _STATUS:
        return _STATUS[status]
    if isinstance(status, str) and status.strip():
        return status.strip()
    return "Unknown"


def _in_production_window(instant, now):
    """True when `instant` is still inside production.build_feed's cutoff.

    The feed drops a settled bet when its kickoff is strictly older than
    `now - KEEP_SETTLED_DAYS`. Those days stay the feed's job. The name is
    read on each call, not copied.
    """
    if instant is None or now is None:
        return False
    try:
        return not instant < now - datetime.timedelta(days=production.KEEP_SETTLED_DAYS)
    except TypeError:
        return False


def _in_shell_window(instant, now):
    """True when the kickoff's Chicago date is inside SHELL_SETTLED_DAYS.

    Today is included. The date SHELL_SETTLED_DAYS ago is not. The name is
    read on each call, so moving the constant moves this window.
    """
    if instant is None or now is None:
        return False
    today = production._chicago_day(now)
    day = production._chicago_day(instant)
    if today is None or day is None:
        return False
    try:
        return 0 <= (today - day).days < SHELL_SETTLED_DAYS
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
    """Live, or the kickoff as "Today, 6:00 AM CT" / "Oct 9, 8:50 AM CT".

    The same clock form as every other page. Only today and the two
    neighbouring days get a word, and they keep the time.
    """
    if bucket == "live":
        return "Live"
    if kickoff is None:
        return "—"
    try:
        return fmt.when_relative(kickoff, now)
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
    route = lead.get("route") if isinstance(lead.get("route"), dict) else {}
    venue = route.get("venue")
    if venue is None:
        venue = lead.get("venue")
    pair = str(lead.get("pair") or "")
    source = lead.get("source") or pair.split("|", 1)[0]
    edge = lead.get("edge_at_log") if "edge_at_log" in lead else lead.get("edge")
    return {
        "pair": pair,
        "quote_id": lead.get("sandbox_quote") or lead.get("id"),
        "sport": _sport_label(lead.get("sport")),
        "sport_key": str(lead.get("sport") or ""),
        "source": str(source or ""),
        "home": home,
        "away": away,
        "match": str(lead.get("match") or ""),
        "headline": str(lead.get("headline") or ""),
        "competition": str(lead.get("league") or ""),
        "kickoff": kickoff,
        "price": lead.get("price_at_log"),
        "edge": edge,
        "venue": None if venue is None else str(venue),
        "status": _status_label(lead.get("status")),
        "lane": "Sandbox" if lead.get("lane") == "sandbox" else "Production",
        "settled_at": settled_at,
    }


def _settled_status(status):
    """A graded result. Open and anything this map does not know are not graded."""
    return status in ("W", "L", "Void", PRICE_LABEL)


def _keeps(lane, now):
    if lane["status"] == "Open":
        return True
    kick = lane.get("kickoff")
    # An unknown status is not a void and not a drop. A future kickoff stays
    # on the list so it can sit in Upcoming; a past one uses the settled window.
    if not _settled_status(lane.get("status")) and kick is not None and kick > now:
        return True
    return _in_shell_window(kick, now)


def _contest_sides(lane):
    """Home and away, or the two sides Production writes into the match title.

    A Production lead's match is ``{home} v {away}`` whenever it has sides.
    A second lead for that fixture can carry the title and not the sides.
    Both have to share one key, or the contest splits into two rows.
    """
    home, away = lane.get("home"), lane.get("away")
    if home and away:
        return str(home).strip(), str(away).strip()
    match = str(lane.get("match") or "")
    parts = match.split(" v ")
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return None, None


def _contest_key(lane):
    """Sport, the two sides in either order, and the Chicago day.

    Reversed home and away on the same Chicago day are one contest. A same-day
    doubleheader is too: both games share those sides and that day, so they
    share a row. Kickoffs that fall on different Chicago dates stay apart.
    """
    day = production._chicago_day(lane.get("kickoff"))
    day_key = day.isoformat() if day is not None else ""
    home, away = _contest_sides(lane)
    if home and away:
        sides = tuple(sorted((home.casefold(), away.casefold())))
        return ("sides", lane["sport"], sides, day_key)
    return ("match", lane["sport"], (lane.get("match") or "").casefold(), day_key)


def _contest_bucket(items, now):
    opens = [lane for lane in items if lane["status"] == "Open"]
    if not opens:
        # No open bet. Graded bets are Settled. An unknown status follows
        # its kickoff: still to come is Upcoming, already started is Settled.
        future = [lane for lane in items
                  if lane.get("kickoff") is not None and lane["kickoff"] > now
                  and not _settled_status(lane.get("status"))]
        if items and len(future) == len(items):
            return "upcoming"
        return "settled"
    started = [lane for lane in opens
               if lane.get("kickoff") is not None and lane["kickoff"] <= now]
    if started:
        return "live"
    return "upcoming"


# Visual token and spoken phrase for each bet status. W and L glue to the
# count ("1W", "2L"); the words stay separate ("1 void", "1 open").
_COMBO_ORDER = ("W", "L", PRICE_LABEL, "Void", "Awaiting result", "Open")
_COMBO_TOKEN = {
    "W": "W",
    "L": "L",
    PRICE_LABEL: "no result",
    "Void": "void",
    "Awaiting result": "awaiting",
    "Open": "open",
}
_SPOKEN = {
    "W": "won",
    "L": "lost",
    PRICE_LABEL: "no result, paid 50 cents",
    "Void": "void",
    "Awaiting result": "awaiting result",
    "Open": "open",
}


def _status_face(items, statuses=None):
    """One contest row, one result line, counted per bet.

    A single bet keeps its own label (W, L, Open, Void, No result · paid 50¢,
    Awaiting result). Several bets add up: 2W, 1W 1L, 1L 1 awaiting. The
    spoken line is what a screen reader should say instead of the letters.
    `statuses` overrides each lane's stored status, so an open bet past the
    await window can read Awaiting result without leaving the Live bucket.
    """
    counts = {}
    labels = statuses if statuses is not None else [lane["status"] for lane in items]
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return {"visual": "—", "spoken": "unknown", "data": ""}
    if total == 1:
        label = next(iter(counts))
        return {"visual": label, "spoken": _SPOKEN.get(label, label), "data": label}
    visual = []
    spoken = []
    for label in _COMBO_ORDER:
        n = counts.get(label, 0)
        if not n:
            continue
        token = _COMBO_TOKEN[label]
        if label in ("W", "L"):
            visual.append(f"{n}{token}")
        else:
            visual.append(f"{n} {token}")
        spoken.append(f"{n} {_SPOKEN.get(label, label)}")
    for label, n in counts.items():
        if label in _COMBO_ORDER or not n:
            continue
        visual.append(f"{n} {label}")
        spoken.append(f"{n} {label}")
    data = next(iter(counts)) if len(counts) == 1 else "mixed"
    return {"visual": " ".join(visual), "spoken": ", ".join(spoken), "data": data}


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
                # Days the feed still carries stay on the feed. The ledger
                # only fills the older days that are still inside the shell window.
                if _in_production_window(kickoff, now) or not _in_shell_window(kickoff, now):
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


def _bet_awaiting(lane, now):
    """An open bet whose kickoff is strictly more than SHELL_AWAIT_HOURS ago."""
    if lane.get("status") != "Open" or now is None:
        return False
    kick = lane.get("kickoff")
    if kick is None:
        return False
    try:
        return now - kick > datetime.timedelta(hours=SHELL_AWAIT_HOURS)
    except TypeError:
        return False


def _shown_status(lane, now):
    """The status a card and the result line show.

    An open bet past the await window stays in the Live bucket, but it no
    longer reads Open. The lane's own status is left as Open so the bucket
    still sees an open bet.
    """
    if _bet_awaiting(lane, now):
        return "Awaiting result"
    return lane.get("status") or "Unknown"


def _price_text(items):
    """Every bet's cents, in card order. One price stays a single figure."""
    parts = [_cents(lane.get("price")) for lane in items]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0]
    return " / ".join(parts)


def _lane_name(source, sport_key):
    """The rule or tipster label the Sandbox and Production pages already print."""
    if not S.SOURCES.get(source):
        return str(source or "") or "—"
    return S.scoped_rule(source, sport_key) or "—"


def _venue_name(venue):
    """The venue badge, from the same source label the board prints. Omit if absent.

    ``kalshi_binary`` is the ledger's name for a Kalshi yes/no contract. It is
    not its own source. The board's Kalshi label is the one the badge uses.
    """
    if venue is None or venue == "":
        return None
    key = "kalshi" if str(venue) == "kalshi_binary" else str(venue)
    meta = S.SOURCES.get(key) or {}
    label = meta.get("label")
    if label:
        return str(label).split(" (")[0]
    return str(venue)


def _quote_venues(d):
    """Quote id to the venue on that paper-bet row. The feed lead often omits it."""
    found = {}
    if not isinstance(d, dict):
        return found
    try:
        rows = T.bet_rows(d)
    except (KeyError, TypeError):
        return found
    for quote in rows:
        qid = quote.get("id")
        venue = quote.get("venue")
        if qid and venue and qid not in found:
            found[qid] = str(venue)
    return found


def _edge_text(edge):
    """Edge already stored on the lead, in the board's percent format. None omits it."""
    if edge is None or edge == "":
        return None
    try:
        text = fmt.pct(float(edge), digits=1, sign=True)
    except (TypeError, ValueError, OverflowError):
        return None
    if not text or text == "—":
        return None
    return text


def _lane_board(d, st, pair_key, cache):
    """Verdict, ROI after fees, and record from the helpers the sport pages use.

    `pair_status` is the Sandbox row's assess. `verdict` and `pct` are the
    words and the ROI that row already prints. Nothing here is a new formula.
    A missing sample omits ROI and record. A missing pair omits all three.
    """
    if pair_key in cache:
        return cache[pair_key]
    found = {"verdict": None, "roi": None, "record": None}
    cache[pair_key] = found
    if not d or not st or not pair_key or "|" not in str(pair_key):
        return found
    source, sport = str(pair_key).split("|", 1)
    try:
        group, assessed, _qa, _open_n, _last, _pair = sandbox_build.pair_status(
            d, st, source, sport)
    except (KeyError, TypeError):
        return found
    if not isinstance(assessed, dict):
        return found
    try:
        key = sandbox_build.verdict(assessed) if group is not None else "nobets"
        found["verdict"] = sandbox_build.VERDICTS[key][0]
    except (KeyError, TypeError):
        found["verdict"] = None
    n = assessed.get("n")
    if not n:
        return found
    roi = assessed.get("roi_fee")
    if roi is not None:
        try:
            text = sandbox_build.pct(roi, sign=True)
        except (TypeError, ValueError, OverflowError):
            text = None
        if text and text != "—":
            found["roi"] = text
    won = assessed.get("won")
    if won is not None:
        try:
            found["record"] = f"{won}\u2013{n - won}"
        except TypeError:
            found["record"] = None
    return found


def _full_page(sport_key):
    """The existing sport page for this lane, or the Production board."""
    key = str(sport_key or "")
    try:
        base = str(sandbox_build._base_sport(key))
    except (TypeError, AttributeError):
        base = key
    for slug, href in _SPORT_PAGES.items():
        if key == slug or key.startswith(slug + "_") or base == slug or base.startswith(slug + "_"):
            return href
    return "./production.html"


def _contest_page(items):
    pages = [_full_page(lane.get("sport_key")) for lane in items]
    chosen = [href for href in pages if href != "./production.html"]
    if chosen and all(href == chosen[0] for href in pages):
        return chosen[0]
    return "./production.html"


def _about(source):
    """The first sentence of the rule's registered note, so every card says what the lane is."""
    meta = S.SOURCES.get(source) or {}
    note = str(meta.get("note") or "").strip()
    if not note:
        return None
    first = re.split(r"(?<=[.!?])\s+", note, maxsplit=1)[0].strip()
    # A bare pre-registration date is not a description. Take the next sentence.
    if re.fullmatch(r"Pre-registered \d{4}-\d{2}-\d{2}\.?", first) and " " in note[len(first):].strip():
        rest = note[len(first):].strip()
        first = re.split(r"(?<=[.!?])\s+", rest, maxsplit=1)[0].strip()
    return first or None


def _card(lane, board):
    """One bet's mini card. Fields the helpers did not compute are left out."""
    status = lane.get("status") or "Unknown"
    card = {
        "lane": _lane_name(lane.get("source") or "", lane.get("sport_key")),
        "pill": "PRODUCTION" if lane.get("lane") == "Production" else "Sandbox",
        "price": _cents(lane.get("price")),
        "status": status,
        "spoken": _SPOKEN.get(status, status),
    }
    about = _about(lane.get("source") or "")
    if about:
        card["about"] = about
    if lane.get("headline"):
        card["market"] = lane["headline"]
    venue = _venue_name(lane.get("venue"))
    if venue:
        card["venue"] = venue
    edge = _edge_text(lane.get("edge"))
    if edge:
        card["edge"] = edge
    if board.get("verdict"):
        card["verdict"] = board["verdict"]
    if board.get("roi"):
        card["roi"] = board["roi"]
    if board.get("record"):
        card["record"] = board["record"]
    # The numbers are that pair's Sandbox record on the US exchanges, every
    # competition together. The sport page splits the same record by competition.
    # pair_status already limits the judged sample to TRADEABLE_VENUES.
    if board.get("verdict") or board.get("roi") or board.get("record"):
        card["stats_note"] = "Sandbox, US exchanges, all competitions"
    return card


def _cards_attr(cards):
    raw = json.dumps(cards, ensure_ascii=True, separators=(",", ":"))
    return site_chrome.esc(raw)


def contests_from_lanes(lanes, now, d=None, st=None):
    """One contest per event. Production bets sort ahead of Sandbox bets."""
    grouped = {}
    for lane in lanes:
        grouped.setdefault(_contest_key(lane), []).append(lane)
    cache = {}
    venues = _quote_venues(d)
    contests = []
    for items in grouped.values():
        items.sort(key=lambda lane: (
            0 if lane.get("lane") == "Production" else 1,
            lane.get("pair") or "",
            str(lane.get("quote_id") or ""),
        ))
        kickoff = min((lane["kickoff"] for lane in items if lane.get("kickoff") is not None),
                      default=None)
        rep = next((lane for lane in items if lane["status"] == "Open"), items[0])
        competition = next((lane["competition"] for lane in items if lane.get("competition")), "")
        # A feed that has no competition falls back to the sport's own name.
        # "Cricket · Cricket" says nothing twice; leave the field out.
        if competition.strip().casefold() == str(items[0]["sport"] or "").strip().casefold():
            competition = ""
        for lane in items:
            if not lane.get("venue"):
                venue = venues.get(lane.get("quote_id"))
                if venue:
                    lane["venue"] = venue
        bucket = _contest_bucket(items, now)
        shown = [_shown_status(lane, now) for lane in items]
        awaiting = bucket == "live" and any(text == "Awaiting result" for text in shown)
        if shown and all(text == "Awaiting result" for text in shown):
            face = {"visual": "Awaiting result", "spoken": "awaiting result", "data": "awaiting"}
        else:
            face = _status_face(items, shown)
        bets = [
            {"status": lane["status"], "price": lane.get("price"), "pair": lane.get("pair")}
            for lane in items
        ]
        cards = [
            _card(dict(lane, status=text), _lane_board(d, st, lane.get("pair"), cache))
            for lane, text in zip(items, shown)
        ]
        contests.append({
            "sport": items[0]["sport"] or "Other",
            "match": rep.get("match") or items[0].get("match") or "",
            "competition": competition,
            "kickoff": kickoff,
            "price": rep.get("price"),
            "price_text": _price_text(items),
            "status": face["visual"],
            "spoken": face["spoken"],
            "data_status": face["data"],
            "awaiting": awaiting,
            "bucket": bucket,
            "page": _contest_page(items),
            "pill": "Production" if any(lane["lane"] == "Production" for lane in items) else "Sandbox",
            "lanes": len({lane["pair"] for lane in items if lane.get("pair")}) or len(items),
            "n_bets": len(items),
            "bets": bets,
            "cards": cards,
        })
    return contests


def _group_key(label):
    try:
        return (0, _GROUP_ORDER.index(label))
    except ValueError:
        return (1, label.lower())


def _sport_letter(label):
    """One letter for the roll. The full sport name stays in the chip for readers."""
    text = str(label or "").strip()
    return text[:1].upper() if text else "?"


_OPEN_CHIP = ("Open", "Awaiting result")
_SETTLED_CHIP = ("W", "L", "Void", PRICE_LABEL)


def _chip_rank(kind, kick, order):
    """Open bets by kickoff, then settled bets newest first. Missing times go last."""
    if kind == "open":
        when = kick.timestamp() if kick is not None else float("inf")
        return (0, when, order)
    when = -kick.timestamp() if kick is not None else float("inf")
    return (1, when, order)


def _chip_html(contest, index, card):
    """One bet. Text is escaped here; the browser does not parse a payload."""
    status = card.get("status") or "Unknown"
    sport = contest.get("sport") or "Other"
    name = fmt.contest(contest.get("match") or "—")
    market = card.get("market") or "—"
    price = card.get("price") or "—"
    spoken = card.get("spoken") or status
    token = _status_token(status)
    esc = site_chrome.esc
    return (
        f'<button type="button" class="bet-chip"'
        f' data-contest="c{index}" data-status="{esc(token)}" aria-pressed="false">'
        f'<span class="bet-chip-letter" aria-hidden="true" title="{esc(sport)}">{esc(_sport_letter(sport))}</span>'
        f'<span class="sr-only">{esc(sport)}: </span>'
        f'<span class="bet-chip-contest" title="{esc(name)}">{esc(name)}</span>'
        f'<span class="bet-chip-line" title="{esc(market)}">{esc(market)} · {esc(price)}</span>'
        f'{_status_html("bet-chip-status", status, spoken, token)}'
        f'</button>'
    )


def _roll_html(ordered):
    """Open chips, then recently settled chips. Same contests as the Running list.

    An open bet past the await window is still an open chip, with the Awaiting
    result status the row already uses. Settled chips are the graded bets on
    contests the 14-day window kept. Nothing else, including a contest outside
    that window, is a chip.
    """
    pending = []
    order = 0
    for index, contest in enumerate(ordered):
        kick = contest.get("kickoff")
        for card in contest.get("cards") or []:
            status = card.get("status") or ""
            if status in _OPEN_CHIP:
                kind = "open"
            elif contest.get("bucket") == "settled" or status in _SETTLED_CHIP:
                kind = "settled"
            else:
                continue
            pending.append((kind, kick, order, _chip_html(contest, index, card)))
            order += 1
    if not pending:
        return '<p class="bet-roll-empty">No open or recent paper bets yet.</p>'
    pending.sort(key=lambda item: _chip_rank(item[0], item[1], item[2]))
    return "".join(item[3] for item in pending)


def _roll_counts(ordered):
    """(open chips, settled chips, won chips): the same bets _roll_html draws.

    A no-result chip is on the settled list and out of this settled count: it is
    neither a win nor a loss, so it must not read as a miss in the landed tile.
    _roll_no_result counts those.
    """
    n_open = n_settled = n_won = 0
    for contest in ordered:
        for card in contest.get("cards") or []:
            status = card.get("status") or ""
            if status in _OPEN_CHIP:
                n_open += 1
            elif status == PRICE_LABEL:
                continue
            elif contest.get("bucket") == "settled" or status in _SETTLED_CHIP:
                n_settled += 1
                if status == "W":
                    n_won += 1
    return n_open, n_settled, n_won


def _roll_no_result(ordered):
    """How many chips on the roll were paid out at a price."""
    return sum(1 for contest in ordered for card in contest.get("cards") or []
               if (card.get("status") or "") == PRICE_LABEL)


def _row_html(contest, index, now):
    bucket = contest["bucket"]
    hidden = "" if bucket == "live" else " hidden"
    lanes = ""
    if contest["lanes"] > 1:
        lanes = f'<span class="lane-n">{int(contest["lanes"])} lanes</span>'
    competition = contest["competition"] or ""
    name = fmt.contest(contest["match"] or "—")
    kickoff = _when_text(contest["kickoff"])
    price = contest.get("price_text") or _cents(contest.get("price"))
    awaiting = ' data-awaiting="true"' if contest.get("awaiting") else ""
    n_bets = int(contest.get("n_bets") or len(contest.get("cards") or ()) or 1)
    esc = site_chrome.esc
    return (
        f'<button type="button" class="running-row"'
        f' data-filter="{esc(bucket)}" data-contest="c{index}"'
        f' data-competition="{esc(competition)}" data-sport="{esc(contest["sport"])}"'
        f' data-name="{esc(name)}" data-kickoff="{esc(kickoff)}" data-price="{esc(price)}"'
        f' data-lanes="{n_bets}"'
        f' data-page="{esc(contest.get("page") or "./production.html")}"'
        f' data-cards="{_cards_attr(contest.get("cards") or [])}"'
        f' aria-pressed="false"{awaiting}{hidden}>'
        f'<span class="running-time">{esc(_time_text(bucket, contest["kickoff"], now))}</span>'
        f'<span class="running-contest">{esc(name)}</span>'
        f'<span class="running-price">{esc(price)}</span>'
        f'<span class="running-meta">'
        f'{_status_html("running-status", contest["status"], contest["spoken"], _status_token(contest["data_status"]))}'
        f'<span class="running-pills"><span class="lane-pill">{esc(contest["pill"])}</span>{lanes}</span>'
        f'</span></button>'
    )


def _running_body(d, st, blob, now):
    contests = contests_from_lanes(collect_lanes(d, st, blob, now), now, d=d, st=st)
    by_sport = {}
    for contest in contests:
        by_sport.setdefault(contest["sport"], []).append(contest)
    # Counts are paper bets (lanes). A contest with two bets counts twice,
    # the same way the roll draws two chips for it.
    counts = {key: 0 for key, _label, _pressed in RUNNING}
    for contest in contests:
        counts[contest["bucket"]] = counts.get(contest["bucket"], 0) + int(contest.get("n_bets") or 1)
    groups = []
    ordered = []
    number = 0
    for label in sorted(by_sport, key=_group_key):
        items = sorted(by_sport[label],
                       key=lambda contest: (contest["kickoff"] is None,
                                            contest["kickoff"] or datetime.datetime.max.replace(
                                                tzinfo=datetime.timezone.utc)))
        rows = []
        for contest in items:
            rows.append(_row_html(contest, number, now))
            ordered.append(contest)
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
    present = {contest["sport"] for contest in contests}
    return {
        "filters": _running_filters(counts),
        "sports": _sport_pills(present),
        "groups": "".join(groups),
        "empty": empty,
        "roll": _roll_html(ordered),
        "roll_counts": _roll_counts(ordered),
        "roll_no_result": _roll_no_result(ordered),
        "counts": counts,
    }


_LANDED_TILE = re.compile(
    r'<div class="tile"><b>[^<]*</b><span>recent leads landed</span></div>')


def _landed_tile(n_won, n_settled):
    return (f'<div class="tile"><b>{int(n_won)}/{int(n_settled)}</b>'
            f'<span>paper bets landed · last {int(SHELL_SETTLED_DAYS)} days</span></div>')


def _with_landed(tiles, n_won, n_settled):
    """The Production strip with its landed tile counted the way this page counts.

    production.html counts leads over its own {KEEP_SETTLED_DAYS}-day feed. The
    shell lists bets over SHELL_SETTLED_DAYS, so its tile has to count those
    same bets or the two numbers on one screen disagree. The other three tiles
    are still production.html's own.
    """
    tile = _landed_tile(n_won, n_settled)
    if _LANDED_TILE.search(tiles):
        return _LANDED_TILE.sub(lambda _m: tile, tiles, count=1)
    end = tiles.rfind("</div>")
    return tiles[:end] + tile + tiles[end:] if end >= 0 else tiles + tile


def page(now, d=None, st=None, blob=None, tiles=None):
    """The shell document.

    Pass `tiles` to reuse a strip already computed for production.html. Omitting
    it builds that strip from `d`, `st`, and `blob` (the live board by default)
    for callers that are not the tracker build. Running rows use `now` either way
    and do not count the tiles again, except the landed tile, which is this
    page's own bets over its own window.
    """
    when = _now(now)
    if tiles is None:
        d, st, blob = _load(d, st, blob)
        summary = production_summary(d, st, blob, when)
    else:
        summary = tiles
        if d is None or st is None or blob is None:
            d, st, blob = _load(d, st, blob)
    parts = _running_body(d, st, blob, when)
    n_open, n_settled, n_won = parts["roll_counts"]
    summary = _with_landed(summary, n_won, n_settled)
    caption = (
        f'<p class="settled-caption" id="settled-caption" hidden>'
        f'Last {int(SHELL_SETTLED_DAYS)} days · counts are paper bets, one contest can carry several</p>'
    )
    n_price = parts.get("roll_no_result") or 0
    roll_note = (f'{n_open} open, then {n_settled} settled in the last {int(SHELL_SETTLED_DAYS)} days'
                 + (f', {n_price} no result' if n_price else '')
                 if (n_open or n_settled or n_price) else "")
    body = f"""<h1 class="sr-only">Edge Machine · Home</h1>
<div class="desk-layout" data-layout="analyst-desk">
<div class="shell-columns">
<div class="desk-center">
<section class="shell-pane running-pane" id="running" aria-labelledby="running-title">
<div class="pane-head">
<div>
<h2 id="running-title">Running markets</h2>
<p class="shell-kicker">Production lanes · choose a market to inspect its rules</p>
</div>
<span class="production-badge">Production</span>
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
<section class="bet-roll shell-pane" id="bets-roll" aria-labelledby="bets-roll-title">
<div class="bet-roll-head">
<p class="bet-roll-label" id="bets-roll-title">Bets roll</p>
<p class="bet-roll-note">{site_chrome.esc(roll_note)}</p>
</div>
<div class="bet-roll-track">
{parts["roll"]}
</div>
</section>
</div>
<div class="desk-side">
<section class="shell-pane rules-pane" id="rules" aria-labelledby="rules-title">
<div class="pane-head">
<h2 id="rules-title">Rule cards</h2>
<a class="full-page" href="./production.html">Full page →</a>
</div>
<div class="rules-head" id="rules-head" hidden>
<p class="rules-line" id="rules-line"></p>
</div>
<p class="sr-only" id="rules-live" aria-live="polite"></p>
<h3 class="rules-section" id="rules-section" hidden></h3>
<div class="rules-cards" id="rules-cards" hidden></div>
<p class="shell-empty" id="rules-empty">Select a contest in Running.</p>
</section>
<section class="shell-pane desk-status" id="status" aria-labelledby="status-title">
<div class="pane-head">
<h2 id="status-title">System status</h2>
<span class="production-badge">Production</span>
</div>
<section class="shell-summary" aria-label="Production totals" data-board="production">
{summary}
</section>
</section>
</div>
</div>
</div>
<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
"""
    return site_chrome.document(
        "Home",
        "Production headlines, and the paper bets on those lanes.",
        "index",
        (("running", "Running"), ("bets-roll", "Bets roll"), ("rules", "Rule cards"), ("status", "Status")),
        _stamp(now),
        body,
        script_src="./tables.js",
        scripts=("./shell.js",),
        body_class="analyst-desk",
    )


def sport_board(active, title, description, stamp_html, body):
    """Read-only sport board with the shared compact sport navigation."""
    return site_chrome.document(title, description, active, (), stamp_html, body,
                                scripts=("./tables.js",), sports=True)
