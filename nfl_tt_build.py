"""The NFL page's rows for nfl_tt_over_3545 and nfl_tt_over_main (nfl_tt.py), paper only.

The rows sit in the page's own Sandbox rules list, drawn with sport_page's markup (a closed
"Rule details" fold with the record cells), so they read like every other Sandbox rule. Their
numbers come from their own ledger (data/nfl_tt_ledger.json), not the Sandbox ledger. Built on
tennis_totals_build (2026-10-21), the same placement, for two rows.
"""
import html as _h
import os
import re

import fmt
import sandbox_build as B
import sport_page as SP
import nfl_tt as N

MARKET = "Kalshi NFL team total · over"
SANDBOX_LIST = '<div class="sp-rules-list" data-list="sandbox">'
EMPTY_SANDBOX = '<p class="sp-empty" data-empty="sandbox">'
# The Sandbox fold closes the Rules section (sport_page.rules_html); a rule row's own fold ends
# "</div></details>" too, so the list's end is found with the section close after it.
LIST_END = "</div></details></section>"
SANDBOX_COUNT = re.compile(r'(?<=<h3>Sandbox rules</h3><span class="sm mut">)· (\d+) rules?')
SANDBOX_COUNT_DONE = re.compile(r'(<h3>Sandbox rules</h3><span class="sm mut">· \d+ rules)')
EARLY_COUNT = re.compile(r'(?<=rules )· (\d+) too early to read')
# The Rules section's own head: "1 in Production · 0 in the Sandbox".
HEAD_COUNT = re.compile(r'(<h2>Rules</h2><span class="sm mut">\d+ in Production · )(\d+)( in the Sandbox)')


def esc(x):
    return _h.escape(str(x))


def _state(state):
    if state is not None:
        return state
    return N.load() if os.path.exists(N.PATH) else N.empty()


def _picks(state, lane):
    return ((state.get("rules") or {}).get(lane) or {}).get("picks") or []


def row_data(lane, state=None):
    """The sport_page row shape (a, v) for one lane, from its own ledger."""
    state = _state(state)
    picks = _picks(state, lane)
    a = N.stats(picks)
    a["unit"] = "bet"
    return dict(name=lane, sport="nfl_team_total", a=a, v=B.verdict(dict(a, n=a["n"] + a["n_price"])),
                meta={"note": N.DEFINITION[lane]}, picks=picks)


def _early(row):
    """Too early to read, counting no-result entries as settled (sport_page.is_early)."""
    a = row["a"]
    return SP.is_early(dict(row, a=dict(a, n=a["n"] + a["n_price"])))


def _entries(picks, limit=15):
    rows = []
    for p in sorted(picks, key=lambda p: (p.get("start") or "", p.get("team") or ""), reverse=True)[:limit]:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        money = f" · ${p['profit']:+.2f}" if p.get("profit") is not None else ""
        rows.append(f'<tr><td>{esc(fmt.when(p["start"]))}</td><td>{esc(p["game"])}</td>'
                    f'<td>{esc(p["team"])} over {esc(p["line"])}</td><td class="num">{p["price"] * 100:.0f}c</td>'
                    f'<td>{esc(res + money)}</td></tr>')
    body = "".join(rows) or ('<tr><td colspan="5" class="mut">No entries yet: each team ladder enters '
                             '45-75 minutes before its ESPN kickoff, from rungs quoted two-sided with a '
                             'spread of 5c or less.</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Game</th><th>Rung</th>'
            f'<th class="num">Price</th><th>Result</th></tr></thead><tbody>{body}</tbody></table></div>')


def _record_words(a):
    if not (a["n"] or a["n_price"]):
        return "no settled entries"
    roi = "—" if a["roi_fee"] is None else B.pct(a["roi_fee"], sign=True)
    return (f'{a["won"]}/{a["n"]} won · {a["won"]} v {a["expected"]:.1f} priced · z {a["z"]:+.2f} '
            f'({a["weeks"]} week{"s" if a["weeks"] != 1 else ""}) · ROI {roi} after fee')


def row_html(lane, state=None):
    """One Sandbox rule row, sport_page.rule_row's markup, with its details fold."""
    state = _state(state)
    row = row_data(lane, state)
    a = row["a"]
    name = N.NAMES[lane]
    base = N.stats(_picks(state, N.BASE))
    early = _early(row)
    last = state.get("last_run")
    open_words = f" · {a['open']} open" if a["open"] else ""
    details = (
        f'<div class="sp-details-body"><p class="sp-details-name"><b>{esc(name)}</b> · {esc(MARKET)} · '
        f'registered {esc(N.REGISTERED)} · paper · own ledger</p>'
        f'{SP.definition_html(N.DEFINITION[lane])}{SP.definition_html(N.PREREG[lane], "mut")}'
        f'<p class="sp-def">This record: {esc(_record_words(a))}. z is clustered by NFL week.</p>'
        f'<p class="sp-def">Blind baseline (the YES on every in-window team-total rung, same quote): '
        f'{esc(_record_words(base))}{" · " + str(base["open"]) + " open" if base["open"] else ""}.</p>'
        f'<h4 class="sp-details-sub">Recent entries{open_words}</h4>'
        f'{_entries(row["picks"])}'
        f'<p class="sm mut">Last scan {esc(fmt.when(last) if last else "not yet")}'
        f'{(" · " + esc(state["error"])) if state.get("error") else ""}.</p></div>')
    return (
        f'<details class="sp-rule{" is-early" if early else ""}" data-source="{esc(lane)}" '
        f'data-sport="nfl_team_total" data-scope="clubs" data-stage="sandbox"{" data-early=\"1\"" if early else ""}>'
        f'<summary class="sp-line">'
        f'<span class="sp-cell sp-c-name"><span class="sp-chev" aria-hidden="true">›</span>'
        f'<b class="sp-name" title="{esc(name)}">{esc(name)}</b>'
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
    """Put both rows at the end of the page's Sandbox rules list; build the fold if the page has none."""
    rows, n_early = [], 0
    for lane in N.LANES:
        try:
            rows.append(row_html(lane, state))
            n_early += 1 if _early(row_data(lane, state)) else 0
        except Exception as exc:                                # noqa: BLE001
            rows.append(f'<p class="sm mut" data-source="{esc(lane)}">{esc(N.NAMES[lane])} unavailable '
                        f'({type(exc).__name__}).</p>')
    body, k = "".join(rows), len(rows)
    html = HEAD_COUNT.sub(lambda m: f"{m.group(1)}{int(m.group(2)) + k}{m.group(3)}", html, count=1)
    i = html.find(SANDBOX_LIST)
    if i >= 0:
        end = html.find(LIST_END, i)
        if end >= 0:
            head = SANDBOX_COUNT.sub(lambda m: f"· {int(m.group(1)) + k} rules", html[:i], count=1)
            if n_early:
                bumped = EARLY_COUNT.sub(lambda m: f"· {int(m.group(1)) + n_early} too early to read", head, count=1)
                head = bumped if bumped != head else SANDBOX_COUNT_DONE.sub(
                    rf"\1 · {n_early} too early to read", head, count=1)
            return head + html[i:end] + body + html[end:]
    j = html.find(EMPTY_SANDBOX)
    if j >= 0:
        e = html.find("</p>", j) + len("</p>")
        count = f"{k} rules" + (f" · {n_early} too early to read" if n_early else "")
        fold = (f'<details class="fold sp-sandbox" id="sandbox"><summary><h3>Sandbox rules</h3>'
                f'<span class="sm mut">· {count} · by evidence</span></summary>'
                f'{SANDBOX_LIST}{SP.list_head(False)}{body}</div></details>')
        return html[:j] + fold + html[e:]
    return html.replace("<footer>", f'<section id="nfl-team-totals">{body}</section><footer>', 1)
