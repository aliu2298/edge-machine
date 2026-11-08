"""The three phase-4 WATCH lanes (soccer_p4_lanes.py, 2026-11-08) as rows on the Soccer page, one row per lane, every word
and table inside the row's closed "Rule details" fold (the NHL page's panel). Each lane's baseline sits in its own fold,
not as a row. Presentation only: every number is the ledger's own."""
import datetime as dt
import html as _h

import fmt
import soccer_lanes as L
import soccer_p4_lanes as P

RESEARCH = {
    # lane: (discovery, halves, holdout)
    "p4_mid_no": ("+40.5% on 47 matches", "+69% / +22%", "+29.2% on 11 (halves +18% / +35%)"),
    "p4_late_over": ("+44.3% on 29 matches", "+53% / +35%", "+13.5% on 20 (halves +20% / +9%)"),
    "p4_late_under": ("+15.1% on 35 matches", "+15% / +15%", "+14.4% on 7 (thin)"),
}


def esc(x):
    return _h.escape(str(x))


def pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%".replace("-", "−")


def zfmt(v):
    return "—" if v is None else f"{v:+.2f}".replace("-", "−")


def params(lane):
    cfg = P.BY_LANE[lane]
    moment = ("An hour before ESPN's kickoff, the last 1-minute quote, spread 5c or less." if cfg["mom"] == "pre" else
              "Minute 75: half-time is the close of the match's 1st-half market, the 2nd half starts 15 minutes later, and "
              "the entry is 30 minutes after that, only when the score then equals the half-time score. Goals are placed "
              "by ESPN's clock and timed by the spread market's own price jump. Quote no older than 3 minutes, spread 5c "
              "or less.")
    labels = ("Each team's last 10 competitive matches before kickoff against its league's mean goals per team: O+/O− "
              "scores at least / less than it, D+/D− concedes at least / less. Only matches that kicked off before this "
              "one count, and the labels are frozen on the row.")
    return [
        ("Entry", cfg["words"]),
        ("Moment", moment),
        ("Labels", labels),
        ("Leagues", "Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League, MLS, Eredivisie, Primeira Liga."),
        ("Fill", "Taker at the ask, counted only when 50+ contracts trade at or through it within 5 minutes. Taker fee in, "
                 "held to settlement. A maker variant (a resting bid filled by a print through it within 15 minutes) is "
                 "shown below, never as the headline."),
        ("Record", f"Fresh from {P.REGISTERED[:16].replace('T', ' ')} UTC, paper only, one row per entry, z clustered by "
                   f"match. Review at {P.REVIEW_N} settled entries, decide at {P.DECIDE_N}."),
        ("Watch", P.SHUFFLE_NOTE),
    ]


def research_table(lane):
    disc, halves, hold = RESEARCH[lane]
    rows = [("Discovery (Aug to Nov 2026, quote ask)", disc), ("Halves", halves), ("August holdout", hold),
            ("Shuffled-label null", "failed: a WATCH forward test")]
    body = "".join(f'<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>' for k, v in rows)
    return (f'<div class="tbl"><table><thead><tr><th>Research</th><th>Figure</th></tr></thead><tbody>{body}</tbody></table>'
            '</div>')


def record_table(s, head="Record"):
    rows = [
        ("Settled entries · matches", f'{s["n"]} · {s["games"]}'),
        ("Won v priced", f'{s["won"]} v {s["priced"]:.1f}'),
        ("ROI per entry, after fees", pct(s["roi"])),
        ("z by match", zfmt(s["z"])),
        ("Earlier half · later half", f'{pct(s["old"])} · {pct(s["new"])}'),
        ("State check v2 only", f'{pct(s["v2"])} ({s["v2_n"]})'),
        ("Logged rows without a fill", str(s["logged"] - s["n"])),
        ("Read", P.read_of(s["n"])),
    ]
    body = "".join(f'<tr><td>{esc(k)}</td><td class="num">{esc(v)}</td></tr>' for k, v in rows)
    return f'<div class="tbl"><table><thead><tr><th>{esc(head)}</th><th class="num">Figure</th></tr></thead><tbody>{body}</tbody></table></div>'


def _when(ts):
    return fmt.when(dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat())


def _contract(r):
    if r["kind"] == "GAME":
        return f'{r["name"]} wins · NO'
    return f'Over {r.get("strike")} · {r["side"].upper()}'


def entry_table(rows):
    if not rows:
        return '<p class="sm mut">No entry yet.</p>'
    body = []
    for r in sorted(rows, key=lambda r: r["ts"], reverse=True):
        t, m = r["taker"], r["maker"]
        labs = r.get("labels") or {}
        body.append(f'<tr><td>{esc(_when(r["ts"]))}</td><td>{esc(r["title"])}</td>'
                    f'<td>{esc((labs.get("home") or "—") + " v " + (labs.get("away") or "—"))}</td>'
                    f'<td>{esc(_contract(r))}</td><td class="num">{r["ask"] * 100:.0f}c</td>'
                    f'<td>{"filled" if t["filled"] else "no fill"}</td><td>{"won" if r["won"] else "lost"}</td>'
                    f'<td class="num">{esc(pct(t["roi"]) if t["filled"] else "—")}</td>'
                    f'<td class="num">{esc(pct(m["roi"]) if m["filled"] else "—")}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Entry</th><th>Match</th><th>Labels</th><th>Contract</th>'
            '<th class="num">Ask</th><th>Taker</th><th>Result</th><th class="num">Taker ROI</th><th class="num">Maker ROI</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def panel(state, lane):
    rows = P.rows_for(state, lane)
    base = P.BASELINE[lane]
    out = [L.params_html(params(lane)), research_table(lane), record_table(P.summary(rows)),
           record_table(P.summary(rows, "maker"), "Maker variant (fold only)")]
    n = len(rows)
    out.append(f'<details class="section-disclosure"><summary><b>Entries</b><span>{n} logged row{"s" if n != 1 else ""}</span></summary>'
               f'{entry_table(rows)}</details>')
    b = P.BY_LANE[base]
    out.append(f'<details class="section-disclosure baseline"><summary><b>{esc(b["label"])}</b><span>not a lane</span></summary>'
               f'<p class="sm mut">{esc(b["words"])} {esc(b["research"])}</p>'
               f'{record_table(P.summary(P.rows_for(state, base)), "Baseline")}</details>')
    return "".join(out)


def template_row(state, lane):
    cfg = P.BY_LANE[lane]
    rows = P.rows_for(state, lane)
    s = P.summary(rows)
    won = sum(1 for r in rows if r["taker"]["filled"] and r["won"])
    r = L.row(lane, "soccer", cfg["label"], cfg["market"], L.inplay_record(s["n"], won, s["roi"], s["z"]),
              panel(state, lane), anchor=lane.replace("_", "-"), kind="Pre-match" if cfg["mom"] == "pre" else "In-play",
              note="Watch forward test. Record: taker fills with 50+ contracts of depth, held to settlement, after fees.")
    r["pin"] = True        # near the top of the Sandbox list (Olu, 2026-11-08), not sunk with the too-early rows
    return r


def rows(state=None):
    state = state if state is not None else P.load()
    return [template_row(state, lane) for lane in P.HEADLINES]
