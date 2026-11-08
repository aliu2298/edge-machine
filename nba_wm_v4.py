"""NBA win margin, two new Sandbox PAPER lanes (2026-11-06, Olu). Production version 3 is untouched; nothing here places an order.

YES v4 (lane nba_wm_yes_v4). The tracker's own rows (data/nba_winmargin_tracker.json: the bid and ask an hour before the tip from the
1-minute candles, every trade print from then) are the entries:
  buckets   1-5, 6-10 and 11-20, either team. 21+ is excluded.
  entry     the YES ask 10-20c, spread 5c or less, the tracker's ask check (10+ contracts traded at or through the ask in the hour
            after the entry, stamped on the row), one hour before the tip; a taker buy, with the taker fee.
  matchup   (pre-registered) a game whose favourite's pregame win share is 0.70 or more is skipped. The share is the tracker row's
            team_share (a team's bucket mids over both teams'); the favourite is the larger of the two.
  exit      half rests at 2x and half at 2.5x of the ask paid (cap 98c), each filled only by a print STRICTLY through its target from the
            tip on; a leg not filled settles. The control is the same entries held to settlement.
  record    fresh from SINCE_YES; review at 10 settled events, decide at 30.

NO fade 65% (lane nba_wm_nofade_65). The v3 NO fade with the post-only NO bid at 65% of the bucket's pregame NO price (not 75%); the sell
back at the pregame price needs a print strictly above it, else settlement. nba_wm_nofade.py already replays the 65% variant of every
bucket under the follower's strict rules, so this lane is that variant's games from SINCE_NO on, with its own fresh record.

IN-SAMPLE (the rules were chosen on these, never the headline): the tracker's 544 eligible contracts, Oct 20 to Nov 5 - the 10-20c core
with a 2x / 2.5x split +41% against the 2x / 3x split +34% (the 3x leg fell to +16% on the newer nights); toss-up games +51%, lopsided
+25%; 11-20 at 10-20c +40% (46 contracts); 21+ about zero.

Own ledger data/nba_wm_v4.json (the YES v4 rows). Rows are stamped and never rewritten.

SWITCH (2026-11-08, Olu): version 4 is now Production (nba_wm_v4prod.py). These two lanes' rules are Production's, so from the switch night the
Sandbox pages stop listing them (their ledger and history stay). The Sandbox instead keeps the OLD Production rules as paper, for the comparison:
  YES v3 paper (lane nba_wm_yes_v3)  the same tracker rows with the version 3 terms: buckets 1-5 and 6-10, no matchup skip, 2x / 3x sells.
                                     Own ledger data/nba_wm_v3paper.json, fresh from SINCE_V3_PAPER.
  NO fade 75% paper (lane nba_wm_nofade_75)  the 75% bid's games from SINCE_V3_PAPER on (nba_wm_nofade.py's replay), its own fresh record.
The parameters live in RULE_V4 / RULE_V3 below; the functions take the rule.
"""
import datetime as dt
import json
import os

import chaos_replay as C
import daily_track as D
import nba_winmargin as W
import nba_wm_nofade as N

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_wm_v4.json")
YES_LANE, NO_LANE = "nba_wm_yes_v4", "nba_wm_nofade_65"
YES_VERSION, NO_VERSION = "wm-yes-v4", "wm-nofade-65-v1"
SINCE_YES = "2026-11-06"
SINCE_NO = "2026-11-06"
NO_DIP = 0.65
BUCKETS = ("1-5", "6-10", "11-20")
ASK_BAND = (0.10, 0.20)
MAX_SPREAD = 0.05
MAX_FAV_SHARE = 0.70
SELLS = ((2.0, 0.5), (2.5, 0.5))
SELL_CAP = 0.98
SINCE_V3_PAPER = "2026-11-08"
NO75_LANE = "nba_wm_nofade_75"
PATH_V3_PAPER = os.path.join(ROOT, "data", "nba_wm_v3paper.json")
RULE_V4 = dict(lane=YES_LANE, version=YES_VERSION, path=PATH, since=SINCE_YES, buckets=BUCKETS, max_fav=MAX_FAV_SHARE, sells=SELLS)
RULE_V3 = dict(lane="nba_wm_yes_v3", version="wm-yes-v3-paper", path=PATH_V3_PAPER, since=SINCE_V3_PAPER, buckets=("1-5", "6-10"), max_fav=None,
               sells=((2.0, 0.5), (3.0, 0.5)))
REVIEW_N, DECIDE_N = C.REVIEW_N, C.PROMOTE_N
EPS = 1e-9
# The tracker's in-sample read of the YES rule (544 eligible contracts, Oct 20 - Nov 5): a fixed note, not a live figure.
IN_SAMPLE = (("Core 10-20c, 2x / 2.5x split", "+41%"), ("Core 10-20c, 2x / 3x split (the v3 exit)", "+34%"),
             ("3x leg on the newer nights", "+16%"), ("Toss-up games", "+51%"), ("Lopsided games", "+25%"),
             ("11-20 bucket at 10-20c (46 contracts)", "+40%"), ("21+ bucket", "about 0"))


def load(path=None, rule=None):
    rule = rule or RULE_V4
    try:
        with open(path or rule["path"]) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("version", rule["version"])
    s.setdefault("since", rule["since"])
    s.setdefault("rows", {})
    s.setdefault("skips", {})
    return s


def favourite_share(rows):
    """{event: the larger team_share among the event's rows} (None when no row carries one)."""
    out = {}
    for r in rows:
        p = r.get("team_share")
        if p is not None:
            out[r["event"]] = max(out.get(r["event"], 0.0), p)
    return out


def candidates(tracker_rows, since=SINCE_YES, rule=None):
    """(entries, skips): the tracker rows that pass the rule, and {id: reason} for the eligible rows the matchup or the ask check left out."""
    rule = rule or RULE_V4
    fav = favourite_share(tracker_rows)
    ok, skips = [], {}
    for r in tracker_rows:
        if r.get("night", "") < since or r.get("bucket") not in rule["buckets"] or not r.get("eligible"):
            continue
        if not ASK_BAND[0] - EPS <= r["ask"] <= ASK_BAND[1] + EPS or r["spread"] > MAX_SPREAD + EPS:
            continue
        if rule["max_fav"] is not None and fav.get(r["event"], 0.0) >= rule["max_fav"] - EPS:
            skips[r["id"]] = f"favourite share {fav[r['event']]:.2f} (0.70 or more)"
            continue
        if r.get("ask_ok") is not True:
            skips[r["id"]] = "unverified ask"
            continue
        ok.append(r)
    return ok, skips


def trade(path, ask, won, sells=SELLS):
    """The 2x / 2.5x split (`sells`: version 3's 2x / 3x for the paper copy) from the tracker's price path [[seconds from the tip, price cents, contracts]]: cost = the ask + the taker fee;
    each leg fills on a print from the tip on STRICTLY above its target; an unfilled leg settles."""
    pay = 1.0 if won else 0.0
    cost = C.cost(ask)
    proceeds, legs = 0.0, []
    for mult, share in sells:
        target = round(min(ask * mult, SELL_CAP), 2)
        hit = any(t >= 0 and c / 100 > target + EPS for t, c, _n in path or [])
        legs.append(dict(multiple=mult, target=target, filled=hit))
        proceeds += share * ((target - C.maker_fee(target)) if hit else pay)
    return dict(ask=ask, cost=round(cost, 5), profit=round(proceeds - cost, 5), roi=round((proceeds - cost) / cost, 4), won=proceeds > cost,
                hold_roi=round((pay - cost) / cost, 4), filled_2x=legs[0]["filled"], reason="split",
                **{"filled_" + f"{sells[1][0]:g}".replace(".", "") + "x": legs[1]["filled"]})


def run(state, tracker, now=None, rule=None):
    """Add a row for every candidate tracker row not yet recorded. The tracker only lists settled games, so a row is final."""
    now = now or dt.datetime.now(dt.timezone.utc)
    rule = rule or RULE_V4
    ok, skips = candidates(tracker.get("rows") or [], state.get("since") or rule["since"], rule)
    new = 0
    for r in ok:
        if r["id"] in state["rows"]:
            continue
        if not r.get("path") and not r.get("m"):
            state["skips"][r["id"]] = "no price path"
            continue
        row = dict(key=r["id"], lane=rule["lane"], version=rule["version"], event=r["event"], night=r["night"], tip=r["tip"], team=r["team"],
                   bucket=r["bucket"], team_share=r.get("team_share"), logged=now.isoformat())
        row.update(trade(r.get("path"), r["ask"], bool(r["won"]), rule["sells"]))
        state["rows"][r["id"]] = row
        new += 1
    state["skips"].update({k: v for k, v in skips.items() if k not in state["rows"]})
    state["last_run"] = now.isoformat()
    state["observations"] = dict(at=now.isoformat(), new=new, skipped=len(state["skips"]))
    return state


def yes_rows(state):
    return [r for r in state["rows"].values() if "roi" in r]


def no_entries(nofade, since=SINCE_NO):
    return [e for e in nofade["entries"] if e["night"] >= since and N.phase_of(e["night"]) == "v2"]


def no_games(nofade, dip=NO_DIP, since=SINCE_NO):
    """One row per game with a verified 65% fill (or the comparison dip), on the lane's fresh record."""
    return N.game_rows(no_entries(nofade, since), N.vkey(dip))


def no75_games(nofade, since=SINCE_V3_PAPER):
    """The 75% bid's games on the paper lane's fresh record (Production's rule before the switch)."""
    return no_games(nofade, N.HEAD, since)


def before_games(nofade, dip, since=SINCE_NO):
    """The same variant on the nights before the lane (v2 and the in-sample days): the rule was chosen on them."""
    es = [e for e in nofade["entries"] if e["night"] < since]
    return N.game_rows(es, N.vkey(dip))


def main(argv=None):
    for rule in (RULE_V4, RULE_V3):
        st = load(None, rule)
        try:
            with open(W.PATH) as f:
                tracker = json.load(f)
            run(st, tracker, rule=rule)
            st["error"] = None
        except Exception as e:                                       # noqa: BLE001
            st["error"] = (type(e).__name__ + ": " + str(e))[:300]
        os.makedirs(os.path.dirname(rule["path"]), exist_ok=True)
        tmp = rule["path"] + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, rule["path"])
        print("nba_wm_v4", rule["lane"], "rows", len(st["rows"]), "since", st["since"], st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
