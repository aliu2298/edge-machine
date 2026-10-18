"""The Soccer page's Rules section: the 21 total-goals and 3 BTTS Sandbox label rules (soccer_rules.py), paper only."""
import html as _h
import os

import fmt
import soccer_rules as SR


def esc(x):
    return _h.escape(str(x))


def _record(picks):
    done = [p for p in picks if p["status"] in ("won", "lost", "no_result")]
    won = sum(p["status"] == "won" for p in done)
    roi = sum(p.get("profit", 0) for p in done) / (100 * len(done)) if done else None
    return len(done), won, roi


# One compact row per rule, on the Rules section's own grid (sport_page: .sp-rules-list,
# .sp-line, .sp-cell with data-l for the phone labels). .is-label sets this list's columns:
# rule · league · definition · Settled · Won · ROI after fee · Open. Shared with
# soccer_team_rules_build.py so the two sections read alike.
COLS = (("Settled", "Settled"), ("Won", "Won"), ("ROI after fee", "ROI"), ("Open", "Open"))


def rule_head(scope="League"):
    cells = "".join(f'<span class="sp-cell num">{esc(h)}</span>' for h, _ in COLS)
    return (f'<div class="sp-line sp-head-line is-label" aria-hidden="true"><span class="sp-cell">Rule</span>'
            f'<span class="sp-cell">{esc(scope)}</span><span class="sp-cell">Definition</span>{cells}</div>')


def rule_line(key, scope, definition, evidence, picks):
    n, won, roi, live = *_record(picks), sum(p["status"] == "open" for p in picks)
    tip = f"{definition} · {evidence}" if evidence else definition
    ev = f' <small class="mut">· {esc(evidence)}</small>' if evidence else ""
    vals = (n, won, "—" if roi is None else f"{roi * 100:+.1f}%", live)
    nums = "".join(f'<span class="sp-cell num" data-l="{esc(short)}">{esc(v)}</span>' for (_, short), v in zip(COLS, vals))
    return (f'<div class="sp-line is-label" data-rule="{esc(key)}"><span class="sp-cell sp-c-id"><b>{esc(key)}</b></span>'
            f'<span class="sp-cell sp-c-market" title="{esc(scope)}">{esc(scope)}</span>'
            f'<span class="sp-cell sp-c-def" title="{esc(tip)}">{esc(definition)}{ev}</span>{nums}</div>')


def group_fold(g, words, lines, picks, opened, extra="", scope="League"):
    """One group as the page's section disclosure; its summary carries the count and the record."""
    n, won, _roi = _record(picks)
    live = sum(p["status"] == "open" for p in picks)
    head = f'{len(lines)} rule{"s" if len(lines) != 1 else ""} · {n} settled · {won} won' + (f" · {live} open" if live else "")
    return (f'<details class="section-disclosure label-group" data-group="{esc(g)}"{" open" if opened else ""}>'
            f'<summary><b>Group {esc(g)}</b><span>{esc(head)}</span><span class="label-group-words">{esc(words)}</span></summary>'
            f'<div class="sp-rules-list" data-list="label-{esc(g.lower())}">{rule_head(scope)}{"".join(lines)}</div>{extra}</details>')


# Group BTTS evidence (617 matches, Aug 1 - Oct 17 2026): only matchups positive in 3+ leagues and pooled.
BTTS_EVIDENCE = (
    ("D1", "O+D− v O+D−", "YES 45-75c", "Serie A 7/9, La Liga 4/6, Bundesliga 4/5, Eredivisie 4/4, Saudi 3/4, Ligue 1 3/3",
     "44/64 (69%) @61c", "+10.4%", "+1.34"),
    ("D2", "O−D− v O+D+", "NO 30-60c", "EPL 5/7, Turkey 3/5, La Liga 3/4, Ligue 1 2/3, Scotland 3/3",
     "25/49 @43c", "+13.6%", "+1.11"),
    ("D3", "O−D− v O+D−", "YES 40-70c", "La Liga 10/14, Serie A 4/6, Primeira 4/6, UCL 3/4",
     "54/86 (63%) @56c", "+8.2%", "+1.22"),
)
BTTS_NOTE = ('<details class="section-disclosure"><summary><b>Group BTTS evidence</b><span>617 matches</span></summary>'
             '<div class="tbl"><table><thead><tr><th>Rule</th><th>Matchup</th><th>Side</th><th>Leagues where it held</th>'
             '<th>Pooled</th><th class="num">After fee</th><th class="num">z</th></tr></thead><tbody>'
             + "".join(f'<tr><td><b>{esc(k)}</b></td><td>{esc(m)}</td><td>{esc(sd)}</td><td>{esc(lg)}</td><td>{esc(pl)}</td>'
                       f'<td class="num">{esc(r)}</td><td class="num">{esc(z)}</td></tr>' for k, m, sd, lg, pl, r, z in BTTS_EVIDENCE)
             + '</tbody></table></div><p class="sm mut">Caveat: no single box reached z +2, so these are B-tier, breadth across '
               'leagues rather than strength. D1 is the same matchup as the total-goals over pattern. One Kalshi market per '
               'match; YES means both teams score.</p></details>')


def section(state=None):
    if state is None:
        state = SR.load() if os.path.exists(SR.PATH) else {"rules": {k: {"picks": []} for k in SR.RULES}}
    groups, recent = [], []
    for g, words in SR.GROUPS.items():
        lines, picks_g = [], []
        for key, meta in SR.RULES.items():
            if meta["group"] != g:
                continue
            picks = (state.get("rules", {}).get(key) or {}).get("picks") or []
            scope = (f"All {len(SR.MARKETS[meta['market']])} BTTS leagues" if meta["league"] == SR.ALL else meta["league"])
            lines.append(rule_line(key, scope, meta["label"], meta.get("evidence"), picks))
            picks_g += picks
        recent += picks_g
        groups.append(group_fold(g, words, lines, picks_g, opened=(g == "A"), extra=BTTS_NOTE if g == "BTTS" else ""))
    recent.sort(key=lambda p: p.get("start") or "", reverse=True)
    pick_rows = []
    for p in recent[:25]:
        res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(p["status"], p["status"])
        money = f" · ${p['profit']:+.2f}" if p.get("profit") is not None else ""
        labs = p.get("labels") or {}
        pick_rows.append(f'<tr><td>{esc(fmt.when(p["start"]) if p.get("start") else "")}</td><td>{esc(p["match"])}</td>'
                         f'<td>{esc(labs.get("home") or "")} v {esc(labs.get("away") or "")}</td>'
                         f'<td><b>{esc(p["rule"])}</b></td><td>{esc(p.get("title") or "")}</td><td>{esc(p["side"].upper())}</td>'
                         f'<td class="num">{p["price"] * 100:.0f}c</td><td>{esc(res + money)}</td></tr>')
    body = "".join(pick_rows) or '<tr><td colspan="8" class="mut">No entries yet: rules enter 20–90 minutes before kickoff once both teams carry a label and Kalshi quotes the match total inside the rule\'s price range.</td></tr>'
    last = state.get("last_run")
    return f"""<section id="label-rules">
<div class="nba-section-head"><div><h2>Sandbox rules</h2><p class="shell-kicker">21 total-goals rules from 674 matches and 3 both-teams-to-score rules from 617, Aug 1 – Oct 17 2026 · paper at the Kalshi price, 7% fee · not in Production</p></div></div>
{"".join(groups)}
<details class="section-disclosure"><summary><b>Entries</b><span>latest 25</span></summary>
<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Match</th><th>Labels</th><th>Rule</th><th>Contract</th><th>Side</th><th class="num">Price</th><th>Result</th></tr></thead>
<tbody>{body}</tbody></table></div></details>
<p class="sm mut">Labels: each team's last 10 competitive matches against its league's mean goals per team (O+/O− scores more/less, D+/D− concedes more/less); pairs read either way round. Last scan {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>
</section>"""
