#!/usr/bin/env python3
"""production.py — the Production stage: the pairs put here by hand, and their bets.

    Sandbox -> Production (by hand)

A (source, sport) pair is IN PRODUCTION because it was put there BY HAND: listed in
sandbox_track.PAIR_OVERRIDES, on the record the Sandbox measured. Nothing promotes itself
(2026-09-18). A pair leaves the same way, or on its own when it stops working — no new bet in
STALE_DAYS, behind the prices it paid, or beaten by a blind rule on the same contests.

data/production_leads.json is the machine-readable feed. It has the Leads ledger's shape —
{"leads": {id: lead}, "updated_at", "board_built_at"} — so anything that reads one reads both:

  * every bet a Production pair logs AFTER it entered Production, and only bets the feed can
    express as a standard claim (sandbox_track.placeable): a soccer result (home, away or draw)
    on a Kalshi GAME market, or Yes on a soccer goals market, in a mapped league
  * and only with a VERIFIED kickoff (start_source "espn"). Kalshi publishes no kickoff and
    its estimate has been a day off both ways; a kickoff listed too late would publish a
    match already in play as upcoming. Held back and counted.
  * bet {"kind": "match_result", "side": "home" | "away" | "draw"} (home = the Kalshi event's first
    side, sandbox_sources.kalshi_sides), or {"kind": "total_gte", "n": 2} /
    {"kind": "team_gte", "n": 1 | 2, "team": ...} — the Leads board's own bet vocabulary
  * status pending / hit / miss / void from the Sandbox settlement
  * last_seen_at == board_built_at on every lead still open; a lead whose pair has left
    Production is dropped from the file, which reads as withdrawn

An empty feed is normal until the first pair arrives. This file only ever changes when the
tracker runs (every 3h).
"""
import datetime, html, json, os

import sandbox_sources as S
import sandbox_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(ROOT, "data", "production_leads.json")
KEEP_SETTLED_DAYS = 7          # settled leads stay in the feed this long, so results can be joined
STATUS = {"open": "pending", "won": "hit", "lost": "miss", "void": "void"}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def production_pairs(st):
    """{"source|sport": pair} for every pair in Production and trading."""
    return {k: p for k, p in (st.get("pairs") or {}).items()
            if p.get("stage") == "production" and p.get("ready_at")}


def entered_at(pair):
    """When the pair's Production record starts."""
    return pair.get("ready_at") or pair.get("promoted_at")


def route_label(pair):
    return f"moved by hand on {pair['by_hand']}" if pair.get("by_hand") else "moved by hand"


def _kickoff(q):
    dt = datetime.datetime.fromisoformat(str(q["start"]))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def start_verified(q):
    """Is this bet's start time a real start rather than an estimate?

    Kalshi publishes a DATE for a soccer fixture, not a kickoff, so soccer leads are held
    back until an ESPN fixture has confirmed the time — otherwise a bet could be published
    on a match already under way. Polymarket US publishes the match start itself, which is
    where the tennis lane's times come from.
    """
    if q.get("sport") in T.ROUTED_SPORTS:
        # Polymarket US publishes the contest's own start; a Kalshi row has one only once
        # something else has confirmed it (the tennis schedule, an ESPN fixture).
        return (q.get("venue") == "polymarket_us"
                or q.get("start_source") in T.VERIFIED_STARTS)
    return q.get("start_source") == "espn"


def lead_from_quote(q, pair_key, built):
    """One Sandbox bet as a feed lead."""
    ko = _kickoff(q)
    label = S.SOURCES.get(q["source"], {}).get("label", q["source"]).split(" (")[0]
    date = ko.date().isoformat()
    if q["sport"] in T.FEED_BETS:
        bet = dict(T.FEED_BETS[q["sport"]])
        home, away = q["espn_home"], q["espn_away"]
        if bet["kind"] == "team_gte":
            bet["team"] = q["team"]
            headline = f"{q['team']} to score {bet['n']}+"
        else:
            headline = "Over 1.5 goals"
    else:
        home, away = q["side_a"], q["side_b"]
        side = {"a": "home", "b": "away", "draw": "draw"}[q["pick"]]
        bet = {"kind": "match_result", "side": side}
        headline = "Draw" if side == "draw" else f"{home if side == 'home' else away} to win"
    # A sport with no league table to look the fixture up in carries the venue's own market
    # instead, so a follower buys the contract this bet was priced on rather than one found
    # by matching two player names across two sites.
    route = None
    if q["sport"] in T.ROUTED_SPORTS:
        # Kalshi lists a market per player inside one event, so backing either player is a
        # plain Yes on that player's market. Polymarket lists ONE market with two outcomes,
        # so the second player is the No side of it.
        route = {"venue": q["venue"], "market": q["market_id"],
                 "outcome": home if q["pick"] == "a" else away,
                 "outcome_side": "yes" if (q["pick"] == "a" or q["venue"] == "kalshi") else "no"}
    lead = {
        "id": f"{date}|{home}|{away}|{headline} · {label}",
        "date": date, "kickoff": ko.strftime("%Y-%m-%dT%H:%MZ"),
        "league": S.quote_league(q) or (S.SPORTS.get(q["sport"]) if q["sport"] in T.ROUTED_SPORTS else None),
        "match": f"{home} v {away}",
        "home": home, "away": away, "headline": headline,
        "bet": bet,
        "status": STATUS.get(q["status"], "void"),
        "first_seen": str(q["logged"])[:10],
        "source": q["source"], "sport": q["sport"], "pair": pair_key, "lane": "production",
        "sandbox_quote": q["id"], "price_at_log": q.get("price"), "edge_at_log": q.get("edge"),
    }
    # A model pair's claim is a PROBABILITY, and that is what a follower should judge today's
    # price against — not how far the price has drifted since the Sandbox wrote it down days
    # earlier. Two-way markets only: in a three-way one 1 - P(home) also holds the draw.
    if q.get("prob_a") is not None and q.get("edge") is not None and q.get("price_draw") is None:
        pa = float(q["prob_a"])
        lead["model_prob"] = round(pa if q["pick"] == "a" else 1.0 - pa, 4)
    if route:
        lead["route"] = route
    if lead["status"] == "pending":
        lead["last_seen"] = built[:10]
        lead["last_seen_at"] = built
    return lead


def _sandbox_record(d, key, since):
    source, sport = key.split("|", 1)
    a = T.assess(d, source, sport, since=since, venues=T.TRADEABLE_VENUES)
    r = lambda x: round(x, 4) if isinstance(x, float) else x
    return {"sandbox_n": a["n"], "sandbox_roi": r(a["roi"]), "sandbox_roi_fee": r(a["roi_fee"]),
            "sandbox_clv": r(a["clv"])}


def prune_feed(path=None, st=None):
    """Strip every lead from a pair that is no longer in Production. Returns how many went.

    The feed is rebuilt from scratch on each tracker run, so it is correct three hours after
    a demotion. Three hours is too long: this file is the one thing here that reaches past a
    web page, and a follower reading it has no way to know a pair was taken off the list an
    hour ago. On 2026-09-23 the tennis band left Production and the feed went on naming 285
    of its open leads until the next run.

    Two holes, one fix. This runs BEFORE anything else in a tracker run, so a demotion
    committed since the last one takes effect immediately rather than at the end; and it runs
    again if build_feed throws, because the old file staying put is exactly the failure that
    would otherwise go unnoticed -- the run prints a warning and the stale feed keeps being
    served.

    It reads the file and the stage registry only. No ledger, no network, nothing that can
    fail in a way that leaves a demoted pair published.
    """
    path = path or FEED
    try:
        with open(path) as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return 0
    live = set(production_pairs(st if st is not None else T.load_stages()))
    leads = blob.get("leads") or {}
    gone = [i for i, l in leads.items() if l.get("pair") not in live]
    stale_pairs = [k for k in (blob.get("pairs") or {}) if k not in live]
    if not gone and not stale_pairs:
        return 0
    for i in gone:
        del leads[i]
    for k in stale_pairs:
        del blob["pairs"][k]
    blob["pruned_at"] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    save_feed(blob, path)
    return len(gone)


def build_feed(d, st, now=None):
    """The Production feed as a dict. Pure: `d` is the Sandbox ledger, `st` the stage registry."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    built = now.replace(microsecond=0).isoformat()
    pairs = production_pairs(st)
    leads, skipped, unverified = {}, 0, 0
    for key, pair in pairs.items():
        source, sport = key.split("|", 1)
        for q in T.all_bets(d):
            if q["source"] != source or q["sport"] != sport or not q.get("bet"):
                continue
            try:
                ko = _kickoff(q)
            except (KeyError, TypeError, ValueError):
                continue
            # Published on the CONTEST, not on when the bet was written down. A pair moved
            # into Production has usually logged the next few days' fixtures already — under
            # a "logged since entry" rule those matches were never published at all, and the
            # lane sat silent for a day for no reason. What matters is that the pair was in
            # Production when the match was played.
            if ko.isoformat() < entered_at(pair):
                continue
            if q["status"] == "open" and ko <= now:
                continue                              # started: nothing left to act on
            if q["status"] != "open" and ko < now - datetime.timedelta(days=KEEP_SETTLED_DAYS):
                continue
            if not T.placeable(q):
                skipped += 1
                continue
            if not start_verified(q):
                unverified += 1
                continue
            lead = lead_from_quote(q, key, built)
            leads[lead["id"]] = lead
    return {
        "updated_at": built, "board_built_at": built, "stage": "production",
        # The Sandbox's own record for each pair since it entered Production, at the logged
        # price, so a follower's real fills can be compared with it.
        "pairs": {k: dict({"ready_at": p.get("ready_at"), "promoted_at": p.get("promoted_at"),
                           "entered_at": entered_at(p), "route": route_label(p),
                           "by_hand": p.get("by_hand")},
                          **_sandbox_record(d, k, entered_at(p)))
                  for k, p in pairs.items()},
        "leads": leads, "unlisted_skipped": skipped, "unverified_kickoff_skipped": unverified,
    }


def save_feed(blob, path=None):
    path = path or FEED
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)


def load_feed(path=None):
    try:
        with open(path or FEED) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"leads": {}, "pairs": {}}


def _day_label(day, today):
    """'Today', 'Tomorrow', or 'Sat 20 Sep' for a kickoff date."""
    delta = (day - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    return day.strftime("%a %d %b")


EARLY_N = 10      # under this many settled bets an ROI is shown grey and marked too early


def page(d, st, blob, style, now=None):
    """public_site/production.html — shares the Sandbox stylesheet.

    Organised as the questions a visitor actually asks, in order: what is in Production and on
    what evidence, what is coming up and when, how the recent leads have landed, what was held
    back, and — folded away — how a pair gets here. Written for a public page: it describes
    published leads and the record behind them, never anything that acts on them.
    """
    now_dt = now or datetime.datetime.now(datetime.timezone.utc)
    now_s = now_dt.strftime("%Y-%m-%d %H:%M UTC")
    today = now_dt.date()
    pairs = production_pairs(st)
    name = lambda key: S.SOURCES.get(key.split("|")[0], {}).get("label", key).split(" (")[0]
    sport_of = lambda key: S.SPORTS.get(key.split("|")[1], key.split("|")[1])
    label = lambda key: f"{name(key)} · {sport_of(key)}"
    pct = lambda x: "—" if x is None else f"{x*100:+.1f}%"
    tone = lambda x, n: "mut" if not n or x is None else ("pos" if x > 0 else "neg")
    leads = list(blob.get("leads", {}).values())
    upcoming = sorted((l for l in leads if l["status"] == "pending"
                       and l["kickoff"] >= now_dt.strftime("%Y-%m-%dT%H:%MZ")),
                      key=lambda l: l["kickoff"])
    settled = sorted((l for l in leads if l["status"] in ("hit", "miss")),
                     key=lambda l: l["kickoff"], reverse=True)

    # ---- the pairs, each with the evidence it was moved on and what it has done since ----
    cards = []
    for key, pair in sorted(pairs.items(), key=lambda kv: (sport_of(kv[0]), name(kv[0]))):
        source, sport = key.split("|", 1)
        since = entered_at(pair)
        # The SAME window the Sandbox page reads (the pair's stage clock), so the two pages
        # never show two different records for one rule.
        whole = T.assess(d, source, sport, since=pair.get("since"), venues=T.TRADEABLE_VENUES)
        live = T.assess(d, source, sport, since=since, venues=T.TRADEABLE_VENUES)
        mine = [l for l in leads if l.get("pair") == key]
        to_come = sum(1 for l in mine if l in upcoming)
        clv = ("—" if whole["clv"] is None else f"{whole['clv']*100:+.1f}¢")
        cards.append(f"""<tr>
<td><b>{esc(name(key))}</b><div class="sm mut">{esc(sport_of(key))} · moved {esc(str(pair.get('by_hand') or since or '')[:10])}</div></td>
<td class="num">{whole['n']}<div class="sm mut">settled</div></td>
<td class="num"><span class="{tone(whole['roi_fee'], whole['n'])}">{pct(whole['roi_fee'])}</span><div class="sm mut">after fees</div></td>
<td class="num">{clv}<div class="sm mut">v the close</div></td>
<td class="num">{f"{live['won']}–{live['n'] - live['won']}" if live['n'] else '—'}<div class="sm mut">{f"{live['n']} settled" if live['n'] else 'none yet'}</div></td>
<td class="num"><span class="{tone(live['roi_fee'], live['n'] >= EARLY_N)}">{pct(live['roi_fee'])}</span>{'<div class="sm mut">too early</div>' if 0 < live['n'] < EARLY_N else ''}</td>
<td class="num"><b>{to_come}</b></td></tr>""")
    pairs_html = (f"""<div class="tbl"><table>
<tr><th rowspan="2">Pair</th><th colspan="3" class="grp">Sandbox record (US exchanges)</th>
<th colspan="2" class="grp">Since Production</th><th rowspan="2" class="num">Leads<br>to come</th></tr>
<tr><th class="num">Bets</th><th class="num">ROI</th><th class="num">CLV</th><th class="num">Record</th><th class="num">ROI</th></tr>
{''.join(cards)}</table></div>""" if cards else
        '<div class="note">Nothing is in Production. A pair arrives here by hand, on the record '
        'the Sandbox measured.</div>')

    # ---- what is coming up, a table per day ----
    by_day = {}
    for l in upcoming:
        try:
            day = datetime.datetime.fromisoformat(l["kickoff"].replace("Z", "+00:00")).date()
        except ValueError:
            continue
        by_day.setdefault(day, []).append(l)
    days_html = ""
    for i, (day, ls) in enumerate(sorted(by_day.items())):
        rows = "".join(
            f"""<tr><td class="mut">{esc(l['kickoff'][11:16])}</td><td>{esc(l.get('league') or sport_of(l['pair']))}</td>
<td>{esc(l['match'])}</td><td><b>{esc(l['headline'])}</b></td><td class="mut">{esc(name(l['pair']))}</td>
<td class="num">{f"{l['price_at_log']:.2f}" if l.get('price_at_log') else '—'}</td></tr>"""
            for l in ls)
        # Each day folds; the soonest one starts open, since that is what a visitor came for.
        days_html += (f"""<details class="fold"{' open' if i == 0 else ''}><summary>{esc(_day_label(day, today))}
<span class="mut sm">· {len(ls)} lead{'s' if len(ls) != 1 else ''}</span></summary>
<div class="tbl"><table><tr><th>UTC</th><th>Competition</th><th>Match</th><th>Lead</th><th>From</th>
<th class="num">Logged at</th></tr>{rows}</table></div></details>""")
    upcoming_html = days_html or '<div class="note">No leads still to come.</div>'

    # ---- how the recent ones landed ----
    recent = settled[:25]
    rec_rows = "".join(
        f"""<tr><td class="mut">{esc(l['kickoff'][:10])}</td><td>{esc(l['match'])}</td>
<td>{esc(l['headline'])}</td><td class="mut">{esc(name(l['pair']))}</td>
<td class="num"><span class="{'pos' if l['status'] == 'hit' else 'neg'}">{'landed' if l['status'] == 'hit' else 'missed'}</span></td></tr>"""
        for l in recent)
    hits = sum(1 for l in settled if l["status"] == "hit")
    recent_html = (f"""<div class="tbl"><table><tr><th>Date</th><th>Match</th><th>Lead</th><th>From</th>
<th class="num">Result</th></tr>{rec_rows}</table></div>""" if rec_rows else
                   '<div class="note">Nothing has settled since these pairs were moved.</div>')

    nxt = upcoming[0]["kickoff"].replace("T", " ").rstrip("Z") if upcoming else "—"
    held = blob.get("unlisted_skipped", 0) + blob.get("unverified_kickoff_skipped", 0)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · Production</title>
<meta name="description" content="The pairs moved into Production by hand, and their published leads.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{style}
<style>th.grp{{text-align:center;border-bottom:1px solid var(--bd)}}
details.fold>summary{{cursor:pointer;list-style:none;display:flex;align-items:baseline;gap:6px;
  margin:18px 0 8px;font-weight:600;font-size:15px;user-select:none}}
details.fold>summary::-webkit-details-marker{{display:none}}
details.fold>summary::before{{content:"▸";color:var(--mut);font-size:12px;width:12px;transition:transform .15s}}
details.fold[open]>summary::before{{transform:rotate(90deg)}}
details.fold.sec>summary{{margin-top:26px}}
details.fold.sec>summary h2{{margin:0;display:inline}}
details.fold details.fold>summary{{margin:12px 0 6px;font-size:14px}}</style>
</head><body><div class="wrap">

<h1>Production</h1>
<div class="sub">The pairs moved here by hand, and the leads they publish · updated {esc(now_s)}</div>
<div class="nav"><a class="" href="./sandbox.html">Sandbox</a><a class="on" href="./production.html">Production</a></div>

<div class="tiles">
<div class="tile"><b>{len(pairs)}</b><span>pairs in Production</span></div>
<div class="tile"><b>{len(upcoming)}</b><span>leads still to come</span></div>
<div class="tile"><b>{hits}/{len(settled)}</b><span>recent leads landed</span></div>
<div class="tile"><b style="font-size:17px">{esc(nxt)}</b><span>next lead (UTC)</span></div>
</div>

<details class="fold sec" open><summary><h2>Pairs</h2> <span class="mut sm">· {len(pairs)}</span></summary>
<p class="sm mut">Each pair's Sandbox record on the US exchanges — the same numbers the Sandbox page shows —
and its record since it entered Production. Under {EARLY_N} settled bets an ROI is grey: one win at 0.46 reads
+117%, and means nothing yet. CLV is the closing price minus the price at logging: positive means its leads got
dearer after they were published.</p>
{pairs_html}</details>

<details class="fold sec" open><summary><h2>Coming up</h2> <span class="mut sm">· {len(upcoming)} leads over {len(by_day)} day{'s' if len(by_day) != 1 else ''}</span></summary>
{upcoming_html}</details>

<details class="fold sec"><summary><h2>Recently settled</h2> <span class="mut sm">· {hits} of {len(settled)} landed</span></summary>
{recent_html}</details>

<details class="fold sec"><summary><h2>Held back</h2> <span class="mut sm">· {held}</span></summary>
<div class="note">{held} bet{'s' if held != 1 else ''} from these pairs {'were' if held != 1 else 'was'} not published:
{blob.get('unlisted_skipped', 0)} cannot be expressed as a standard market, and
{blob.get('unverified_kickoff_skipped', 0)} {'are' if blob.get('unverified_kickoff_skipped', 0) != 1 else 'is'} waiting for a verified start
time. A lead is only published once its start has been confirmed.</div></details>

<details class="fold sec"><summary><h2>How a pair gets here</h2></summary>
<div class="note">Nothing promotes itself. Every source and rule starts in the <a href="./sandbox.html">Sandbox</a>,
logged before the start at the price available then and graded on the real result. A pair — one source in
one sport — is moved into Production by hand, on that record. It leaves the same way, or on its own when it
stops working: no new bet for {T.STALE_DAYS} days, behind the prices it logged at, or beaten by a blind rule
on the same contests. Every lead a Production pair logs is published to
<code>data/production_leads.json</code>.</div></details>

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
</div></body></html>"""


def main(argv=None):
    """`python3 production.py --prune-feed` — drop leads from pairs no longer in Production.

    For a demotion made by hand: the feed stops naming the pair straight away, without
    waiting for a tracker run. Prints what it dropped, and says so when there was nothing.
    """
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if "--prune-feed" not in argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: python3 production.py --prune-feed")
        return 2
    st = T.load_stages()
    live = sorted(production_pairs(st))
    n = prune_feed(st=st)
    print(f"in Production: {', '.join(live) if live else 'nothing'}")
    print(f"dropped {n} lead(s) from pairs no longer in Production"
          if n else "feed already names only Production pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
