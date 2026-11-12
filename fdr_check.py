"""The Sandbox-wide false-discovery check (2026-11-12, Olu: too many tests, too few bets). Research tooling, read-only, no network.

We try many rules and judge the survivors on 10 to 30 bets. With that many tries some will look good by luck alone. This asks, over
EVERY lane the ledgers hold (active, retired, tipster or rule), how many clear once luck across all of them is priced in.

  record      one lane (and scope): each settled bet's return per $1 after fees, with the outcome it belongs to. A day is one
              outcome (a crypto day, a commodity close, a slate); a Trump-mention week is one outcome.
  t           mean return over its standard error, the larger of the plain one and the one that lets a whole outcome move together
              (the pages' rule), and never under the spread a fair lane of that shape would have (fair_var). p = one-sided
              Student t on (outcomes - 1) degrees of freedom: few outcomes, fatter tails.
  tested      a lane counts as tested once it has MIN_BETS settled bets on MIN_CLUSTERS outcomes (Olu's review point).
  BH          Benjamini-Hochberg over every tested lane: q = the share of false finds to expect among lanes at least this good.
  shuffled    the null made by flipping the sign of each outcome's result at random (the same flip for one calendar day in every
              lane, so lanes that share a day stay tied), 2,000 times. adj p = how often the BEST lane of a shuffled Sandbox beats
              this lane's t. Nothing but luck is in a shuffled Sandbox.

A lane re-graded by fillsim (fillsim_regrade.py --json) is read at its honest figure when --regrade is given: a lane with resting
orders or sells is not judged on a fill it could not have had.

Also here: the family counts (how many variants each idea tried), promotion shrinkage (the record before a lane went live v its
live record after) and the bets a real edge needs (power). Run: python3 fdr_check.py [--regrade file.json] [--json out.json]
"""
import datetime as dt
import json
import math
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MIN_BETS, MIN_CLUSTERS = 10, 3
DRAWS, SEED = 2000, 20261112
ALPHA = 0.10            # the false-discovery rate the report reads q against


def load(name):
    with open(os.path.join(ROOT, "data", name + ".json")) as f:
        return json.load(f)


# ---------------------------------------------------------------- the maths
def _betacf(a, b, x):
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h


def betai(a, b, x):
    """The regularised incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1 - x) / b


def t_sf(t, df):
    """P(T >= t) for Student's t on df degrees of freedom."""
    if df <= 0:
        return 1.0
    half = 0.5 * betai(df / 2.0, 0.5, df / (df + t * t))
    return half if t >= 0 else 1.0 - half


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def groups(vals):
    """{outcome: (sum, sum of squares, count)} of [(value, outcome)]."""
    g = {}
    for v, c in vals:
        s, q, k = g.get(c, (0.0, 0.0, 0))
        g[c] = (s + v, q + v * v, k + 1)
    return g


def fair_var(vals):
    """The spread one bet's return has when the lane is exactly fair: the mean size of a win.

    A bet that returns +w when it wins and -1 when it loses is fair at a win chance of 1 / (1 + w), and its variance there is w.
    This is the floor under every standard error here. Without it a favourites lane that has not lost yet (15 wins of 15 at 93c)
    shows almost no spread in its own results and an absurd t; at 93c, 15 of 15 happens one time in three."""
    wins = [v for v, _c in vals if v > 0]
    return sum(wins) / len(wins) if wins else 0.0


def t_of(g, n, sign=None, floor=0.0):
    """(mean, t) from grouped sums; `sign` {outcome: +1 | -1} flips whole outcomes (the shuffled null); `floor` = fair_var."""
    tot = sum((sign[c] if sign else 1) * s for c, (s, _q, _k) in g.items())
    mean = tot / n
    iid = max(max(sum(q for _s, q, _k in g.values()) - n * mean * mean, 0.0) / max(n - 1, 1), floor) / n
    clu = sum(((sign[c] if sign else 1) * s - k * mean) ** 2 for c, (s, _q, k) in g.items()) / (n * n)
    se = math.sqrt(max(iid, clu))
    return mean, (mean / se if se > 1e-12 else 0.0)


_MON = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}


def when(cluster):
    """A sort key that puts outcomes in time order: an ISO day or week as it is, a Kalshi date token (26NOV16) as its date."""
    m = re.search(r"(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})", str(cluster))
    return f"20{m.group(1)}-{_MON[m.group(2)]:02d}-{m.group(3)}" if m else str(cluster)


def lane_stats(vals):
    """One lane's read: n, outcomes, mean return, t, one-sided p, both halves, and whether one outcome carries it."""
    n = len(vals)
    g = groups(vals)
    out = dict(n=n, clusters=len(g), roi=None, t=None, p=None, tested=False, halves=None, without_best=None)
    if not n:
        return out
    mean, t = t_of(g, n, floor=fair_var(vals))
    out.update(roi=round(mean, 4), t=round(t, 2))
    if n < MIN_BETS or len(g) < MIN_CLUSTERS:
        return out
    order = sorted(g, key=when)
    k = len(order) // 2
    half = lambda cs: (sum(g[c][0] for c in cs) / sum(g[c][2] for c in cs)) if cs else None
    best = max(order, key=lambda c: g[c][0])
    rest_n = n - g[best][2]
    out.update(tested=True, p=t_sf(t, len(g) - 1), halves=(round(half(order[:k]), 4), round(half(order[k:]), 4)),
               without_best=round((sum(s for s, _q, _k in g.values()) - g[best][0]) / rest_n, 4) if rest_n else None)
    return out


def bh(ps):
    """Benjamini-Hochberg q-values, in the order given."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    q, prev = [0.0] * m, 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, ps[i] * m / rank)
        q[i] = prev
    return q


def max_t_null(recs, draws=DRAWS, seed=SEED):
    """The best t of a shuffled Sandbox, `draws` times: each outcome's sign flipped at random, one flip per outcome id across lanes."""
    rng = random.Random(seed)
    gs = [(groups(r["vals"]), len(r["vals"]), fair_var(r["vals"])) for r in recs]
    keys = sorted({c for g, _n, _f in gs for c in g})
    out = []
    for _ in range(draws):
        sign = {c: (1 if rng.random() < 0.5 else -1) for c in keys}
        out.append(max(t_of(g, n, sign, f)[1] for g, n, f in gs))
    return sorted(out)


def adj_p(t, null):
    """The share of shuffled Sandboxes whose best lane reaches t."""
    lo, hi = 0, len(null)
    while lo < hi:
        mid = (lo + hi) // 2
        if null[mid] < t:
            lo = mid + 1
        else:
            hi = mid
    return (len(null) - lo + 1) / (len(null) + 1)


# ---------------------------------------------------------------- the records
def iso_week(day):
    y, w, _ = dt.date.fromisoformat(day[:10]).isocalendar()
    return f"{y}-W{w:02d}"


def sandbox_records():
    """{(source, scope): [(return, day)]} for every settled bet in the Sandbox ledger, after the venue's taker fee."""
    import sandbox_track as T
    out = {}
    for q in load("sandbox_ledger")["quotes"]:
        if not q.get("bet") or q.get("status") not in ("won", "lost", "settled") or not isinstance(q.get("price"), (int, float)):
            continue
        day = str(q.get("start") or q.get("date") or q.get("logged"))[:10]
        out.setdefault((q["source"], q["sport"]), []).append((T.pnl_after_fee(q) / T.STAKE, day))
    return out


FAMILIES = (                                        # (family, test on src, lane, scope) first match wins
    ("Tipsters and outside models", lambda s, l, c, tip: tip),
    ("Crypto price bands", lambda s, l, c, tip: s == "sandbox" and (c or "").startswith("crypto")),
    ("Commodity and economic ladders", lambda s, l, c, tip: (s == "sandbox" and (c or "").startswith("commod")) or s in ("daily", "finance_nc")),
    ("Soccer form and price rules (tracker)", lambda s, l, c, tip: s == "sandbox" and (c or "").startswith("soccer")),
    ("Tennis, fights and US sports bands (tracker)", lambda s, l, c, tip: s == "sandbox"),
    ("Soccer total-goals label rules", lambda s, l, c, tip: s in ("soccer_rules_ledger.json", "contender_overs_ledger.json", "sa_o15_ledger.json")),
    ("Soccer team-total label rules", lambda s, l, c, tip: s == "soccer_team_rules_ledger.json"),
    ("NBA label and value rules", lambda s, l, c, tip: s in ("nba_rules_ledger.json", "nba_value_ledger.json")),
    ("NFL team totals", lambda s, l, c, tip: s in ("nfl_tt_ledger.json", "nfl_tt_main1_ledger.json")),
    ("Tennis totals", lambda s, l, c, tip: s == "tennis_totals_ledger.json"),
    ("Culture (mentions, films, albums)", lambda s, l, c, tip: s == "culture" or "album" in l or "mentions" in l),
    ("NBA win margin", lambda s, l, c, tip: "nba_wm" in l or "nba_winmargin" in l),
    ("Goalless dips and cheap NO (soccer in-play)", lambda s, l, c, tip: "dip" in l or "o35" in l),
    ("Cheap side with early sells", lambda s, l, c, tip: True),
)


def family_of(src, lane, scope, tipster=False):
    return next(name for name, test in FAMILIES if test(src, lane, scope, tipster))


# Variants an idea tried in RESEARCH, before (or instead of) a lane. Hand-entered from the pre-registration docs and research notes
# named in `source`; "built" is the lanes that came out of it. They are context for the report, not part of the lane test.
RESEARCH = (
    dict(idea="Kalshi Invest big moves (fade or follow a drop or jump)", tried=648, built=4, cleared=0, source="docs/invest_bigmove/PREREGISTRATION.md, table.md"),
    dict(idea="Rebound after a slide", tried=56, built=0, cleared=0, source="Trading page research, Nov 11"),
    dict(idea="NBA win margin v5 grid (12 YES and 9 NO cells)", tried=21, built=2, cleared=0, source="docs/prereg_nba_wm_v5_2026-11-11.md"),
    dict(idea="Soccer spread, correct score and NO shapes", tried=8118, built=1, cleared=0, source="soccer market breakdown, Nov 7-8 (11 candidates, none held)"),
    dict(idea="Streak and lead rules (over 1.5, team to score 2+)", tried=655, built=2, cleared=0, source="leads profitability study, Sep 12"),
    dict(idea="Nasdaq and gold opening-range breakouts", tried=40, built=6, cleared=0, source="ORB research, Oct 18; lanes retired Nov 11"),
    dict(idea="15-minute markets: ask calibration by minute and price", tried=49, built=3, cleared=0, source="15-Minute Swing research, Nov 9"),
    dict(idea="Soccer total-goals label angles", tried=21, built=21, cleared=None, source="soccer_rules.py (groups A, B, C)"),
    dict(idea="Cheap side with split sells, by Kalshi category", tried=26, built=9, cleared=None, source="cheap-side standard, Oct 27 (9 built, about 17 rejected)"),
)


def universe(regrade=None):
    """Every lane record: dict(key, src, lane, scope, family, stage, basis, vals [(return, outcome)])."""
    import leaderboard as LB
    stage = LB.lane_stages()
    recs = {}
    for (src, scope), vals in sandbox_records().items():
        b = dict(src="sandbox", lane=src, scope=scope)
        recs[("sandbox", src, scope)] = dict(src="sandbox", lane=src, scope=scope, stage=stage(b), basis="page", vals=vals,
                                             tipster=LB.is_tipster(src) or (_kind(src) not in (None, "Rule")))
    for b in LB.collect_bets()[0]:
        if b["src"] == "sandbox" or b["profit"] is None:
            continue
        k = (b["src"], b["lane"], b.get("scope"))
        r = recs.setdefault(k, dict(src=b["src"], lane=b["lane"], scope=b.get("scope"), stage=stage(b), basis="page", vals=[], tipster=False))
        r["vals"].append((b["profit"], iso_week(b["day"]) if b["src"] == "culture" else b["day"]))
    for name, L in ((regrade or {}).get("lanes") or {}).items():
        if "rows" not in L or name.endswith("_bot") or name == "top5_dip_live":
            continue                                        # the "as the follower bid it" rows are a check on the simulator, not a lane
        key = "honest" if L["exit"] == "sell" else "honest_hold"
        vals = [(r[key], str(r["cluster"])) for r in L["rows"] if r[key] is not None]
        old = next((k for k in recs if k[0] == "contract" and (k[1] == name or k[1] == name + "_ledger.json"
                                                               or (name.startswith("o35_cheap_no_v4") and k[1] == "o35_cheap_no"))), None)
        st = recs.pop(old)["stage"] if old else (None if L.get("retired") else "Production" if L.get("live_lane") and name != "o35_cheap_no_v4" else "Sandbox")
        if name == "mentions_dip_hold":
            vals = [(v, c) for v, c in vals]                # its outcome is already the mention week (the event)
        recs[("fillsim", name, None)] = dict(src="fillsim", lane=name, scope=None, stage=st, basis="honest", vals=vals, tipster=False,
                                             label=L["label"])
    out = []
    for k, r in sorted(recs.items(), key=lambda kv: str(kv[0])):
        r["key"] = "|".join(str(x) for x in k[1:] if x)
        r["family"] = family_of(r["src"], r["lane"], r["scope"], r["tipster"])
        out.append(r)
    return out


def _kind(src):
    import sandbox_sources as S
    return (S.SOURCES.get(src) or {}).get("kind")


# ---------------------------------------------------------------- promotion shrinkage and power
def shrinkage(recs):
    """For every lane that went live: its paper record BEFORE the live date v its live record after. [dict(pair, pre, post)]."""
    lr = load("live_record")
    by = {(r["lane"], r["scope"]): r for r in recs if r["src"] == "sandbox"}
    rules = {r["lane"].upper(): r for r in recs if r["src"] in ("soccer_rules_ledger.json", "soccer_team_rules_ledger.json")}
    pairs = {k: v["orders"] for k, v in lr["pairs"].items()}
    pairs.update(lr["pulled"])
    out = []
    for pair, orders in sorted(pairs.items()):
        src, _, scope = pair.partition("|")
        done = [o for o in orders if o.get("r") is not None and o.get("st") in ("won", "lost") and o["id"].partition(":")[2].startswith("KX")]
        if not done:
            continue
        start = min(o["ko"] for o in done)[:10]
        rec = by.get((src, scope)) or rules.get(src.split("_", 1)[-1].upper())
        if rec is None:
            continue
        pre = [v for v, c in rec["vals"] if c < start]
        if len(pre) < 5 or len(done) < 5:
            continue
        out.append(dict(pair=pair, live_from=start, pre_n=len(pre), pre=round(sum(pre) / len(pre), 4), post_n=len(done),
                        post=round(sum(o["r"] for o in done) / len(done), 4)))
    return out


def live_records():
    """[dict(key, kind, stats)] for every lane's LIVE record (data/live_record.json), an outcome being a kickoff day."""
    lr = load("live_record")
    sets = {k: v["orders"] for k, v in lr["pairs"].items()}
    sets.update(lr["pulled"])
    sets.update(lr["lanes"])
    out = []
    for key, orders in sorted(sets.items()):
        vals = [(o["r"], o["ko"][:10]) for o in orders if o.get("r") is not None and o.get("st") not in ("open", "unfilled", "unconfirmed")
                and (o["id"].startswith("KX") or o["id"].partition(":")[2].startswith("KX"))]
        if vals:
            out.append(dict(key=key, now=key in lr["pairs"] or key in lr["lanes"], vals=vals))
    return out


def power(edge, sd, n, z=2.0):
    """The chance a lane with a true `edge` per bet (returns spread `sd`) shows z or better after n independent bets."""
    return norm_sf(z - edge * math.sqrt(n) / sd)


def bets_needed(edge, sd, z=2.0, chance=0.8):
    """Independent bets for a true `edge` to clear z with that chance."""
    zb = next(x / 1000 for x in range(0, 4000) if norm_sf(-x / 1000) >= chance)
    return math.ceil(((z + zb) * sd / edge) ** 2)


def typical_sd(recs):
    """The median spread of one bet's return across tested lanes."""
    sds = []
    for r in recs:
        v = [x for x, _c in r["vals"]]
        if len(v) >= MIN_BETS:
            m = sum(v) / len(v)
            sds.append(math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1)))
    sds.sort()
    return sds[len(sds) // 2] if sds else None


# ---------------------------------------------------------------- the proposed promotion gate
GATE = dict(bets=30, outcomes=10, t=2.0)                # step 1, Sandbox -> probation (the report states step 2)


def gate(s):
    """A lane's record against step 1 of the proposed gate: {check: passed}. The pre-registration and baseline checks are not
    machine-readable and are left to the review."""
    if not s["n"]:
        return {}
    ok = s["tested"]
    return {"30+ bets": s["n"] >= GATE["bets"], "10+ outcomes": s["clusters"] >= GATE["outcomes"],
            "both halves up": bool(ok and s["halves"][0] > 0 and s["halves"][1] > 0),
            "up without its best outcome": bool(ok and s["without_best"] is not None and s["without_best"] > 0),
            "t of 2+": bool(s["t"] is not None and s["t"] >= GATE["t"])}


# ---------------------------------------------------------------- the check
def run(regrade=None, draws=DRAWS):
    recs = universe(regrade)
    for r in recs:
        r["stats"] = lane_stats(r["vals"])
    tested = [r for r in recs if r["stats"]["tested"]]
    qs = bh([r["stats"]["p"] for r in tested])
    null = max_t_null(tested, draws) if tested else []
    for r, q in zip(tested, qs):
        r["stats"].update(q=round(q, 4), adj_p=round(adj_p(r["stats"]["t"], null), 4))
    fam, pooled = {}, {}
    for r in recs:
        pooled.setdefault(r["family"], []).extend(r["vals"])
        r["stats"]["gate"] = gate(r["stats"])
        f = fam.setdefault(r["family"], dict(lanes=0, tested=0, active=0, raw=0, bh=0, shuffled=0, bets=0))
        s = r["stats"]
        f["lanes"] += 1
        f["bets"] += s["n"]
        f["active"] += r["stage"] is not None
        f["tested"] += s["tested"]
        f["raw"] += bool(s["tested"] and s["t"] >= 2)
        f["bh"] += bool(s["tested"] and s["q"] <= ALPHA)
        f["shuffled"] += bool(s["tested"] and s["adj_p"] <= ALPHA)
    for name, vals in pooled.items():                       # the whole idea as one record: every lane of the family pooled
        p = lane_stats(vals)
        fam[name].update(roi=p["roi"], t=p["t"], outcomes=p["clusters"])
    sd = typical_sd(recs)
    live = live_records()
    for r in live:
        r["stats"] = lane_stats(r["vals"])
    lt = [r for r in live if r["stats"]["tested"]]
    for r, q in zip(lt, bh([r["stats"]["p"] for r in lt])):
        r["stats"]["q"] = round(q, 4)
    return dict(live=[dict(key=r["key"], now=r["now"], **r["stats"]) for r in live],
                generated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), basis="honest where re-graded" if regrade else "page",
                lanes=len(recs), tested=len(tested), bets=sum(r["stats"]["n"] for r in recs),
                raw=sum(1 for r in tested if r["stats"]["t"] >= 2), by_chance=round(len(tested) * norm_sf(2.0), 1),
                bh=sum(1 for r in tested if r["stats"]["q"] <= ALPHA), shuffled=sum(1 for r in tested if r["stats"]["adj_p"] <= ALPHA),
                null_best_t=dict(median=null[len(null) // 2], p90=null[int(len(null) * 0.9)], p95=null[int(len(null) * 0.95)]) if null else None,
                families=fam, research=list(RESEARCH), shrinkage=shrinkage(recs), sd=sd,
                records=[dict({k: r[k] for k in ("key", "src", "lane", "scope", "family", "stage", "basis")}, label=r.get("label"), **r["stats"])
                         for r in recs])


def _pc(x):
    return "-" if x is None else f"{x * 100:+.1f}%"


def report(out):
    L = [f"{out['lanes']} lanes hold {out['bets']} settled bets ({out['basis']}). {out['tested']} have {MIN_BETS}+ bets on {MIN_CLUSTERS}+ outcomes.",
         f"t of 2 or better: {out['raw']} lanes. Luck alone would give about {out['by_chance']}.",
         f"Clear after Benjamini-Hochberg at {ALPHA:.0%}: {out['bh']}. Clear against the shuffled Sandbox at {ALPHA:.0%}: {out['shuffled']}.",
         f"The best lane of a shuffled Sandbox: t {out['null_best_t']['median']:.2f} typically, {out['null_best_t']['p90']:.2f} one time in ten.", "",
         f"{'family':46} {'lanes':>5} {'tested':>6} {'active':>6} {'t>=2':>5} {'BH':>3} {'shuf':>4} {'bets':>6} {'pooled':>8} {'t':>6}"]
    for name, f in sorted(out["families"].items(), key=lambda kv: -kv[1]["lanes"]):
        L.append(f"{name[:46]:46} {f['lanes']:>5} {f['tested']:>6} {f['active']:>6} {f['raw']:>5} {f['bh']:>3} {f['shuffled']:>4} {f['bets']:>6} "
                 f"{_pc(f['roi']):>8} {f['t']:>+6.2f}")
    L += ["", f"{'lane':44} {'stage':10} {'basis':6} {'n':>5} {'out':>4} {'return':>8} {'t':>6} {'p':>7} {'q':>6} {'adj p':>6}  halves / without best outcome"]
    rows = [r for r in out["records"] if r["tested"]]
    for r in sorted(rows, key=lambda r: r["p"]):
        if r["stage"] is None and r["t"] < 1.5:
            continue
        L.append(f"{r['key'][:44]:44} {str(r['stage'] or 'retired')[:10]:10} {r['basis']:6} {r['n']:>5} {r['clusters']:>4} {_pc(r['roi']):>8} {r['t']:>+6.2f} "
                 f"{r['p']:>7.4f} {r['q']:>6.3f} {r['adj_p']:>6.3f}  {_pc(r['halves'][0])} / {_pc(r['halves'][1])} / {_pc(r['without_best'])}")
    L += ["", "Step 1 of the proposed gate, active lanes (x = fails):"]
    for r in sorted((r for r in out["records"] if r["stage"] and r["n"] >= MIN_BETS), key=lambda r: (-sum(r["gate"].values()), -(r["t"] or 0))):
        fails = [k for k, v in r["gate"].items() if not v]
        L.append(f"  {r['key'][:40]:40} {r['stage']:10} {r['n']:>4} bets  {_pc(r['roi']):>8}  " + ("PASSES" if not fails else "x " + "; ".join(fails)))
    L += ["", f"{'LIVE record':44} {'n':>5} {'out':>4} {'return':>8} {'t':>6} {'p':>7} {'q':>6}"]
    for r in sorted((r for r in out["live"] if r["tested"]), key=lambda r: r["p"]):
        L.append(f"{(r['key'] + ('' if r['now'] else ' (pulled)'))[:44]:44} {r['n']:>5} {r['clusters']:>4} {_pc(r['roi']):>8} {r['t']:>+6.2f} {r['p']:>7.4f} {r['q']:>6.3f}")
    sh = out["shrinkage"]
    if sh:
        L += ["", f"{'went live':40} {'before: paper':>16} {'after: live':>16}"]
        for s in sorted(sh, key=lambda s: -s["pre"]):
            L.append(f"{s['pair'][:40]:40} {_pc(s['pre']):>9} ({s['pre_n']:>3}) {_pc(s['post']):>9} ({s['post_n']:>3})")
        wp = sum(s["pre"] * s["post_n"] for s in sh) / sum(s["post_n"] for s in sh)
        wl = sum(s["post"] * s["post_n"] for s in sh) / sum(s["post_n"] for s in sh)
        L.append(f"{'ALL (weighted by live bets)':40} {_pc(wp):>9}       {_pc(wl):>9} ({sum(s['post_n'] for s in sh):>3})")
    return "\n".join(L)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    regrade = None
    if "--regrade" in argv:
        with open(argv[argv.index("--regrade") + 1]) as f:
            regrade = json.load(f)
    out = run(regrade)
    print(report(out))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f:
            json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
