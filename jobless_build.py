#!/usr/bin/env python3
"""The "Econ weekly" block of the Daily Markets tab (2026-11-11): the jobless claims NO 70-85c paper lane and its YES
comparison line, judged by weeks, from data/jobless_claims_ledger.json (jobless_claims.py). Few words; the rule, the
study evidence and the entries sit in closed folds."""
import html as _h

import jobless_claims as J


def esc(x):
    return _h.escape(str(x))


def _pct(x):
    return "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")


def _z(x):
    return "—" if x is None else f"{x:+.2f}".replace("-", "−")


def _row(label, rec, status):
    return (f'<tr><td><b>{esc(label)}</b></td><td>{status}</td>'
            f'<td class="num">{rec["weeks"]} ({rec["positive"]} positive)</td>'
            f'<td class="num">{rec["won"]} v {rec["priced"]:.1f}</td>'
            f'<td class="num">{_pct(rec["roi_week"])}</td><td class="num">{_z(rec["z"])}</td></tr>')


def _entries(state):
    rows = []
    for ev in sorted(state.get("events") or {}, reverse=True):
        st = state["events"][ev]
        for e in st.get("entries") or []:
            chk = (e.get("ask_check") or {}).get("status") or "checking"
            res = "open" if not e.get("result") else ("won" if e.get("won") else "lost")
            strike = "—" if e.get("strike") is None else f'{e["strike"]:,.0f}'
            rows.append(f'<tr><td>{esc((st.get("close") or "")[:10])}</td><td>{esc(e["side"].upper())} ≥ {esc(strike)}</td>'
                        f'<td class="num">{e["price"] * 100:.0f}c</td><td>{esc(chk)}</td><td>{esc(res)}</td></tr>')
        if not st.get("entries") and st.get("note"):
            rows.append(f'<tr><td>{esc((st.get("close") or "")[:10])}</td><td colspan="4" class="mut">{esc(st["note"])}</td></tr>')
    body = "".join(rows) or '<tr><td colspan="5" class="mut">No release read yet.</td></tr>'
    return ('<div class="tbl"><table><thead><tr><th>Release</th><th>Rung</th><th class="num">Ask</th><th>Ask check</th>'
            f'<th>Result</th></tr></thead><tbody>{body}</tbody></table></div>')


def section(state=None):
    state = state if state is not None else J.load()
    rec = J.week_record(J.entries(state, J.SIDE))
    cmp_ = J.week_record(J.entries(state, J.COMPARE))
    chip = f'<span class="sig n">{esc(J.stage(rec))} · {rec["weeks"]}/{J.REVIEW_WEEKS} wks</span>'
    table = ('<div class="tbl"><table class="jobless-weeks"><thead><tr><th>Rule</th><th>Status</th><th class="num">Weeks</th>'
             '<th class="num">Won v priced</th><th class="num">Mean week ROI</th><th class="num">z (weeks)</th></tr></thead><tbody>'
             + _row(J.LABEL, rec, chip)
             + _row(J.COMPARE_LABEL, cmp_, '<span class="sig n">comparison</span>')
             + '</tbody></table></div>')
    last = state.get("last_run")
    return f"""<section id="econ-weekly">
<h3>Econ weekly</h3>
<p class="sm mut">Paper · selects by price only; no filter yet · fresh from {esc(J.SINCE)} · review {J.REVIEW_WEEKS} weeks, decide {J.DECIDE_WEEKS}</p>
{table}
<details class="section-disclosure" id="jobless-rule"><summary><b>Rule and study</b><span>pre-registered {esc(J.REGISTERED)}</span></summary>
<ul class="sm"><li>Kalshi weekly initial jobless claims ladder.</li>
<li>From 3h to 1h before the 8:30 ET print, buy NO on each rung at a 70-85c ask, spread 10c or less. Hold to settlement.</li>
<li>Taker fee in. An entry counts only if 10+ contracts traded at or through its ask within the hour.</li>
<li>One release is one week. The YES side at 70-85c on the same ladder is the comparison.</li></ul>
<p class="sm mut">{esc(J.EVIDENCE)}</p></details>
<details class="section-disclosure" id="jobless-entries"><summary><b>Entries</b><span>{rec["open"]} open · {rec["unverified"]} unverified ask{"" if rec["unverified"] == 1 else "s"} · last read {esc((last or "not yet")[:16].replace("T", " "))}{" UTC" if last else ""}</span></summary>
{_entries(state)}</details>
</section>"""
