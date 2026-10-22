"""The NBA page's Safe Card section (nba_safe_card.py), paper only.

In the board's own style (nba_value_build.py): tonight's card with a rationale per leg, the card
and leg records, the legs' model calibration, and which filter mattered. Never breaks the board:
nba_pace_build wraps the call.
"""
import html as _h
import os

import fmt
import nba_safe_card as SC


def esc(x):
    return _h.escape(str(x))


def _pct(won, n):
    return "—" if not n else f"{won}/{n} ({won / n * 100:.0f}%)"


def _c(v, scale=100, unit="c", d=1):
    return "—" if v is None else f"{v * scale:.{d}f}{unit}"


def _leg_row(leg):
    res = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(leg.get("status"), leg.get("status"))
    what = f"{leg['unit']} team total" if leg["kind"] == "tt" else SC.MARKET_WORD[leg["kind"]]
    tip = "—" if leg.get("price_at_tip") is None else f"{leg['price_at_tip'] * 100:.0f}c"
    return (f'<tr><td>{esc(fmt.when(leg["start"]))}</td><td>{esc(leg["match"])}</td><td>{esc(what)}</td>'
            f'<td>{"OVER" if leg["side"] == "yes" else "UNDER"} {leg["line"]:g}</td>'
            f'<td class="num">{leg["price"] * 100:.0f}c</td><td class="num">{leg["p"] * 100:.1f}%</td>'
            f'<td class="num">{leg["edge"] * 100:+.1f}c</td><td class="num">{tip}</td><td>{esc(res)}</td></tr>'
            f'<tr class="sc-why"><td colspan="9" class="sm mut">{esc(leg["rationale"])}</td></tr>')


def card_html(card):
    if card is None:
        return ('<p class="sm mut">No card yet: the card is built once per slate, 60-90 minutes before the '
                'night\'s first tip.</p>')
    night = card["night"]
    if not card.get("legs"):
        return (f'<p><b>{esc(night)}</b> · no card · {esc(card.get("reason") or "")}</p>'
                f'<p class="sm mut">{esc(card.get("rationale") or "")}</p>')
    status = {"open": "open", "won": "won", "lost": "lost", "no_result": "no result"}.get(card["status"], card["status"])
    head = (f'<p><b>{esc(night)}</b> · {len(card["legs"])} legs · combined odds {card["odds"]:.2f} · '
            f'model combo chance {card["combo_p"] * 100:.0f}% · {esc(status)}</p>')
    rows = "".join(_leg_row(leg) for leg in card["legs"])
    return (head + f'<p class="sm mut">{esc(card.get("rationale") or "")}</p>'
            '<div class="tbl"><table><thead><tr><th>Tip</th><th>Game</th><th>Market</th><th>Leg</th>'
            '<th class="num">Price</th><th class="num">Model P</th><th class="num">Edge</th><th class="num">Price at tip</th>'
            f'<th>Result</th></tr></thead><tbody>{rows}</tbody></table></div>')


def section(state=None):
    if state is None:
        state = SC.load() if os.path.exists(SC.PATH) else SC.empty()
    cards = state.get("cards") or {}
    nights = sorted(cards, reverse=True)
    latest = cards[nights[0]] if nights else None
    r = SC.records(state)
    card_rec = (f"{r['won']} won · {r['lost']} lost · {r['open']} open · {r['no_card']} no-card night"
                f"{'s' if r['no_card'] != 1 else ''} · ${r['profit']:+.2f} at $1 a card")
    leg_rec = f"{_pct(r['legs_won'], r['legs'])} · ${r['leg_profit']:+.2f} at $1 a leg after the fee"
    steps = "".join(
        f'<tr><td>{esc(SC.STEP_WORDS[s["step"]])}</td><td class="num">{s["n"]}</td>'
        f'<td class="num">{_pct(s["won"], s["n"])}</td>'
        f'<td class="num">{_c(s["price"])}</td><td class="num">{_c(s["p"], unit="%")}</td></tr>' for s in r["steps"])
    calib = "".join(
        f'<tr><td>{c["lo"] * 100:.0f}-{c["hi"] * 100:.0f}%</td><td class="num">{c["n"]}</td>'
        f'<td class="num">{c["p"] * 100:.1f}%</td><td class="num">{_pct(c["won"], c["n"])}</td></tr>' for c in r["calibration"]
    ) or '<tr><td colspan="4" class="mut">No settled card legs yet.</td></tr>'
    hist = []
    for night in nights[1:15]:
        c = cards[night]
        if c.get("legs"):
            legs = ", ".join(f"{leg['match']} {'1Q ' if leg['kind'] == 'q1' else '1H ' if leg['kind'] == 'h1' else ''}"
                             f"{leg['unit'] + ' ' if leg['kind'] == 'tt' else ''}"
                             f"{'O' if leg['side'] == 'yes' else 'U'}{leg['line']:g} @{leg['price'] * 100:.0f}c" for leg in c["legs"])
            hist.append(f'<tr><td>{esc(night)}</td><td>{esc(c["status"])}</td><td class="num">{c["odds"]:.2f}</td><td>{esc(legs)}</td></tr>')
        else:
            hist.append(f'<tr><td>{esc(night)}</td><td>no card</td><td class="num">—</td><td class="mut">{esc(c.get("reason") or "")}</td></tr>')
    hist_html = "".join(hist) or '<tr><td colspan="4" class="mut">No earlier nights yet.</td></tr>'
    last = state.get("last_run")
    return f"""<section id="safe-card">
<div class="nba-section-head"><div><h2>Safe Card</h2><p class="shell-kicker">One card a slate: 3-4 legs priced 84-95c that the model, the value check and the labels all back, combined odds 1.70+ · paper · not in Production</p></div></div>
{card_html(latest)}
<div class="tbl"><table><thead><tr><th>Record</th><th>Since {esc(SC.REGISTERED)}</th></tr></thead><tbody>
<tr><td>Cards</td><td>{esc(card_rec)}</td></tr><tr><td>Card legs</td><td>{esc(leg_rec)}</td></tr></tbody></table></div>
<details class="section-disclosure"><summary><b>Which filter mattered</b><span>hit rate of the legs that passed each step, cut later or not</span></summary>
<div class="tbl"><table><thead><tr><th>Passed step</th><th class="num">Settled</th><th class="num">Hit</th><th class="num">Avg price</th><th class="num">Avg model P</th></tr></thead>
<tbody>{steps}</tbody></table></div></details>
<details class="section-disclosure"><summary><b>Model calibration</b><span>card legs</span></summary>
<div class="tbl"><table><thead><tr><th>Model P</th><th class="num">Legs</th><th class="num">Avg P</th><th class="num">Hit</th></tr></thead>
<tbody>{calib}</tbody></table></div></details>
<details class="section-disclosure"><summary><b>Earlier nights</b><span>latest 14</span></summary>
<div class="tbl"><table><thead><tr><th>Night</th><th>Card</th><th class="num">Odds</th><th>Legs or reason</th></tr></thead>
<tbody>{hist_html}</tbody></table></div></details>
<details class="section-disclosure"><summary><b>Rules and pre-registration</b><span>registered {esc(SC.REGISTERED)}</span></summary>
<p class="sm">Markets: Kalshi NBA team totals (both teams), 1st-quarter, 1st-half and full-game totals, every rung both ways (over at the YES ask, under at 1 − the YES bid). Model P: Normal with the value model's mu; sd 11.83 team, 8.28 1Q, 18.9 game (fitted 18.44, out of sample 19.11), 1H at 0.505 × the game mu with sd 13.0 (not fitted: no first-half history).</p>
<p class="sm">Funnel: (1) price 84-95c, two-sided, spread ≤3c; (2) model P ≥ 0.90; (3) P ≥ price + 3c; (4) labels agree: team over own O+ and opponent D+, under own O− and opponent D−; game over both D+, under both D−; 1Q and 1H over both O+, under both O−; (5) team totals: the team cleared (or stayed under) the line in 8 of its last 10; (6) best edge first, one leg per game, until combined odds ≥ 1.70 with 3-4 legs; (7) level guard: no card when the model sits more than 4 points from Kalshi's median team-total lines or more than 80% of 5+ label survivors are one side. Built once, 60-90 minutes before the slate's first tip; each leg's price is read again 60-90 minutes before its own tip.</p>
<p class="sm mut">Pre-registered 2026-10-22. Wednesday 2026-10-21's back-run: 62 legs after steps 1-3, 16 after labels; card PHX@POR game U249.5 @84c, MIL@WSH 1Q U68.5 @85c, UTAH@MEM 1H O104.5 @87c, GS@LAL game U253.5 @86c, combined odds 1.87, model combo chance about 70%. 2025-26 backtest: the model's 95% lines hit 94.4-94.9%; a label-filtered daily 3-leg card at the 95% line went 64/73 days. Caveat: the model sits about 2 points below Kalshi's lines this season, so the funnel leans to unders, which is what the level guard is for. Read at 20+ cards.</p></details>
<p class="sm mut">Last scan {esc(fmt.when(last) if last else "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>
</section>"""
