"""The "15-Minute" section of the Daily Markets tab and its Sandbox index rows (swing15.py). Paper · no orders.

Layout (2026-11-10, Olu: fewer words, clean, everything collapsible): one block per lane (Swing v3, The Flip Side v3,
Steady Favourites, Hold to End v3, the Lead Swap Board), each a one-line intro and its rule rows, collapsed; a row's fold
opens on its per-market Doing well / Not doing well tables (by return after fees, best first) with the rule's words in a
nested "Rule details" fold, and every other sentence sits in the lane's "How the record is kept" fold. Then the v1
baseline and one "Retired & removed" archive, both collapsed. Controls are a muted "vs control" figure, never rows. Times
read in Central, as the page header does. Layout only: no rule, record or pick depends on this file.
"""
import datetime as _dt
import html as _h
import re
from zoneinfo import ZoneInfo

import swing15 as W

HEADLINE_S1 = ("swing15_s1", "0.25", "2.0", "hold")
EXIT_WORDS = {"hold": "else hold", "bid": "else sell at the bid, 1 min left"}


def esc(x):
    return _h.escape(str(x))


# 2026-11-09 (Olu): readable market names everywhere in the 15-Minute section; display only, tickers stay in the data.
NAMES = {
    "KXBTC15M": "Bitcoin", "KXETH15M": "Ethereum", "KXSOL15M": "Solana", "KXXRP15M": "XRP", "KXBNB15M": "BNB",
    "KXDOGE15M": "Dogecoin", "KXHYPE15M": "Hyperliquid", "KXNEAR15M": "NEAR", "KXZEC15M": "Zcash",
    "KXCRYPTOLEAD15M": "Coin Race (biggest gainer)",
    "KXGOLD15M": "Gold", "KXSILVER15M": "Silver", "KXCOPPER15M": "Copper", "KXPLATINUM15M": "Platinum",
    "KXPALLADIUM15M": "Palladium", "KXWTI15M": "WTI Crude Oil", "KXBRENT15M": "Brent Crude Oil",
    "KXNATGAS15M": "Natural Gas",
    "KXINX15M": "S&P 500", "KXNDQ15M": "Nasdaq 100", "KXDJIA15M": "Dow Jones",
    "KX2YRRATE15M": "2-Year Treasury Yield", "KX5YRRATE15M": "5-Year Treasury Yield",
    "KX10YRRATE15M": "10-Year Treasury Yield", "KX30YRRATE15M": "30-Year Treasury Yield",
    "KXEURUSD15M": "EUR/USD (Euro)", "KXGBPUSD15M": "GBP/USD (British Pound)", "KXUSDJPY15M": "USD/JPY (Japanese Yen)",
    "KXUSDCAD15M": "USD/CAD (Canadian Dollar)", "KXAUDUSD15M": "AUD/USD (Australian Dollar)",
}


def name(ticker):
    """The display name; a series not in NAMES falls back to the ticker without KX and 15M, never a blank."""
    t = str(ticker or "")
    if t in NAMES:
        return NAMES[t]
    core = t[2:] if t.startswith("KX") else t
    core = core[:-3] if core.endswith("15M") else core
    return core or t or "?"


def mkt(ticker):
    """A market cell's text: the readable name, the ticker in a hover title so it is still findable."""
    return f'<span title="{esc(ticker)}">{esc(name(ticker))}</span>'


def pct(x, d=1):
    return "—" if x is None else f"{x * 100:+.{d}f}%".replace("-", "−")


def _z(x):
    return "—" if x is None else f"{x:+.2f}".replace("-", "−")




CT = ZoneInfo("America/Chicago")


def _start(iso):
    """A time in this section, in Central like the page header: 'Nov 9, 6:00 PM CT'."""
    t = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    t = (t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)).astimezone(CT)
    return f"{t:%b} {t.day}, {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'} CT"


def _tone(c):
    if not c or c["n"] < W.REVIEW_AT:
        return "mut"
    return "pos" if c["mean_roi"] > 0 else "neg"


def _per_series(state, key):
    """{series: n} for one strategy cell: the review clock (10) and decision (30) run per strategy x series."""
    out = {}
    for s in sorted({w["series"] for w in state["windows"].values()}):
        c = W.cells(state, lambda w, s=s: w["series"] == s).get(key)
        out[s] = c["n"] if c else 0
    return out


def status_chip(per):
    """The lane's status from its per-market bet counts ({market: n}; one pooled entry for a pooled lane):
    'Too early (n/10)' until a market reaches 10, 'Review' from 10, 'Ready to decide (30+)' from 30."""
    best = max(per.values(), default=0)
    due = sum(n >= W.DECIDE_AT for n in per.values())
    many = len(per) > 1
    if due:
        return (f'<span class="sig w">Ready to decide ({W.DECIDE_AT}+)'
                + (f' · {due} market{"s" * (due != 1)}' if many else "") + '</span>')
    if best >= W.REVIEW_AT:
        return '<span class="sig w">Review</span>'
    return f'<span class="sig n">Too early ({best}/{W.REVIEW_AT})</span>'


def _ctrl_txt(ctrl):
    """The muted 'vs control' figure: the control's return after fees (its record in the hover)."""
    if not ctrl:
        return '<span class="mut">—</span>'
    return (f'<span class="mut" title="Control: {ctrl["hits"]}/{ctrl["n"]} won">{pct(ctrl["mean_roi"])}</span>')


HEAD_LINE = ('<div class="sp-line sp-head-line" aria-hidden="true"><span class="sp-cell sp-c-name">Rule</span>'
             '<span class="sp-cell sp-c-market">vs control</span><span class="sp-cell num">Record</span>'
             '<span class="sp-cell num">Return after fees</span><span class="sp-cell num">Won v priced</span>'
             '<span class="sp-cell num">Evidence</span><span class="sp-cell sp-c-verdict">Status</span></div>')


def _row(key, label, c, per, body, ctrl=None, anchor=None, sport="swing15", status=None, evidence=None):
    """One rule row in the Rules-list design. Its fold holds the rule details only; the per-market tables sit open
    beneath it (_card)."""
    record = '<span class="mut">—</span>' if not c else f'{c["hits"]}–{c["n"] - c["hits"]}'
    roi = '<span class="mut">—</span>' if not c else f'<span class="{_tone(c)}">{pct(c["mean_roi"])}</span>'
    wvp = "—" if not c else f'{c["hits"]} v {c["fair"] * c["n"]:.1f}'
    best = max(per.values(), default=0)
    return (f'<details class="sp-rule{"" if c and c["n"] >= W.REVIEW_AT else " is-early"}"'
            + (f' id="{esc(anchor)}"' if anchor else "")
            + f' data-source="{esc(key)}" data-sport="{esc(sport)}" data-scope="clubs" data-stage="sandbox">'
            f'<summary class="sp-line"><span class="sp-cell sp-c-name"><span class="sp-chev" aria-hidden="true">›</span>'
            f'<b class="sp-name" title="{esc(label)}">{esc(label)}</b><span class="sr-only"> · Rule details</span></span>'
            f'<span class="sp-cell sp-c-market" data-l="vs control">{_ctrl_txt(ctrl)}</span>'
            f'<span class="sp-cell num" data-l="Record">{record}</span>'
            f'<span class="sp-cell num" data-l="Return after fees">{roi}</span>'
            f'<span class="sp-cell num" data-l="Won v priced">{esc(wvp)}</span>'
            f'<span class="sp-cell num" data-l="Evidence">{evidence or f"{min(best, W.DECIDE_AT)}/{W.DECIDE_AT}"}</span>'
            f'<span class="sp-cell sp-c-verdict" data-l="Status">{status or status_chip(per)}</span></summary>'
            f'<div class="sp-details-body">{body}</div></details>')


def _label(row, head):
    """Each cell names its column (data-l) for the phone's card layout. sandbox_build.label_cells skips a table that
    already has its <thead>, which every table here has, so the cells are labelled here."""
    it = iter(head)
    return re.sub(r"<td(?=[ >])", lambda m: f'<td data-l="{esc(next(it, ""))}"', row)


def _table(head, rows):
    return ('<div class="tbl"><table><thead><tr>' + "".join(f"<th{' class=\"num\"' if i else ''}>{esc(h)}</th>" for i, h in enumerate(head))
            + "</tr></thead><tbody>" + "".join(_label(r, head) for r in rows) + "</tbody></table></div>")


SORT_LINE = "Sorted automatically each hour by return after fees; nothing is removed."
BAD_THEAD = '<thead class="sw15-bad">'          # a class, not an inline style: the site's CSP blocks style attributes


def _zd(c):
    """z clustered by day means nothing on one day: 'needs 2+ days' until there are two."""
    return "needs 2+ days" if (c.get("days") or 0) < 2 else _z(c.get("z"))


def _under10(n):
    return ' <span class="mut sm">under 10</span>' if n < 10 else ""


def split_markets(items):
    """items: [(series, n, roi)] -> (doing, not_doing, no_bets): return after fees > 0 v <= 0, each by return after fees,
    best first (then bets, then name); markets with no bets yet listed apart. Recomputed from the live record on every build."""
    key = lambda r: (-r[2], -r[1], name(r[0]))
    bet = [r for r in items if r[1]]
    return (sorted([r for r in bet if r[2] > 0], key=key), sorted([r for r in bet if r[2] <= 0], key=key),
            sorted([r[0] for r in items if not r[1]], key=name))


def count_line(good, bad):
    """The count as a header chip over a lane's per-market tables."""
    return (f'<p class="sw15-split-h"><span class="sig n ls-count">{len(good)} doing well · {len(bad)} not</span> '
            f'<span class="sm mut">per market</span></p>')


def _split_html(head, good, bad, tr, none=()):
    """Doing well, then Not doing well (red header) directly below, then any no-bet markets on one line."""
    return (f'<p class="sm">Doing well · return after fees above 0 ({len(good)})</p>'
            + (_table(head, [tr(r) for r in good]) if good else '<p class="sm mut">None yet.</p>')
            + f'<p class="sm ls-bad">Not doing well · return after fees 0 or below ({len(bad)})</p>'
            + (_table(head, [tr(r) for r in bad]).replace("<thead>", BAD_THEAD, 1) if bad
               else '<p class="sm mut">None yet.</p>')
            + (f'<p class="sm mut">No bets yet: {", ".join(mkt(t) for t in none)}</p>' if none else ""))


def _card(row, split):
    """One rule row, collapsed: its fold opens on the per-market Doing well / Not doing well tables, with the rule's own
    words in a nested "Rule details" fold below them."""
    head, body = row.split('<div class="sp-details-body">', 1)
    body = body[:-len("</div></details>")]
    return (f'{head}<div class="sp-details-body"><div class="sw15-split">{split}</div>'
            f'<details class="fold sw15-rule"><summary>Rule details</summary>{body}</details></div></details>')


def _list(cards):
    return f'<div class="sp-rules-list" data-list="sandbox">{HEAD_LINE}{"".join(cards)}</div>'


def _intro(start, extra=""):
    """A lane's one line: 'Paper · fresh record from <CT> · review 10, decide 30'."""
    return (f'<p class="scope sw15-intro">Paper{" · " + esc(extra) if extra else ""} · fresh record from '
            f'{esc(_start(start))} · review {W.REVIEW_AT}, decide {W.DECIDE_AT}</p>')


def _how(*parts):
    """Every other sentence about a lane, in one collapsed fold under its rows."""
    return ('<details class="fold sw15-how"><summary>How the record is kept</summary>'
            + "".join(p if p.startswith("<") else f'<p class="sm">{esc(p)}</p>' for p in parts if p)
            + f'<p class="sm mut">{SORT_LINE}</p></details>')


def _cell_tr(label, c, ticker=None):
    first = mkt(ticker) if ticker else esc(label)
    if not c:
        return f'<tr><td>{first}</td>' + '<td class="num">—</td>' * 6 + '</tr>'
    h0, h1 = c["half_roi"]
    return (f'<tr><td>{first}</td><td class="num">{c["n"]}</td><td class="num">{c["hit_rate"] * 100:.0f}%</td>'
            f'<td class="num">{c["fair"] * 100:.0f}%</td><td class="num">{pct(c["mean_roi"])}</td>'
            f'<td class="num">{_zd(c)}</td><td class="num">{pct(h0)} / {pct(h1)}</td></tr>')


HEAD = ("Cell", "n", "Hit", "Fair", "Return after fees", "z (by day)", "Halves")


def _splits(state, key):
    rows = []
    for label, flt in (
            *[(g, (lambda w, g=g: w["group"] == g)) for g in W.GROUPS],
            ("US hours (8:30 AM–3:00 PM CT weekdays)", lambda w: w["us_hours"]),
            ("Overnight and weekends", lambda w: not w["us_hours"])):
        rows.append(_cell_tr(label, W.cells(state, flt).get(key)))
    return _table(HEAD, rows)


def _v1_markets(state, key):
    """(good, bad, split tables) for one v1 strategy cell, by series."""
    cs = {s: W.cells(state, lambda w, s=s: w["series"] == s).get(key)
          for s in sorted({w["series"] for w in state["windows"].values()})}
    good, bad, none = split_markets([(s, c["n"] if c else 0, c["mean_roi"] if c else 0) for s, c in cs.items()])
    tr = lambda r: _cell_tr(r[0], cs[r[0]], ticker=r[0]).replace(f"{mkt(r[0])}</td>", f"{mkt(r[0])}{_under10(r[1])}</td>", 1)
    return good, bad, _split_html(("Market",) + HEAD[1:], good, bad, tr, none)


def _removed_fold(labels, removed, removed_at, won_word, word="Removed", note=""):
    """The cells taken out at a cut: their final n, wins and return (windows before the cut), collapsed."""
    trs = []
    for strat, label in labels.items():
        r = (removed or {}).get(strat) or {}
        for s, x in (r.get("series") or {}).items():
            trs.append(f'<tr><td>{esc(label)}</td><td>{mkt(s)}</td><td class="num">{x["n"] if x else 0}</td>'
                       f'<td class="num">{x["hits"] if x else "—"}</td>'
                       f'<td class="num">{pct(x["mean_roi"]) if x else "—"}</td></tr>')
    if not trs:
        return ""
    return (f'<details class="fold sw15-removed"><summary>{esc(word)} {esc(_start(removed_at))} · {len(trs)} '
            f'market{"s" * (len(trs) != 1)}, final records</summary>{note}'
            + _table(("Rule", "Market", "n", "Wins", "Return after fees"), trs) + '</details>')



def _frozen_block(anchor, title, start, version, labels, rec, sport, won_word, how=(), intro="", extra_cards=()):
    """A frozen-cell lane block (sw15, flip, hte): one card per strategy with cells: the row (rule details folded) and
    its markets' n, wins, return and z open beneath, split Doing well / Not doing well. Removed and retired cells live in
    the archive at the bottom of the section."""
    cards = []
    for strat, label in labels.items():
        r = rec[strat]
        if not r["series"]:
            continue                                             # a row with every market removed is archive-only
        per = {s: (x["n"] if x else 0) for s, x in r["series"].items()}
        ser = r["series"]
        good, bad, none = split_markets([(s, x["n"] if x else 0, x["mean_roi"] if x else 0) for s, x in ser.items()])
        tr = lambda q, ser=ser: (f'<tr><td>{mkt(q[0])}{_under10(q[1])}</td><td class="num">{q[1]}</td>'
                                 f'<td class="num">{ser[q[0]]["hits"]}</td><td class="num">{pct(ser[q[0]]["mean_roi"])}</td>'
                                 f'<td class="num">{_zd(ser[q[0]])}</td></tr>')
        skips = r.get("skips") or {}
        body = (f'<p class="sp-details-name"><b>{esc(label)}</b> · Kalshi 15-minute windows · paper · {esc(version)}</p>'
                f'<p class="sp-def">Frozen: {len(r["series"])} markets ({esc(", ".join(name(s) for s in r["series"]))}). '
                f'Held to settlement; taker fee on entry.</p>'
                + (f'<p class="sm mut">Skipped: {esc(", ".join(f"{k} {v}" for k, v in sorted(skips.items())))}</p>'
                   if skips else ""))
        lid = f"sw15-{strat}"
        cards.append(_card(_row(strat, label, r["all"], per, body, anchor=lid, sport=sport),
                           count_line(good, bad) + _split_html(("Market", "n", won_word(strat), "Return after fees",
                                                                "z (by day)"), good, bad, tr, none)))
    return (f'<h3 class="dm-title" id="{anchor}">{esc(title)}</h3>' + _intro(start, intro) + _list(list(extra_cards) + cards)
            + _how(*how))


def _cut_line(M):
    return f"{M.VERSION} from {_start(M.REMOVED_AT)}: negative markets removed after ~4h of results."


def lossreader_block(state, now=None):
    """Rule 1 v2 · Loss Reader (lossreader.py, sw15-lr1): one collapsed row; inside, the Now line, today's bets, the
    per-market split and the two comparison books; the rules and the backtest in the How-kept fold."""
    import json as _json
    import lossreader as LR
    led = LR.ledger(state, now)
    c, every, fixed = led["record"], led["every"], led["fixed2"]
    n = c["n"] if c else 0
    days = len(led["days"])
    if n >= LR.DECIDE_BETS or days >= LR.DECIDE_DAYS:
        chip = f'<span class="sig w">Ready to decide ({LR.DECIDE_BETS} bets or {LR.DECIDE_DAYS} days)</span>'
    elif n >= LR.REVIEW_AT:
        chip = '<span class="sig w">Review</span>'
    else:
        chip = f'<span class="sig n">Too early ({n}/{LR.REVIEW_AT})</span>'
    per = led["per_market"]
    good, bad, none = split_markets([(m, (per[m] or {}).get("n", 0), (per[m] or {}).get("mean_roi", 0)) for m in LR.MARKETS])
    tr = lambda q: (f'<tr><td>{mkt(q[0])}{_under10(q[1])}</td><td class="num">{q[1]}</td>'
                    f'<td class="num">{per[q[0]]["hits"]} v {per[q[0]]["fair"] * q[1]:.1f}</td>'
                    f'<td class="num">{pct(per[q[0]]["mean_roi"])}</td></tr>')
    today = LR.ct_day((now or __import__("datetime").datetime.now(__import__("datetime").timezone.utc)).timestamp())
    todays = [b for b in led["bets"] if LR.ct_day(b["t"]) == today]
    bet_rows = [f'<tr><td>{esc(_start(b["at"]).replace(today.strftime("%b") + f" {today.day}, ", ""))}</td><td>{mkt(b["m"])}</td>'
                f'<td>{esc(LR.trigger_word(b["k"]))}</td><td class="num">{b["price"] * 100:.0f}c</td>'
                + (f'<td>{"won" if b["won"] else "lost"}</td><td class="num">{pct(b["roi"])}</td>' if b["status"] == "filled"
                   else '<td>no fill</td><td class="num">—</td>') + '</tr>' for b in reversed(todays)]
    comp = lambda name_, x: (f'<tr><td>{esc(name_)}</td><td class="num">{x["n"]}</td><td class="num">{x["hits"]} v '
                             f'{x["fair"] * x["n"]:.1f}</td><td class="num">{pct(x["mean_roi"])}</td></tr>' if x else
                             f'<tr><td>{esc(name_)}</td><td class="num">0</td><td class="num">—</td><td class="num">—</td></tr>')
    split = (f'<p class="sw15-now"><b>{esc(led["now"])}</b></p>'
             + f'<p class="sm">Today\'s bets ({len(todays)})</p>'
             + (_table(("Time (CT)", "Market", "Trigger", "Price", "Result", "Return after fees"), bet_rows) if bet_rows
                else '<p class="sm mut">None yet today.</p>')
             + count_line(good, bad)
             + _split_html(("Market", "Bets", "Won v priced", "Return after fees"), good, bad, tr, none)
             + '<p class="sm">Compared over the same windows</p>'
             + _table(("Book", "Bets", "Won v priced", "Return after fees"),
                      [comp("Loss Reader", c), comp("Every bet (S2 on the 3 markets)", every), comp("Fixed after 2 losses", fixed)]))
    body = ('<p class="sp-details-name"><b>' + esc(LR.LABEL) + f'</b> · Kalshi 15-minute windows · paper · {esc(LR.VERSION)}</p>'
            '<p class="sp-def">Rule 1 = v1\'s S2 on Bitcoin, Solana and WTI: at minute 2, buy the favourite at its ask, filled '
            'only on a print at or through it in the next minute; held to settlement; taker fee. Each market is bet on its '
            'best trigger (every window, or after 1, 2 or 3 observed losses in a row), re-learned before every window.</p>')
    try:
        bt = _json.load(open(LR.PATH.replace("lossreader_ledger.json", "lossreader_backtest.json")))
    except (OSError, ValueError):
        bt = None
    bt_line = ("" if not bt else
               f'Backtest (report only, not a gate; {bt["days"]}, candle quotes without the print check): '
               f'{bt["lane"]["n"]} bets {pct(bt["lane"]["mean_roi"])} after fees, against every bet '
               f'{pct(bt["every"]["mean_roi"])} ({bt["every"]["n"]}) and fixed after 2 {pct(bt["fixed2"]["mean_roi"])} '
               f'({bt["fixed2"]["n"]}); it beat every bet on {bt["days_beating_every"]} of {bt["n_days"]} days and was '
               f'profitable on {bt["days_profitable"]}; shuffling each day\'s outcome order {bt["shuffles"]} times puts '
               f'the real result at the {bt["shuffle_percentile"]:.0f}th percentile (below 95: not significant).')
    how = _how("Learning: before every window, each trigger's score on a market is the sum of (won − price) over today's "
               "observed windows (midnight to midnight CT) where it would have fired, plus a third of the same over the "
               "previous 3 days; the best trigger is used only with at least 4 such windows today and a score above 0, "
               "otherwise the market is Off. Two losing bets in a row turn a market Off for its next 4 windows. When "
               "more than one market fires, only the highest score is bet. Observed = every window where S2 filled, "
               "bet or not.", bt_line)
    row = _row("lossreader", LR.LABEL, c, {"all": n}, body, ctrl=every, anchor="sw15-lossreader", sport="lossreader",
               status=chip, evidence=f"{min(n, LR.DECIDE_BETS)}/{LR.DECIDE_BETS}")
    intro = (f'<p class="scope sw15-intro">Paper · fresh record from {esc(_start(LR.FROM))} · review {LR.REVIEW_AT}, '
             f'decide {LR.DECIDE_BETS} bets or {LR.DECIDE_DAYS} trading days</p>')
    return f'<h3 class="dm-title" id="lossreader">{esc(LR.LABEL)}</h3>' + intro + _list([_card(row, split)]) + how


NEVER_WORD = {"price": "price", "trigger_minute": "trigger minute", "lead_changes": "lead-change setting",
              "time_ct": "time of day"}
SETTING_HEAD = {"price": "Price of the side bought", "trigger_minute": "Trigger minute",
                "lead_changes": "Lead changes before the entry", "time_ct": "Open hour (CT)"}


def eps_card(M, state, key, comp_label, rule_text):
    """One "Every Positive Setting" rule (an allowgate.py lane module M: records, ALLOW, LABEL, VERSION, fingerprint,
    REVIEW_AT, DECIDE_AT): a collapsed row whose fold holds the per-market split and the lane against its comparison
    book, with the frozen allow-list as a table in Rule details. -> the card (a row for _list)."""
    rec = M.records(state)
    lane, every = rec["lane"], rec["every"]
    c, e = lane["all"], every["all"]
    n = c["n"] if c else 0
    chip = (f'<span class="sig w">Ready to decide ({M.DECIDE_AT} bets)</span>' if n >= M.DECIDE_AT else
            '<span class="sig w">Review</span>' if n >= M.REVIEW_AT else f'<span class="sig n">Too early ({n}/{M.REVIEW_AT})</span>')
    ser = lane["series"]
    good, bad, none = split_markets([(m, x["n"] if x else 0, x["mean_roi"] if x else 0) for m, x in ser.items()])
    tr = lambda q: (f'<tr><td>{mkt(q[0])}{_under10(q[1])}</td><td class="num">{q[1]}</td>'
                    f'<td class="num">{ser[q[0]]["hits"]} v {ser[q[0]]["fair"] * q[1]:.1f}</td>'
                    f'<td class="num">{pct(ser[q[0]]["mean_roi"])}</td><td class="num">{_zd(ser[q[0]])}</td></tr>')
    comp = lambda name_, x: (f'<tr><td>{esc(name_)}</td><td class="num">{x["n"]}</td><td class="num">{x["hits"]} v '
                             f'{x["fair"] * x["n"]:.1f}</td><td class="num">{pct(x["mean_roi"])}</td></tr>' if x else
                             f'<tr><td>{esc(name_)}</td><td class="num">0</td><td class="num">—</td><td class="num">—</td></tr>')
    split = (count_line(good, bad)
             + _split_html(("Market", "Bets", "Won v priced", "Return after fees", "z (by day)"), good, bad, tr, none)
             + '<p class="sm">Compared over the same windows</p>'
             + _table(("Book", "Bets", "Won v priced", "Return after fees"), [comp(M.LABEL, c), comp(comp_label, e)]))
    keys = list(next(iter(M.ALLOW.values())))
    allow = _table(("Market",) + tuple(SETTING_HEAD.get(k, k) for k in keys),
                   [f'<tr><td>{mkt(m)}</td>' + "".join(f'<td>{esc(", ".join(a[k]) or "none (never bets)")}</td>' for k in keys)
                    + '</tr>' for m, a in M.ALLOW.items()])
    body = (f'<p class="sp-details-name"><b>{esc(M.LABEL)}</b> · Kalshi 15-minute windows · paper · {esc(M.VERSION)}</p>'
            f'<p class="sp-def">{esc(rule_text)} Bet only when every setting is in the market\'s allow-list (frozen, '
            f'fingerprinted){"; any hour outside 07-22 CT is never bet" if "time_ct" in keys else "; every hour"}.</p>'
            + allow + f'<p class="sm mut">Allow-list fingerprint {esc(M.fingerprint()[:12])}</p>')
    row = _row(key, M.LABEL, c, {"all": n}, body, ctrl=e, anchor=f"sw15-{key}", sport=key, status=chip,
               evidence=f"{min(n, M.DECIDE_AT)}/{M.DECIDE_AT}")
    return _card(row, split)


def s3v2_block(state):
    """Rule 2 v2 · Every Positive Setting (s3v2.py, sw15-s3v2): its own lane, one collapsed row."""
    import s3v2 as S
    card = eps_card(S, state, "s3v2", "Every bet (old S3 on the same 6 markets)",
                    "S3: at minute 10, buy the favourite at its ask, filled only on a print at or through it in the next "
                    "minute; held to settlement; taker fee.")
    intro = (f'<p class="scope sw15-intro">Paper · fresh record from {esc(_start(S.FROM))} · review {S.REVIEW_AT}, '
             f'decide {S.DECIDE_AT} bets</p>')
    how = _how("Replaces Swing v3 S3. The allow-list was chosen from each market's positive cells on Nov 9; the "
               "comparison is the old S3 on the same 6 markets over the same windows, to show whether the filter adds "
               "anything.", f'<p class="sm mut s3v2-in-sample">{esc(S.IN_SAMPLE)}</p>')
    return f'<h3 class="dm-title" id="s3v2">{esc(S.LABEL)}</h3>' + intro + _list([card]) + how


def swing_v3_block(state):
    import swing15v2 as V
    return _frozen_block("swing15v2", "15-Minute Swing v3", V.FROM, V.VERSION, V.LABELS, V.records(state),
                         "swing15v2", lambda k: "Won",
                         how=("Cells picked from one overnight session.", _cut_line(V)))


FLIP_EPS = (("flipf1v2", "F1"), ("flipf2v2", "F2"), ("flipf3v2", "F3"), ("flipf4v2", "F4"))
FLIP_TRADE = {
    "F1": "F1: when the cheap side prints at 25c in the first 5 minutes, buy the other side at its ask at the end of the "
          "trigger minute; held to settlement; taker fee.",
    "F2": "F2: when the cheap side prints at 35c in the first 5 minutes, buy the other side at its ask at the end of the "
          "trigger minute; held to settlement; taker fee.",
    "F3": "F3: the underdog (the side opposite the minute-2 favourite) at its ask from the minute-2 quote; held to "
          "settlement; taker fee.",
    "F4": "F4 on Zcash: the underdog (the side opposite the minute-10 favourite) at its ask from the minute-10 quote; "
          "held to settlement; taker fee; every hour.",
}


def flip_block(state):
    import flipside_v2 as F
    cards, how_eps = [], []
    for name, old in FLIP_EPS:                                   # Rules 3-5 v2 (2026-11-10) replace F1-F3, in this list
        try:
            M = __import__(name)
            cards.append(eps_card(M, state, name, M.COMP_LABEL, FLIP_TRADE[old]))
            how_eps += [f"{M.LABEL} replaces {old}: fresh record from {_start(M.FROM)}, review {M.REVIEW_AT}, decide "
                        f"{M.DECIDE_AT} bets.", f'<p class="sm mut {name}-in-sample">{esc(M.IN_SAMPLE)}</p>']
        except Exception:                                        # noqa: BLE001  (never breaks the section)
            pass
    return _frozen_block("flipside_v2", "The Flip Side v3", F.FROM, F.VERSION, F.LABELS, F.records(state),
                         "flipside_v2", lambda k: "Won",
                         how=("Opposite side of the 15-Minute Swing; cells picked from one overnight session; the 14-day "
                              "backtest of the flips ran −0.5% to −16%.", _cut_line(F)) + tuple(how_eps), extra_cards=cards)


def _v3_s3_retired(state, V):
    """S3 (sw15-v3) retired 2026-11-10 for Rule 2 v2 · Every Positive Setting: its final record, collapsed."""
    ret = V.records(state, retired=True)
    a = (ret.get("swing15v2_s3") or {}).get("all")
    note = ("" if not a else
            f'<p class="sm">S3 final: {a["hits"]}/{a["n"]} won against {a["fair"] * a["n"]:.1f} priced, '
            f'{pct(a["mean_roi"])} after fees. Replaced by Rule 2 v2 · Every Positive Setting. No new entries.</p>')
    return _removed_fold({"swing15v2_s3": V.LABELS["swing15v2_s3"]}, {"swing15v2_s3": ret.get("swing15v2_s3")},
                         V.RETIRED_S3_AT, lambda k: "Won", word="Retired", note=note)


def _v3_s1_retired(state, V):
    """S1 (sw15-v3) retired 2026-11-09 22:00Z for Steady Favourites: its final record, collapsed."""
    ret = V.records(state, retired=True)
    a = (ret.get("swing15v2_s1") or {}).get("all")
    since = (V.records(state, retired=True, start=V.REMOVED_AT).get("swing15v2_s1") or {}).get("all")
    note = ("" if not a else
            f'<p class="sm">S1 final: {a["hits"]}/{a["n"]} sells filled against {a["fair"] * a["n"]:.1f} priced, '
            f'{pct(a["mean_roi"])} after fees'
            + ("" if not since else f'; since the {_start(V.REMOVED_AT)} cut, {since["hits"]}/{since["n"]}, '
                                    f'{pct(since["mean_roi"])}')
            + '. Replaced by Steady Favourites. No new entries.</p>')
    return _removed_fold({"swing15v2_s1": V.LABELS["swing15v2_s1"]}, ret, V.RETIRED_AT,
                         lambda k: "Sells filled", word="Retired", note=note)


def _v1_s1_retired(state, allc_before):
    """S1 (sw15-v1) retired 2026-11-09 22:00Z: the headline cell's final record and the whole grid, collapsed. v1 keeps
    grading S1 entries underneath (The Flip Side, Hold to End and the Lead Swap Board read them)."""
    import swing15v2 as V
    c = allc_before.get(HEADLINE_S1)
    grid = [_cell_tr(f'{float(b) * 100:g}c · {float(m):g}x · {EXIT_WORDS[how]}', allc_before.get(("swing15_s1", b, m, how)))
            for b in map(str, W.BANDS) for m in map(str, W.MULTS) for how in ("hold", "bid")]
    neg = sum(1 for b in map(str, W.BANDS) for m in map(str, W.MULTS) for how in ("hold", "bid")
              if (allc_before.get(("swing15_s1", b, m, how)) or {}).get("mean_roi", 0) < 0)
    note = ("" if not c else
            f'<p class="sm">S1 Swing · 25c · 2x · else hold, final: {c["hits"]}–{c["n"] - c["hits"]} against '
            f'{c["fair"] * c["n"]:.1f} priced, {pct(c["mean_roi"])} after fees; {neg} of {len(grid)} grid cells negative. '
            f'Replaced by Steady Favourites. No new entries.</p>')
    return (f'<details class="fold sw15-removed"><summary>Retired {esc(_start(V.RETIRED_AT))} · S1 Swing, final '
            f'records</summary>{note}' + _table(HEAD, grid) + '</details>')


def steadyfav_block(state):
    """Steady Favourites (steadyfav.py, sw15-sf1): rules A and B on four fixed markets; the pooled control of each
    rule is a muted figure in its row and one muted line under its tables."""
    import steadyfav as S
    rec = S.records(state)
    cards = []
    defs = {"steadyfav_a": "At minute 2, buy the side above 50c (by the mid) at its ask, filled only on a print at or "
                           "through it in the next minute; held to settlement; taker fee on entry (v1's S2).",
            "steadyfav_b": "The same at minute 10, with 5 minutes left (v1's S3)."}
    for rule, text in defs.items():
        r = rec[rule]
        ser = r["series"]
        good, bad, none = split_markets([(s, x["n"] if x else 0, x["mean_roi"] if x else 0) for s, x in ser.items()])
        tr = lambda q, ser=ser: (f'<tr><td>{mkt(q[0])}{_under10(q[1])}</td><td class="num">{q[1]}</td>'
                                 f'<td class="num">{ser[q[0]]["hits"]} v {ser[q[0]]["fair"] * q[1]:.1f}</td>'
                                 f'<td class="num">{pct(ser[q[0]]["mean_roi"])}</td><td class="num">{_zd(ser[q[0]])}</td></tr>')
        ctl_rec = rec.get(rule + "_ctrl") or {}
        c = ctl_rec.get("all")
        ctl = ("no control windows yet" if not c else
               f'{c["hits"]}/{c["n"]} won against {c["fair"] * c["n"]:.1f} priced, {pct(c["mean_roi"])} after fees')
        body = (f'<p class="sp-details-name"><b>{esc(S.LABELS[rule])}</b> · Kalshi 15-minute windows · paper · '
                f'{esc(S.VERSION)}</p><p class="sp-def">{esc(text)} Frozen: {len(S.MARKETS)} markets. Control: the same '
                f'rule on the other {ctl_rec.get("markets", 0)} 15-minute markets, pooled.</p>')
        per = {s: (x["n"] if x else 0) for s, x in ser.items()}
        lid = f"sw15-{rule}"
        split = (count_line(good, bad)
                 + _split_html(("Market", "Bets", "Won v priced", "Return after fees", "z (by day)"), good, bad, tr, none)
                 + f'<p class="sm mut sf-ctrl">Control (the same rule on the other markets, pooled): {esc(ctl)}.</p>')
        cards.append(_card(_row(rule, S.LABELS[rule], r["all"], per, body, ctrl=c, anchor=lid, sport="steadyfav"), split))
    old = S.records(state, earlier=True)
    ea, eb = old["steadyfav_a"]["all"], old["steadyfav_b"]["all"]
    early = ("" if not (ea or eb) else
             '<p class="sm mut sf-earlier">Earlier result, not counted (v1 on these four markets, before the start): '
             + "; ".join(f'{k} {x["hits"]}/{x["n"]}, {pct(x["mean_roi"])}' for k, x in (("A", ea), ("B", eb)) if x) + '.</p>')
    names = ", ".join(name(s) for s in S.MARKETS)
    return (f'<h3 class="dm-title" id="steadyfav">Steady Favourites</h3>' + _intro(S.FROM) + _list(cards)
            + _how(f"{names}: the favourite bought at minute 2 (A) and at 5 minutes left (B), held to settlement. "
                   "Replaces the S1 Swing. Each rule's control is the same rule on every other 15-minute market, pooled.",
                   early))


def holdtoend_block(state, H):
    """Hold to End v3: one live cell (USDCAD 35c) on a fresh record; USDCAD's earlier hte-v1 result as a muted
    not-counted line. hte-v2 and the 18:00Z cut are in the archive."""
    gone = H.records(state, removed=True)
    early = (gone.get("holdtoend_35") or {}).get("series", {}).get("KXUSDCAD15M")
    early_line = ("" if not early else
                  f'<p class="sm mut hte-earlier">Earlier result, not counted: USD/CAD 35c went {early["hits"]}/{early["n"]}, '
                  f'{pct(early["mean_roi"])} after fees ({esc(_start(H.FROM))} to {esc(_start(H.REMOVED_AT))}, hte-v1).</p>')
    return _frozen_block("holdtoend", "Hold to End v3", H.FROM_V3, H.VERSION,
                         {k: v.replace("Hold to End · ", "") for k, v in H.LABELS.items()}, H.records(state), "holdtoend",
                         lambda k: "Won", intro="USD/CAD at 35c",
                         how=("Buy the 35c side and hold it to settlement.", early_line))


def _hte_archive(state, H):
    ret = H.records(state, retired=True)
    r35 = (ret.get("holdtoend_35") or {}).get("all")
    note = ("" if not r35 else
            f'<p class="sm">hte-v2 final (decide at {W.DECIDE_AT}): {r35["hits"]}/{r35["n"]} against '
            f'{r35["fair"] * r35["n"]:.1f} priced, {pct(r35["mean_roi"])} after fees. No new entries.</p>')
    return (_removed_fold({"holdtoend_35": "Hold to End v2 · 35c"}, {"holdtoend_35": ret.get("holdtoend_35")},
                          H.RETIRED_AT, lambda k: "Won", word="Retired", note=note)
            + _removed_fold(H.LABELS, H.records(state, removed=True), H.REMOVED_AT, lambda k: "Won"))


def _bars(vals, labels):
    top = max(vals) or 1
    return _table(("Minute", "Swaps", ""), [
        f'<tr><td>{esc(l)}</td><td class="num">{v}</td><td><span class="sw15-bar sw15-bar-{round(10 * v / top)}" '
        f'aria-hidden="true"></span></td></tr>' for v, l in zip(vals, labels)])


def _rank_tr(r):
    return (f'<tr><td>{mkt(r[0])}</td><td class="num">{r[1]:.2f}</td><td class="num">{r[2]}</td>'
            f'<td class="num">{r[3]:.0f}c</td></tr>')


LS_TRADES = (("leadswap_swing", "leadswap_swing_ctrl", "Swing on swappy markets"),
             ("leadswap_fav", "leadswap_fav_ctrl", "Favourite on steady markets"))


def _picked(picks):
    """{series: [hours in the top 3, hours in the bottom 3]} over every frozen hour."""
    out = {}
    for p in (picks or {}).values():
        for i, side in enumerate(("top", "bottom")):
            for t in p.get(side) or []:
                out.setdefault(t, [0, 0])[i] += 1
    return out


def ls_groups(rt, picks, ranked=()):
    """{trade: (doing, not_doing, not_picked)}: the trade's markets split by REAL return after fees (> 0 doing well,
    <= 0 not), each sorted by bets descending; rows are (series, [n, wins, roi sum], control or None, [top, bottom]).
    not_picked: ranked markets with no bets in the trade. Recomputed from the live record every build."""
    times = _picked(picks)
    out = {}
    for strat, ctrl, _label in LS_TRADES:
        ser = ((rt or {}).get(strat) or {}).get("series") or {}
        cs = ((rt or {}).get(ctrl) or {}).get("series") or {}
        rows = [(s, v, cs.get(s), times.get(s, [0, 0])) for s, v in ser.items() if v and v[0]]
        rows.sort(key=lambda r: (-r[1][2] / r[1][0], -r[1][0], name(r[0])))   # return after fees, best first
        traded = {r[0] for r in rows}
        seen = sorted({t for t in list(ranked) + list(times) if t not in traded}, key=name)
        out[strat] = ([r for r in rows if r[1][2] > 0], [r for r in rows if r[1][2] <= 0], seen)
    return out


def _ls_tr(r):
    s, v, c, t = r
    tag = _under10(v[0])
    ctl = "—" if not c or not c[0] else f"{c[1]}/{c[0]}, {pct(c[2] / c[0])}"
    return (f'<tr><td>{mkt(s)}{tag}</td><td class="num">{v[0]}</td><td class="num">{v[1]}</td>'
            f'<td class="num">{pct(v[2] / v[0])}</td><td class="num mut">{ctl}</td><td class="num">{t[0]} / {t[1]}</td></tr>')


LS_HEAD = ("Market", "Bets", "Wins", "Return after fees", "Control (wins/bets, return)",
           "Times picked (hours top 3 / bottom 3)")


def _ls_trade_split(g, strat):
    good, bad, none = g[strat]
    return (f'<div class="ls-trade" data-trade="{strat}">{count_line(good, bad)}' + _split_html(LS_HEAD, good, bad, _ls_tr)
            + f'<details class="fold"><summary>Not picked yet ({len(none)})</summary><p class="sm">'
            + (", ".join(mkt(t) for t in none) or "none") + '</p></details></div>')


def ls_groups_html(rt, picks, ranked=()):
    """Both trades' per-market splits, each under its trade's name (the block puts each under its own row)."""
    g = ls_groups(rt, picks, ranked)
    return f'<p class="sm mut">{SORT_LINE}</p>' + "".join(
        f'<h4>{esc(label)}</h4>' + _ls_trade_split(g, strat) for strat, _c, label in LS_TRADES)


def leadswap_block(state):
    """The Lead Swap Board (leadswap.py): the two trades (row + open per-market split, each against its control), then
    one collapsed fold with how the board ranks markets (picks, board, persistence, timing, hour of day)."""
    import leadswap as L
    led = L.load()
    if not led.get("board"):
        led = L.update(state, L.empty())
    b, per, rt = led["board"], led["persistence"] or {}, led["routing"] or {}
    pk = led.get("picks") or {}
    g = ls_groups(rt, pk, [r[0] for r in (b.get("past24h") or []) + (b.get("past2h") or [])])
    cards = []
    for strat, ctrl_key, _short in LS_TRADES:
        label = L.STRATS[strat]
        c, ctrl = rt.get(strat), rt.get(ctrl_key)
        what = ("v1's S1 35c entry held to settlement" if "swing" in strat else "v1's S3 favourite at minute 10, held")
        clus = "" if not c else "; %d clusters, z %s" % (c["clusters"], _z(c["z"]))
        bf = ("" if not c or c.get("before_freeze") is None else
              " %d of %d entries came before that hour's picks were frozen (~:04); the picks use only data to :00, "
              "but a live version could only act from :05." % (c["before_freeze"], c["n"]))
        who, opp = (("the top 3", "the bottom 3") if strat == "leadswap_swing" else ("the bottom 3", "the top 3"))
        body = (f'<p class="sp-details-name"><b>{esc(label)}</b> · Kalshi 15-minute windows · paper · {esc(L.VERSION)}</p>'
                f'<p class="sp-def">{esc(what)}, on {esc(who)} series by lead swaps over the past 2 hours, picked at the '
                f'top of each hour and frozen. Control: the same entry on {esc(opp)}. z clusters one block (crypto, '
                f'metals, energy, yields, FX, indices) in one window{clus}.{bf}</p>')
        good, bad, _none = g[strat]
        lid = f"sw15-{strat}"
        cards.append(_card(_row(strat, label, c, {"all": c["n"] if c else 0}, body, ctrl=ctrl, anchor=lid,
                                sport="leadswap"), _ls_trade_split(g, strat)))
    sl = L.SPOTLAG
    spot = ("Spot lag recorder: not started" if not sl.get("since") else
            f"Spot lag recorder: recording since {_start(sl['since'])}"
            + (f", until {_start(sl['until'])}" if sl.get("until") else "")
            + " (Coinbase spot v Kalshi BTC/ETH/SOL 15-minute books, every second; record only)")
    last = pk[max(pk)] if pk else None
    picks_line = ("" if not last else
                  f'<p class="sm">Picks for {esc(_start(max(pk)))} (frozen {esc(_start(last.get("at") or max(pk)))}): '
                  f'swing → {", ".join(mkt(t) for t in last.get("top") or []) or "none"}; favourite → '
                  f'{", ".join(mkt(t) for t in last.get("bottom") or []) or "none"}.</p>')
    rh = ("Market", "Swaps a window", "Windows", "Mid range 0-9")
    med = "—" if b["median_swing"] is None else "%gc" % b["median_swing"]
    f14 = "—" if b["fav14_won"] is None else "%.0f%%" % (b["fav14_won"] * 100)
    p2, p24 = b["past2h"], b["past24h"]
    board = (f'<details class="fold" open><summary>Board · last 2 hours (8 windows) and last 24 hours</summary>'
             f'{picks_line}'
             f'<p class="sm">Most swaps, last 2 hours</p>{_table(rh, [_rank_tr(r) for r in p2[:5]])}'
             f'<p class="sm">Most stable, last 2 hours</p>{_table(rh, [_rank_tr(r) for r in p2[::-1][:5]])}'
             f'<p class="sm">Most swaps, last 24 hours</p>{_table(rh, [_rank_tr(r) for r in p24[:5]])}'
             f'<p class="sm">Most stable, last 24 hours</p>{_table(rh, [_rank_tr(r) for r in p24[::-1][:5]])}'
             f'<p class="sm mut">Last 24 hours: {b["windows_24h"]} windows, {b["swaps_24h"]} swaps; median swing '
             f'{med}; the minute-14 favourite won {f14}.</p></details>')
    timing = (f'<details class="fold"><summary>When in the window the swaps happen (last 24 hours)</summary>'
              f'{_bars(b["minutes"], [str(m) for m in range(15)])}</details>')
    heat_rows = []
    for s, hs in sorted(b["heat"].items(), key=lambda kv: (b["blocks"].get(kv[0], ""), kv[0])):
        cells = []
        for ct in range(24):                                    # Central = Eastern − 1 all year (both switch together)
            v = hs.get(str((ct + 1) % 24))
            if not v or not v[1]:
                cells.append('<td class="num mut">·</td>')
                continue
            r = v[0] / v[1]
            cells.append(f'<td class="num sw15-heat sw15-heat-{min(6, int(r / 4 * 10))}">{r:.1f}</td>')
        heat_rows.append(_label(f'<tr><td>{mkt(s)}</td>{"".join(cells)}</tr>', ['Market'] + [f'{h}:00 CT' for h in range(24)]))
    heat = ('<details class="fold"><summary>Swaps a window by hour of day (CT), every series</summary><div class="tbl">'
            '<table><thead><tr><th>Market</th>' + "".join(f'<th class="num">{h}</th>' for h in range(24))
            + '</tr></thead><tbody>' + "".join(heat_rows) + '</tbody></table></div></details>')
    corr = [f'<tr><td>{esc(f)}</td><td class="num">{v["n"]}</td><td class="num">{_z(v["corr"])}</td></tr>'
            for f, v in (per.get("corr") or {}).items()]
    frac = lambda x: "—" if x is None else f"{x * 100:.0f}%"
    persist = (f'<details class="fold"><summary>Persistence: does the ranking carry into the next hour?</summary>'
               f'<p class="sm">Over {per.get("hours", 0)} hours, the past-2h top 3 were still top 3 in that hour '
               f'{frac(per.get("top"))} of the time and the bottom 3 stayed bottom 3 {frac(per.get("bottom"))}; '
               f'chance is {frac(per.get("chance"))}. FX swaps more by construction (small moves against the strike), so '
               f'the top 3 is mostly FX; within each block, the past-2h top stayed top '
               f'{frac((per.get("within_all") or {}).get("stay"))} against chance '
               f'{frac((per.get("within_all") or {}).get("chance"))}.</p>'
               + _table(("Block", "Slots", "Stayed top", "Chance"),
                        [f'<tr><td>{esc(bk)}</td><td class="num">{v["slots"]}</td><td class="num">{frac(v["stay"])}</td>'
                         f'<td class="num">{frac(v["chance"])}</td></tr>' for bk, v in (per.get("within") or {}).items()])
               + _table(("Group", "Windows", "Corr: past-2h swaps v the window"), corr) + '</details>')
    ranks = (f'<details class="fold sw15-ranks"><summary>How the board ranks markets</summary>'
             f'{board}{persist}{timing}{heat}</details>')
    return (f'<h3 class="dm-title" id="leadswap">Lead Swap Board</h3>' + _intro(L.FROM) + _list(cards)
            + _how("How often the lead (YES mid across 50c) swaps on every 15-minute series; the swing trade goes to the "
                   "most swaps, the favourite to the most stable, each against its opposite. Picks are frozen at about "
                   ":04 each hour, so a live version could only act from :05.",
                   f'<p class="sm mut" id="spotlag-status">{esc(spot)}</p>')
            + ranks)


def _v1_block(state, allc, n_w):
    """v1, the full collector on every series: the baseline, collapsed. S2 and S3 rows with their per-market split."""
    defs = {
        "swing15_s2": ("S2 Favourite at start",
                       "At minute 2, buy the side above 50c (by the mid) at its ask, filled only on a print at or through "
                       "it in the next minute; held to settlement. Judged against the price paid."),
        "swing15_s3": ("S3 Favourite at 5 minutes left",
                       "The same at minute 10. Judged against the price paid."),
    }
    cards = []
    for key, (label, text) in defs.items():
        ck = (key,)
        per = _per_series(state, ck)
        body = (f'<p class="sp-details-name"><b>{esc(label)}</b> · Kalshi 15-minute windows · paper · {esc(W.VERSION)}</p>'
                f'<p class="sp-def">{esc(text)}</p>'
                '<dl class="sp-params"><dt>Scope</dt><dd>Every Kalshi 15-minute series in Crypto, Commodities and '
                f'Financials (scanned {len(state.get("series") or [])} / with windows '
                f'{len({w["series"] for w in (state.get("windows") or {}).values()})})</dd>'
                '<dt>Fees</dt><dd>Taker 0.07·p(1−p) on an entry and a sell at the bid; maker 0.0175·p(1−p) on a resting '
                'sell</dd><dt>Read</dt><dd>Review at 10 and decide at 30 settled windows per strategy and series; z '
                'clustered by day</dd></dl>'
                f'<details class="fold"><summary>Splits: group and hours</summary>{_splits(state, ck)}</details>')
        good, bad, mk = _v1_markets(state, ck)
        cards.append(_card(_row(key, label, allc.get(ck), per, body, anchor=f"sw15-{key}"), count_line(good, bad) + mk))
    last = state.get("last_run")
    method = (f'<section class="sp-method"><details><summary><b>Method</b><small>registration · fills · fees</small></summary><div>'
              f'<p class="sm">Pre-registered {esc(W.REGISTERED)} as {esc(W.VERSION)}, frozen before any window was graded: '
              f'windows opening from {esc(_start(W.FROM))} are graded once each, after Kalshi settles '
              'them, from its own 1-minute candles and trade prints. A minute is read print by print only where its candle '
              'shows the price could have touched an entry or a target. Paper only; nothing is placed.</p>'
              f'<p class="sm mut">{n_w} windows graded. Last run {esc(_start(last) if last else "not yet")}.</p>'
              '</div></details></section>')
    return (f'<details class="fold sw15-v1" id="sw15-v1"><summary><b>v1 baseline · every market</b> · nothing picked'
            f'</summary><p class="scope sw15-intro">Paper · every 15-minute market · record from {esc(_start(W.FROM))}</p>'
            + _list(cards) + method + '</details>')


def _archive(state, s1_final):
    """Every retired and removed cell's final record, in one collapsed block, grouped by lane."""
    import swing15v2 as V
    parts = []
    def grp(title, fn):
        try:
            html = fn()
        except Exception:                                       # noqa: BLE001  (never breaks the section)
            html = ""
        if html:
            parts.append(f'<h4>{esc(title)}</h4>{html}')
    grp("15-Minute Swing v3", lambda: _v3_s3_retired(state, V) + _v3_s1_retired(state, V)
        + _removed_fold(V.LABELS, V.records(state, removed=True), V.REMOVED_AT, lambda k: "Won"))
    def flip():
        import flipside_v2 as F
        import allowgate as G
        ret = F.records(state, retired=True)
        out = ""
        for name, old in FLIP_EPS:
            strat = f"flipside_v2_{old.lower()}"
            r = ret.get(strat) or {}
            a = r.get("all")
            try:
                M = __import__(name)
                label, nv = M.LABEL, G.never(M.ALLOW)
            except Exception:                                    # noqa: BLE001
                label, nv = "its v2 rule", {}
            note = ("" if not a else
                    f'<p class="sm">{old} final: {a["hits"]}/{a["n"]} won against {a["fair"] * a["n"]:.1f} priced, '
                    f'{pct(a["mean_roi"])} after fees. Replaced by {esc(label)}. No new entries.</p>')
            out += _removed_fold({strat: F.LABELS[strat]}, {strat: r}, F.RETIRED_TIMES[strat], lambda k: "Won",
                                 word="Retired", note=note)
            if nv:
                out += (f'<p class="sm mut {name}-never">{esc(label)} · no positive setting (never bets): '
                        + "; ".join(f'{mkt(m)} (' + ("no positive setting at all" if len(ks) == len(M.ALLOW[m]) else
                                                    "no positive " + " or ".join(NEVER_WORD.get(k, k) for k in ks)) + ")"
                                    for m, ks in nv.items()) + '.</p>')
        return out + _removed_fold(F.LABELS, F.records(state, removed=True), F.REMOVED_AT, lambda k: "Won")
    grp("The Flip Side v3", flip)
    def hte():
        import holdtoend as H
        return _hte_archive(state, H)
    grp("Hold to End", hte)
    grp("15-Minute Swing v1", lambda: _v1_s1_retired(state, s1_final))
    if not parts:
        return ""
    return ('<details class="fold sw15-archive" id="sw15-archive"><summary><b>Retired &amp; removed · final records</b>'
            '</summary>' + "".join(parts) + '</details>')


def section(state=None):
    state = W.load() if state is None else state
    allc = W.cells(state)
    n_w = len(state.get("windows") or {})
    import swing15v2 as V
    s1_final = W.cells(state, lambda w: W._ts(w["open"]) < W._ts(V.RETIRED_AT))
    blocks = []
    import holdtoend as H
    # The order after #378/#379 (Steady Favourites, the Lead Swap Board, Swing v3, The Flip Side v3, Hold to End v3),
    # with the newest lane, Rule 1 v2 · Loss Reader (2026-11-10), on top.
    for fn in (lambda: lossreader_block(state), lambda: s3v2_block(state), lambda: steadyfav_block(state),
               lambda: leadswap_block(state),
               lambda: swing_v3_block(state),
               lambda: flip_block(state), lambda: holdtoend_block(state, H)):
        try:
            blocks.append(fn())
        except Exception:                                       # noqa: BLE001  (one lane never breaks the section)
            pass
    # 2026-11-10 (Olu): no scoreboard, lane rows collapsed, one line per lane; v1 and the archive collapsed at the bottom.
    # Each lane in its own div: tables.js opens a #swing15 link's first direct-child <details>, which must not be a fold.
    return (f'<h2 class="dm-title">15-Minute</h2>' + "".join(f'<div class="sw15-lane">{b}</div>' for b in blocks)
            + f'<div class="sw15-lane">{_v1_block(state, allc, n_w)}{_archive(state, s1_final)}</div>')


def index_rows(state=None):
    state = W.load() if state is None else state
    allc = W.cells(state)
    out = []
    try:                                                        # Rule 1 v2 · Loss Reader (2026-11-10): first
        import lossreader as LR
        c = LR.ledger(state)["record"]
        out.append(dict(lane="lossreader", label=LR.LABEL, n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                        hit=(c["hits"] / c["n"]) if c else None, fair=c["fair"] if c else None,
                        status=f"{c['n'] if c else 0}/{LR.DECIDE_BETS} bets"))
    except Exception:                                           # noqa: BLE001  (never breaks the index)
        pass
    try:                                                        # Rule 2 v2 · Every Positive Setting (2026-11-10)
        import s3v2 as S32
        c = S32.records(state)["lane"]["all"]
        out.append(dict(lane="s3v2", label=S32.LABEL, n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                        hit=c["hit_rate"] if c else None, fair=c["fair"] if c else None,
                        status=f"{c['n'] if c else 0}/{S32.DECIDE_AT} bets"))
    except Exception:                                           # noqa: BLE001  (never breaks the index)
        pass
    for name, _old in FLIP_EPS:                                 # Rules 3-5 v2 · Every Positive Setting (2026-11-10)
        try:
            M = __import__(name)
            c = M.records(state)["lane"]["all"]
            out.append(dict(lane=name, label=M.LABEL, n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                            hit=c["hit_rate"] if c else None, fair=c["fair"] if c else None,
                            status=f"{c['n'] if c else 0}/{M.DECIDE_AT} bets"))
        except Exception:                                       # noqa: BLE001  (never breaks the index)
            pass
    import steadyfav as S                                       # Steady Favourites (2026-11-09)
    for key, r in S.records(state).items():
        c = r["all"]
        out.append(dict(lane=key, label="Steady Favourites · " + S.LABELS[key], n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{c['n'] if c else 0}/{W.DECIDE_AT}"))
    for key, label in W.STRATS.items():
        if key == "swing15_s1":
            continue                                             # retired 2026-11-09 22:00Z (graded underneath)
        ck = HEADLINE_S1 if key == "swing15_s1" else (key,)
        c = allc.get(ck)
        per = _per_series(state, ck)
        out.append(dict(lane=key, label=label + (" · 25c · 2x · hold" if key == "swing15_s1" else ""),
                        n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                        hit=c["hit_rate"] if c else None, fair=c["fair"] if c else None,
                        status=(f"{max(per.values(), default=0)}/{W.DECIDE_AT} in its best series")))
    import swing15v2 as V                                       # v2 (2026-11-09): its own rows, a fresh record
    for key, r in V.records(state).items():
        if not r["series"]:
            continue
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label="Swing v3 · " + V.LABELS[key], n=c["n"] if c else 0, roi=c["mean_roi"] if c else None,
                        hit=c["hit_rate"] if c else None, fair=c["fair"] if c else None,
                        status=f"{best}/{W.DECIDE_AT} in its best market"))
    import flipside_v2 as F                                     # The Flip Side v2 (2026-11-09)
    for key, r in F.records(state).items():
        if not r["series"]:
            continue
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label="Flip Side v3 · " + F.LABELS[key], n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{best}/{W.DECIDE_AT} in its best market"))
    import holdtoend as H                                       # Hold to End (2026-11-09)
    import leadswap as L
    for key, r in H.records(state).items():
        if not r["series"]:
            continue                                            # hte-v2 removed the 25c row entirely
        c = r["all"]
        best = max(((x or {}).get("n", 0) for x in r["series"].values()), default=0)
        out.append(dict(lane=key, label="Hold to End v3 · " + H.LABELS[key].replace("Hold to End · ", ""), n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{best}/{W.DECIDE_AT} in its best market"))
    rt = (L.load().get("routing") or {})                        # Lead Swap Board routing (2026-11-09)
    for key, label in L.STRATS.items():
        c = rt.get(key)
        out.append(dict(lane=key, label="Lead Swap · " + label, n=c["n"] if c else 0,
                        roi=c["mean_roi"] if c else None, hit=c["hit_rate"] if c else None,
                        fair=c["fair"] if c else None, status=f"{c['n'] if c else 0}/{W.DECIDE_AT}"))
    return out


def index_html(state=None):
    """The Sandbox's index rows, linking to the section on the Daily Markets tab."""
    try:
        rs = index_rows(state)
    except Exception:                                           # noqa: BLE001
        return ""
    def hv(r):
        return "—" if r["hit"] is None else f'{r["hit"] * 100:.0f}% v {r["fair"] * 100:.0f}%'
    rows = "".join(
        f'<tr data-lane="{esc(r["lane"])}"><td><b>{esc(r["label"])}</b></td>'
        f'<td><a href="./daily_markets.html#swing15">Daily Markets</a></td><td class="num">{r["n"]}</td>'
        f'<td class="num">{hv(r)}</td><td class="num">{pct(r["roi"])}</td><td>{esc(r["status"])}</td></tr>' for r in rs)
    return ('<section id="swing15-index"><h2>15-Minute Swing</h2><p class="shell-kicker">Every Kalshi 15-minute window in '
            'Crypto, Commodities and Financials · pre-registered strategies · paper · not in Production</p>'
            '<div class="tbl"><table><tr><th>Strategy</th><th>Page</th><th class="num">Windows</th>'
            '<th class="num">Hit v fair</th><th class="num">ROI after fees</th><th>Evidence</th></tr>'
            + rows + '</table></div></section>')
