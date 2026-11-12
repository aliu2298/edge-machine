"""The promotion gate (2026-11-12, Olu): no lane moves from the Sandbox to Production unless its honest figure says so.

THE RULE. A lane may be in Production only if, on its own entries, graded by fillsim's strict rule set (honest-v1):
  1. its return after fees is POSITIVE. No exception.
  2. it passes the evidence test (fdr_check.gate): 30+ settled bets on 10+ separate outcomes, up in both halves, still up without its
     best outcome, and a clustered score of 2 or better. Olu may waive this test for a named lane; the waiver is written into the
     lane's record (who, when, why) and stays there. Nothing waives rule 1.

ENFORCED, NOT ADVISORY. test_promotion_gate.py runs on every pull request. It lists every lane the code puts in Production (the
tracker's PAIR_OVERRIDES, each own-feed module's registry) and fails if one of them has no passing record in
data/promotion_gate.json. A promotion is a code change, so it cannot merge without its record. A Production feed or module this file
does not know also fails the test, so a new feed cannot go around the gate.

GRANDFATHERED. The lanes that were live when the gate was built (2026-11-12) are listed below. The gate does not pull them. Their
figures are recorded and reported, and the decision on any that fail is Olu's. A grandfathered lane that leaves Production and
comes back is a new promotion: take it off the list.

HOW A LANE IS GRADED. A lane that rests an order or sells early: fillsim's strict rules, from trade prints (fillsim_regrade's
adapters). A buy-and-hold lane: every bet at its logged ask and the exchange's real fee, less any bet whose ask the prints refute
(fillsim.QUOTED); `confirmed` counts the bets whose ask the prints or a book read positively confirmed.

THE RECORD (data/promotion_gate.json) holds, per lane: the honest figure (bets, outcomes, return, score, halves), the page figure,
the "if touches fill" figure as a note (never the gate, never on a page), the checks, and any waiver. It is written by
`python3 promotion_gate.py check [lane ...]`, which reads Kalshi's public trade prints. Pages do not read this file.

  python3 promotion_gate.py check                     re-grade every Production lane and every lane already on record
  python3 promotion_gate.py check "source|scope" ...  grade the named lanes too (a lane about to be promoted)
  python3 promotion_gate.py status                    the record as a table
  python3 promotion_gate.py verify                    the test's own check, offline (exit 1 = a lane is in Production without its record)
"""
import datetime as dt
import glob
import json
import os
import sys

import fdr_check as FD
import fillsim as F
import fillsim_regrade as G

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "promotion_gate.json")
BUILT = "2026-11-12"

GRANDFATHERED = frozenset({
    "corners_ucl_fade|soccer_corners", "crypto_fav_band_below|crypto_fav", "ftts_no_70_80|soccer_ftts", "mls_fade_home|soccer_p05",
    "team1_form_l5|soccer_team1_intl", "team2_form_l10|soccer_team2_intl", "team2_ranked|soccer_team2", "u35_low_scoring|soccer_u35_cup",
    "u35_low_scoring|soccer_u35_intl",
    "sr_a7|soccer_u35", "sr_a6|soccer_o25", "sr_c3|soccer_o25", "sr_c4|soccer_o25", "sr_a2|soccer_u35", "sr_a3|soccer_u35",
    "st_t7|soccer_team3", "st_t1h|soccer_team2", "st_t1m|soccer_u35",
    "econ_nc_yes|econ_daily", "finance_spx_nc_no|finance_daily",
    "nba_winmargin_live", "nba_wm_nofade", "arg_goalless_dip_live",
})

# Every file and module that can put a lane in front of the follower. A new one must be added here AND to production_lanes().
KNOWN_FEEDS = frozenset({
    "production_leads.json", "soccer_rules_production_leads.json", "soccer_team_rules_production_leads.json", "econ_production_leads.json",
    "culture_production_leads.json", "nba_value_production_leads.json", "production_nba_wm_leads.json",
    "production_nba_wm_nofade_leads.json", "production_o35_leads.json", "production_top5_dip_leads.json", "production_arg_dip_leads.json",
})
KNOWN_MODULES = frozenset({
    "production.py", "production_live.py", "production_overview.py", "soccer_rules_production.py", "soccer_team_rules_production.py",
    "daily_production.py", "culture_production.py", "nba_value_production.py", "nba_wm_production.py", "o35_production.py",
    "top5_dip_production.py", "arg_dip_production.py", "live_record_publish.py",
})
# Own-engine Production lanes -> the fillsim_regrade lane that grades their own entries.
OWN = {"nba_winmargin_live": "nba_winmargin_live", "nba_wm_nofade": "nba_wm_nofade", "o35_cheap_no_wave": "o35_cheap_no_v4",
       "top5_goalless_dip_live": "top5_dip", "arg_goalless_dip_live": "arg_dip"}


def _ended(module, today):
    end = getattr(module, "ENDED_ON", None) or getattr(module, "DEMOTED_ON", None)
    return bool(end) and end <= today


def production_lanes(today=None):
    """{lane key: label} for every lane the CODE puts in Production today."""
    import arg_dip_production as AP
    import culture_production as CP
    import daily_production as DP
    import nba_value_production as NVP
    import nba_wm_production as NWP
    import o35_production as OP
    import sandbox_track as T
    import soccer_rules_production as SRP
    import soccer_team_rules_production as STRP
    import top5_dip_production as TP
    today = today or dt.datetime.now(dt.timezone.utc).date().isoformat()
    out = {}
    for key, o in T.PAIR_OVERRIDES.items():
        gone = T.PAIR_REMOVALS.get(key)
        if o.get("moved_on") and not (gone and gone.get("removed_on", "") >= o["moved_on"]):
            out[key] = "tracker rule"
    for registry in (SRP.PAIRS, STRP.PAIRS):
        for _rule, (pair, sport, label) in registry.items():
            out[f"{pair}|{sport}"] = label
    for pair in DP.NC_PAIRS.values():
        out[pair] = "economic daily, near-certain"
    out[DP.FIN_PAIR] = "S&P 500 near-certain NO"
    for pair in NVP.PAIRS:
        out[pair] = "NBA value"
    if not _ended(CP, today):
        out[CP.PAIR] = CP.LABEL
    if not _ended(OP, today):
        out[OP.LANE] = OP.NAME
    if not _ended(TP, today):
        out[TP.LANE] = TP.NAME
    if not _ended(AP, today):
        out[AP.LANE] = AP.NAME
    out["nba_winmargin_live"] = "NBA win margin YES split"
    out["nba_wm_nofade"] = "NBA win margin NO fade"
    return out


def unknown_feeds(root=ROOT):
    """Production feed files and modules the gate has not been told about."""
    feeds = {os.path.basename(p) for p in glob.glob(os.path.join(root, "data", "*leads*.json")) if "production" in os.path.basename(p)}
    mods = {os.path.basename(p) for p in glob.glob(os.path.join(root, "*production*.py")) if not os.path.basename(p).startswith("test_")}
    return sorted((feeds - KNOWN_FEEDS) | (mods - KNOWN_MODULES))


# ---------------------------------------------------------------- grading a lane on its own entries
def grader(key):
    """(rows(tape), exit kind "sell" | "hold") for a lane key, or None when nothing here can grade it."""
    import daily_production as DP
    lanes = G.lanes()
    name = OWN.get(key, key)
    if name in lanes:
        return lanes[name][3], lanes[name][1]
    src, _, scope = key.partition("|")
    if src.startswith(("sr_", "st_")) and scope:
        ledger = "soccer_rules_ledger" if src.startswith("sr_") else "soccer_team_rules_ledger"
        rule = src.split("_", 1)[1].upper()
        return (lambda tp: G.hold_lane(G.pick_bets(((G.load(ledger)["rules"].get(rule) or {}).get("picks")) or []), tp)), "hold"
    if scope == "econ_daily":
        return (lambda tp: G.hold_lane(G.pick_bets(((G.load("daily_ledger")["nc"].get(src) or {}).get("picks")) or []), tp)), "hold"
    if key == DP.FIN_PAIR:
        return (lambda tp: G.hold_lane(G.pick_bets(G.load("finance_nc_ledger").get("picks") or []), tp)), "hold"
    if scope:
        return (lambda tp: G.hold_lane(G.tracker_bets(src, scope), tp)), "hold"
    return None


def figure(rows, exit_kind, which="honest"):
    """One figure of a lane's rows as fdr_check reads a lane: bets, outcomes, return, score, halves, without its best outcome."""
    k = which if exit_kind == "sell" else which + "_hold"
    s = FD.lane_stats([(r[k], FD.when(r["cluster"])) for r in rows if r.get(k) is not None])
    return dict(n=s["n"], outcomes=s["clusters"], roi=s["roi"], t=s["t"], halves=s["halves"], without_best=s["without_best"], tested=s["tested"],
                clusters=s["clusters"])


def grade(key, tape, label=None, now=None):
    """One lane's gate record, or None when it cannot be graded."""
    g = grader(key)
    if g is None:
        return None
    adapter, exit_kind = g
    G.RULES[0] = F.HONEST
    rows = adapter(tape)
    honest, page = figure(rows, exit_kind), figure(rows, exit_kind, "page")
    hk = "honest" if exit_kind == "sell" else "honest_hold"
    G.RULES[0] = F.TOUCH
    touch = figure(adapter(tape), exit_kind)
    G.RULES[0] = F.HONEST
    checks = FD.gate(honest)
    drop = lambda f: {k: f[k] for k in ("n", "outcomes", "roi", "t", "halves", "without_best")}
    return dict(label=label, rules=F.VERSION, checked_at=(now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds"),
                exit=exit_kind, honest=dict(drop(honest), confirmed=sum(1 for r in rows if r.get("confirmed", r.get(hk) is not None)
                                                                         and r.get(hk) is not None)),
                page=dict(n=page["n"], roi=page["roi"]),
                note_touch=dict(n=touch["n"], roi=touch["roi"]),        # internal note only: never the gate, never on a page
                honest_positive=bool(honest["n"] and honest["roi"] is not None and honest["roi"] > 0),
                checks=checks, evidence=bool(checks) and all(checks.values()), waiver=None)


def load(path=PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return dict(rules=F.VERSION, built=BUILT, lanes={})


def check(keys=(), tape=None, path=PATH, now=None, log=print):
    """Grade every Production lane, every lane already on record and `keys`; keep each lane's waiver; write the record."""
    import fillsim_tape as T
    tape = tape or T.settled_tape
    blob = load(path)
    live = production_lanes()
    for key in sorted(set(live) | set(blob["lanes"]) | set(keys)):
        try:
            rec = grade(key, tape, live.get(key) or (blob["lanes"].get(key) or {}).get("label"), now)
        except Exception as e:                                  # one lane's data must not stop the others
            log(f"{key}: FAILED {type(e).__name__}: {e}")
            continue
        if rec is None:
            log(f"{key}: no grader")
            continue
        rec["waiver"] = (blob["lanes"].get(key) or {}).get("waiver")
        blob["lanes"][key] = rec
        log(line(key, rec, key in live))
    blob.update(rules=F.VERSION, built=BUILT, updated=(now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds"))
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return blob


# ---------------------------------------------------------------- the rule
def verdict(rec):
    """(passes, [reasons it fails]) for one lane's record."""
    if not rec:
        return False, ["no gate record: run `python3 promotion_gate.py check <lane>`"]
    why = []
    if rec.get("rules") != F.VERSION:
        why.append(f"graded under {rec.get('rules')}, not {F.VERSION}")
    if not rec.get("honest_positive"):
        h = rec.get("honest") or {}
        why.append("honest return is not positive (" + ("no entry survives" if not h.get("n") else f"{h['roi'] * 100:+.1f}% on {h['n']}") + ")")
    w = rec.get("waiver")
    waived = isinstance(w, dict) and all(w.get(k) for k in ("by", "on", "why"))
    if not rec.get("evidence") and not waived:
        fails = [k for k, v in (rec.get("checks") or {}).items() if not v]
        why.append("evidence test: " + ("; ".join(fails) if fails else "no settled bet") + " (no waiver on record)")
    return not why, why


def verify(blob=None, lanes=None, feeds=None):
    """Every reason the gate refuses the current code: [(lane or file, reason)]. Empty = the gate holds."""
    blob = load() if blob is None else blob
    lanes = production_lanes() if lanes is None else lanes
    out = [(f, "a Production feed or module the promotion gate does not know: register it in promotion_gate.py") for f in
           (unknown_feeds() if feeds is None else feeds)]
    for key in sorted(lanes):
        if key in GRANDFATHERED:
            continue
        ok, why = verdict((blob.get("lanes") or {}).get(key))
        out += [(key, w) for w in why] if not ok else []
    return out


def _pc(x):
    return "-" if x is None else f"{x * 100:+.1f}%"


def line(key, rec, live):
    ok, why = verdict(rec)
    h = rec["honest"]
    where = "Production" + (" (grandfathered)" if key in GRANDFATHERED else "") if live else "Sandbox"
    return (f"{key[:38]:38} {where[:26]:26} page {_pc(rec['page']['roi']):>8} ({rec['page']['n']:>3})  honest {_pc(h['roi']):>8} ({h['n']:>3}, "
            f"{h.get('confirmed', h['n']):>3} confirmed, {h['outcomes']:>2} outcomes, score {h['t'] if h['t'] is not None else '-'})  " + ("PASSES" if ok else "FAILS: " + " | ".join(why)))


def status(blob=None):
    blob = load() if blob is None else blob
    live = production_lanes()
    rows = sorted(blob["lanes"].items(), key=lambda kv: (kv[0] not in live, kv[0]))
    return "\n".join(line(k, r, k in live) for k, r in rows) or "no lane on record"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd == "check":
        check(argv[1:])
        return 0
    if cmd == "verify":
        bad = verify()
        for key, why in bad:
            print(f"REFUSED {key}: {why}")
        print("promotion gate: " + ("holds" if not bad else f"{len(bad)} problem(s)"))
        return 1 if bad else 0
    print(status())
    return 0


if __name__ == "__main__":
    sys.exit(main())
