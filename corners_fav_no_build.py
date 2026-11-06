"""The Soccer page's row for Corners total · favourite-side NO (v2) (2026-11-06, Olu).

One row in the Sandbox rules table, right under Corners total under. Its headline is the lane's own entry, the MAKER
bid (corners_fav_no.py); the same rung at the taker ask (the Sandbox rule's row) is the comparison, shown beside it in
the row's fold with the fill rate. The row exists from registration, before the first entry.
"""
import html as _h

import corners_fav_no as C
import sandbox_sources as S

NAME, SPORT = "corners_fav_no", "soccer_corners"
AFTER = "corners_total_under"
IN_SAMPLE = ("On 188 settled match-total rungs in the corners_market baseline (Oct 15 to Nov 6): No ask 60c or more hit "
             "73% v 65% priced, +8.5%, z +0.97; No under 30c hit 12% v 23%, −45%. The corners_under form model's Brier "
             "0.2028 equals the market mid's 0.2028, so it adds nothing; Yes + No asks sum to about 1.08 (an 8c spread). "
             "This is the reason for looking, never the record: the lane is judged on its own entries only.")


def esc(x):
    return _h.escape(str(x))


def _pct(x):
    return "—" if x is None else f"{x * 100:+.1f}%".replace("-", "−")


def headline(m):
    """The maker record in the template's shape (one entry a match)."""
    return dict(n=m["n"], n_price=0, won=m["won"], expected=m["priced"], roi_fee=m["roi"],
                z=m["z"] if m["z"] is not None else 0.0, n_bets=m["n"], unit="match")


def record_table(rec):
    m, t = rec["maker"], rec["taker"]
    heads = ("Entry", "Bids filled", "Settled", "Won", "Priced to win", "ROI after fees", "Open")
    rate = f'{m["filled"]} of {m["placed"]}' + (f' ({m["filled"] / m["placed"] * 100:.0f}%)' if m["placed"] else "")
    rows = (("Maker: No bid at the ask − 2c (headline)", rate, m["n"], m["won"], f'{m["priced"]:.1f}', _pct(m["roi"]),
             m["open"]),
            ("Taker: the same rung at the No ask, every selected match (comparison)", "every entry", t["n"], t["won"],
             f'{t["priced"]:.1f}', _pct(t["roi"]), t["open"]),
            ("Taker, on the matches the bid filled", "filled", rec["taker_filled"]["n"], rec["taker_filled"]["won"],
             f'{rec["taker_filled"]["priced"]:.1f}', _pct(rec["taker_filled"]["roi"]), "—"),
            ("Taker, on the matches the bid did not fill", "not filled", rec["taker_unfilled"]["n"],
             rec["taker_unfilled"]["won"], f'{rec["taker_unfilled"]["priced"]:.1f}', _pct(rec["taker_unfilled"]["roi"]), "—"))
    body = "".join("<tr>" + f'<td data-l="{heads[0]}">{esc(r[0])}</td>'
                   + "".join(f'<td class="num" data-l="{h}">{esc(c)}</td>' for h, c in zip(heads[1:], r[1:])) + "</tr>"
                   for r in rows)
    return ('<div class="tbl"><table><thead><tr><th>Entry</th>' + "".join(f'<th class="num">{h}</th>' for h in heads[1:])
            + f'</tr></thead><tbody>{body}</tbody></table></div>')


def details(d, rec):
    from soccer_lanes import params_html
    skips = (((d.get("meta") or {}).get("lane_skips") or {}).get(NAME) or {})
    bet_keys = {S.corners_fixture_key(q) for q in C.entries(d)}
    skips = {k: v for k, v in skips.items() if k not in bet_keys}
    last = max(skips.values(), key=lambda v: v.get("at") or "") if skips else None
    m = rec["maker"]
    return (params_html([
        ("Entry", "On a match whose own Kalshi 1X2 board has a favourite of 0.55+ (de-vigged), within 4h of kickoff: "
                  "the LOWEST N whose No ask is 0.60 or more (No book 5c or tighter), and no more than 0.95; if the "
                  "lowest qualifying rung's No is above 0.95 the match is skipped. The cheapest No at or above 60c, "
                  "never under 0.30. A No bid rests at that ask − 2c until kickoff and fills only on a print strictly below it"),
        ("Exit", "Held to Kalshi's own settlement; maker fee 0.0175 × p × (1 − p)"),
        ("Leagues", "Every league the corners feed reads, the Champions League included"),
        ("Count", f"One entry a match, 5 a day · read after Corners total under and the Champions League fade, which "
                  f"keep their matches · fresh record from {C.REGISTERED} · review at 10 settled, decide at 30"),
        ("Bids", f'{m["waiting"]} waiting for kickoff' if m["waiting"] else ""),
        ("Filled v not", "A bid fills only on a print below it, so a fill can mean the price moved against the entry; "
                         "the taker rows on the matches it filled and did not fill show whether that happens here"),
        ("Skipped", f"{len(skips)} match{'' if len(skips) == 1 else 'es'}, last: {last.get('label')}, {last.get('reason')}"
                    if last else ""),
    ]) + record_table(rec)
        + '<details class="section-disclosure"><summary><b>In-sample</b><span>why this lane</span></summary>'
        f'<p class="sm mut">{esc(IN_SAMPLE)}</p></details>')


def row(d, rows, state=None):
    """The lane's row: the tracker's row for it (taker entries, recent picks) with the maker record as its headline,
    or, before its first entry, a fresh one. Placed right under Corners total under."""
    import soccer_lanes as L
    state = state if state is not None else C.load()
    rec = C.records(d, state)
    base = next((r for r in rows if r["name"] == NAME and r["sport"] == SPORT), None)
    meta = S.SOURCES[NAME]
    a = headline(rec["maker"])
    out = dict(base or dict(name=NAME, sport=SPORT, prod=False, gone=None, since=None, side="b"),
               # The fold says the rule in its own lines, so the registration note (on the Sandbox page) is not repeated.
               meta=dict((base or {}).get("meta") or meta, note=""),
               a=a, open=rec["maker"]["open"] + rec["maker"]["waiting"], v=L.verdict(a), after=AFTER,
               own=dict(label=meta["label"], market="Corners · No", details=details(d, rec), entries=""))
    return out


def place(d, rows, state=None):
    """`rows` with the lane's row in it (replacing the tracker's own row for it)."""
    return [r for r in rows if not (r["name"] == NAME and r["sport"] == SPORT)] + [row(d, rows, state)]
