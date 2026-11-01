"""o35_cheap_no_wave: Over 3.5 cheap NO, a resting bid sold into the quiet spell (2026-10-28, Olu). Sandbox PAPER.

Kalshi soccer total-goals markets, the over 3.5 rung (event ticker + "-4", floor_strike 3.5), in the eleven
leagues the Soccer page tracks (soccer_rules.SERIES less the Saudi Pro League). Before kickoff a NO bid rests at 10c.
It can only fill in play, after goals push YES to 80-90c or more.

TRIMMED 2026-10-31 (Olu), version o35-v2: NO bid 10c, sell at 4x (3x tracked beside it); 15c and 20c bids and the Saudi
Pro League dropped (v1, 41 fills: 10c at 4x +61.6%, 20c at 4x -36%; Saudi 0/5, no sell filled). The v1 record stays on the
page, collapsed; the v2 record is fresh from SINCE and its headline counts only v2 entries. The ledger still stores every
target (2x, 3x, 4x, hold) so nothing is lost; the page shows 3x and 4x.

FILL. The bid fills at its limit when the first TRADE after it was placed prints NO at or under the limit (NO
price = 1 - yes_price on /markets/trades). Fills after the 4th goal are KEPT (a real resting bid is hit there
too) and flagged "dead fill": by the market's own prices that is a fill whose print is NO 2c or less, when the
over is all but certain (we have no goal clock, so this is the proxy; it can only miss a dead fill, never invent one).

EXITS, on the same entries: a resting sell at 2x, 3x or 4x of the limit (4x is the headline since v2), or hold to settlement. A sell
fills only on a LATER trade print at or above the target AND only if at least 50 contracts traded at or above the
target after the bid filled. Under 50 the sell does not fill (held to settlement) and the trade is marked "thin";
the volume is logged either way. Maker fee 0.0175 p(1-p) on BOTH legs (both rest), none on settlement.

SECOND HALF ONLY, version o35-v3 (Olu, 2026-11-01): the bid counts only from kickoff + BID_AFTER_MIN (60) minutes, so a
fill needs a print after that. A comparison bid, "10e", is tracked beside it: the old rule (bid an hour BEFORE kickoff)
counted only for fills that came before kickoff + 60 min, so the split keeps being measured. Why: the 10c fills split by
the clock, in-sample Oct 28-31 2nd-half 27 fills reached 4x 56% (+116.5%) v 1st-half 9 fills 22% (-13%); holdout Oct 17-27
(190 matches) 2nd-half 63 fills 40% (+54.6% at 4x, z 2.3) v 1st-half 24 fills 21% (-18.8%); fair to reach 4x is 25%.
This is research, not evidence for the lane (the v3 record starts fresh on SINCE).

KICKOFF = Kalshi occurrence_datetime minus 4 hours (verified on 72 games against ESPN). The v1 and v2 bids were placed
an hour before it; only prints after that count for them.

Every settled market since SINCE is evaluated once, from its trades, whether or not the bid filled. Each entry
is tagged with whether the match was also an over 1.5 form-rule match (the research population: o15_form_l10).
Own ledger data/o35_cheap_no_ledger.json (fresh record from SINCE; no other ledger is read or written).
Review at 10 filled, decide at 30, on the v2 record.
"""
import datetime as dt
import json
import os

import chaos_replay as C
import daily_track as D
import soccer_rules as SR

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "o35_cheap_no_ledger.json")
SOURCE_LEDGER = os.path.join(ROOT, "data", "sandbox_ledger.json")
LANE = "o35_cheap_no_wave"
LABEL = "Over 3.5 cheap NO · second-half NO bid 10c · sell at 4× (3× tracked)"
RESEARCH_NOTE = ("Research note, not evidence: on 10c fills measured by minutes after kickoff, second-half fills (60+ min) reached 4x "
                 "56% of the time, +117% at 4x (27 fills, Oct 28-31), and 40%, +55% at 4x, z 2.3 (63 fills, 190 matches, Oct 17-27); "
                 "first-half fills reached it 22% and 21%, -13% and -19% (9 and 24 fills). Fair to reach 4x is 25%. "
                 "That is why the bid now waits for the second half; this record starts fresh.")
V2_LABEL = "Before the second-half rule (v2)"
TRIM_NOTE = "Trimmed 2026-10-31: v1 (41 fills) showed 10c at 4× best, 15c/20c worse, and the Saudi Pro League 0 for 5 with no sell filled; fresh v2 record."
V1_LABEL = "Before the Nov trim (v1)"
V1 = "o35-v1"
V2 = "o35-v2"
SINCE = "2026-11-01"
VERSION = "o35-v3"
LIMITS = (0.10,)
V1_LIMITS = (0.10, 0.15, 0.20)
HEADLINE = 0.10
MULTS = (2, 3, 4)
HEAD_MULT = 4
COMPARE_MULT = 3
V1_HEAD_MULT = 2
LEAGUES = {k: v for k, v in SR.SERIES.items() if k != "Saudi Pro League"}
MIN_VOL = 50
DEAD_NO = 0.02
KICKOFF_BACK_H = 4
BID_LEAD_MIN = 60              # the old rule: bid this long before kickoff (v1, v2, and the "10e" comparison)
BID_AFTER_MIN = 60             # v3: the bid counts from this long AFTER kickoff
EARLY = "e"                    # bids key suffix of the comparison: first-half fills of the old bid
CAP = 0.98
MAKER = 0.0175
REVIEW_N, DECIDE_N = 10, 30
MAX_EVENTS_PER_RUN = 60
EPS = 1e-9
ET = D.ET
UTC = dt.timezone.utc


def fee(p):
    return MAKER * p * (1 - p)


def vkey(limit, mult):
    return f"{round(limit * 100)}c_{'hold' if mult is None else str(mult) + 'x'}"


def vlabel(key):
    lim, ex = key.split("_")
    return f"NO bid {lim} · " + ("hold to settlement" if ex == "hold" else f"sell at {ex}")


def _ts(raw):
    t = D.instant(raw)
    return int(t.timestamp()) if t else None


def night_of(ts):
    return dt.datetime.fromtimestamp(ts, UTC).astimezone(ET).date().isoformat()


def prints_of(trades):
    """[(ts, no_price, contracts)] oldest first, from /markets/trades rows."""
    out = []
    for t in trades or []:
        ts = _ts(t.get("created_time"))
        yes = D.number(t.get("yes_price_dollars"))
        no = D.number(t.get("no_price_dollars"))
        if no is None and yes is not None:
            no = round(1 - yes, 4)
        n = D.number(t.get("count_fp")) or 0.0
        if ts is not None and no is not None:
            out.append((ts, no, n))
    return sorted(out)


def fetch_trades(ticker, min_ts, fetch, max_pages=30):
    rows, path, pages = [], f"markets/trades?ticker={ticker}&min_ts={min_ts}&limit=1000", 0
    while path and pages < max_pages:
        d = fetch(path)
        rows += d.get("trades") or []
        cur = d.get("cursor")
        path = f"markets/trades?ticker={ticker}&min_ts={min_ts}&limit=1000&cursor={cur}" if cur and d.get("trades") else None
        pages += 1
    return rows


def evaluate(prints, kickoff_ts, result, limits=None):
    """{limit key: bid outcome} for one market. A bid is None when no print reached it. A filled bid carries the
    fill time, the dead-fill flag, and per multiple the target, whether the sell filled, whether it was thin and
    the contracts traded at or above the target after the fill. Key "10" is the second-half bid (prints from kickoff +
    BID_AFTER_MIN); "10e" is the comparison: the old bid from an hour before kickoff, kept only if it filled before
    kickoff + BID_AFTER_MIN (a first-half fill)."""
    payout = 1.0 if result == "no" else 0.0
    out = {}
    for limit in limits or LIMITS:
        key = f"{round(limit * 100)}"
        lo = kickoff_ts + BID_AFTER_MIN * 60
        out[key] = _bid([p for p in prints if p[0] >= lo], limit, payout)
        early = _bid([p for p in prints if p[0] >= kickoff_ts - BID_LEAD_MIN * 60], limit, payout)
        out[key + EARLY] = early if early and early["fill_at"] < lo else None
    return out


def _bid(live, limit, payout):
    i = next((k for k, p in enumerate(live) if p[1] <= limit + EPS), None)
    if i is None:
        return None
    after = live[i + 1:]
    sells = {}
    for m in MULTS:
        target = round(min(limit * m, CAP), 2)
        hit = [p for p in after if p[1] >= target - EPS]
        vol = round(sum(p[2] for p in hit), 2)
        sells[str(m)] = dict(target=target, volume=vol, filled=bool(hit) and vol >= MIN_VOL - EPS,
                             thin=bool(hit) and vol < MIN_VOL - EPS, at=hit[0][0] if hit and vol >= MIN_VOL - EPS else None)
    return dict(limit=limit, fill_at=live[i][0], fill_print=live[i][1], dead=live[i][1] <= DEAD_NO + EPS,
                sells=sells, payout=payout)


def split(entries):
    """(older entries, current-version entries): an entry without a version stamp is v1."""
    return ([e for e in entries if e.get("version", V1) != VERSION], [e for e in entries if e.get("version", V1) == VERSION])


def split3(entries):
    """(v1, v2, v3 entries)."""
    v = lambda e: e.get("version", V1)
    return ([e for e in entries if v(e) not in (V2, VERSION)], [e for e in entries if v(e) == V2], [e for e in entries if v(e) == VERSION])


def trade_rows(entries, early=False):
    """One row per filled bid per variant: the stats shape chaos_replay.stats reads. early=True reads the
    first-half comparison bids ("10e") instead of the second-half ones."""
    rows = []
    for e in entries:
        for lk, b in (e.get("bids") or {}).items():
            if not b or lk.endswith(EARLY) != early:
                continue
            limit = b["limit"]
            cost = limit + fee(limit)
            for m in (None,) + MULTS:
                if m is None:
                    proceeds, reason, thin = b["payout"], "settled", False
                else:
                    s = b["sells"][str(m)]
                    proceeds = s["target"] - fee(s["target"]) if s["filled"] else b["payout"]
                    reason, thin = ("target" if s["filled"] else "settled"), s["thin"]
                profit = proceeds - cost
                rows.append(dict(variant=vkey(limit, m), limit=limit, mult=m, cost=cost, profit=profit, roi=profit / cost,
                                 won=profit > 0, reason=reason, night=e["night"], kickoff=e["kickoff"], league=e["league"],
                                 event=e["event"], dead=b["dead"], thin=thin, form_rule=e["form_rule"]))
    return rows


def form_rule_events(path=SOURCE_LEDGER):
    """Events the over 1.5 form rule (o15_form_l10) fired on: read-only."""
    try:
        with open(path) as f:
            q = json.load(f).get("quotes") or []
    except (OSError, ValueError):
        return set()
    return {x["market_id"].rsplit("-", 1)[0] for x in q if x.get("source") == "o15_form_l10" and x.get("market_id")}


def load(path=None):
    try:
        with open(path or PATH) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("lane", LANE)
    if s.get("version") != VERSION:                             # older records stay; v3 starts fresh from SINCE
        if s.get("version") == V2:
            s["v2_since"] = s.get("since") or "2026-10-31"
        else:
            s["v1_since"] = s.get("v1_since") or s.get("since") or "2026-10-28"
        s["since"], s["version"] = SINCE, VERSION
    s.setdefault("entries", [])
    s.setdefault("seen", {})
    s.setdefault("skips", {})
    return s


def over35(markets):
    return next((m for m in markets if D.number(m.get("floor_strike")) == 3.5 and m["ticker"].endswith("-4")), None)


def run(state, now=None, fetch=D.get, forms=None):
    now = now or dt.datetime.now(UTC)
    forms = form_rule_events() if forms is None else forms
    since = dt.date.fromisoformat(state["since"])
    obs = dict(at=now.isoformat(), new=0, waiting=0, errors=[])
    done = 0
    for league, series in LEAGUES.items():
        try:
            events = C.list_events(series, since, fetch, until=now.astimezone(ET).date())
        except Exception as e:                                  # noqa: BLE001
            obs["errors"].append(f"{series}: {str(e)[:80]}")
            continue
        for event in events:
            if event in state["seen"] or event in state["skips"]:
                continue
            if done >= MAX_EVENTS_PER_RUN:
                break
            try:
                ms = D.pages(f"markets?limit=200&event_ticker={event}", "markets", fetch)
                m = over35(ms)
                if m is None:
                    state["skips"][event] = "no over 3.5 market"
                    continue
                result = m.get("result")
                if m.get("status") not in ("finalized", "settled") or result not in ("yes", "no"):
                    obs["waiting"] += 1
                    continue
                occ = _ts(m.get("occurrence_datetime"))
                if occ is None:
                    state["skips"][event] = "no occurrence time"
                    continue
                kickoff = occ - KICKOFF_BACK_H * 3600
                night = night_of(kickoff)
                if night < state["since"]:
                    state["seen"][event] = "before the lane's first night"
                    continue
                prints = prints_of(fetch_trades(m["ticker"], kickoff - BID_LEAD_MIN * 60, fetch))
            except Exception as e:                              # noqa: BLE001
                obs["errors"].append(f"{event}: {str(e)[:80]}")
                continue
            state["entries"].append(dict(id=m["ticker"], event=event, league=league, series=series, kickoff=kickoff,
                                         night=night, result=result, form_rule=event in forms, prints=len(prints),
                                         bids=evaluate(prints, kickoff, result), logged=now.isoformat(), version=VERSION))
            state["seen"][event] = now.isoformat()
            obs["new"] += 1
            done += 1
    state["last_run"] = now.isoformat()
    state["error"] = "; ".join(obs["errors"])[:600] or None
    state["observations"] = obs
    return state


def main():
    st = load()
    try:
        run(st)
    except Exception as e:                                      # noqa: BLE001
        st["error"] = (type(e).__name__ + ": " + str(e))[:300]
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    print(LANE, "entries", len(st["entries"]), "this run", st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
