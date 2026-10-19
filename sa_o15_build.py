"""The Soccer page's Argentina & Brasileirão over 1.5 section (sa_o15.py), paper only."""
import html as _h
import os

import fmt
import sa_o15 as SA
import soccer_rules_build as SB


def esc(x):
    return _h.escape(str(x))


def section(state=None):
    if state is None:
        state = SA.load() if os.path.exists(SA.PATH) else {"rules": {k: {"picks": []} for k in SA.ROWS}}
    lines, recent = [], []
    for key, row in SA.ROWS.items():
        picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
        lines.append(SB.rule_line(key, row["league"], "Every league match · over 1.5 goals · YES at the ask",
                                  row["evidence"], picks))
        recent += picks
    n, won, _roi = SB._record(recent)
    live = sum(p["status"] == "open" for p in recent)
    head = f"2 leagues · {n} settled · {won} won" + (f" · {live} open" if live else "")
    recent.sort(key=lambda p: p.get("start") or "", reverse=True)
    rows = []
    for p in recent[:25]:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        money = f" · ${p['profit']:+.2f}" if p.get("profit") is not None else ""
        rows.append(f'<tr><td>{esc(fmt.when(p["start"]) if p.get("start") else "")}</td><td>{esc(p["match"])}</td>'
                    f'<td><b>{esc(p["rule"])}</b></td><td class="num">{p["price"] * 100:.0f}c</td><td>{esc(res + money)}</td></tr>')
    body = "".join(rows) or ('<tr><td colspan="5" class="mut">No entries yet: every Argentine and Brasileirão league match '
                             'enters 20–90 minutes before kickoff once Kalshi quotes over 1.5 with a spread of 5c or less.</td></tr>')
    last = state.get("last_run")
    return f"""<section id="sa-o15">
<div class="nba-section-head"><div><h2>Argentina &amp; Brasileirão over 1.5 (paper)</h2><p class="shell-kicker">Every league match, YES on over 1.5 at the Kalshi ask, no selection · a league-character lane · paper · not in Production · 7% fee</p></div></div>
<details class="section-disclosure label-group" data-group="sa-o15" open><summary><b>Over 1.5, by league</b><span>{esc(head)}</span><span class="label-group-words">Research: every match, Jan–Oct 2026, ask 30 min before kickoff</span></summary>
<div class="sp-rules-list" data-list="sa-o15">{SB.rule_head("League")}{"".join(lines)}</div></details>
<details class="section-disclosure"><summary><b>Entries</b><span>latest 25</span></summary>
<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Match</th><th>League</th><th class="num">Price</th><th>Result</th></tr></thead>
<tbody>{body}</tbody></table></div></details>
<p class="sm mut">Argentina and the Brasileirão are judged apart, never pooled. The line is read from the Kalshi market title; a match whose names fit two fixtures is skipped. Last scan {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>
</section>"""
