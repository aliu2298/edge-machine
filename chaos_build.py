"""The Sandbox page's Chaos section (chaos_replay.py): in-play take-profit lanes, replayed nightly, paper only.

Per lane and per exit variant: trades, hit rate, ROI after fees, the random-minute control's ROI, the
lane's edge over that control, the day-clustered z and a review / promotable flag; then the trade list.
The tables are written as header-row tables (no <thead>) so the Sandbox page's own label_cells gives
each cell its column name on a phone. Never breaks the page: sandbox_build wraps the call.
"""
import datetime as dt
import html as _h
import os

import chaos_replay as C
import mentions_split as MS


def esc(x):
    return _h.escape(str(x))


def _pct(v, sign=False, d=1):
    if v is None:
        return "—"
    return f"{v * 100:+.{d}f}%" if sign else f"{v * 100:.0f}%"


def _num(v, scale=1, unit="", d=1):
    return "—" if v is None else f"{v * scale:+.{d}f}{unit}"


def _clock(ts):
    t = dt.datetime.fromtimestamp(ts, C.UTC).astimezone(C.ET)
    return f"{t:%-I:%M %p}"


FLAG_WORDS = {"too early": "too early", "review": "review (10+ events)", "promotable": "promotable: 30+ events and beats its hold",
              "control": "control"}


def variant_table(L, skip=()):
    rows = []
    for key, v in C.lane_table(L).items():
        if C.split_key(key)[1] in skip:
            continue
        a, c = v["lane"], v["control"]
        ctl = "the control" if c is None else f"{_pct(c['roi'], sign=True)} · {c['n']}"
        rows.append(f'<tr data-variant="{esc(key)}"><td><b>{esc(C.variant_label(key))}</b></td>'
                    f'<td class="num">{a["n"]}</td><td class="num">{a["events"]}</td><td class="num">{_pct(a["hit"])}</td>'
                    f'<td class="num">{_pct(a["roi"], sign=True)}</td>'
                    f'<td class="num">{ctl}</td>'
                    f'<td class="num">{_num(v["delta"], 100, " pts")}</td>'
                    f'<td class="num">{_num(a["z"], 1, "", 2)}</td>'
                    f'<td class="num">{a["nights"]}</td><td>{esc(FLAG_WORDS[v["flag"]])}</td></tr>')
    return ('<div class="tbl"><table><tr><th>Entry · exit</th><th class="num">Trades</th><th class="num">Events</th><th class="num">Hit</th>'
            '<th class="num">ROI after fees</th><th class="num">Hold control</th><th class="num">v hold</th>'
            '<th class="num">z (by night)</th><th class="num">Nights</th><th>Read</th></tr>'
            + "".join(rows) + "</table></div>")


def _cell(t):
    if t is None:
        return "—"
    word = {"target": "T", "stop": "S", "settled": "H", "split": "split"}[t["reason"]]
    return f"{t['roi'] * 100:+.0f}% {word}"


def trade_list(L, limit=30):
    groups = {}
    for t in L.get("trades") or []:
        groups.setdefault((t["event"], t["ticker"], t["side"], t["hours"]), {})[t["exit_key"]] = t
    recent = sorted(groups.items(), key=lambda kv: next(iter(kv[1].values()))["entry_ts"], reverse=True)[:limit]
    keys = [C.SPLIT] + [k for k in (L.get("exits") or C.EXITS) if k != C.SPLIT]
    rule = bool(L.get("ask_rule_since"))
    head = ('<tr><th>Night</th><th>Market</th><th>Side</th><th class="num">Entry</th>'
            + "".join(f'<th class="num">{esc(k.replace("_stop50", "+stop"))}</th>' for k in keys)
            + ("<th>Ask check</th>" if rule else "") + "</tr>")
    rows = []
    for (event, ticker, side, hours), by in recent:
        first = next(iter(by.values()))
        rows.append(f'<tr><td>{esc(first["night"])}</td><td>{esc(ticker.split("-", 1)[-1])}</td><td>{esc(side.upper())}</td>'
                    f'<td class="num">{hours}h before · {_clock(first["entry_ts"])} · {first["entry"] * 100:.0f}c</td>'
                    + "".join(f'<td class="num">{esc(_cell(by.get(k)))}</td>' for k in keys)
                    + (f'<td>{esc(MS.check_text(dict(ask_check=first.get("ask") or {})))}</td>' if rule else "") + "</tr>")
    body = "".join(rows) or f'<tr><td colspan="{4 + len(keys) + rule}" class="mut">No trade yet.</td></tr>'
    return f'<div class="tbl"><table>{head}{body}</table></div>'


def _in_band(t, band):
    """A trade whose entry ask is inside the sub-band [lo, hi], edges included as band_picker does."""
    return band is None or band["lo"] - C.EPS <= t["entry"] <= band["hi"] + C.EPS


def _by(L, exit_key, hours=None, band=None):
    """The lane's counted trades of one exit (under the ask rule, verified entries only)."""
    return [t for t in C.counted(L.get("trades") or [], L) if t["exit_key"] == exit_key
            and (hours is None or t["hours"] == hours) and _in_band(t, band)]


def unverified(L):
    """Entries whose ask failed the check (2026-10-30), and entries not checked yet."""
    if not L.get("ask_rule_since"):
        return 0, 0
    ent = {}
    for t in L.get("trades") or []:
        ent[(t["event"], t["ticker"], t["side"], t["hours"])] = (t.get("ask") or {}).get("status")
    return sum(v == "unverified" for v in ent.values()), sum(v not in ("verified", "unverified") for v in ent.values())


def voided_line(L):
    """The lane's figure before the ask rule, once, labelled voided, when an entry failed the check."""
    v = L.get("voided")
    bad, _ = unverified(L)
    if not v or not bad:
        return ""
    return (f'<p class="sm voided"><b>Voided {esc(v["on"])}:</b> the earlier figure ({v["entries"]} entries on '
            f'{v["events"]} events, split {_pct(v["split"], sign=True)}, hold {_pct(v["hold"], sign=True)}) counted asks '
            f'with no evidence they could be traded. {bad} entries failed the ask check (under {MS.MIN_SIZE} contracts '
            f'traded at or through the ask within {MS.PRINT_WINDOW_MIN} minutes, or an ask under half the last trade) '
            'and left the record; the record restarts on the verified entries.</p>')


def split_hold(L, hours=None, band=None):
    """The cheap-side split v the same entries held: entries, won (held), legs filled 2x / 3x, split ROI,
    hold ROI (each after fees, sum of profit over sum of cost), split z by night. `band` narrows the
    same entries to an entry ask of band["lo"]-band["hi"] (a lane's sub_bands). `events` counts the Kalshi
    events entered (one game, match or fight each: the independent outcome; 2026-10-29, Olu). Only settled
    events are replayed, so every event here is settled, and the review status counts them."""
    sp, hd = _by(L, C.SPLIT, hours, band), _by(L, "hold", hours, band)
    a, h = C.stats(sp), C.stats(hd)
    return dict(entries=len({(t["event"], t["ticker"], t["side"], t["hours"]) for t in (sp or hd)}), settled=len(hd),
                events=len({t.get("event") or id(t) for t in hd}),
                won=h["won"], filled_2x=sum(1 for t in sp if t.get("filled_2x")),
                filled_3x=sum(1 for t in sp if t.get("filled_3x")), split=a["roi"], hold=h["roi"], z=a["z"],
                n_split=len(sp), spread=(lambda xs: sum(xs) / len(xs) if xs else None)(
                    [t["spread"] for t in (sp or hd) if t.get("spread") is not None]))


def ordered(lanes):
    return sorted(lanes, key=lambda L: (not L.get("first"), list(lanes).index(L)))


def _spread(x):
    return "—" if x is None else f"{x:.2f}"


def summary(lanes, spread=False):
    """One row per lane; with `spread`, the average spread paid at entry (recorded from 2026-10-27)."""
    rows = []
    for L in lanes:
        for band in [None] + list(L.get("sub_bands") or ()):
            r = split_hold(L, band=band)
            name = (f'<b>{esc(L.get("label") or L["id"])}</b>' if band is None else
                    f'<span class="sub-band">· {esc(band["label"])}, same entries</span>')
            attrs = f' data-band="{esc(band["id"])}"' if band else ""
            rows.append(f'<tr data-lane="{esc(L["id"])}"{attrs}><td>{name}</td>'
                        f'<td class="num">{r["entries"]}</td><td class="num">{unverified(L)[0] if band is None else "·"}</td>'
                        f'<td class="num">{r["settled"]}</td>'
                        f'<td class="num">{r["events"]}</td><td class="num">{r["won"]}</td>'
                        f'<td class="num">{_pct(r["split"], sign=True) if r["n_split"] else "—"}</td>'
                        f'<td class="num">{_pct(r["hold"], sign=True)}</td>'
                        f'<td class="num">{r["filled_2x"]} / {r["filled_3x"]}</td>'
                        + (f'<td class="num">{_spread(r["spread"])}</td>' if spread else "")
                        + f'<td>{esc(status_of(L, r["events"]))}</td></tr>')
    return ('<div class="tbl"><table class="chaos-summary"><tr><th>Lane</th><th class="num">Entries</th>'
            '<th class="num">Unverified asks</th><th class="num">Settled entries</th><th class="num">Settled events</th><th class="num">Won</th><th class="num">Split ROI</th><th class="num">Hold ROI</th>'
            '<th class="num">Legs filled 2x / 3x</th>' + ('<th class="num">Avg spread paid</th>' if spread else "")
            + '<th>Status</th></tr>' + "".join(rows) + "</table></div>")


def split_table(L):
    """SPLIT v HOLD first, a row per entry time."""
    rows = []
    for h in L.get("entry_hours") or C.ENTRY_HOURS:
        for band in [None] + list(L.get("sub_bands") or ()):
            r = split_hold(L, h, band)
            name = (f'<b>{esc(C.variant_label(C.vkey(h, C.SPLIT)))}</b>' if band is None else
                    f'<span class="sub-band">· {esc(band["label"])}, same entries</span>')
            attrs = f' data-band="{esc(band["id"])}"' if band else ""
            rows.append(f'<tr{attrs}><td>{name}</td><td class="num">{r["entries"]}</td><td class="num">{r["won"]}</td>'
                        f'<td class="num">{r["filled_2x"]} / {r["filled_3x"]}</td>'
                        f'<td class="num">{_pct(r["split"], sign=True) if r["n_split"] else "—"}</td>'
                        f'<td class="num">{_pct(r["hold"], sign=True)}</td><td class="num">{_num(r["z"], 1, "", 2)}</td></tr>')
    return ('<div class="tbl"><table class="chaos-split"><tr><th>Entry</th><th class="num">Entries</th><th class="num">Won</th>'
            '<th class="num">Legs filled 2x / 3x</th><th class="num">Split ROI</th><th class="num">Hold ROI</th>'
            '<th class="num">Split z (by night)</th></tr>' + "".join(rows) + "</table></div>")


def record_words(L):
    if L.get("insample"):
        return f"IN-SAMPLE backfill {esc(L.get('since'))} to the lane's first night, not evidence"
    return f"fresh record since {esc(L.get('since'))}"


def status_of(L, events):
    """The review status, counted in settled events (2026-10-29); an in-sample backfill is never evidence."""
    return "in-sample backfill, not evidence" if L.get("insample") else MS.status(events)


def _checking_line(L):
    bad, waiting = unverified(L)
    if not L.get("ask_rule_since"):
        return ""
    return (f'<p class="sm mut">Skipped: unverified ask: {bad}' + (f'; still to check: {waiting}' if waiting else '')
            + f'. An entry counts only with {MS.MIN_SIZE}+ contracts traded at or through its ask within '
            f'{MS.PRINT_WINDOW_MIN} minutes (a replay cannot read the book at entry), and never under half the last '
            'trade; an entry in the market\'s first minutes is flagged.</p>')


def lane_html(L):
    trades = L.get("trades") or []
    entries = len({(t["event"], t["ticker"], t["side"], t["hours"]) for t in trades})
    hours = ", ".join(f"{h}h" for h in L.get("entry_hours") or C.ENTRY_HOURS)
    others = [k for k in (L.get("exits") or C.EXITS) if k not in (C.SPLIT, "hold")]
    pending = C.SPLIT in (L.get("exits") or ()) and not _by(L, C.SPLIT) and trades
    return f"""<details class="section-disclosure" data-lane="{esc(L['id'])}" open><summary><b>{esc(L.get('label') or L['id'])}</b><span>{len(L.get('replayed') or {})} events replayed · {entries} entries · {split_hold(L)["events"]} settled events entered · {record_words(L)}</span></summary>
<p class="sm">{esc(L.get('note') or '')}{(' <b>WATCH lane.</b>') if L.get('watch') else ''}{(' <b>' + esc(L['caution']) + '</b>') if L.get('caution') else ''} Bought {esc(hours)} before the start. Series {esc(', '.join(L.get('series') or []))}. Review at {C.REVIEW_N} settled events, decide at {C.PROMOTE_N}: one game, match or fight is one outcome, however many entries it holds.</p>
{voided_line(L)}{_checking_line(L)}<p class="sm"><b>Split v hold</b>{(' · the split joined this lane on 2026-10-27 and is being added to its earlier entries, newest events first') if pending else ''}</p>
{split_table(L)}
{f'<details class="section-disclosure"><summary><b>Other exits</b><span>{len(others)} variants · the original targets and stops, each against its hold control</span></summary>{variant_table(L, skip=(C.SPLIT,))}</details>' if others else ''}
<details class="section-disclosure"><summary><b>Trades</b><span>latest 30 entries · split, T target, S stop, H held to settlement</span></summary>{trade_list(L)}</details></details>"""


# Every chaos lane lives on its own sport page (2026-10-27, Olu: "Each strategy needs to be under its own
# sport/event"): a "Cheap side + resting take-profit" section near the top of that page, read from
# data/chaos_ledger.json (the same records, never copied). The Sandbox's Chaos section is an index
# that links to them. A lane not listed here would have no home: test_sport_cheap_homes checks.
HOMES = {
    "tennis": ("challenger_cheap_split", "challenger_dog_tp30", "atp_coinflip_tp30"),
    "nba": ("nba_ml_dog_tp50", "nba_winmargin_split", "nba_winmargin_split_insample", "nba_tt_cheap_tp30"),
    "nfl": ("cfb_dog_tp50",),
}
HOME_OF = {lane: page for page, lanes in HOMES.items() for lane in lanes}
TENNIS = HOMES["tennis"]
PAGE_LABEL = {"tennis": "Tennis", "nba": "NBA", "nfl": "NFL · College football"}
_BUY = {"tennis": "Buy the cheap player about an hour before the match, at the real ask.",
        "nba": "Buy the cheap side before the tip (1h, and 24h for the team totals), at the real ask.",
        "nfl": "College football: buy the underdog 1h and 24h before kickoff, at the real ask."}


def with_config(state):
    """The ledger's lanes with each registered lane's retirement, label, note, caution, headline and sub-bands
    (chaos_lanes) applied, so a page shows a change from the day it is registered, before the next replay
    writes it. A copy: never saved."""
    lanes = dict(state.get("lanes") or {})
    try:
        import chaos_lanes
        for cfg in chaos_lanes.LANES:
            if cfg["id"] not in lanes:
                continue
            shown = {k: cfg[k] for k in ("label", "note", "caution", "headline") if cfg.get(k) is not None}
            if cfg.get("sub_bands"):
                shown["sub_bands"] = [dict(b) for b in cfg["sub_bands"]]
            if cfg.get("retired"):
                shown["retired"] = dict(cfg["retired"])
            lanes[cfg["id"]] = dict(lanes[cfg["id"]], **shown)
    except Exception:                                           # noqa: BLE001
        pass
    return dict(state, lanes=lanes)


def home_href(lane_id):
    page = HOME_OF.get(lane_id)
    return f"./{page}.html#cheap-side" if page else None


def sport_section(page, state=None, retired=True):
    """A sport page's "Cheap side + resting take-profit" section: its chaos lanes, split v hold first."""
    if state is None:
        state = C.load() if os.path.exists(C.PATH) else C.empty()
    have = with_config(state).get("lanes") or {}
    every = [have[k] for k in HOMES[page] if k in have]
    lanes = [L for L in every if not L.get("retired") and not L.get("insample")]
    gone = [L for L in every if L.get("retired")]
    sample = [L for L in every if L.get("insample") and not L.get("retired")]
    body = (summary(lanes, spread=True) + "".join(lane_html(L) for L in lanes)) if lanes else (
        '<p class="sm mut">No cheap-side lane on this page has replayed yet.</p>')
    if page == "nba" and lanes:                                 # the NO fade (2026-10-30), under the YES split it mirrors
        try:
            import nba_wm_nofade_build
            body += nba_wm_nofade_build.card(chaos=state)
        except Exception:                                       # noqa: BLE001
            pass
    if sample:                                                  # a lane's in-sample backfill: its own labelled row, never the headline
        body += in_sample_block(sample)
    if gone and retired:                                        # the NBA page lists its retired lanes in its own bottom fold
        body += retired_block(gone)
    block = ('<h3>College football</h3><p class="sm mut">The college football lane sits on the NFL page: '
             'it is the same football markets, and the site has no college football page.</p>' if page == "nfl" else "")
    return f"""<section id="cheap-side">
<h2>Cheap side + resting take-profit</h2>
<ul class="sm"><li>{esc(_BUY[page])}</li>
<li>Rest a split sell: half at 2x, half at 3x.</li><li>A fill counts only on a traded print.</li>
<li>Every lane is shown next to the same entries held.</li></ul>
<p class="sm mut">Sandbox, paper only, replayed nightly from Kalshi's 1-minute candles: review at {C.REVIEW_N} settled, decide at {C.PROMOTE_N}. Every cheap-side lane is listed in the <a href="./sandbox.html#chaos">Sandbox's Chaos index</a>, which links here; the records are the same. The average spread paid is recorded from 2026-10-27.</p>
{block}{body}
</section>"""


def in_sample_block(lanes):
    """In-sample backfills, apart from the lane they back-test: the rule was chosen on this data."""
    return ('<div class="in-sample" id="cheap-side-insample"><h3>In-sample backfill</h3>'
            '<p class="sm mut">The same rule replayed on the days it was chosen from. In-sample, so it is NOT evidence '
            'and is never a lane\'s headline; the lane above starts a fresh record after it.</p>'
            + summary(lanes, spread=True) + "".join(lane_html(L) for L in lanes) + '</div>')


def retired_line(L):
    g = L["retired"]
    return f"Retired {g['on']} at {g['at']}: {g['reason']}. Its rows stay; nothing new from that night on."


def retired_block(lanes):
    """Retired chaos lanes, collapsed, one line each with the record they were retired on."""
    items = "".join(f'<li data-lane="{esc(L["id"])}"><b>{esc(L.get("label") or L["id"])}</b> ({esc(L["id"])}): '
                    f'{esc(retired_line(L))}</li>' for L in lanes)
    return (f'<details class="section-disclosure" id="cheap-side-retired"><summary><b>Retired</b><span>{len(lanes)} '
            f'lane{"s" if len(lanes) != 1 else ""} · kept, not deleted</span></summary><ul class="sm">{items}</ul></details>')


def tennis_section(state=None):
    return sport_section("tennis", state)


def place(html, page, state=None, before=None, retired=True):
    """Insert the page's cheap-side section near the top: before `before` (an opening tag), else before
    the first top-level <section id=...> in <main>. Never breaks the page."""
    try:
        import sandbox_build
        # Labelled here (phone cards), so every caller of a page's build() gets the phone layout.
        sec = sandbox_build.label_cells(sport_section(page, state, retired))
        at = html.find(before) if before else html.find("<section id=", html.find("<main"))
        return html[:at] + sec + html[at:] if at >= 0 else html
    except Exception:                                           # noqa: BLE001
        return html


def index(lanes):
    """The Sandbox's Chaos index: one row per lane, its headline numbers and a link to its home."""
    rows = []
    for L in lanes:
        r = split_hold(L)
        href = home_href(L["id"])
        page = PAGE_LABEL.get(HOME_OF.get(L["id"]), "—")
        link = f'<a href="{esc(href)}">{esc(page)}</a>' if href else esc(page)
        rows.append(f'<tr data-lane="{esc(L["id"])}"><td><b>{esc(L.get("label") or L["id"])}</b></td><td>{link}</td>'
                    f'<td class="num">{r["entries"]}</td><td class="num">{r["events"]}</td><td class="num">{r["won"]}</td>'
                    f'<td class="num">{_pct(r["split"], sign=True) if r["n_split"] else "—"}</td>'
                    f'<td class="num">{_pct(r["hold"], sign=True)}</td>'
                    f'<td>{esc("retired " + L["retired"]["on"] if L.get("retired") else status_of(L, r["events"]))}</td></tr>')
    return ('<div class="tbl"><table class="chaos-index"><tr><th>Lane</th><th>Page</th><th class="num">Entries</th>'
            '<th class="num">Settled events</th><th class="num">Won</th><th class="num">Split ROI</th><th class="num">Hold ROI</th><th>Status</th></tr>'
            + "".join(rows + _extra_index_rows()) + "</table></div>")


def _extra_index_rows():
    """Cheap-side lanes that keep their own ledger (the NBA win margin NO fade, 2026-10-30)."""
    try:
        import nba_wm_nofade_build
        return [nba_wm_nofade_build.index_row()]
    except Exception:                                           # noqa: BLE001
        return []


def section(state=None):
    if state is None:
        state = C.load() if os.path.exists(C.PATH) else C.empty()
    lanes = ordered(list((with_config(state).get("lanes") or {}).values()))
    last = state.get("last_run")
    # An index (2026-10-27): each lane's full card lives on its sport page (HOMES).
    body = index(lanes) if lanes else (
        '<p class="sm mut">No chaos lane is registered yet. The engine is built; each lane plugs in as a config '
        '(chaos_lanes.py) and starts a fresh record from its first replayed night.</p>')
    return f"""<section id="chaos">
<h2>Chaos</h2>
<p class="shell-kicker">Cheap side + resting take-profit · buy before the start at the real ask · rest a split sell, half at 2x and half at 3x · a fill counts only on a traded print · every lane next to the same entries held · replayed nightly from Kalshi's 1-minute candles · paper · not in Production</p>
{body}
<details class="section-disclosure"><summary><b>How a lane is replayed</b><span>entries, exits, fees, control</span></summary>
<p class="sm">A lane buys before the event starts, at a set time before it (1 hour before, and a 24-hour variant), at the ask on the first tight quote (spread 3c or less, 5c for the cheap-side lane). The standard exit is the split: half the stake rests at 2x the entry ask and half at 3x, each capped at 0.98, and a leg fills only when a trade prints at or above it; a leg not filled is held to Kalshi's settlement. Nothing is bought during the event. The start comes from the lane's own kickoff source where it has one, otherwise from the price path.</p>
<p class="sm">Other exits, from the same entry: a resting limit sell at +20%, +30%, +50% or +100% ROI after fees, each with no stop or a −50% stop. Those sells fill when the bid trades 1c through the limit inside a minute; a minute touching both the stop and the limit takes the stop. Fees: taker 0.07·p(1−p) on entry and on a stop, maker 0.0175·p(1−p) on a limit exit or a filled split leg.</p>
<p class="sm">The control is the same entry held to settlement. A variant is flagged for review at {C.REVIEW_N} settled events; promotion needs {C.PROMOTE_N} AND a better ROI than its hold control. An event (one game, match or fight) is one outcome: several entries on one event move together, so they count once. z is clustered by night, never below the independent-trades z. Every lane's record starts fresh from its first replayed night and never inherits an older lane's rows; the split was added to the older lanes on 2026-10-27 by replaying their recorded entries, nothing edited or removed.</p></details>
<p class="sm">Each lane's card (split v hold, its other exits, its trades) is on its own page: tennis lanes on the <a href="./tennis.html#cheap-side">Tennis page</a>, NBA lanes on the <a href="./nba.html#cheap-side">NBA page</a>, college football on the <a href="./nfl.html#cheap-side">NFL page</a>.</p>
<p class="sm mut">Last replay {esc(last or 'not yet')}{(' · ' + esc(state['error'])) if state.get('error') else ''}.</p>
</section>"""
