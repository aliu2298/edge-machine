"""The NBA page's Rules section: the seven Sandbox label rules (nba_rules.py), paper only."""
import html as _h
import json
import os

import fmt
import nba_rules as NR


def esc(x):
    return _h.escape(str(x))


def _record(picks):
    done = [p for p in picks if p["status"] in ("won", "lost", "no_result")]
    won = sum(p["status"] == "won" for p in done)
    roi = sum(p.get("profit", 0) for p in done) / (100 * len(done)) if done else None
    return len(done), won, roi


def section(state=None):
    if state is None:
        state = NR.load() if os.path.exists(NR.PATH) else {"rules": {k: {"picks": []} for k in NR.RULES}}
    rows, recent = [], []
    for key, meta in NR.RULES.items():
        picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
        n, won, roi = _record(picks)
        live = sum(p["status"] == "open" for p in picks)
        rows.append(f'<tr><td><b>{esc(key)}</b></td><td>{esc(meta["label"])}</td>'
                    f'<td class="num">{n}</td><td class="num">{won}</td>'
                    f'<td class="num">{"—" if roi is None else f"{roi * 100:+.1f}%"}</td>'
                    f'<td class="num">{live}</td></tr>')
        recent += picks
    recent.sort(key=lambda p: p.get("start") or "", reverse=True)
    pick_rows = []
    for p in recent[:25]:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        money = f" · ${p['profit']:+.2f}" if p.get("profit") is not None else ""
        pick_rows.append(f'<tr><td>{esc(fmt.when(p["start"]) if p.get("start") else "")}</td><td>{esc(p["match"])}</td>'
                         f'<td>{esc(p["team"])}</td><td><b>{esc(p["rule"])}</b></td>'
                         f'<td>{esc(p.get("title") or "")}</td><td>{esc(p["side"].upper())}</td>'
                         f'<td class="num">{p["price"] * 100:.0f}c</td><td>{esc(res + money)}</td></tr>')
    body = "".join(pick_rows) or '<tr><td colspan="8" class="mut">No entries yet: rules enter 20–90 minutes before tip-off once Kalshi lists the game\'s team-total and first-half markets.</td></tr>'
    last = state.get("last_run")
    return f"""<section id="rules">
<div class="nba-section-head"><div><h2>Sandbox rules</h2><p class="shell-kicker">Seven label rules from the 2026-27 preseason · paper at the Kalshi ask, 7% fee · not in Production</p></div></div>
<div class="tbl"><table><thead><tr><th>Rule</th><th>Definition</th><th class="num">Settled</th><th class="num">Won</th><th class="num">ROI after fee</th><th class="num">Open</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<details class="section-disclosure"><summary><b>Entries</b><span>latest 25</span></summary>
<div class="tbl"><table><thead><tr><th>Tip</th><th>Game</th><th>Team</th><th>Rule</th><th>Contract</th><th>Side</th><th class="num">Price</th><th>Result</th></tr></thead>
<tbody>{body}</tbody></table></div></details>
<p class="sm mut">Labels are the rolling last-five O/D labels on this board (full game for team totals, first half for R5). Last scan {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>
</section>"""
