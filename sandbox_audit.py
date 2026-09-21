#!/usr/bin/env python3
"""sandbox_audit.py — an independent check that the Sandbox record is right.

A wrong record is worse than no record: it gets believed. The tracker writes the ledger and
this reads it back, recomputing everything it can from first principles and asking the venues
again, so an error in the tracker cannot also be an error in the check. It never writes the
ledger; it runs with read-only permissions in its own workflow.

Checks, each an ERROR (fails the run) unless marked:

  bets        every settled bet's P/L follows from its price and stake; won/lost follows from
              pick against result; no duplicate ids; a bet's price sits in its domain's band
              and equals its side's ask; nothing counted was logged at or after the start.
  records     every pair's record recomputed straight from its raw bets, independently of the
              tracker's own assess(), and required to match it exactly.
  production  the Production list agrees three ways: the stages file, the hand-kept list in
              sandbox_track, and the published feed. No eliminated or disconnected pair in it,
              and no open lead belonging to a pair that is not.
  combos      every basket holds the legs its name says.
  settlement  a sample of settled bets asked of the venue again; the stored result must match.
  fresh       the ledger was graded recently. Two missed tracker runs is an ERROR: nothing is
              being settled, so every other check here is reading a record that stopped.
  stale       a bet open two days past its start. An ERROR only if the venue went final BEFORE
              the ledger's last grading run, so the grader had its chance and missed it. A
              venue still pending is a WARNING (the venue is late); so is one that went final
              after the last run (the next run settles it). Kalshi took 2.4 days to settle WTI
              on 2026-09-18 and finalised it eight minutes after a grading run — a check that
              could not tell those apart called a healthy grader broken.
  copy        no public file uses the phrases the public pages are kept free of.

Usage:  python3 sandbox_audit.py [--no-network] [--sample N]
Writes GitHub Actions annotations and a run summary when run in Actions. Exits 1 on any ERROR.
"""
import argparse
import base64
import collections
import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import sandbox_build as B
import sandbox_sources as S
import sandbox_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(ROOT, "data", "production_leads.json")
STALE_H = 48                     # open this long past the start, the venue is asked
FRESH_WARN_H = 4.5               # the tracker runs every 3h; one late run is a warning
FRESH_ERR_H = 6.5                # two missed runs: the grader has stopped
PNL_TOL = 0.011                  # stored P/L is rounded to the cent
PRICE_TOL = 0.0051               # a logged price and its side's ask may differ by rounding

# The phrases the public pages must never contain. Stored encoded so that this file, which is
# itself public, does not print them in the clear.
_COPY = base64.b64decode(
    "XGJib3RzP1xifFxidHJhZCg/OmVzP3xpbmcpIGZyb21cYnxcYm1vbmV5IGZvbGxvd3NcYnxcYm5vdGhpbmcgdHJh"
    "ZGVzXGJ8XGJub3QgdHJhZGVkXGJ8XGJwbGFjZWFibGVcYnxcYmFybWVkXGJ8XGJyZWFsIG1vbmV5XGJ8XGJsaXZl"
    "IG1vbmV5XGJ8XGJ0aGUgYm90XGJ8XGJmb2xsb3dzIHByb2R1Y3Rpb25cYg==").decode()
# A phrase wrapped across a line — "real" at the end of one comment line, "money" at the
# start of the next — reads the same to a visitor, so the gap between words may be any run
# of whitespace and comment markers, and files are scanned whole, not line by line. The
# first version matched a literal space and missed exactly such a wrapped phrase.
COPY_RE = re.compile(_COPY.replace(" ", r"[\s#/*]+"), re.I)
# An internal function name is not copy. It is exempt only where it is plainly an identifier.
# Spelled in two halves for the same reason the patterns are encoded.
_FN = "place" + "able"
_IDENT = re.compile(rf"\bdef {_FN}\b|\b{_FN}\(|\.{_FN}\b")
COPY_TYPES = (".py", ".yml", ".yaml", ".sh", ".md", ".html", ".txt")
# data/ is public too, but most of it is text the venues and tipsters wrote, which is not ours
# to police. These two carry prose this repository writes itself (stage reasons, lead routes).
COPY_DATA = ("data/stages.json", "data/production_leads.json")


class Report:
    def __init__(self):
        self.errors, self.warnings, self.passed = [], [], []

    def error(self, check, msg):
        self.errors.append((check, msg))

    def warn(self, check, msg):
        self.warnings.append((check, msg))

    def ok(self, check, msg):
        self.passed.append((check, msg))


def _dt(x):
    try:
        v = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _resolve(q):
    v, mid = q.get("venue"), q["market_id"]
    if v == "combo":
        return S.resolve_combo(q.get("legs") or [])
    return (S.resolve_kalshi(mid) if v == "kalshi"
            else S.resolve_kalshi_market(mid) if v == "kalshi_binary"
            else S.resolve_polymarket_us(mid) if v == "polymarket_us"
            else S.resolve_polymarket(mid))


def check_bets(d, rep):
    qs = T.all_bets(d)
    dup = [i for i, n in collections.Counter(q.get("id") for q in qs).items() if n > 1]
    for i in dup:
        rep.error("bets", f"duplicate quote id {i}")
    bad = 0
    for q in qs:
        st, tag = q.get("status"), q.get("id")
        if not q.get("bet"):
            if st in ("won", "lost"):
                rep.error("bets", f"{tag}: a non-bet is marked {st}")
                bad += 1
            continue
        p, stake = q.get("price"), q.get("stake")
        if stake != T.STAKE:
            rep.error("bets", f"{tag}: stake {stake}, not {T.STAKE}")
            bad += 1
        lo, hi = T.price_band(q.get("sport"))
        if p is None or not lo <= p <= hi:
            rep.error("bets", f"{tag}: price {p} outside the {lo}-{hi} band")
            bad += 1
            continue
        side = {"a": q.get("price_a"), "b": q.get("price_b"), "draw": q.get("price_draw")}.get(q.get("pick"))
        if side is not None and abs(side - p) > PRICE_TOL:
            rep.error("bets", f"{tag}: logged at {p} but its side's ask was {side}")
            bad += 1
        if st == "won" and abs(q["pnl"] - round(stake * (1.0 / p - 1.0), 2)) > PNL_TOL:
            rep.error("bets", f"{tag}: won, P/L {q['pnl']} should be {round(stake * (1.0 / p - 1.0), 2)}")
            bad += 1
        elif st == "lost" and abs(q["pnl"] + stake) > PNL_TOL:
            rep.error("bets", f"{tag}: lost, P/L {q['pnl']} should be {-stake}")
            bad += 1
        elif st == "void" and abs(q.get("pnl") or 0) > 0.001:
            rep.error("bets", f"{tag}: void but carries P/L {q['pnl']}")
            bad += 1
        if st in ("won", "lost"):
            if q.get("result") is None or not q.get("settled"):
                rep.error("bets", f"{tag}: {st} with no result or settle time")
                bad += 1
            elif (q.get("pick") == q.get("result")) != (st == "won"):
                rep.error("bets", f"{tag}: pick {q.get('pick')}, result {q.get('result')}, but marked {st}")
                bad += 1
        # A late quote is not a prediction. One that was voided for it is correctly handled.
        lg, sa = _dt(q.get("logged")), _dt(q.get("start"))
        if st != "void" and lg and sa and lg >= sa:
            rep.error("bets", f"{tag}: logged {q['logged'][:16]}, at or after its start {str(q['start'])[:16]}")
            bad += 1
    if not bad and not dup:
        n = sum(1 for q in qs if q.get("bet"))
        rep.ok("bets", f"{len(qs):,} quotes, {n:,} bets: P/L, status, prices and timing all consistent")


def check_records(d, st, rep):
    """Recount every pair from its raw bets, without assess(), and compare."""
    rows = B.pair_list(d, st)
    n = 0
    for r in rows:
        name, sport = r["name"], r["sport"]
        if sport in S.DAY_CLUSTERED:
            continue                  # unit-collapsed by assess(); its bets are checked above
        key = f"{name}|{sport}"
        pair = (st.get("pairs") or {}).get(key) or {}
        since = (None if r["v"] == "retired"
                 else T.qa_since(pair, sport, key) if pair.get("stage") == "production"
                 else pair.get("since"))
        raw = [q for q in T.all_bets(d) if q["source"] == name and q["sport"] == sport
               and q.get("bet") and q["status"] in ("won", "lost")
               and (q.get("venue") or "polymarket") in T.TRADEABLE_VENUES
               and (since is None or q["logged"] >= since)]
        a = T.assess(d, name, sport, since=since, venues=T.TRADEABLE_VENUES)
        won, exp = sum(1 for q in raw if q["status"] == "won"), sum(q["price"] for q in raw)
        if (len(raw), won) != (a["n"], a["won"]) or abs(exp - a["expected"]) > 1e-6:
            rep.error("records", f"{key}: raw bets say {won}/{len(raw)} v {exp:.2f} priced, "
                                 f"the page says {a['won']}/{a['n']} v {a['expected']:.2f}")
        n += 1
    shown = {(r["name"], r["sport"]) for r in rows}
    settled = [q for q in T.all_bets(d) if q.get("bet") and q["status"] in ("won", "lost")]
    in_sec = sum((r["a"].get("n_bets") or r["a"]["n"]) for r in rows)
    outside = sum(1 for q in settled if (q["source"], q["sport"]) not in shown
                  or (q.get("venue") or "polymarket") not in T.TRADEABLE_VENUES)
    # The reconciliation line's remainder is floored at zero on the page, which would hide a
    # double count. Unfloored, a negative number means some bet is counted twice.
    if len(settled) - in_sec - outside < 0:
        rep.error("records", f"bets counted twice: {in_sec:,} in the sections + {outside:,} outside "
                             f"is more than the {len(settled):,} settled")
    if not any(c == "records" for c, _ in rep.errors):
        rep.ok("records", f"{n} pair records recomputed from raw bets match the page exactly")


def check_production(d, st, rep):
    prod = {k for k, v in (st.get("pairs") or {}).items() if v.get("stage") == "production"}
    listed = set(T.PAIR_OVERRIDES)
    try:
        feed = json.load(open(FEED))
    except (OSError, ValueError) as e:
        rep.error("production", f"the Production feed cannot be read: {e}")
        return
    published = set(feed.get("pairs") or {})
    if prod != listed:
        rep.error("production", f"the stages file and the hand-kept list disagree: only in stages "
                                f"{sorted(prod - listed)}, only in the list {sorted(listed - prod)}")
    if published != prod:
        rep.error("production", f"the feed and the stages file disagree: only in the feed "
                                f"{sorted(published - prod)}, only in stages {sorted(prod - published)}")
    for k in prod:
        s, sp = k.split("|")
        if (s, sp) in S.ELIMINATED:
            rep.error("production", f"{k} is eliminated but in Production")
        m = S.SOURCES.get(s) or {}
        if not m.get("connected") or sp not in (m.get("sports") or []):
            rep.error("production", f"{k} is in Production but not connected for {sp}")
    stray = [l for l in (feed.get("leads") or {}).values()
             if l.get("status") == "pending" and l.get("pair") not in prod]
    for l in stray:
        rep.error("production", f"an open lead belongs to {l.get('pair')}, which is not in Production: "
                                f"{l.get('headline')} {str(l.get('kickoff'))[:16]}")
    if not any(c == "production" for c, _ in rep.errors):
        rep.ok("production", f"stages, hand-kept list and feed agree on {len(prod)} pairs; "
                             f"every open lead belongs to one of them")


def check_combos(d, rep):
    qs = [q for q in d["quotes"] if q.get("sport") == "tennis_combo"]
    for q in qs:
        legs = q.get("legs") or []
        want = int(q["market_id"][5]) if str(q["market_id"]).startswith("combo") else None
        if not legs or want != len(legs):
            rep.error("combos", f"{q['id']}: named for {want} legs, holds {len(legs)}")
    if not any(c == "combos" for c, _ in rep.errors):
        rep.ok("combos", f"{len(qs)} baskets hold the legs their names say")


def check_settlement(d, rep, sample):
    """Ask the venues again. The stored result must be the venue's result."""
    by = collections.defaultdict(list)
    for q in d["quotes"]:
        if q.get("bet") and q["status"] in ("won", "lost") and q.get("venue") in (
                "kalshi", "kalshi_binary", "polymarket_us", "combo"):
            by[q["venue"]].append(q)
    rng = random.Random(datetime.now(timezone.utc).strftime("%Y%m%d%H"))
    picked = []
    for v, qs in by.items():
        recent = sorted(qs, key=lambda q: q.get("settled") or "", reverse=True)[:400]
        picked += rng.sample(recent, min(sample, len(recent)))
    match = gone = 0
    for q in picked:
        r = _resolve(q)
        if r is None:
            gone += 1
        elif r == q["result"]:
            match += 1
        else:
            rep.error("settlement", f"{q['id']} ({q['venue']}): stored {q['result']}, the venue now says {r}")
    if gone:
        rep.warn("settlement", f"{gone} of {len(picked)} sampled bets no longer answer at the venue")
    if not any(c == "settlement" for c, _ in rep.errors):
        rep.ok("settlement", f"{match} of {len(picked)} settled bets asked again: every one matches the venue")


def _final_at(q):
    """When the venue's result became final, where the venue says so; else None.

    Kalshi's yes/no markets carry an updated_time, which for a determined market is the
    determination. Other venues do not say, and the caller treats that as unknown.
    """
    if q.get("venue") != "kalshi_binary":
        return None
    try:
        m = (S._get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{q['market_id']}",
                    tries=2, timeout=20) or {}).get("market") or {}
    except Exception:
        return None
    return _dt(m.get("updated_time"))


def check_fresh(d, rep, now=None):
    now = now or datetime.now(timezone.utc)
    last = _dt((d.get("meta") or {}).get("updated"))
    if last is None:
        rep.error("fresh", "the ledger carries no last-graded time")
        return
    age = (now - last).total_seconds() / 3600
    if age > FRESH_ERR_H:
        rep.error("fresh", f"the ledger was last graded {age:.1f}h ago — at least two tracker runs "
                           f"have been missed, so nothing is being settled")
    elif age > FRESH_WARN_H:
        rep.warn("fresh", f"the ledger was last graded {age:.1f}h ago; one tracker run looks late")
    else:
        rep.ok("fresh", f"the ledger was graded {age:.1f}h ago")


def check_stale(d, rep, network, now=None):
    now = now or datetime.now(timezone.utc)
    graded = _dt((d.get("meta") or {}).get("updated"))
    stale = [q for q in d["quotes"] if q.get("bet") and q["status"] == "open"
             and (_dt(q.get("start")) or now) < now - timedelta(hours=STALE_H)]
    if not stale:
        rep.ok("stale", f"no bet open {STALE_H}h past its start")
        return
    for q in stale:
        age = (now - _dt(q["start"])).total_seconds() / 3600
        r = _resolve(q) if network else None
        if r is None:
            rep.warn("stale", f"{q['id']}: open {age:.0f}h past the start; the venue has no final "
                              f"result yet{'' if network else ' (not asked: --no-network)'}")
            continue
        final = _final_at(q)
        if final and graded and final < graded:
            rep.error("stale", f"{q['id']}: the venue went final ({r}) at {final:%Y-%m-%d %H:%M}Z, "
                               f"before the last grading run at {graded:%H:%M}Z, and the ledger still "
                               f"has it open — the grader missed it")
        elif final and graded:
            rep.warn("stale", f"{q['id']}: the venue went final ({r}) at {final:%Y-%m-%d %H:%M}Z, after "
                              f"the last grading run at {graded:%H:%M}Z; the next run settles it")
        elif age > 24 * 7:
            rep.error("stale", f"{q['id']}: the venue is final ({r}) and the ledger has had it open "
                               f"{age / 24:.0f} days — far past any delay the grader could have")
        else:
            rep.warn("stale", f"{q['id']}: the venue is final ({r}); it cannot say when, so if this "
                              f"is still here next audit the grader has missed it")


def check_copy(rep):
    try:
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError) as e:
        rep.warn("copy", f"could not list the repository's files: {e}")
        return
    hits = 0
    for f in files:
        if f not in COPY_DATA and (not f.endswith(COPY_TYPES) or f.startswith("data/")):
            continue
        try:
            text = open(os.path.join(ROOT, f), errors="replace").read()
        except OSError:
            continue
        lines = text.splitlines()
        for m in COPY_RE.finditer(text):
            i = text.count("\n", 0, m.start()) + 1
            line = lines[i - 1] if i <= len(lines) else ""
            # An internal function name, and nothing else guarded on its line, is not copy.
            if (f.endswith(".py") and m.group(0).lower() == _FN and _IDENT.search(line)
                    and not COPY_RE.search(_IDENT.sub("", line))):
                continue
            rep.error("copy", f"{f}:{i} uses a phrase the public pages are kept free of")
            hits += 1
    if not hits:
        rep.ok("copy", "no public file uses a phrase the public pages are kept free of")


def emit(rep):
    """Print, annotate for GitHub Actions, and write the run summary."""
    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    for c, m in rep.errors:
        print(f"::error title=Sandbox audit: {c}::{m}" if gha else f"  ERROR [{c}] {m}")
    for c, m in rep.warnings:
        print(f"::warning title=Sandbox audit: {c}::{m}" if gha else f"  warn  [{c}] {m}")
    for c, m in rep.passed:
        print(f"  ok    [{c}] {m}")
    verdict = (f"{len(rep.errors)} error(s)" if rep.errors else "clean") + (
        f", {len(rep.warnings)} warning(s)" if rep.warnings else "")
    print(f"\nSandbox audit: {verdict}")
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(f"## Sandbox audit — {verdict}\n\n| | Check | Detail |\n|---|---|---|\n")
            for mark, rows in (("❌", rep.errors), ("⚠️", rep.warnings), ("✅", rep.passed)):
                for c, m in rows:
                    f.write(f"| {mark} | {c} | {m.replace('|', '/')} |\n")


def run(network=True, sample=25):
    d, st, rep = T.load(), T.load_stages(), Report()
    check_bets(d, rep)
    check_records(d, st, rep)
    check_production(d, st, rep)
    check_combos(d, rep)
    check_fresh(d, rep)
    if network:
        check_settlement(d, rep, sample)
    check_stale(d, rep, network)
    check_copy(rep)
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-network", action="store_true", help="skip every check that asks a venue")
    ap.add_argument("--sample", type=int, default=25, help="settled bets re-asked per venue")
    args = ap.parse_args()
    rep = run(network=not args.no_network, sample=args.sample)
    emit(rep)
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
