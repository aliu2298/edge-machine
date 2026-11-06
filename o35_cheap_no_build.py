"""The Soccer page's "Cheap side + resting bid" section for o35_cheap_no_wave (o35_cheap_no.py), near the top.

Read from the lane's own ledger (data/o35_cheap_no_ledger.json). Header-row tables, so the page's own
label_cells names each cell for the phone layout. Never breaks the page: soccer_build wraps the call.
"""
import datetime as dt
import html as _h
import os

import chaos_replay as CR
import o35_cheap_no as O

HEAD = O.vkey(O.HEADLINE, O.HEAD_MULT)
V1_HEAD = O.vkey(O.HEADLINE, O.V1_HEAD_MULT)
# The ROI basis change (2026-10-31, Olu): chaos_replay.stats(), which this section reads, moved from sum profit / sum
# cost to the equal-stake mean. Said once, with the headline and hold as they read on the old basis that day.
ROI_BASIS = dict(on="2026-10-31", head=0.0786, hold=-0.1796, n=36)


def esc(x):
    return _h.escape(str(x))


def pct(v, sign=True):
    return "—" if v is None else (f"{v * 100:+.0f}%" if sign else f"{v * 100:.0f}%")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}"


def clock(ts):
    t = dt.datetime.fromtimestamp(ts, O.UTC).astimezone(O.ET)
    return f"{t:%b %-d, %-I:%M %p}"


def halves(rows):
    """ROI of the older and the newer half of a variant's rows (by kickoff), or (None, None) under 4 rows."""
    rows = sorted(rows, key=lambda r: r["kickoff"])
    if len(rows) < 4:
        return None, None
    k = len(rows) // 2
    return CR.stats(rows[:k])["roi"], CR.stats(rows[k:])["roi"]


def read_of(n, delta=None):
    if n < O.REVIEW_N:
        return f"too early ({n} of {O.REVIEW_N})"
    if n < O.DECIDE_N:
        return f"review ({n} of {O.DECIDE_N} to decide)"
    return "decide"


def variant_table(rows, limits, head, mults, hold):
    """One row per exit. v2 shows 4x (headline) and 3x only; the v1 fold shows everything it ever recorded."""
    body = []
    for lim in limits:
        hs = CR.stats([r for r in rows if r["variant"] == O.vkey(lim, None)])
        for m in mults:
            key = O.vkey(lim, m)
            rs = [r for r in rows if r["variant"] == key]
            s = CR.stats(rs)
            old, new = halves(rs)
            delta = None if m is None or s["roi"] is None or hs["roi"] is None else s["roi"] - hs["roi"]
            bold = " class=\"hl\"" if key == head else ""
            hcell = f'<td class="num">{pct(hs["roi"]) if m is not None else "—"}</td>' if hold else ""
            body.append(f'<tr data-variant="{key}"{bold}><td><b>{esc(O.vlabel(key))}{" (headline)" if key == head else ""}</b></td>'
                        f'<td class="num">{s["n"]}</td><td class="num">{s["won"]}</td><td class="num">{pct(s["roi"])}</td>'
                        f'{hcell}'
                        f'<td class="num">{zfmt(s["z"])}</td><td class="num">{s["nights"]}</td>'
                        f'<td class="num">{pct(old)}</td><td class="num">{pct(new)}</td>'
                        f'<td class="num">{sum(1 for r in rs if r["dead"])}</td><td class="num">{sum(1 for r in rs if r["thin"])}</td>'
                        f'<td>{esc(read_of(s["n"], delta if hold else None))}</td></tr>')
    hh = '<th class="num">Hold, same bid</th>' if hold else ""
    return ('<div class="tbl"><table><tr><th>Bid · exit</th><th class="num">Filled</th><th class="num">Won</th>'
            f'<th class="num">ROI after fees</th>{hh}<th class="num">z (by night)</th>'
            '<th class="num">Nights</th><th class="num">Older half</th><th class="num">Newer half</th>'
            '<th class="num">Dead fills</th><th class="num">Thin sells</th><th>Read</th></tr>' + "".join(body) + "</table></div>")


def league_table(entries, rows, head, hold_on=True):
    head_rows = [r for r in rows if r["variant"] == head]
    hold_rows = [r for r in rows if r["variant"] == O.vkey(O.HEADLINE, None)]
    sell = head.split("_")[1]
    hh = '<th class="num">Hold</th>' if hold_on else ""
    body = []

    def row(name, games, sel, bold=True):
        a = CR.stats([r for r in head_rows if sel(r)])
        h = CR.stats([r for r in hold_rows if sel(r)])
        hc = f'<td class="num">{pct(h["roi"]) if h["n"] else "—"}</td>' if hold_on else ""
        nm = f"<b>{esc(name)}</b>" if bold else f"<i>{esc(name)}</i>"
        body.append(f'<tr><td>{nm}</td><td class="num">{games}</td><td class="num">{a["n"]}</td>'
                    f'<td class="num">{pct(a["roi"]) if a["n"] else "—"}</td>{hc}</tr>')

    for lg in sorted({e["league"] for e in entries}):
        row(lg, sum(1 for e in entries if e["league"] == lg), lambda r, lg=lg: r["league"] == lg)
    forms = sum(1 for e in entries if e["form_rule"])
    row("Over 1.5 form-rule matches", forms, lambda r: r["form_rule"], False)
    row("All other matches", len(entries) - forms, lambda r: not r["form_rule"], False)
    return ('<div class="tbl"><table><tr><th>League</th><th class="num">Games</th><th class="num">Filled at 10c</th>'
            f'<th class="num">Sell at {sell}</th>{hh}</tr>' + "".join(body) + "</table></div>")


def trade_list(entries, mults, hold, limit=30, field="bids"):
    filled = [(e, e[field].get("10")) for e in entries if (e.get(field) or {}).get("10")]
    filled.sort(key=lambda x: x[0]["kickoff"], reverse=True)
    body = []
    for e, b in filled[:limit]:
        cells = []
        cost = b["limit"] + O.fee(b["limit"])
        for m in mults:
            s = b["sells"][str(m)]
            tag = "sold" if s["filled"] else ("thin" if s["thin"] else "held")
            proceeds = s["target"] - O.fee(s["target"]) if s["filled"] else b["payout"]
            cells.append(f'<td class="num">{(proceeds - cost) / cost * 100:+.0f}% {tag} · {s["volume"]:.0f}</td>')
        hc = f'<td class="num">{(b["payout"] - cost) / cost * 100:+.0f}%</td>' if hold else ""
        body.append(f'<tr><td>{esc(clock(e["kickoff"]))}</td><td>{esc(e["event"].split("-", 1)[-1])}</td><td>{esc(e["league"])}</td>'
                    f'<td class="num">{b["fill_print"] * 100:.0f}c{" · dead fill" if b["dead"] else ""}</td>'
                    + "".join(cells) + hc + '</tr>')
    cols = 4 + len(mults) + (1 if hold else 0)
    body = "".join(body) or f'<tr><td colspan="{cols}" class="mut">No bid has filled yet.</td></tr>'
    heads = "".join(f'<th class="num">Sell at {m}x · contracts</th>' for m in mults) + ('<th class="num">Hold</th>' if hold else "")
    return ('<div class="tbl"><table><tr><th>Kickoff (ET)</th><th>Match</th><th>League</th><th class="num">Filled at</th>'
            + heads + '</tr>' + body + "</table></div>")


def v1_fold(entries):
    """The v1 record as it stands, collapsed: every bid, every exit, the old 2x headline, hold included."""
    if not entries:
        return ""
    rows = O.trade_rows(entries)
    f10 = [e for e in entries if (e["bids"] or {}).get("10")]
    dead = sum(1 for e in f10 if e["bids"]["10"]["dead"])
    summ = f'{len(entries)} games · {len(f10)} bids filled at 10c · {dead} dead · closed 2026-10-31'
    allm = (None,) + O.MULTS
    return (f'<details class="section-disclosure" data-lane="{O.LANE}_v1"><summary><b>{esc(O.V1_LABEL)}</b><span>{esc(summ)}</span></summary>'
            f'<p class="sm">The first record: 10c, 15c and 20c bids in twelve leagues, headline sold at 2x, ended 2026-10-31 and shown as it stood. '
            f'{esc(O.TRIM_NOTE)}</p>'
            f'<p class="sm mut roi-basis">ROI basis changed {ROI_BASIS["on"]} from cost-weighted to equal-stake (the mean of each fill\'s ROI, the same quantity its z tests); '
            f'old figure: 10c bid sold at 2x {pct(ROI_BASIS["head"])}, hold {pct(ROI_BASIS["hold"])} on {ROI_BASIS["n"]} fills.</p>'
            + variant_table(rows, O.V1_LIMITS, V1_HEAD, allm, True)
            + '<p class="sm"><b>By league, and the over 1.5 form-rule matches</b> · 10c bid, sell at 2x</p>'
            + league_table(entries, rows, V1_HEAD) + '</details>')


def v2_fold(entries):
    """The v2 record (bid an hour before kickoff, 4x headline, 3x beside it), collapsed."""
    if not entries:
        return ""
    rows = O.trade_rows(entries)
    f10 = [e for e in entries if (e["bids"] or {}).get("10")]
    dead = sum(1 for e in f10 if e["bids"]["10"]["dead"])
    summ = f'{len(entries)} games · {len(f10)} bids filled at 10c · {dead} dead · closed 2026-11-01'
    return (f'<details class="section-disclosure" data-lane="{O.LANE}_v2"><summary><b>{esc(O.V2_LABEL)}</b><span>{esc(summ)}</span></summary>'
            f'<p class="sm">The second record: the 10c bid rested from an hour before kickoff, so it could fill in either half; sold at 4x, 3x beside it. '
            f'Ended 2026-11-01 and shown as it stood; the live record from the follower covers its fills.</p>'
            + variant_table(rows, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False)
            + '<p class="sm"><b>By league, and the over 1.5 form-rule matches</b> · 10c bid, sell at 4x</p>'
            + league_table(entries, rows, HEAD, False) + '</details>')


V4_NOTE = ("Why v4 (2026-11-02): on Nov 1 the live account and the v3 paper record differed on seven matches. Five live bids were "
           "rejected as post-only crosses because No was already at or under the bid when the bid went up, and are not retried "
           "(Racing Santander v Real Madrid, Nashville v Red Bull New York, Basaksehir v Samsun, Telstar v Utrecht, Groningen v Sparta), "
           "yet v3 counted them as fills. Athletic v Real Sociedad rested unfilled while v3 filled it on a print exactly at the bid. "
           "One sell was refused by the exchange in the live account and has since been fixed. v4 enters a match only if No is above "
           "the bid at the bid minute, and fills only on a trade strictly under the bid; re-scored on Nov 1 it reproduces the live fills.")


def v3_fold(entries):
    """The v3 record (second-half bid, touch fills, no crossing check), collapsed."""
    if not entries:
        return ""
    rows = O.trade_rows(entries)
    f10 = [e for e in entries if (e["bids"] or {}).get("10")]
    dead = sum(1 for e in f10 if e["bids"]["10"]["dead"])
    summ = f'{len(entries)} games · {len(f10)} bids filled at 10c · {dead} dead · closed 2026-11-02'
    return (f'<details class="section-disclosure" data-lane="{O.LANE}_v3"><summary><b>{esc(O.V3_LABEL)}</b><span>{esc(summ)}</span></summary>'
            f'<p class="sm">The third record: the second-half bid, filled on a print at or under the bid, with no check for a bid the exchange would reject. '
            f'Ended 2026-11-02 and shown as it stood.</p><p class="sm mut">{esc(V4_NOTE)}</p>'
            + variant_table(rows, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False)
            + '<p class="sm"><b>By league, and the over 1.5 form-rule matches</b> · 10c bid, sell at 4x</p>'
            + league_table(entries, rows, HEAD, False) + '</details>')


def section(state=None):
    if state is None:
        state = O.load() if os.path.exists(O.PATH) else O.load("/nonexistent")
    all_entries = sorted(state.get("entries") or [], key=lambda e: e["kickoff"])
    old, v2, v3 = O.split3(all_entries)
    entries = [e for e in all_entries if e.get("version") == O.VERSION]
    rows = O.trade_rows(entries)
    early_rows = O.trade_rows(entries, early=True)
    filled10 = [e for e in entries if (e["bids"] or {}).get("10")]
    dead = sum(1 for e in filled10 if e["bids"]["10"]["dead"])
    thin = sum(1 for e in filled10 if e["bids"]["10"]["sells"][str(O.HEAD_MULT)]["thin"])
    last = state.get("last_run")
    summ = (f'{len(entries)} games · {len(filled10)} bids filled at 10c · {dead} dead · {thin} thin' if entries
            else "0 entries since the v4 record began")
    shown = (O.COMPARE_MULT, O.HEAD_MULT)
    body = (variant_table(rows, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False)
            + '<p class="sm"><b>By league, and the over 1.5 form-rule matches</b> · 10c bid, sell at 4x</p>'
            + league_table(entries, rows, HEAD, False) if entries else '<p class="sm mut">0 entries: no game has settled since the v4 record began on '
            f'{esc(state.get("since"))}. The first rows appear after the first matches finish.</p>')
    return f"""<section id="cheap-side">
<h2>Cheap side · resting bid</h2>
<p class="shell-kicker">Paper only · no orders · fresh v4 record (second-half bid the exchange would accept) since {esc(state.get("since"))} · review at {O.REVIEW_N} filled, decide at {O.DECIDE_N}</p>
<details class="section-disclosure" data-lane="{O.LANE}" open><summary><b>{esc(O.LABEL)}</b><span>{esc(summ)}</span></summary>
<p class="sm"><b class="chip">Production</b> since 2026-11-01 the follower trades this rule live on Kalshi: a resting NO bid at 10c in a small fixed size, posted an hour after kickoff (the second half only); on a fill it rests a sell at 40c (4x); the unfilled bid is cancelled at the final whistle and an unsold position is held to settlement. Never chases, never takes. The live record is the follower&#39;s own fills. The paper record below is unchanged and keeps running beside it.</p>
<p class="sm mut">{esc(O.TRIM_NOTE)}</p>
<p class="sm mut">{esc(O.RESEARCH_NOTE)}</p>
<p class="sm">On the over 3.5 goals market of every game in the eleven leagues on this page, a NO bid rests at 10c from {O.BID_AFTER_MIN} minutes after kickoff. It can fill only in the second half, after goals push the over to 80c or more. A match is not entered when No already sits at or under the bid at that minute (the exchange would reject the bid), and a fill needs a trade strictly under the bid. The headline sells at 4x the bid (40c); selling at 3x is shown beside it.</p>
<p class="sm">A bid fills when the first trade after it prints NO at or under the bid. Fills after the 4th goal are kept and marked dead fill. A sell counts only if a later trade prints at or above its target and at least {O.MIN_VOL} contracts traded at or above the target after the fill; fewer is marked thin and the trade is held. Fees: 1.75% of p(1-p) on both legs. Kickoff is the Kalshi time minus 4 hours.</p>
{body}
<details class="section-disclosure"><summary><b>Fills</b><span>latest 30 at 10c</span></summary>{trade_list(entries, shown, False)}</details>
<details class="section-disclosure" data-lane="{O.LANE}_first_half"><summary><b>First-half fills, tracked</b><span>{len(early_rows) // 4} bids from the old time that filled before the break</span></summary>
<p class="sm">The old bid (posted an hour before kickoff), counted only where it filled in the first {O.BID_AFTER_MIN} minutes. Kept only so the split stays measured.</p>
{variant_table(early_rows, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False) if early_rows else '<p class="sm mut">No first-half fill yet in the v3 record.</p>'}</details>
{v3_fold(v3)}{v2_fold(v2)}{v1_fold(old)}
</details>
<p class="sm mut">Last read {esc(last or 'not yet')}{(' · ' + esc(state['error'])) if state.get('error') else ''}.</p>
</section>"""


def honest_table(entries):
    """Each record re-scored under the honesty rules (a fill strictly under the bid; a sell on prints 60+ seconds after the fill), against
    its own old figure, on each version's headline exit and 10c bid."""
    body = ""
    for label, vs, mult in (("v1 · 10c bid, sell at 2x", (O.V1,), O.V1_HEAD_MULT), ("v2 · sell at 4x", (O.V2,), O.HEAD_MULT),
                            ("v3 · second-half bid, sell at 4x", (O.V3,), O.HEAD_MULT), ("v4 · second-half bid, sell at 4x", (O.VERSION,), O.HEAD_MULT)):
        es = [e for e in entries if e.get("version", O.V1) in vs and "honest" in e]
        key = O.vkey(O.HEADLINE, mult)
        new = CR.stats([r for r in O.trade_rows(es, field="honest") if r["variant"] == key])
        old = CR.stats([r for r in O.trade_rows(es) if r["variant"] == key])
        body += (f'<tr><td><b>{esc(label)}</b></td><td class="num">{len(es)}</td><td class="num">{old["n"]}</td><td class="num">{pct(old["roi"])}</td>'
                 f'<td class="num">{new["n"]}</td><td class="num">{new["won"]}</td><td class="num">{pct(new["roi"])}</td><td class="num">{zfmt(new["z"])}</td></tr>')
    return ('<div class="tbl"><table><tr><th>Record</th><th class="num">Games re-scored</th><th class="num">Fills before</th><th class="num">ROI before</th>'
            '<th class="num">Fills honest</th><th class="num">Won honest</th><th class="num">ROI honest</th><th class="num">z honest</th></tr>' + body + "</table></div>")


HONEST_RULE = ("Honest rules: a fill needs a trade strictly under the bid (the queue), and a sell counts only on prints at least "
               f"{O.SELL_DELAY_S} seconds after the fill (order latency), with the same {O.MIN_VOL}-contract volume rule counted over those later prints.")
STOP_NOTE = ("Production 2026-11-01 to 2026-11-06, then switched off: 21 live fills, 4 sold at 40c, -33% after fees. In paper, 15 of 15 2x sells and "
             "4 of 6 4x sells printed within a minute of the fill; the live fills came 68 to 131 minutes in and none held. Back in the Sandbox until the paper rules match what the exchange does.")


def panel(state=None):
    """The v4 row's "Rule details" fold on the Soccer page: the rule, the HONEST record (2026-11-06), then folds. The record before
    the honesty rules (the exits, league split, fills, first-half fills and v3 / v2 / v1) sits in one closed fold, unchanged."""
    if state is None:
        state = O.load() if os.path.exists(O.PATH) else O.load("/nonexistent")
    all_entries = sorted(state.get("entries") or [], key=lambda e: e["kickoff"])
    old, v2, v3 = O.split3(all_entries)
    entries = [e for e in all_entries if e.get("version") == O.VERSION]
    rows = O.trade_rows(entries)
    hrows = O.trade_rows(entries, field="honest")
    early_rows = O.trade_rows(entries, early=True)
    filled10 = [e for e in entries if (e["bids"] or {}).get("10")]
    hfilled = [e for e in entries if (e.get("honest") or {}).get("10")]
    dead = sum(1 for e in filled10 if e["bids"]["10"]["dead"])
    thin = sum(1 for e in filled10 if e["bids"]["10"]["sells"][str(O.HEAD_MULT)]["thin"])
    summ = (f'{len(entries)} games · {len(filled10)} bids filled at 10c · {dead} dead · {thin} thin' if entries
            else "0 entries since the v4 record began")
    left = sum(1 for e in all_entries if "honest" not in e)
    last = state.get("last_run")
    fold = lambda title, hint, body, extra="": (                # noqa: E731
        f'<details class="section-disclosure"{extra}><summary><b>{esc(title)}</b><span>{esc(hint)}</span></summary>{body}</details>')
    honest_body = (variant_table(hrows, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False) if entries
                   else f'<p class="sm mut">0 entries since {esc(state.get("since"))}.</p>')
    earlier = (fold("Exits", "sell at 4x (headline) and 3x, before the honesty rules", variant_table(rows, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False)
                    + '<p class="sm"><b>By league, and the over 1.5 form-rule matches</b> · 10c bid, sell at 4x</p>' + league_table(entries, rows, HEAD, False))
               if entries else "")
    first_half = (variant_table(early_rows, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False) if early_rows
                  else '<p class="sm mut">No first-half fill yet in the v3 record.</p>')
    earlier += (fold("Fills", "latest 30 at 10c, before the honesty rules", trade_list(entries, (O.COMPARE_MULT, O.HEAD_MULT), False))
                + fold("First-half fills, tracked", f"{len(early_rows) // 4} bids from the old time that filled before the break",
                       f'<p class="sm">The old bid (posted an hour before kickoff), counted only where it filled in the first {O.BID_AFTER_MIN} minutes.</p>' + first_half,
                       f' data-lane="{O.LANE}_first_half"')
                + v3_fold(v3) + v2_fold(v2) + v1_fold(old))
    return (f'<p class="sm sp-rule-line">Entry: a NO bid at 10c on the over 3.5 market of every game in eleven leagues, from {O.BID_AFTER_MIN} minutes after kickoff (second half only); not entered when No already sits at or under the bid.</p>'
            f'<p class="sm sp-rule-line">Exit: sell at 4x (40c), 3x tracked; the unfilled bid is cancelled at the final whistle, an unsold position held. Paper. {esc(HONEST_RULE)}</p>'
            f'<p class="sm"><b>v4, honest record</b> since {esc(state.get("since"))} · {len(hfilled)} bids filled · review at {O.REVIEW_N} filled, decide at {O.DECIDE_N}'
            f'{f" · {left} games still being re-scored" if left else ""}</p>'
            + honest_body
            + fold("Honest re-score by version", "v1, v2, v3 and v4 against their old figures", honest_table(all_entries))
            + fold("Live run", "Production 2026-11-01 to 2026-11-06, ended", f'<p class="sm">{esc(STOP_NOTE)}</p>')
            + fold("Before the honesty rules", f"the old v4 record and v3, v2, v1 as they stood · {summ}", earlier)
            + fold("Research notes", "why the bid sits where it does", f'<p class="sm mut">{esc(O.TRIM_NOTE)}</p><p class="sm mut">{esc(O.RESEARCH_NOTE)}</p>')
            + f'<p class="sm mut">Last read {esc(last or "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>')


def v5_panel(state=None):
    """The v5 row's fold: the rule, its record beside v4 re-scored on the same nights, the fills."""
    if state is None:
        state = O.load() if os.path.exists(O.PATH) else O.load("/nonexistent")
    es = [e for e in sorted(state.get("entries") or [], key=lambda e: e["kickoff"]) if e.get("night", "") >= O.SINCE_V5 and "v5" in e]
    v4 = [e for e in es if e.get("version") == O.VERSION]
    rows5 = O.trade_rows(es, field="v5")
    rows4 = O.trade_rows(v4, field="honest")
    fold = lambda title, hint, body: (                          # noqa: E731
        f'<details class="section-disclosure"><summary><b>{esc(title)}</b><span>{esc(hint)}</span></summary>{body}</details>')
    side = []
    for label, rs in (("v5 · bid cancelled at minute 80", rows5), ("v4 re-scored · bid kept to the end", rows4)):
        for m in (O.HEAD_MULT, O.COMPARE_MULT):
            s = CR.stats([r for r in rs if r["variant"] == O.vkey(O.HEADLINE, m)])
            side.append(f'<tr><td><b>{esc(label)} · sell at {m}x</b></td><td class="num">{s["n"]}</td><td class="num">{s["won"]}</td>'
                        f'<td class="num">{pct(s["roi"])}</td><td class="num">{zfmt(s["z"])}</td><td class="num">{s["nights"]}</td></tr>')
    beside = ('<div class="tbl"><table><tr><th>Record (same nights)</th><th class="num">Filled</th><th class="num">Won</th><th class="num">ROI after fees</th>'
              '<th class="num">z (by night)</th><th class="num">Nights</th></tr>' + "".join(side) + "</table></div>")
    n5 = len([e for e in es if (e.get("v5") or {}).get("10")])
    last = state.get("last_run")
    return (f'<p class="sm sp-rule-line">Entry: the v4 second-half NO bid at 10c, under the honest rules; the bid is cancelled {O.CANCEL_MIN} minutes after kickoff '
            f'(match minute 80, about), so there are no late fills.</p>'
            f'<p class="sm sp-rule-line">Exit: sell at 4x (40c), 3x tracked; unsold held to settlement. Paper. {esc(HONEST_RULE)}</p>'
            f'<p class="sm"><b>v5</b> since {esc(O.SINCE_V5)} · {len(es)} games · {n5} bids filled · review at {O.REVIEW_N} filled, decide at {O.DECIDE_N}</p>'
            + (variant_table(rows5, O.LIMITS, HEAD, (O.HEAD_MULT, O.COMPARE_MULT), False) if es else f'<p class="sm mut">0 games since {esc(O.SINCE_V5)}.</p>')
            + fold("Beside v4 re-scored", "the same nights, the same honest rules, the bid kept to the end", beside)
            + fold("Fills", "latest 30 at 10c", trade_list(es, (O.COMPARE_MULT, O.HEAD_MULT), False, field="v5"))
            + f'<p class="sm mut">Last read {esc(last or "not yet")}{(" · " + esc(state["error"])) if state.get("error") else ""}.</p>')


def place(html, state=None):
    """Put the section near the top: before the page's first <section id=...> in <main>. Never breaks the page."""
    try:
        import sandbox_build
        sec = sandbox_build.label_cells(section(state))
        at = html.find("<section id=", html.find("<main"))
        return html[:at] + sec + html[at:] if at >= 0 else html
    except Exception:                                           # noqa: BLE001
        return html
