"""The Tennis page's row for tennis_atp_low_over (tennis_totals.py), paper only.

The row sits in the page's own Sandbox rules list, drawn with sport_page's markup (a closed
"Rule details" fold with the record cells), so it reads like every other Sandbox rule. Its
numbers come from its own ledger (data/tennis_totals_ledger.json), not the Sandbox ledger.
"""
import html as _h
import os
import re

import fmt
import sandbox_build as B
import sport_page as SP
import tennis_totals as TT

NAME = "ATP total games · low rung · OVER"
MARKET = "Kalshi ATP total games · over"
SANDBOX_LIST = '<div class="sp-rules-list" data-list="sandbox">'
EMPTY_SANDBOX = '<p class="sp-empty" data-empty="sandbox">'
# The Sandbox fold closes the Rules section (sport_page.rules_html); a rule row's own fold ends
# "</div></details>" too, so the list's end is found with the section close after it.
LIST_END = "</div></details></section>"
SANDBOX_COUNT = re.compile(r'(?<=<h3>Sandbox rules</h3><span class="sm mut">)· (\d+) rules?')
SANDBOX_COUNT_DONE = re.compile(r'(<h3>Sandbox rules</h3><span class="sm mut">· \d+ rules)')
EARLY_COUNT = re.compile(r'(?<=rules )· (\d+) too early to read')


def esc(x):
    return _h.escape(str(x))


def _state(state):
    if state is not None:
        return state
    return TT.load() if os.path.exists(TT.PATH) else TT.empty()


def row_data(state=None):
    """The sport_page row shape (a, v) for the lane, from its own ledger."""
    state = _state(state)
    picks = ((state.get("rules") or {}).get(TT.LANE) or {}).get("picks") or []
    a = TT.stats(picks)
    a["unit"] = "bet"
    return dict(name=TT.LANE, sport="tennis_total", a=a, v=B.verdict(dict(a, n=a["n"] + a["n_price"])),
                meta={"note": TT.DEFINITION}, picks=picks)


def _early(row):
    """Too early to read, counting no-result entries as settled (sport_page.is_early)."""
    a = row["a"]
    return SP.is_early(dict(row, a=dict(a, n=a["n"] + a["n_price"])))


def _entries(picks, limit=15):
    rows = []
    for p in sorted(picks, key=lambda p: p.get("start") or "", reverse=True)[:limit]:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        money = f" · ${p['profit']:+.2f}" if p.get("profit") is not None else ""
        rows.append(f'<tr><td>{esc(fmt.when(p["start"]))}</td><td>{esc(p["match"])}</td>'
                    f'<td>over {esc(p["line"])}</td><td class="num">{p["price"] * 100:.0f}c</td>'
                    f'<td>{esc(res + money)}</td></tr>')
    body = "".join(rows) or ('<tr><td colspan="5" class="mut">No entries yet: an ATP singles match enters '
                             '15-45 minutes before its ESPN start once its rung at or below 19.5 is quoted '
                             '0.70-0.92 with a spread of 5c or less.</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Start</th><th>Match</th><th>Rung</th>'
            f'<th class="num">Price</th><th>Result</th></tr></thead><tbody>{body}</tbody></table></div>')


def _record_words(a):
    if not (a["n"] or a["n_price"]):
        return "no settled entries"
    roi = "—" if a["roi_fee"] is None else B.pct(a["roi_fee"], sign=True)
    return f'{a["won"]}/{a["n"]} won · {a["won"]} v {a["expected"]:.1f} priced · z {a["z"]:+.2f} · ROI {roi} after fee'


def row_html(state=None):
    """One Sandbox rule row, sport_page.rule_row's markup, with its details fold."""
    state = _state(state)
    row = row_data(state)
    a = row["a"]
    base = TT.stats(((state.get("rules") or {}).get(TT.BASE) or {}).get("picks") or [])
    early = _early(row)
    last = state.get("last_run")
    open_words = f" · {a['open']} open" if a["open"] else ""
    details = (
        f'<div class="sp-details-body"><p class="sp-details-name"><b>{esc(NAME)}</b> · {esc(MARKET)} · '
        f'registered {esc(TT.REGISTERED)} · paper · own ledger</p>'
        f'{SP.definition_html(TT.DEFINITION)}{SP.definition_html(TT.PREREG, "mut")}'
        f'<p class="sp-def">Blind baseline (every in-window rung ≤19.5, ask 0.70-0.92): {esc(_record_words(base))}'
        f'{" · " + str(base["open"]) + " open" if base["open"] else ""}.</p>'
        f'<h4 class="sp-details-sub">Recent entries{open_words}</h4>'
        f'{_entries(row["picks"])}'
        f'<p class="sm mut">Last scan {esc(fmt.when(last) if last else "not yet")}'
        f'{(" · " + esc(state["error"])) if state.get("error") else ""}.</p></div>')
    return (
        f'<details class="sp-rule{" is-early" if early else ""}" data-source="{esc(TT.LANE)}" '
        f'data-sport="tennis_total" data-scope="clubs" data-stage="sandbox"{" data-early=\"1\"" if early else ""}>'
        f'<summary class="sp-line">'
        f'<span class="sp-cell sp-c-name"><span class="sp-chev" aria-hidden="true">›</span>'
        f'<b class="sp-name" title="{esc(NAME)}">{esc(NAME)}</b>'
        f'<span class="sp-badges"><span class="badge stage" title="Paper, own ledger">Paper</span></span>'
        f'<span class="sr-only"> · Rule details</span></span>'
        f'<span class="sp-cell sp-c-market" data-l="Market">{esc(MARKET)}</span>'
        f'<span class="sp-cell num" data-l="Record">{SP.record_compact(a)}</span>'
        f'<span class="sp-cell num" data-l="ROI after fees">{SP.roi_html(row)}</span>'
        f'<span class="sp-cell num" data-l="Won v priced">{esc(SP.won_v_priced(a))}</span>'
        f'<span class="sp-cell num" data-l="Evidence">{esc(SP.evidence(a))}</span>'
        f'<span class="sp-cell sp-c-verdict" data-l="Verdict">{SP.verdict_badge(row)}</span>'
        f'</summary>{details}</details>')


def place(html, state=None):
    """Put the row at the end of the page's Sandbox rules list; build the fold if the page has none."""
    try:
        row = row_html(state)
    except Exception as exc:                                    # noqa: BLE001
        row = f'<p class="sm mut" data-source="{esc(TT.LANE)}">{esc(NAME)} unavailable ({type(exc).__name__}).</p>'
    i = html.find(SANDBOX_LIST)
    if i >= 0:
        end = html.find(LIST_END, i)
        if end >= 0:
            early = _early(row_data(state))
            head = SANDBOX_COUNT.sub(lambda m: f"· {int(m.group(1)) + 1} rules", html[:i], count=1)
            if early:
                bumped = EARLY_COUNT.sub(lambda m: f"· {int(m.group(1)) + 1} too early to read", head, count=1)
                head = bumped if bumped != head else SANDBOX_COUNT_DONE.sub(r"\1 · 1 too early to read", head, count=1)
            return head + html[i:end] + row + html[end:]
    j = html.find(EMPTY_SANDBOX)
    if j >= 0:
        k = html.find("</p>", j) + len("</p>")
        fold = (f'<details class="fold sp-sandbox" id="sandbox"><summary><h3>Sandbox rules</h3>'
                f'<span class="sm mut">· 1 rule</span></summary>'
                f'{SANDBOX_LIST}{SP.list_head(False)}{row}</div></details>')
        return html[:j] + fold + html[k:]
    return html.replace("<footer>", f'<section id="atp-totals">{row}</section><footer>', 1)
