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


FLAG_WORDS = {"too early": "too early", "review": "review (10+)", "promotable": "promotable: 30+ and beats its hold",
              "control": "control"}


def variant_table(L):
    rows = []
    for key, v in C.lane_table(L).items():
        a, c = v["lane"], v["control"]
        ctl = "the control" if c is None else f"{_pct(c['roi'], sign=True)} · {c['n']}"
        rows.append(f'<tr data-variant="{esc(key)}"><td><b>{esc(C.variant_label(key))}</b></td>'
                    f'<td class="num">{a["n"]}</td><td class="num">{_pct(a["hit"])}</td>'
                    f'<td class="num">{_pct(a["roi"], sign=True)}</td>'
                    f'<td class="num">{ctl}</td>'
                    f'<td class="num">{_num(v["delta"], 100, " pts")}</td>'
                    f'<td class="num">{_num(a["z"], 1, "", 2)}</td>'
                    f'<td class="num">{a["nights"]}</td><td>{esc(FLAG_WORDS[v["flag"]])}</td></tr>')
    return ('<div class="tbl"><table><tr><th>Entry · exit</th><th class="num">Trades</th><th class="num">Hit</th>'
            '<th class="num">ROI after fees</th><th class="num">Hold control</th><th class="num">v hold</th>'
            '<th class="num">z (by night)</th><th class="num">Nights</th><th>Read</th></tr>'
            + "".join(rows) + "</table></div>")


def _cell(t):
    if t is None:
        return "—"
    word = {"target": "T", "stop": "S", "settled": "H"}[t["reason"]]
    return f"{t['roi'] * 100:+.0f}% {word}"


def trade_list(L, limit=30):
    groups = {}
    for t in L.get("trades") or []:
        groups.setdefault((t["event"], t["ticker"], t["side"], t["hours"]), {})[t["exit_key"]] = t
    recent = sorted(groups.items(), key=lambda kv: next(iter(kv[1].values()))["entry_ts"], reverse=True)[:limit]
    keys = list(C.EXITS)
    head = ('<tr><th>Night</th><th>Market</th><th>Side</th><th class="num">Entry</th>'
            + "".join(f'<th class="num">{esc(k.replace("_stop50", "+stop"))}</th>' for k in keys) + "</tr>")
    rows = []
    for (event, ticker, side, hours), by in recent:
        first = next(iter(by.values()))
        rows.append(f'<tr><td>{esc(first["night"])}</td><td>{esc(ticker.split("-", 1)[-1])}</td><td>{esc(side.upper())}</td>'
                    f'<td class="num">{hours}h before · {_clock(first["entry_ts"])} · {first["entry"] * 100:.0f}c</td>'
                    + "".join(f'<td class="num">{esc(_cell(by.get(k)))}</td>' for k in keys) + "</tr>")
    body = "".join(rows) or '<tr><td colspan="12" class="mut">No trade yet.</td></tr>'
    return f'<div class="tbl"><table>{head}{body}</table></div>'


def lane_html(L):
    trades = L.get("trades") or []
    entries = len({(t["event"], t["ticker"], t["side"], t["hours"]) for t in trades})
    hours = ", ".join(f"{h}h" for h in L.get("entry_hours") or C.ENTRY_HOURS)
    return f"""<details class="section-disclosure" data-lane="{esc(L['id'])}" open><summary><b>{esc(L.get('label') or L['id'])}</b><span>{len(L.get('replayed') or {})} events · {entries} entries · fresh record since {esc(L.get('since'))}</span></summary>
<p class="sm">{esc(L.get('note') or '')}{(' <b>Headline: ' + esc(C.exit_label(L['headline'])) + ' v hold.</b>') if L.get('headline') else ''}{(' <b>WATCH lane.</b>') if L.get('watch') else ''}{(' <b>' + esc(L['caution']) + '</b>') if L.get('caution') else ''} Bought {esc(hours)} before the start with a resting limit sell. Series {esc(', '.join(L.get('series') or []))}.</p>
{variant_table(L)}
<details class="section-disclosure"><summary><b>Trades</b><span>latest 30 entries · T target, S stop, H held to settlement</span></summary>{trade_list(L)}</details></details>"""


def section(state=None):
    if state is None:
        state = C.load() if os.path.exists(C.PATH) else C.empty()
    lanes = list((state.get("lanes") or {}).values())
    last = state.get("last_run")
    body = "".join(lane_html(L) for L in lanes) or (
        '<p class="sm mut">No chaos lane is registered yet. The engine is built; each lane plugs in as a config '
        '(chaos_lanes.py) and starts a fresh record from its first replayed night.</p>')
    return f"""<section id="chaos">
<h2>Chaos</h2>
<p class="shell-kicker">Take-profit lanes: buy before the start, rest a limit sell at a target · replayed nightly from Kalshi's 1-minute candles, point-in-time, no live orders · paper · not in Production</p>
{body}
<details class="section-disclosure"><summary><b>How a lane is replayed</b><span>entries, exits, fees, control</span></summary>
<p class="sm">A lane buys before the event starts, at a set time before it (1 hour before, and a 24-hour variant), at the ask on the first tight quote (spread 3c or less), and at the same moment rests a limit sell at +20%, +30%, +50% or +100% ROI after fees. The swings during the event either fill that sell or the position settles. Nothing is bought during the event. The start comes from the lane's own kickoff source where it has one, otherwise from the price path.</p>
<p class="sm">Exits, all from the same entry: the resting limit sell at +20%, +30%, +50% or +100%, or none; each with no stop or a −50% stop; otherwise held to Kalshi's settlement. A target that would need a price of 0.99 or more cannot be reached, so that entry is held. A sell fills only when the bid trades 1c through the limit inside a minute; a minute touching both the stop and the limit takes the stop. Fees: taker 0.07·p(1−p) on entry and on a stop, maker 0.0175·p(1−p) on a limit exit.</p>
<p class="sm">The control is the same entry held to settlement, so every lane shows hold against each target (a stop variant against hold with the same stop). A variant is flagged for review at {C.REVIEW_N} trades; promotion needs {C.PROMOTE_N} AND a better ROI than its hold control. z is clustered by night, never below the independent-trades z. Every lane's record starts fresh from its first replayed night and never inherits an older lane's rows.</p></details>
<p class="sm mut">Last replay {esc(last or 'not yet')}{(' · ' + esc(state['error'])) if state.get('error') else ''}.</p>
</section>"""
