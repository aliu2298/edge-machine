"""The NFL page's row for nfl_tt_main1 (nfl_tt_main1.py), paper only.

One row of the NFL page's Sandbox rules list, the same template row as the other team-total lane
(nfl_tt_build.template_row): the record cells on the line, everything else in its "Rule details" fold. Its
numbers come from its own ledger (data/nfl_tt_main1_ledger.json); the blind baseline is nfl_tt's, read over
the same dates. The deep dive's numbers sit in the fold as a labelled in-sample note and are never counted.
"""
import datetime as dt
import html as _h
import os

import fmt
import sandbox_build as B
import sport_page as SP
import nfl_tt_build as TB
import nfl_tt_main1 as M

MARKET = TB.MARKET


def esc(x):
    return _h.escape(str(x))


def _state(state):
    if state is not None:
        return state
    return M.load() if os.path.exists(M.PATH) else M.empty()


def _picks(state, lane=M.LANE):
    return ((state.get("rules") or {}).get(lane) or {}).get("picks") or []


def floor(lane=M.LANE):
    return M.READ_AT.get(lane, SP.EVIDENCE_FLOOR)


def row_data(lane=M.LANE, state=None):
    state = _state(state)
    picks = _picks(state, lane)
    a = M.stats(picks)
    a["unit"] = "bet"
    v = B.verdict(dict(a, n=a["n"] + a["n_price"]))
    return dict(name=lane, sport="nfl_team_total", a=a, v=v, meta={"note": M.DEFINITION[lane]}, picks=picks)


def _entries(picks, limit=15):
    rows = []
    for p in sorted(picks, key=lambda p: (p.get("start") or "", p.get("team") or ""), reverse=True)[:limit]:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        rows.append(f'<tr><td>{esc(fmt.when(p["start"]))}</td><td>{esc(p["game"])}</td>'
                    f'<td>{esc(p["team"])} over {esc(p["line"])}</td><td>{esc(p.get("main_line", "—"))}</td>'
                    f'<td class="num">{p["price"] * 100:.0f}c</td><td>{esc(res)}</td></tr>')
    body = "".join(rows) or ('<tr><td colspan="6" class="mut">No entries yet: each team ladder enters 45-75 minutes '
                             'before its ESPN kickoff, on the rung one above its main line.</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Game</th><th>Rung</th><th>Main line</th>'
            f'<th class="num">Price</th><th>Result</th></tr></thead><tbody>{body}</tbody></table></div>')


def details_words(lane=M.LANE, state=None, base_state=None):
    """The words of the row's "Rule details" fold: registration, definition, pre-registration, record, reads,
    baseline over the same dates, in-sample note, entries, skips."""
    state = _state(state)
    row = row_data(lane, state)
    a = row["a"]
    base = M.stats(M.baseline_picks(base_state))
    last = state.get("last_run")
    skips = state.get("skips") or []
    open_words = f" · {a['open']} open" if a["open"] else ""
    return (f'<p class="sp-def mut">Registered {esc(M.REGISTERED)} · paper · own ledger · fresh record</p>'
            f'{SP.definition_html(M.DEFINITION[lane])}{SP.definition_html(M.PREREG[lane], "mut")}'
            f'<p class="sp-def">This record: {esc(TB._record_words(a))}. z is clustered by NFL week. '
            f'Review at {M.REVIEW_AT} settled entries, decide at {floor(lane)}.</p>'
            f'<p class="sp-def">Blind baseline (the YES on every in-window team-total rung, same quote, same dates): '
            f'{esc(TB._record_words(base))}{" · " + str(base["open"]) + " open" if base["open"] else ""}.</p>'
            f'<p class="sp-def mut nfl-tt-insample">{esc(M.IN_SAMPLE)}</p>'
            f'<h4 class="sp-details-sub">Recent entries{open_words}</h4>'
            f'{_entries(row["picks"])}'
            f'<p class="sm mut">Skipped ladders (no quoted rung above the main line): {len(skips)} · '
            f'last scan {esc(fmt.when(last) if last else "not yet")}'
            f'{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>')


def template_row(lane=M.LANE, state=None, base_state=None):
    """The lane as a row of the NFL page's own template lists (nfl_build): tiles, Sandbox count, Events."""
    state = _state(state)
    row = row_data(lane, state)
    row.update(prod=False, floor=floor(lane), open=row["a"]["open"], ledger="main1",
               own=dict(label=M.NAMES[lane], market=MARKET, details=details_words(lane, state, base_state)))
    return row


def events(rows, state=None, now=None):
    """The lane's entries as the template's events (open, and settled inside the window)."""
    state = _state(state)
    now = SP.as_utc(now)
    floor_t = now - dt.timedelta(days=SP.DONE_DAYS)
    by = {}
    for row in rows:
        for p in _picks(state, row["name"]):
            when = SP.instant(p.get("start"))
            st = {"open": "open", "won": "won", "lost": "lost", "no_result": "price"}.get(p.get("status"), "open")
            if st != "open" and (when or now) < floor_t:
                continue
            q = dict(start=p.get("start"), venue="kalshi_binary", market_id=p.get("ticker"), settled=p.get("settled"),
                     status=p.get("status"), label=p.get("game"))
            ev = by.setdefault((p.get("game"), p.get("start")), dict(when=when, label=p.get("game") or "", picks=[]))
            ev["picks"].append(SP.pick(row, q, f'{p.get("team")} over {p.get("line")}', st, price=p.get("price")))
    return [SP.event(e["when"], fmt.contest(e["label"]), e["picks"], key=(e["label"], str(e["when"]))) for e in by.values()]


def row_html(lane=M.LANE, state=None, base_state=None):
    """One Sandbox rule row in sport_page.rule_row's markup (for tests and a standalone read)."""
    state = _state(state)
    row = row_data(lane, state)
    a = row["a"]
    name = M.NAMES[lane]
    early = TB._early(row)
    details = (f'<div class="sp-details-body"><p class="sp-details-name"><b>{esc(name)}</b> · {esc(MARKET)} · '
               f'registered {esc(M.REGISTERED)} · paper · own ledger</p>'
               + details_words(lane, state, base_state).split("</p>", 1)[1] + '</div>')
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
        f'<span class="sp-cell num" data-l="Evidence">{int(a.get("n") or 0)}/{floor(lane)}</span>'
        f'<span class="sp-cell sp-c-verdict" data-l="Verdict">{SP.verdict_badge(row, floor(lane))}</span>'
        f'</summary>{details}</details>')
