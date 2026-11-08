"""NBA win margin PRODUCTION VERSION 4 (2026-11-08, Olu: "put the better version in production, the one with the better ROI").

Version 3 -> version 4, from the night of 2026-11-08 (the first slate whose entries the executor pins to wm-yes-v4 / wm-nofade-v4):

  YES split   buckets 1-5, 6-10 AND 11-20; the same 10-20c ask, 5c spread and book check; a game whose favourite's pregame win share is
              0.70 or more is skipped (the executor records the share on the decision as fav_share); half rests at 2x and half at 2.5x
              of the ask (cap 98c). The registered rule is nba_wm_v4.py (the Sandbox paper lane nba_wm_yes_v4).
  NO fade     the post-only NO bid at 65% of P (not 75%); the sell back at P and every other term unchanged (paper lane nba_wm_nofade_65).

The replay is nba_wm_v3.py's, unchanged except for the sells and the bid: the entries are the executor's own T-1h decisions
(data/nba_wm_decisions.json, taken by bot_version), only the FILLS are replayed from trade prints. Own ledger data/nba_wm_v4prod.json;
version 3's ledger (data/nba_wm_v3.json) keeps its rows and stops taking decisions pinned to version 4.
"""
import os

import nba_wm_nofade as N
import nba_wm_v3 as V3

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_wm_v4prod.json")
YES_LANE, NO_LANE = V3.YES_LANE, V3.NO_LANE                      # the wire lanes are unchanged (the executor pins the version)
YES_VERSION, NO_VERSION = "wm-yes-v4", "wm-nofade-v4"
SWITCH_ON = "2026-11-08"                                         # the first night version 4 trades
SELLS = ((2.0, 0.5), (2.5, 0.5))
NO_DIP = 0.65
MAX_FAV_SHARE = 0.70
BUCKETS = ("1-5", "6-10", "11-20")


def take(d):
    return d.get("bot_version") in (YES_VERSION, NO_VERSION)


CFG = dict(path=PATH, yes_version=YES_VERSION, no_version=NO_VERSION, sells=SELLS, take=take, dip=NO_DIP, version="v4")


def load(path=None):
    return V3.load(path or PATH, "v4")


def run(state, decisions=None, now=None, fetch=None):
    kw = {} if fetch is None else dict(fetch=fetch)
    return V3.run(state, decisions, now, cfg=CFG, **kw)


def yes_rows(state):
    return V3.yes_rows(state)


def no_games(state):
    return V3.no_games(state)


def headline_state():
    """The Production record the pages headline: version 4 once it has started, else version 3."""
    s = load()
    return s if s.get("since") else V3.load()


def main(argv=None):
    import json
    st = load()
    try:
        run(st)
    except Exception as e:                                       # noqa: BLE001
        st["error"] = (type(e).__name__ + ": " + str(e))[:300]
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    print("nba_wm_v4prod rows", len(st["rows"]), "since", st["since"], "this run", st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
