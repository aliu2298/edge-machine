"""The Soccer page's Team scoring rules section: the 8 Sandbox team-total label rules
(soccer_team_rules.py), paper only."""
import html as _h
import os

import fmt
import soccer_rules_build as SB
import soccer_team_rules as TR

SHORT = {"Premier League": "EPL", "Champions League": "UCL", "Europa League": "UEL"}


def esc(x):
    return _h.escape(str(x))


def section(state=None):
    if state is None:
        state = TR.load() if os.path.exists(TR.PATH) else {"rules": {k: {"picks": []} for k in TR.RULES}}
    groups, recent = [], []
    for g, words in TR.GROUPS.items():
        lines, picks_g = [], []
        for key, meta in TR.RULES.items():
            if meta["group"] != g:
                continue
            picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
            leagues = ", ".join(SHORT.get(x, x) for x in meta["leagues"])
            lines.append(SB.rule_line(key, leagues, meta["label"], meta.get("evidence"), picks))
            picks_g += picks
        recent += picks_g
        groups.append(SB.group_fold(g, words, lines, picks_g, opened=(g == "A"), scope="Leagues"))
    recent.sort(key=lambda p: p.get("start") or "", reverse=True)
    pick_rows = []
    for p in recent[:25]:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        money = f" · ${p['profit']:+.2f}" if p.get("profit") is not None else ""
        labs = p.get("labels") or {}
        pick_rows.append(f'<tr><td>{esc(fmt.when(p["start"]) if p.get("start") else "")}</td><td>{esc(p["match"])}</td>'
                         f'<td>{esc(p.get("team") or "")}</td>'
                         f'<td>{esc(labs.get("own") or "")} v {esc(labs.get("opp") or "")}</td>'
                         f'<td><b>{esc(p["rule"])}</b></td><td>{esc(p.get("title") or "")}</td><td>{esc(p["side"].upper())}</td>'
                         f'<td class="num">{p["price"] * 100:.0f}c</td><td>{esc(res + money)}</td></tr>')
    body = "".join(pick_rows) or ('<tr><td colspan="9" class="mut">No entries yet: rules enter 20–90 minutes before kickoff '
                                  'once both teams carry a label and Kalshi quotes the team total with a spread of 5c or less.</td></tr>')
    last = state.get("last_run")
    return f"""<section id="team-rules">
<div class="nba-section-head"><div><h2>Team scoring rules</h2><p class="shell-kicker">8 team-total label rules from 411 matches, Aug 1 – Oct 17 2026 · paper · not in Production · Kalshi price, 7% fee</p></div></div>
{"".join(groups)}
<details class="section-disclosure"><summary><b>Entries</b><span>latest 25</span></summary>
<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Match</th><th>Team</th><th>Labels</th><th>Rule</th><th>Contract</th><th>Side</th><th class="num">Price</th><th>Result</th></tr></thead>
<tbody>{body}</tbody></table></div></details>
<p class="sm mut">Labels: each team's last 10 competitive matches against its league's mean goals per team (O+/O− scores more/less, D+/D− concedes more/less), read as the contract's team v its opponent. 2+ is the over 1.5 rung, 3+ the over 2.5 rung. Last scan {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>
</section>"""
