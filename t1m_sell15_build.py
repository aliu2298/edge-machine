"""The Soccer page's row for t1m_sell15 (t1m_sell15.py, 2026-11-08): ONE observation-only Sandbox row right under T1 (beside
its siblings T1-H and T1-M; T1-M itself sits in the Production list), its fold the side-by-side readout against T1-M's hold on
the same entries, the in-sample backfill folded apart, the maker variant and the entries. Also a short readout inside T1-M's
own fold and a row in the Sandbox index. Presentation only: every number is the ledger's own."""
import datetime as dt
import html as _h

import fmt
import t1m_sell15 as T

ANCHOR = "t1m-sell15"


def esc(x):
    return _h.escape("" if x is None else str(x))


def pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%".replace("-", "−")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}".replace("-", "−")


def halves(h):
    return f"{pct(h[0])} · {pct(h[1])}"


def side_by_side(s, head="Forward record"):
    """T1-M's hold and the 1.5x sell on the same entries, one table."""
    rate = "—" if s["touch_rate"] is None else f'{s["touched"]}/{s["n"]} = {s["touch_rate"] * 100:.0f}% v fair 67%'
    rows = [
        ("Entries with a 1.5x target · matches", f'{s["n"]} · {s["matches"]}'),
        ("Touched 1.5x (50+ contracts, no sweep minute)", f'{rate} · z {zfmt(s["touch_z"])}'),
        ("Hold ROI, after fees (T1-M's exit)", f'{pct(s["hold"])} · z {zfmt(s["hold_z"])}'),
        ("Sell at 1.5x ROI, after fees", f'{pct(s["sell"])} · z {zfmt(s["sell_z"])}'),
        ("Difference, sell minus hold", f'{pct(s["diff"])} · z {zfmt(s["diff_z"])}'),
        ("Earlier half · later half: hold", halves(s["hold_h"])),
        ("Earlier half · later half: sell", halves(s["sell_h"])),
        ("Earlier half · later half: difference", halves(s["diff_h"])),
        ("Entries above 66c (no target under 99c)", str(s["no_target"])),
        ("Read", T.read_of(s["n"])),
    ]
    body = "".join(f'<tr><td>{esc(k)}</td><td class="num">{esc(v)}</td></tr>' for k, v in rows)
    return f'<div class="tbl"><table><thead><tr><th>{esc(head)}</th><th class="num">Figure</th></tr></thead><tbody>{body}</tbody></table></div>'


def params():
    return [
        ("Entries", "T1-M's own entries: the match over 3.5 YES bought at the ask 90-20 minutes before kickoff on a T1 match. "
                    "Same match, contract, price and time. T1-M's bets, stake and Production record are not touched."),
        ("Exit", "A resting sell at 1.5x the entry. It counts only when 50+ contracts trade at or above it after kickoff, "
                 "leaving out the minute after any sweep (a second printing 5c or more above the last price). Otherwise "
                 "held to Kalshi's settlement."),
        ("Fees", "Taker fee on the entry and, in the headline, on the sell. The maker-sell variant is below. The hold "
                 "beside it pays the same entry fee."),
        ("Record", f"Observation only, paper, fresh from {T.REGISTERED[:10]}. Review at {T.REVIEW_N} settled entries, decide "
                   f"at {T.DECIDE_N}."),
    ]


def entry_table(entries):
    if not entries:
        return '<p class="sm mut">No entry yet.</p>'
    body = []
    for e in sorted(entries, key=lambda e: e["ko"], reverse=True):
        when = fmt.when(dt.datetime.fromtimestamp(e["ko"], dt.timezone.utc).isoformat())
        tgt = "—" if e["target"] is None else f'{e["target"] * 100:.0f}c'
        hit = "—" if e["touched"] is None else ("touched" if e["touched"] else "not touched")
        body.append(f'<tr><td>{esc(when)}</td><td>{esc(e.get("match"))}</td><td class="num">{e["entry"] * 100:.0f}c</td>'
                    f'<td class="num">{tgt}</td><td>{hit}</td><td>{"won" if e["won"] else "lost"}</td>'
                    f'<td class="num">{esc(pct(e["hold"]))}</td><td class="num">{esc(pct(e["sell"]))}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Kickoff</th><th>Match</th><th class="num">Entry</th>'
            '<th class="num">Target</th><th>1.5x</th><th>Over 3.5</th><th class="num">Hold ROI</th><th class="num">Sell ROI</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def panel(state):
    import soccer_lanes as L
    s = T.summary(state["entries"])
    ins = state.get("insample") or {}
    i = T.summary(ins.get("entries") or [])
    maker = (f'<p class="sm mut">Maker-sell variant (maker fee on the exit): forward {pct(s["maker"])}, '
             f'in-sample {pct(i["maker"])}.</p>')
    out = [L.params_html(params()), side_by_side(s), maker,
           f'<details class="section-disclosure"><summary><b>Entries</b><span>{len(state["entries"])} logged</span></summary>'
           f'{entry_table(state["entries"])}</details>',
           f'<details class="section-disclosure insample"><summary><b>In-sample backfill · T1\'s ledger matches since '
           f'{esc(ins.get("since") or T.BACKFILL_FROM)}</b><span>not counted</span></summary>'
           f'<p class="sm mut">{esc(T.PHASE5_NOTE)} Entry = the over 3.5 ask at T1\'s logged time. Shown for reference '
           'only; the readout is judged on its forward record.</p>'
           f'{side_by_side(i, "In-sample (backfill)")}{entry_table(ins.get("entries") or [])}</details>']
    return "".join(out)


def row(state=None):
    """The Sandbox row, right under T1 with its siblings."""
    import soccer_lanes as L
    state = state if state is not None else T.load()
    s = T.summary(state["entries"])
    a = L.inplay_record(s["n"], s["touched"], s["sell"], s["sell_z"])
    r = L.row(T.LANE, "soccer_u35", T.LABEL, "Over 3.5 · resting sell", a, panel(state), prod=False, pair=None,
              anchor=ANCHOR, kind="In-play",
              note="Observation only: T1-M's entries with a resting 1.5x sell, beside T1-M's hold on the same entries.")
    r["after"] = T.PARENT
    return r


def fold_html(state=None):
    """A short readout inside T1-M's own fold: the forward side by side, and a link to the row."""
    state = state if state is not None else T.load()
    s = T.summary(state["entries"])
    i = T.summary((state.get("insample") or {}).get("entries") or [])
    return ('<details class="section-disclosure"><summary><b>1.5x sell readout</b><span>observation only</span></summary>'
            f'<p class="sm">Same entries, resting sell at 1.5x: forward {s["n"]} entries, sell {pct(s["sell"])} v hold '
            f'{pct(s["hold"])}, touched {s["touched"]}/{s["n"]}. In-sample backfill {i["n"]}: sell {pct(i["sell"])} v hold '
            f'{pct(i["hold"])}. <a href="#{ANCHOR}">The readout row</a>.</p></details>')


def index_row(state=None):
    """The Sandbox index row (chaos_build.index's columns: entries, settled events, won, headline ROI, hold, status)."""
    state = state if state is not None else T.load()
    s = T.summary(state["entries"])
    return (f'<tr data-lane="{T.LANE}"><td><b>{esc(T.LABEL)}</b></td><td><a href="./soccer.html#{ANCHOR}">Soccer</a></td>'
            f'<td class="num">{s["n"]}</td><td class="num">{s["matches"]}</td><td class="num">{s["won"]}</td>'
            f'<td class="num">{esc(pct(s["sell"]))}</td><td class="num">{esc(pct(s["hold"]))}</td>'
            f'<td>{esc("observation only · " + T.read_of(s["n"]))}</td></tr>')
