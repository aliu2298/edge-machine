"""Shared page parts for Club 90 (nba_qlines_build) and Club 82 (club82_build) after v2 (2026-11-25): the one-line-per-version header, the category table
(category | v1 | v2 cushion | v2 value | control), and the bets list (newest first, with the actual and 'cleared by'; backfilled rows under a toggle).
Percentages only. Tables carry no thead so the shared label pass names every cell for the phone cards."""
import html as _h

import fmt

REVIEW = (10, 30)
VERSIONS = (("v1", "v1"), ("cushion", "v2 cushion"), ("value", "v2 value"), ("control", "control"))


def esc(x):
    return _h.escape(str(x))


def pct(v, sign=True, d=1):
    return "—" if v is None else (f"{v * 100:+.{d}f}%".replace("-", "−") if sign else f"{v * 100:.{d}f}%")


def stats(picks, cost):
    """n settled, won, open, return on cost after fees. `cost` maps a price to price plus fee."""
    done = [p for p in picks if p.get("profit") is not None or p.get("status") in ("won", "lost")]
    done = [p for p in done if p.get("status") in ("won", "lost")]
    out = dict(n=len(done), won=sum(1 for p in done if p["status"] == "won"), open=sum(1 for p in picks if p.get("status") == "open"), ret=None)
    if done:
        out["ret"] = sum(p["payout"] - cost(p["price"]) for p in done) / sum(cost(p["price"]) for p in done)
    return out


def wl(s):
    return f"{s['won']}-{s['n'] - s['won']}"


def cell_text(s):
    return f"{wl(s)} · {pct(s['ret'])}"


def read_text(n):
    if n < REVIEW[0]:
        return f"{n} of {REVIEW[0]} settled"
    if n < REVIEW[1]:
        return f"{n} settled · first read due, next at {REVIEW[1]}"
    return f"{n} settled · second read due"


def version_lines(groups, cost):
    """groups: {version key: [picks]} for v1, cushion, value, control. One line each."""
    out = ""
    for key, label in VERSIONS:
        s = stats(groups.get(key) or [], cost)
        out += (f'<p class="sm club-version" data-version="{esc(key)}"><b>{esc(label)}</b> · {wl(s)} · {pct(s["ret"])} after fees · {s["open"]} open · '
                f'read at {REVIEW[0]}, then {REVIEW[1]} ({esc(read_text(s["n"]))})</p>')
    return out


def category_table(cats, cost):
    """cats: [(label, {version key: [picks]})]. Rows = category, columns = version."""
    rows = ""
    for label, groups in cats:
        cells = "".join(f'<td class="num">{esc(cell_text(stats(groups.get(k) or [], cost)))}</td>' for k, _ in VERSIONS)
        rows += f'<tr><td><b>{esc(label)}</b></td>{cells}</tr>'
    head = "".join(f'<th class="num">{esc(l)}</th>' for _, l in VERSIONS)
    return f'<div class="tbl"><table class="club-cats"><tr><th>Category</th>{head}</tr>{rows}</table></div>'


def bet_row(p, name_game, bet_text, ret_of):
    res = {"open": "open", "won": "won", "lost": "lost", "void": "void"}.get(p["status"], p["status"])
    r = ret_of(p)
    if r is not None:
        res += f" · {pct(r)}"
    cl = p.get("cleared")
    cleared = "—" if cl is None else ('<span class="%s">%s</span>' % ("pos" if cl > 0 else "neg", ("%+.1f" % cl).replace("-", "−")))
    actual = "—" if p.get("actual") is None else esc("%g" % p["actual"])
    line = esc("%g" % p["line"])
    return (f'<tr><td>{esc(fmt.when(p["start"]))}</td><td>{esc(name_game(p))}</td><td>{esc(bet_text(p))}</td><td class="num">{line}</td>'
            f'<td class="num">{actual}</td><td class="num">{cleared}</td><td class="num">{p["price"] * 100:.0f}c</td><td>{esc(res)}</td></tr>')


HEAD = ('<div class="tbl"><table class="club-bets"><tr><th>Tip</th><th>Game</th><th>Bet</th><th class="num">Line</th><th class="num">Actual</th>'
        '<th class="num">Cleared by</th><th class="num">Price</th><th>Result</th></tr>{}</table></div>')


def bets_block(picks, name_game, bet_text, ret_of, limit=30):
    """picks: lane rows of every version (not the controls). Live rows newest first; backfilled rows under a toggle."""
    live = sorted((p for p in picks if not p.get("backfilled")), key=lambda p: (p["start"], p["id"]), reverse=True)
    back = sorted((p for p in picks if p.get("backfilled")), key=lambda p: (p["start"], p["id"]), reverse=True)
    rows = "".join(bet_row(p, name_game, bet_text, ret_of) for p in live[:limit])
    out = '<h4 class="sm">Bets · newest first</h4>'
    out += HEAD.format(rows) if rows else '<p class="sm mut">No live entries yet. A game enters when a team clears the bar before its start.</p>'
    if len(live) > limit:
        out += f'<p class="sm mut">Latest {limit} of {len(live)} live entries.</p>'
    if back:
        out += (f'<details class="section-disclosure"><summary><b>Backfilled entries</b><span>{len(back)} · recorded afterwards from 1-minute quotes, not live reads</span></summary>'
                + HEAD.format("".join(bet_row(p, name_game, bet_text, ret_of) for p in back)) + "</details>")
    return out
