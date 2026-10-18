"""The Soccer page's Title contenders' matches · overs section (contender_overs.py), paper only."""
import html as _h
import os

import contender_overs as CO
import fmt
import soccer_rules_build as SB


def esc(x):
    return _h.escape(str(x))


def section(state=None):
    if state is None:
        state = CO.load() if os.path.exists(CO.PATH) else {"rules": {k: {"picks": []} for k in CO.VARIANTS}}
    lines, recent = [], []
    for key, v in CO.VARIANTS.items():
        picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
        lines.append(SB.rule_line(key, "Eredivisie, Primeira", f"Contender's match · {v['words']}", v["evidence"], picks))
        recent += picks
    n, won, _roi = SB._record(recent)
    live = sum(p["status"] == "open" for p in recent)
    head = f"3 variants · {n} settled · {won} won" + (f" · {live} open" if live else "")
    recent.sort(key=lambda p: (p.get("start") or "", p.get("rule") or ""), reverse=True)
    rows = []
    for p in recent[:25]:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        money = f" · ${p['profit']:+.2f}" if p.get("profit") is not None else ""
        tops = ", ".join(f"{c['team']} {c['mid'] * 100:.0f}c" for c in p.get("contenders") or [])
        rows.append(f'<tr><td>{esc(fmt.when(p["start"]) if p.get("start") else "")}</td><td>{esc(p["match"])}</td>'
                    f'<td>{esc(", ".join(p.get("contenders_in") or []))}</td><td class="mut">{esc(tops)}</td>'
                    f'<td><b>{esc(p["rule"])}</b></td><td class="num">{p["price"] * 100:.0f}c</td><td>{esc(res + money)}</td></tr>')
    body = "".join(rows) or ('<tr><td colspan="7" class="mut">No entries yet: a variant enters 20–90 minutes before kickoff '
                             'when a top-3 title contender plays and Kalshi quotes the line with a spread of 5c or less.</td></tr>')
    last = state.get("last_run")
    return f"""<section id="contender-overs">
<div class="nba-section-head"><div><h2>Title contenders' matches · overs (paper)</h2><p class="shell-kicker">Eredivisie and Primeira league matches of a top-3 title contender, ranked by the Kalshi champion market at entry · paper · not in Production · Kalshi price, 7% fee</p></div></div>
<details class="section-disclosure label-group" data-group="contenders" open><summary><b>Over 1.5 / 2.5 / 3.5</b><span>{esc(head)}</span><span class="label-group-words">Point-in-time research, 44 matches, Aug–Oct 2026</span></summary>
<div class="sp-rules-list" data-list="contender-overs">{SB.rule_head("Leagues")}{"".join(lines)}</div></details>
<details class="section-disclosure"><summary><b>Entries</b><span>latest 25</span></summary>
<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Match</th><th>Contender</th><th>Top 3 at entry (mid)</th><th>Variant</th><th class="num">Price</th><th>Result</th></tr></thead>
<tbody>{body}</tbody></table></div></details>
<p class="sm mut">Contenders: the top 3 of the open Kalshi champion market by mid at entry, teams with no bid left out. Each variant buys YES at the ask on the match total. Last scan {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>
</section>"""
