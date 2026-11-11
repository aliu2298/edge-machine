#!/usr/bin/env python3
"""The Commodities page: the favourite-band rule on Kalshi's daily commodity ladders,
on the shared sport template (sport_page), built the way crypto.html is. The record,
verdict and ROI are the Sandbox row's own figures, so this page cannot disagree
with the Sandbox about the pair. The page states the unit the Sandbox cannot:
the lane is judged per market-day, not per contract, and a market-day is a
trading day.

No live venue call is made here; the page is rebuilt by
the tracker, and a Kalshi hiccup must not turn into a failed publish.
"""
import datetime
import os

import fmt
import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T
import sport_tab
import site_chrome as C

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "public_site", "commodities.html")

SPORTS = ("commodities_fav",)
SOURCE = "commod_fav_band"
# The near-certain lanes (2026-10-20): Yes or No at 0.90-0.98, 75-45 minutes before the close.
# Each is its own Sandbox row; only commod_fav_band is in Production.
LANES = ("commod_fav_band", "commod_nc_yes", "commod_nc_no")
NC_LANES = ("commod_nc_yes", "commod_nc_no")
RULE_NAMES = {
    "commod_fav_band": "Favourite band · 3h to the close",
    "commod_nc_yes": "Near-certain · last hour · YES",
    "commod_nc_no": "Near-certain · last hour · NO",
}
TOC = (("rules", "Rules"), ("events", "Events"), ("method", "Method"))
LEDE = "Daily favourite-band and near-certain picks on Kalshi commodity closes · times CT"


def esc(x):
    return C.esc("" if x is None else x)


def commod_rows(d, st):
    rows = [r for r in B.pair_list(d, st) if r["sport"] in SPORTS]
    return sorted(rows, key=lambda r: r["name"])


def _fav_row(rows, source=SOURCE):
    return next((r for r in rows if r.get("sport") == "commodities_fav" and r.get("name") == source), None)


def _fav_quotes(d, lanes=LANES):
    """Every row these lanes have logged: bets (live and archived) and watch-only quotes."""
    return [q for q in (T.bet_rows(d) + [q for q in (d.get("quotes") or []) if not q.get("bet")])
            if q.get("source") in lanes and q.get("sport") in SPORTS]


def _series(q):
    market_id = str(q.get("market_id") or "")
    return market_id.split("-", 1)[0] if "-" in market_id else market_id


def _short(series):
    return S.COMMOD_FAV_SHORT.get(series, series)


def _close(q):
    raw = q.get("start")
    if not raw:
        return None
    try:
        return fmt.chicago(raw).astimezone(datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _day_of(q):
    """The Chicago day a quote settles on: its close, else its stored date."""
    close = _close(q)
    if close is not None:
        return fmt.chicago(close).date()
    raw = q.get("date")
    try:
        return datetime.date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _as_utc(now):
    if now.tzinfo is None:
        return now.replace(tzinfo=datetime.timezone.utc)
    return now.astimezone(datetime.timezone.utc)


def _series_close(series, day):
    """This series' close on an Eastern calendar day, as a UTC instant."""
    hour, minute = S.commod_fav_close_et(series)
    local = datetime.datetime.combine(day, datetime.time(hour, minute), S.COMMOD_FAV_TZ)
    return local.astimezone(datetime.timezone.utc)


def state_of(q):
    """(word, class) for one row: W / L once settled, open while it runs, watching for a quote."""
    if q is None:
        return "no entry", "is-none"
    status = q.get("status")
    if q.get("bet"):
        if status == "won":
            return "W", "is-won"
        if status == "lost":
            return "L", "is-lost"
        if status == "void":
            return "void", "is-none"
        return "open", "is-live"
    return "watching", "is-next"


def pick_text(q):
    """The rung backed, named by its commodity: 'WTI above $81.49', or 'No · WTI above $81.49'."""
    side = str((q.get("side_a") if q.get("pick") == "b" else B._side(q)) or "").strip()
    name = _short(_series(q))
    if side.lower().endswith(" or above"):
        text = f"{name} above {side[:-len(' or above')]}"
    else:
        text = f"{name} {side}" if side else name
    return f"No · {text}" if q.get("pick") == "b" else text


# ------------------------------------------------------------------ the picks list
def day_blocks(d, now):
    """[(day, [(series, quote or None)])], today first, then earlier days, newest first.

    Today lists every series once, when today is a trading day: its bet or
    watch-only quote, else no entry. Every other day lists the rows logged on it.
    """
    now = _as_utc(now)
    today = fmt.chicago(now).date()
    by_day = {}
    for q in _fav_quotes(d, (SOURCE,)):
        day = _day_of(q)
        if day is None:
            continue
        by_day.setdefault(day, []).append(q)
    blocks = []
    todays = by_day.pop(today, [])
    if S.commod_fav_trading_day(today) or todays:
        rows = []
        for series in S.COMMOD_FAV_SERIES:
            mine = sorted((q for q in todays if _series(q) == series),
                          key=lambda q: (not q.get("bet"), str(q.get("logged") or "")))
            bets = [q for q in mine if q.get("bet")]
            rows.append((series, bets[0] if bets else (mine[0] if mine else None)))
        blocks.append((today, rows))
    for day in sorted(by_day, reverse=True):
        rows = sorted(by_day[day], key=lambda q: (not q.get("bet"), _series(q)))
        blocks.append((day, [(_series(q), q) for q in rows]))
    return blocks


def _window_text(start, end):
    s, e = fmt.chicago(start), fmt.chicago(end)
    first = f"{s:%-I:%M}" if f"{s:%p}" == f"{e:%p}" else f"{s:%-I:%M %p}"
    return f"{fmt._MONTHS[s.month - 1]} {s.day}, {first}–{e:%-I:%M %p} CT"


def _scan_status(d, now, source=SOURCE):
    """One muted line: last scan · quotes seen · the next entry window (this lane's own)."""
    now = _as_utc(now)
    stamp = (d.get("meta") or {}).get("updated")
    try:
        last = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = None
    except ValueError:
        last = None
    coverage = ((d.get("coverage") or {}).get("commodities_fav") or {}).get(source)
    bits = [f"Last scan {fmt.when(last)}" if last is not None else "Last scan not recorded"]
    if isinstance(coverage, dict) and last is not None:
        bits.append(f'{int(coverage.get("offered") or 0)} quotes')
    else:
        bits.append("no scanner coverage stored")
    windows = S.commod_nc_windows(now) if source in NC_LANES else S.commod_fav_windows(now)
    label, series, start, end, _close_at = windows[0]
    word = "current" if start <= now <= end else "next"
    names = " + ".join(_short(x) for x in series)
    bits.append(f"{word} window {_window_text(start, end)} ({names})")
    return f'<p class="sm mut cr-scan">{esc(" · ".join(bits))}</p>'


# ------------------------------------------------------------------ the rule
def params(source=SOURCE):
    """The entry parameters, as (name, value), from the registered constants."""
    wti_h, wti_m = S.commod_fav_close_et("KXWTI")
    oth_h, oth_m = S.COMMOD_FAV_DEFAULT_CLOSE_ET
    if source in NC_LANES:
        lo, hi = S.COMMOD_NC_BAND
        no = source == "commod_nc_no"
        side = "No ask (1 − Yes bid)" if no else "Yes ask"
        return (
            ("Entry", f"{side} {lo * 100:g}–{hi * 100:g}¢, {S.COMMOD_NC_FROM_MIN}–{S.COMMOD_NC_TO_MIN} min before the close"),
            ("Selection", "cheapest qualifying rung (nearest the price), one per commodity, trading days only"),
            ("Liquidity", f"≤{S.COMMOD_NC_MAX_SPREAD * 100:g}¢ spread, {S.COMMOD_NC_MIN_ASK_SIZE:g}+ {'No ' if no else ''}ask"),
            ("Close", f"WTI {wti_h:02d}:{wti_m:02d} ET · the rest {oth_h:02d}:{oth_m:02d} ET"),
        )
    lo, hi = S.COMMOD_FAV_BAND
    return (
        ("Entry", f"Yes ask {lo * 100:g}–{hi * 100:g}¢, {S.COMMOD_FAV_MIN_H:g}–{S.COMMOD_FAV_MAX_H:g}h before the close"),
        ("Selection", "lowest qualifying rung, one per commodity, trading days only"),
        ("Liquidity", f"≤{S.COMMOD_FAV_MAX_SPREAD * 100:g}¢ spread, {S.COMMOD_FAV_MIN_ASK_SIZE:g}+ ask"),
        ("Close", f"WTI {wti_h:02d}:{wti_m:02d} ET · the rest {oth_h:02d}:{oth_m:02d} ET"),
    )


def _registered_row(source=SOURCE):
    """The lane as registered, before the Sandbox lists it.

    pair_list gives a pair a row once it has bet. Until then the page still has a
    rule to show: the registration itself, with no record, no ROI and the
    Sandbox's own 'Too early' verdict. Nothing here is a number the
    ledger has not produced.
    """
    meta = S.SOURCES.get(source) or {}
    return dict(name=source, sport="commodities_fav", meta=meta, prod=False, open=0,
                v="waiting", a=dict(n=0, won=0, expected=0.0, roi_fee=None, n_bets=0))


def registered_row(source=SOURCE):
    return _registered_row(source)


def page_rows(d, st):
    """The Sandbox rows, and the registration of each lane that has not bet yet."""
    rows = commod_rows(d, st)
    have = {r.get("name") for r in rows}
    # A retired lane (retired_sports, commod_nc_no 2026-11-08) is listed in the Retired fold, not as a registration.
    return rows + [registered_row(name) for name in LANES
                   if name not in have and not (S.SOURCES.get(name) or {}).get("retired_sports")]


def rule_name(row):
    return RULE_NAMES.get(row.get("name"), RULE_NAMES[SOURCE])


def market(d, row):
    return "Kalshi"


def definition(d, row):
    """The entry parameters first, then the registered definition."""
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in params(row.get("name") or SOURCE))
    import sport_page as SP
    return f'<dl class="sp-params">{dl}</dl>' + SP.definition_html(row["meta"].get("note"))


def recent_html(d, row, now):
    """The scanner line: last scan, quotes seen, this lane's next entry window."""
    return _scan_status(d, now, row.get("name") or SOURCE)


def events(d, rows, now):
    """One event per commodity per market-day, holding each lane's bet or watch-only quote."""
    import sport_page as SP
    now = _as_utc(now)
    groups, order = {}, []
    for q in _fav_quotes(d):
        row = _fav_row(rows, q.get("source")) or registered_row(q.get("source"))
        word, _cls = state_of(q)
        state = {"W": "won", "L": "lost", "void": "void", "open": "open"}.get(word, "watch")
        series = _series(q)
        key = (series, q.get("date"))
        if key not in groups:
            groups[key] = dict(close=_close(q), series=series, q=q, picks=[])
            order.append(key)
        groups[key]["picks"].append(SP.pick(row, q, pick_text(q) if (q.get("bet") or q.get("side_a")) else "",
                                            state, price=q.get("price")))
    out = []
    for key in order:
        g = groups[key]
        g["picks"].sort(key=lambda p: LANES.index(p["q"].get("source")) if p["q"].get("source") in LANES else 9)
        out.append(SP.event(g["close"], f"{_short(g['series'])} · {g['series']}", g["picks"],
                            href=S.market_url(g["q"]), sub="", key=(g["series"], key[1])))
    return out


# ------------------------------------------------------------------ method
def method(d, rows, now):
    pairs = S.COMMOD_FAV_CORRELATION
    gs = pairs.get(("KXGOLDD", "KXSILVERD"))
    wb = pairs.get(("KXWTI", "KXBRENTD"))
    inner = f'''{_scan_status(d, now)}
<p class="sm">A day is one bet because the commodities move in pairs: on the ledger's own graded rungs gold and silver moved together at +{gs:.2f} and WTI and Brent at +{wb:.2f}, with copper riding the metals, so a day where both members of a pair fire is reported per commodity here and judged as one outcome in the record. A market-day is a trading day: a weekend or a US exchange holiday is no market-day at all, so the {S.COMMOD_FAV_READ_DAYS}-day read takes about seven weeks. Each contract is logged at the Yes ask inside its window with the bid, ask and ask size it was taken at, settled on Kalshi's own result at a flat ${int(T.STAKE)} stake, and the day is graded as a single outcome against backing every in-band rung that day.</p>
<p class="sm"><b>Scheduling.</b> Two reads a day, one per close: WTI settles at 14:30 Eastern, so its window is 10:00–11:30 Central, and the other five settle at 17:00 Eastern, so theirs is 12:30–2:00 Central, the crypto lane's window. Each is asked for from the always-on box inside its own window by the same stamp-file mechanism the crypto lane uses, because GitHub's cron cannot hold a 90-minute window. The close is matched in Eastern, not UTC, so the November clock change moves it with the exchange.</p>
<p class="sm"><b>The near-certain lanes.</b> The two Sandbox lanes registered 2026-10-20 back the Yes or the No at {S.COMMOD_NC_BAND[0] * 100:g}–{S.COMMOD_NC_BAND[1] * 100:g}¢ in the last hour, {S.COMMOD_NC_FROM_MIN} to {S.COMMOD_NC_TO_MIN} minutes before each close (12:15–12:45 Central for WTI, 2:45–3:15 Central for the rest), on paper only. Each contract is logged at the ask of the side it backs, and the No book is read as the Yes book's complement. A market belongs to one lane only, in the order favourite band, near-certain Yes, near-certain No. These lanes win about 3¢ a time, so one loss costs about 16 wins; they are read at {S.COMMOD_NC_READ_DAYS} market-days like the others.</p>'''
    inner += reading_note(d) + CHEAP_NOTE
    return "Method", "why a day is one bet · scheduling", inner, False


def day_figures(d, lane=SOURCE):
    """The favourite band's figures at the two levels the page mixes, from the Sandbox's own day units (T.day_units):
    days, days with a positive average P&L, the price-implied wins, the rungs behind them, and what a lost day costs.
    Nothing here is a new record: it is the same bets read at the rung."""
    bets = [q for q in T.bet_rows(d) if q.get("source") == lane and q.get("sport") in SPORTS and q.get("status") in ("won", "lost")]
    if not bets:
        return None
    days = T.day_units(bets)
    lost = [u for u in days if u["status"] == "lost"]
    return dict(days=len(days), won_days=len(days) - len(lost), priced=sum(u["price"] for u in days),
                rungs=len(bets), won_rungs=sum(q["status"] == "won" for q in bets),
                rung_price=sum(q["price"] for q in bets) / len(bets),
                lost_cost=[-u["pnl"] / T.STAKE for u in lost])


def reading_note(d):
    """Why 'Won v priced' can sit under the price while the ROI is positive (2026-11-06): the two are read at different levels."""
    f = day_figures(d)
    if f is None:
        return ""
    cost = f["lost_cost"]
    lost_txt = (f" The {len(cost)} lost days cost {min(cost) * 100:.0f}% to {max(cost) * 100:.0f}% of a stake each (mean {sum(cost) / len(cost) * 100:.0f}%), not a whole one, "
                f"because their winning rungs paid part of the losing ones." if cost else "")
    return (f'<p class="sm"><b>Reading the favourite band\'s figures.</b> A day is Won when the average P&amp;L of its rungs is above zero, and the ROI is the mean of those day P&amp;Ls, '
            f'so the two are not the same count. The record counts {f["won_days"]} of {f["days"]} days Won against {f["priced"]:.1f} priced; '
            f'the same bets read rung by rung are {f["won_rungs"]} of {f["rungs"]} won ({f["won_rungs"] / f["rungs"] * 100:.0f}%) against {f["rung_price"] * 100:.0f}% priced.{lost_txt} '
            f'A lane can therefore win fewer days than the prices imply and still return a positive ROI: a lost day loses a fraction of a stake while a won day earns most of one.</p>')


def build(d=None, st=None, now=None):
    import sport_page as SP
    now = _as_utc(now or datetime.datetime.now(datetime.timezone.utc))
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    rows = page_rows(d, st)
    sp = SP.spec(
        family="Commodities", key="commodities", title="Edge Machine · Commodities",
        description="Daily favourite-band and near-certain picks on Kalshi commodity closes, and each rule's record per market-day.",
        scope="Daily favourite-band and near-certain picks on Kalshi commodity closes", venue="Kalshi",
        rows=rows, events=events, rule_name=rule_name, market=market,
        definition=definition, recent=recent_html, method=method, scoped=False,
        unit=lambda row: "market-day",
        # The Retired fold, as on the Crypto and Econ pages (2026-11-08: commod_nc_no retired).
        retired=sport_tab.retired_rows(d, st, "Commodities"))
    html = SP.page(sp, d, st, now, rows=rows)
    # The cheap-side lanes (2026-10-27, own ledgers) are rows of the same Rules list since 2026-11-08 (Olu: one
    # tab, the Econ Daily design): one row per lane on the same columns, the full card in its fold, the retired
    # one in the Retired fold. Their records are read exactly as before (mentions_split).
    return with_cheap_rows(html)


CHEAP_NOTE = ('<p class="sm"><b>Cheap side + resting take-profit.</b> Buy the cheap side when a ladder rung opens, at '
              'the real ask; rest a split sell, half at 2x and half at 3x; a fill counts only on a traded print; every '
              'lane is shown next to the same entries held. Sandbox, paper only, fresh records from the first entry: '
              'review at 10 settled events, decide at 30. An event is one outcome (a WTI day, a gas day, a gas week): '
              'its rungs move together, so they count once, and Evidence on a cheap-side row counts settled events. '
              'Record and Won v priced count settled entries; ROI after fees is the split ROI (pending until the '
              'first settled event). The weekly gas lane is small and slow: about 3 entries a week, all on one weekly '
              'event, so 10 settled events takes about ten weeks. Review at 10, decide at 30. The same engine and '
              'wording as the Culture page.</p>')


def _cheap_row(cfg, st, retired=False):
    """One cheap-side lane as a Rules-list row (sport_page.rule_row's markup and columns), its card in the fold."""
    import mentions_split as MS
    import sport_page as SP
    e = C.esc
    es = MS.counted(st)
    r = MS.record(es)
    settled = [x for x in es if x.get("payout") is not None]
    won = sum(x.get("payout") == 1 for x in settled)
    priced = sum(float(x.get("price") or 0) for x in settled)
    record = f"{won}–{len(settled) - won}" if settled else '<span class="mut">—</span>'
    roi = MS._headline(r["roi"], r)
    roi_cell = (f'<span class="mut">{e(roi)}</span>' if roi in ("pending", "—") or r["settled_events"] < 10
                else f'<span class="{fmt.tone(r["roi"], ".1f", 100)}">{e(roi)}</span>')
    wvp = f"{won} v {priced:.1f}" if settled else "—"
    n = r["settled_events"]
    if retired:
        verdict = SP.verdict_badge(dict(v="retired", a={"n": n}))
    elif n < 10:
        verdict = SP.verdict_badge(dict(v="early", a={"n": n}))
    else:
        verdict = SP.verdict_badge(dict(v="promising" if (r["roi"] or 0) > 0 else "behind", a={"n": n}))
    badges = '<span class="sp-badges"><span class="badge stage">Retired</span></span>' if retired else ""
    side = str(cfg.get("side") or "yes").upper()
    lo, hi = cfg.get("band") or (0, 0)
    params = ('<dl class="sp-params">'
              f'<dt>Entry</dt><dd>{side} at {lo * 100:g}–{hi * 100:g}¢, the real ask, when a {e(cfg.get("series", ""))} rung opens</dd>'
              f'<dt>Exit</dt><dd>Half resting at 2x, half at 3x, filled only on a traded print; else held to settlement</dd>'
              f'<dt>Liquidity</dt><dd>Spread ≤{float(cfg.get("spread") or 0) * 100:g}¢; the ask counted only when it was really there</dd>'
              f'<dt>Record</dt><dd>Sandbox, paper, a fresh record from the first entry · review at 10 settled events, decide at 30</dd></dl>')
    gone = cfg.get("retired") or {}
    gone_line = (f'<p class="sp-def">Retired {e(gone.get("on", ""))} at {e(gone.get("at", ""))}: {e(gone.get("reason", ""))}. '
                 f'Its rows stay; any open entry still settles.</p>' if retired and gone else "")
    if retired and gone.get("note"):
        gone_line += f'<p class="sp-def">{e(gone["note"])}.</p>'
    early = " is-early" if (not retired and n < 10) else ""
    return (f'<details class="sp-rule{early}" data-source="{e(cfg["lane"])}" data-sport="commodities_cheap" '
            f'data-scope="clubs" data-stage="sandbox"{" data-early=\"1\"" if early else ""}>'
            f'<summary class="sp-line"><span class="sp-cell sp-c-name"><span class="sp-chev" aria-hidden="true">›</span>'
            f'<b class="sp-name" title="{e(cfg["label"])}">{e(cfg["label"])}</b>{badges}'
            f'<span class="sr-only"> · Rule details</span></span>'
            f'<span class="sp-cell sp-c-market" data-l="Market">Kalshi</span>'
            f'<span class="sp-cell num" data-l="Record">{record}</span>'
            f'<span class="sp-cell num" data-l="ROI after fees">{roi_cell}</span>'
            f'<span class="sp-cell num" data-l="Won v priced">{e(wvp)}</span>'
            f'<span class="sp-cell num" data-l="Evidence">{n}/30</span>'
            f'<span class="sp-cell sp-c-verdict" data-l="Verdict">{verdict}</span></summary>'
            f'<div class="sp-details-body"><p class="sp-details-name"><b>{e(cfg["label"])}</b> · Kalshi · cheap side + '
            f'resting take-profit · {e(MS.lane_status(cfg, n))}</p>{params}{gone_line}{MS.label_cells(MS.section(st, e, cfg))}</div></details>')


def _insert_rows(html, list_key, rows_html):
    """Put rows at the top of a Rules list (data-list=...), right after its header line."""
    at = html.find(f'data-list="{list_key}">')
    if at < 0 or not rows_html:
        return html, False
    head_end = html.find("</div>", at) + len("</div>")       # the header line holds spans only
    return html[:head_end] + rows_html + html[head_end:], True


def with_cheap_rows(html, states=None):
    """The page with the cheap-side lanes as Rules rows: live ones in the Sandbox list, retired ones in the Retired fold.
    A page with no Sandbox list or Retired fold to hold them keeps the old section, so no lane ever drops off."""
    import mentions_split as MS
    states = states or {cfg["lane"]: MS.load(cfg=cfg) for cfg in MS.COMMOD_LANES}
    live = "".join(_cheap_row(c, states[c["lane"]]) for c in MS.LIVE_COMMOD)
    gone = "".join(_cheap_row(c, states[c["lane"]], retired=True) for c in MS.GONE_COMMOD)
    out, ok_live = _insert_rows(html, "sandbox", live)
    out, ok_gone = _insert_rows(out, "retired", gone)
    if not (ok_live and (ok_gone or not gone)):
        return html.replace('<section id="events"', cheap_side(states) + '<section id="events"', 1)
    return out


def cheap_side(states=None):
    """The Commodities page's "Cheap side + resting take-profit" section (2026-10-27): the Culture
    page's summary table and lane cards for wti_cheap_yes and gas_cheap_no (mentions_split engine)."""
    import mentions_split as MS
    states = states or {cfg["lane"]: MS.load(cfg=cfg) for cfg in MS.COMMOD_LANES}
    e = C.esc
    inner = ('<section id="cheap-side"><h2>Cheap side + resting take-profit</h2>'
             '<ul class="sm"><li>Buy the cheap side when a ladder rung opens, at the real ask.</li>'
             '<li>Rest a split sell: half at 2x, half at 3x.</li><li>A fill counts only on a traded print.</li>'
             '<li>Every lane is shown next to the same entries held.</li></ul>'
             '<p class="sm mut">Sandbox, paper only, fresh records from the first entry: review at 10 settled events, '
             'decide at 30. An event is one outcome (a WTI day, a gas day, a gas week): its rungs move together, so '
             'they count once. The same engine and wording as the Culture page.</p>'
             + MS.summary(MS.LIVE_COMMOD, states, e)
             + "".join((('<p class="sm" id="gas-week-note"><b>The weekly gas lane is small and slow: about 3 entries a '
                         'week, all on one weekly event, so 10 settled events takes about ten weeks. Review at 10, '
                         'decide at 30.</b></p>')
                        if cfg is MS.GAS_WEEK else "") + MS.section(states[cfg["lane"]], e, cfg)
                       for cfg in MS.LIVE_COMMOD)
             + retired_cheap(states, e) + '</section>')
    return MS.label_cells(inner)


def retired_cheap(states, e):
    """The retired cheap-side lanes (WTI cheap YES, 2026-11-04) in one collapsed fold, as on the Culture page: each
    lane's record, the dated reason, then its full card. Records kept, rows stay, open entries still settle."""
    import mentions_split as MS
    if not MS.GONE_COMMOD:
        return ""
    lines = "".join(f'<li data-lane="{e(c["lane"])}"><b>{e(c["label"])}</b>: retired {e(c["retired"]["on"])} at '
                    f'{e(c["retired"]["at"])}: {e(c["retired"]["reason"])}. Its rows stay; any open entry still settles.'
                    + (f' {e(c["retired"]["note"])}.' if c["retired"].get("note") else "") + '</li>'
                    for c in MS.GONE_COMMOD)
    return (f'<details class="fold sec" id="retired-cheap"><summary><h2>Retired</h2> <span class="mut sm">· '
            f'{len(MS.GONE_COMMOD)} cheap-side lane{"s" if len(MS.GONE_COMMOD) != 1 else ""} · kept, not deleted</span>'
            f'</summary><ul class="sm">{lines}</ul>' + MS.summary(MS.GONE_COMMOD, states, e)
            + "".join(MS.section(states[c["lane"]], e, c) for c in MS.GONE_COMMOD) + '</details>')


def main():
    html = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(html)
    os.replace(tmp, OUT)
    print(f"wrote {OUT} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
