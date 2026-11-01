"""The Culture page's "Trump mentions · 10c dip bid, hold" card (mentions_dip_hold.py), near the top, beside the cheap-side
table. Tables carry a <thead>, so culture_build's label_cells names each cell for the phone layout. Never breaks the page:
culture_build wraps the call."""
import datetime as dt

import mentions_dip_hold as M
import mentions_split as MS


def _pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%".replace("-", "−")


def _z(v):
    return "—" if v is None else f"{v:+.2f}"


def _clock(ts):
    t = dt.datetime.fromtimestamp(ts, M.UTC).astimezone(M.D.ET)
    return f"{t:%b %-d, %-I:%M %p}"


def record_table(state, esc, now_ts=None):
    rows = ""
    for bid in M.BIDS:
        r = M.record(state, bid, now_ts)
        head = bid == M.HEAD
        name = f'<b>{round(bid * 100)}c bid · hold</b>{" · headline" if head else " · comparison"}'
        rows += (f'<tr data-bid="{M.key(bid)}"><td>{name}</td><td class="num">{r["entries"]}</td><td class="num">{r["open"]}</td>'
                 f'<td class="num">{r["settled_events"]}</td><td class="num">{r["won"]} / {r["settled"]}</td>'
                 f'<td class="num">{_pct(r["roi"]) if r["settled_events"] else "pending"}</td><td class="num">{_z(r["z"])}</td>'
                 f'<td>{esc(MS.status(r["settled_events"]))}</td></tr>')
    return ('<div class="tbl"><table class="dip-record"><thead><tr><th>Row</th><th class="num">Entries</th><th class="num">Unsettled</th>'
            '<th class="num">Settled weeks</th><th class="num">Won / settled</th><th class="num">ROI after fees</th>'
            '<th class="num">z (by week)</th><th>Status</th></tr></thead><tbody>' + rows + "</tbody></table></div>")


def week_table(state, esc, now_ts=None):
    """Every word whose bid filled, 10c and 15c side by side, for the latest week."""
    if not state.get("events"):
        return '<p class="sm mut">No week has been read yet.</p>'
    tick = max(state["events"])
    mk = state["events"][tick]["markets"]
    by = {bid: {e["ticker"]: e for e in M.entries(state, bid, now_ts)} for bid in M.BIDS}
    rows = ""
    for t in sorted({t for d in by.values() for t in d}, key=lambda t: (mk[t].get("word") or t).lower()):
        cells = ""
        for bid in M.BIDS:
            e = by[bid].get(t)
            cells += (f'<td>{_clock(e["fill_ts"])} · {e["fill_px"] * 100:.0f}c</td><td class="num">{e["contracts"]:g}</td>' if e
                      else '<td class="mut">no entry</td><td class="num">—</td>')
        res = M.payout(mk[t])
        rows += (f'<tr><td><b>{esc(mk[t].get("word") or t)}</b></td>{cells}'
                 f'<td>{"said, settled yes" if res == 1 else "settled no" if res == 0 else "open"}</td></tr>')
    rows = rows or '<tr><td colspan="6" class="mut">No bid has filled yet.</td></tr>'
    words = len(mk)
    return (f'<p class="sm"><b>{esc(tick)}</b> · {words} word markets · {len(by[0.10])} filled at 10c, {len(by[0.15])} at 15c</p>'
            '<div class="tbl"><table class="dip-week"><thead><tr><th>Word</th><th>10c fill</th><th class="num">Contracts at 10c fill</th>'
            '<th>15c fill</th><th class="num">Contracts at 15c fill</th><th>Market</th></tr></thead><tbody>'
            + rows + "</tbody></table></div>")


def research_fold(esc):
    r = M.RESEARCH
    rows = "".join(f'<tr><td><b>{round(b * 100)}c bid · hold</b></td><td class="num">{n}</td><td class="num">{roi}</td>'
                   f'<td class="num">{z}</td><td class="num">{up}</td></tr>' for b, n, roi, z, up in r["rows"])
    return (f'<details class="fold sm" id="dip-research"><summary><b>Research ({r["weeks"]} weeks, in-sample)</b> '
            '<span class="mut">the weeks the rule was chosen on · not evidence</span></summary>'
            f'<p class="sm">{r["weeks"]} settled weekly KXTRUMPSAY events, Aug 31 to Oct 26 2026, verified on trades. At 10c, {r["won10"]} '
            f'of 134 fills were said, against a {r["breakeven10"]} break-even. Selling at 2x, 3x or 4x added nothing (-11% to +15%); '
            'buying at the open ask lost.</p>'
            '<div class="tbl"><table class="dip-research"><thead><tr><th>Row</th><th class="num">Fills</th><th class="num">ROI after fees</th>'
            f'<th class="num">z (by week)</th><th class="num">Weeks up</th></tr></thead><tbody>{rows}</tbody></table></div></details>')


def section(state, esc, now_ts=None):
    last = state.get("last_success")
    return (f'<section id="dip-hold"><h2>{esc(M.LABEL)}</h2>'
            '<p class="sm"><b>Rest a YES bid at 10c from the open and hold it to settlement. Only a word whose first trade is above the '
            'bid counts; it fills on a print at or under the bid with 10+ contracts within an hour.</b></p>'
            '<p class="sm mut">Sandbox, paper only. Weekly KXTRUMPSAY, every word, one entry per word per week. Maker fee on the entry, '
            'none at settlement. A week is one outcome, counted once all its entries settle: review at 10 weeks, decide at 30. '
            f'The record is fresh from the week of {esc(M.FIRST_EVENT)}.</p>'
            f'{record_table(state, esc, now_ts)}'
            f'<details class="fold sm" id="dip-week" open><summary><b>This week\'s entries</b> <span class="mut">10c and 15c side by side</span></summary>'
            f'{week_table(state, esc, now_ts)}</details>'
            f'{research_fold(esc)}'
            f'<p class="sm mut">Last read {esc(last or "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p></section>')
