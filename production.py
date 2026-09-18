#!/usr/bin/env python3
"""production.py — the Production stage: the Sandbox sources that earned a place, and their bets.

    Sandbox -> QA -> Production

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
    if q.get("sport") == "tennis":
        # Polymarket publishes the match start itself; a Kalshi tennis row only has one once
        # the schedule has confirmed it.
        return (q.get("venue") == "polymarket_us"
                or q.get("start_source") == "tennisexplorer")
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
    if q["sport"] == "tennis":
        # Kalshi lists a market per player inside one event, so backing either player is a
        # plain Yes on that player's market. Polymarket lists ONE market with two outcomes,
        # so the second player is the No side of it.
        route = {"venue": q["venue"], "market": q["market_id"],
                 "outcome": home if q["pick"] == "a" else away,
                 "outcome_side": "yes" if (q["pick"] == "a" or q["venue"] == "kalshi") else "no"}
    lead = {
        "id": f"{date}|{home}|{away}|{headline} · {label}",
        "date": date, "kickoff": ko.strftime("%Y-%m-%dT%H:%MZ"),
        "league": S.quote_league(q) or ("Tennis" if q["sport"] == "tennis" else None),
        "match": f"{home} v {away}",
        "home": home, "away": away, "headline": headline,
        "bet": bet,
        "status": STATUS.get(q["status"], "void"),
        "first_seen": str(q["logged"])[:10],
        "source": q["source"], "sport": q["sport"], "pair": pair_key, "lane": "production",
        "sandbox_quote": q["id"], "price_at_log": q.get("price"), "edge_at_log": q.get("edge"),
    }
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


def build_feed(d, st, now=None):
    """The Production feed as a dict. Pure: `d` is the Sandbox ledger, `st` the stage registry."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    built = now.replace(microsecond=0).isoformat()
    pairs = production_pairs(st)
    leads, skipped, unverified = {}, 0, 0
    for key, pair in pairs.items():
        source, sport = key.split("|", 1)
        for q in T.all_bets(d):
            if (q["source"] != source or q["sport"] != sport or not q.get("bet")
                    or str(q.get("logged") or "") < entered_at(pair)):
                continue
            try:
                ko = _kickoff(q)
            except (KeyError, TypeError, ValueError):
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


def page(d, st, blob, style, now=None):
    """public_site/production.html — shares the Sandbox stylesheet."""
    now_s = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    pairs = production_pairs(st)
    label = lambda key: (f'{S.SOURCES.get(key.split("|")[0], {}).get("label", key).split(" (")[0]} · '
                         f'{S.SPORTS.get(key.split("|")[1], key.split("|")[1])}')
    rows = []
    for key, pair in sorted(pairs.items(), key=lambda kv: entered_at(kv[1]) or ""):
        source, sport = key.split("|", 1)
        since = entered_at(pair)
        a = T.assess(d, source, sport, since=since, venues=T.TRADEABLE_VENUES)
        mine = [l for l in blob.get("leads", {}).values() if l.get("pair") == key]
        how = (f"moved by hand {esc(str(pair.get('by_hand') or '')[:10])} · trading since "
               f"{esc(str(since)[:10])}")
        rows.append(f"""<tr><td><b>{esc(label(key))}</b>
<div class="sm mut">{how}</div></td>
<td class="num">{sum(1 for l in mine if l['status'] == 'pending')}</td>
<td class="num">{a['n']}</td>
<td class="num"><span class="{'pos' if (a['roi'] or 0) > 0 else 'neg' if a['n'] else 'mut'}">{f"{a['roi']*100:+.1f}%" if a['roi'] is not None else '—'}</span>
<div class="sm mut">{f"{a['roi_fee']*100:+.1f}% after fees" if a['roi_fee'] is not None else ''}</div></td>
<td class="num">{f"{a['z']:+.2f}" if a['n'] else '—'}</td>
<td class="num">{f"{a['clv']*100:+.1f}¢" if a['clv'] is not None else '—'}</td></tr>""")
    table = (f"""<div class="tbl"><table><tr><th>Pair</th><th class="num">Leads open</th>
<th class="num">Settled in Production</th><th class="num">ROI</th><th class="num">z v price</th><th class="num">CLV</th></tr>
{''.join(rows)}</table></div>""" if rows else
             '<div class="note">Nothing is in Production yet. A pair arrives here automatically '
             'once it has held the QA ready gate for ' + str(T.READY_HOLD_DAYS) + ' days, and leaves '
             'on the first run it fails it.</div>')
    open_leads = sorted((l for l in blob.get("leads", {}).values() if l["status"] == "pending"),
                        key=lambda l: l["kickoff"])
    lead_rows = "".join(
        f"""<tr><td class="mut">{esc(l['kickoff'].replace('T', ' ').rstrip('Z'))}</td><td>{esc(l['league'])}</td>
<td>{esc(l['match'])}</td><td><b>{esc(l['headline'])}</b></td><td>{esc(label(l['pair']))}</td>
<td class="num">{f"{l['price_at_log']:.2f}" if l.get('price_at_log') else '—'}</td></tr>"""
        for l in open_leads)
    leads_table = (f"""<div class="tbl"><table><tr><th>Kickoff (UTC)</th><th>League</th><th>Match</th>
<th>Lead</th><th>From</th><th class="num">Logged at</th></tr>{lead_rows}</table></div>"""
                   if lead_rows else '<div class="note">No open Production leads.</div>')
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edge Machine · Production</title>
<meta name="description" content="Sandbox sources that earned a place in Production, and their published leads.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{style}</head><body><div class="wrap">

<h1>Production</h1>
<div class="sub">The only page anything trades from · updated {esc(now_s)}</div>
<div class="nav"><a class="" href="./record.html">Record</a><a class="" href="./sandbox.html">Sandbox</a><a class="on" href="./production.html">Production</a></div>

<div class="note warn"><b>Sandbox, then Production — by hand.</b> Nothing promotes itself. A (source,
sport) pair is here because it was listed by hand, on the record the <a href="./sandbox.html">Sandbox</a>
measured. It leaves the same way, or on its own when it stops working: no new bet for {T.STALE_DAYS} days,
behind the prices it paid, or beaten by a blind rule on the same contests. Every bet a Production pair logs
is published to <code>data/production_leads.json</code>, and this file is the single thing the money
follows.</div>

<div class="tiles">
<div class="tile"><b>{len(pairs)}</b><span>pairs in Production</span></div>
<div class="tile"><b>{len(open_leads)}</b><span>open leads</span></div>
<div class="tile"><b>{blob.get('unlisted_skipped', 0)}</b><span>bets not expressible as a standard market (not published)</span></div>
<div class="tile"><b>{blob.get('unverified_kickoff_skipped', 0)}</b><span>held back: start time not verified</span></div>
</div>

<h2>Pairs</h2>
{table}

<h2>Open leads</h2>
{leads_table}

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
</div></body></html>"""
