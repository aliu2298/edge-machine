"""NBA win margin VERSION 5, two Sandbox PAPER lanes (2026-11-11, Olu: "option (b), paper only").

Production still runs version 4 + Bucket Priority bp-v3; nothing here places an order or touches the executor. The registered rules are in
docs/prereg_nba_wm_v5_2026-11-11.md (frozen before the first night):

  YES v5 (lane nba_wm_yes_v5)    buckets 6-10 and 11-20 only; the v4 entry (10-20c ask, 5c spread, ask check, an hour before the tip), the
                                 favourite skip ON (share 0.70+), half at 2x and half at 2.5x. The tracker's rows are the entries
                                 (nba_wm_v4.run with RULE_V5).
  NO v5 (lane nba_wm_nofade_v5)  the 65% post-only NO bid on buckets 1-5, 6-10 and the alternate ladder (11+, 11-15, 16-25, 26+): no 11-20 on the
                                 main ladder and no 21+. Replayed from nba_wm_nofade.py's entries under its strict rules.

Fresh record from SINCE; review at 10 nights, decide at 30 entries. Each lane is compared with the v4 rule on the same games.
"""
import json
import os

import nba_wm_nofade as N
import nba_wm_v4 as V4
import nba_winmargin as W

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "nba_wm_v5.json")
SINCE = "2026-11-11"                       # the Nov 11 (ET) slate
YES_LANE, NO_LANE = "nba_wm_yes_v5", "nba_wm_nofade_v5"
YES_VERSION, NO_VERSION = "wm-yes-v5-paper", "wm-nofade-v5-paper"
PREREG = "docs/prereg_nba_wm_v5_2026-11-11.md"
NO_DIP = 0.65
ALT_LADDER = ("11+", "11-15", "16-25", "26+")
NO_BUCKETS = ("1-5", "6-10") + ALT_LADDER
RULE_V5 = dict(lane=YES_LANE, version=YES_VERSION, path=PATH, since=SINCE, buckets=("6-10", "11-20"), max_fav=V4.MAX_FAV_SHARE, sells=V4.SELLS)
LABEL = "Paper test · candidate next version · Production still runs v4"


def load(path=None):
    return V4.load(path, RULE_V5)


def run(state, tracker, now=None):
    return V4.run(state, tracker, now, RULE_V5)


def yes_rows(state):
    return V4.yes_rows(state)


def yes_v4_rows(v4, since=SINCE, events=None):
    """The v4 rule's paper rows (data/nba_wm_v4.json) from `since`, optionally only the games in `events`."""
    return [r for r in V4.yes_rows(v4 or {"rows": {}}) if r["night"] >= since and (events is None or r["event"] in events)]


def no_entries(nofade, since=SINCE, buckets=None):
    """The NO fade ledger's entries from `since` (strict-rules phase), each keeping only `buckets` (None: all)."""
    out = []
    for e in V4.no_entries(nofade, since):
        if buckets is None:
            out.append(e)
        else:
            out.append(dict(e, buckets=[r for r in e["buckets"] if r.get("bucket") in buckets]))
    return out


def no_games(nofade, since=SINCE):
    """The v5 NO rule: the 65% bid on 1-5, 6-10 and the alternate ladder, one row per game with a verified fill."""
    return N.game_rows(no_entries(nofade, since, NO_BUCKETS), N.vkey(NO_DIP))


def no_v4_games(nofade, since=SINCE, events=None):
    """The v4 NO rule (the 65% bid on every bucket) on the same nights, optionally only the games in `events`."""
    g = N.game_rows(no_entries(nofade, since), N.vkey(NO_DIP))
    return [r for r in g if events is None or r["event"] in events]


def main(argv=None):
    st = load()
    try:
        with open(W.PATH) as f:
            tracker = json.load(f)
        run(st, tracker)
        st["error"] = None
    except Exception as e:                                       # noqa: BLE001
        st["error"] = (type(e).__name__ + ": " + str(e))[:300]
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)
    print("nba_wm_v5", YES_LANE, "rows", len(st["rows"]), "since", st["since"], st.get("observations"), "error", st.get("error"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
