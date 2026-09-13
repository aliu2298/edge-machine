#!/usr/bin/env python3
"""production.py — the Production stage: what the trading bot takes from the Sandbox ladder.

    Sandbox -> QA -> Production

A (source, sport) pair is IN PRODUCTION while it sits in QA with `ready_at` set — it has held
the full ready gate (the stamp on fresh data, beating the close, profitable after fees, every
bet routable by the bot) for READY_HOLD_DAYS. The moment that gate fails, evaluate_stages
withdraws `ready_at` and the pair leaves Production on the same run. Nothing is promoted by
hand.

data/production_leads.json is the FEED the bot reads next to the Leads ledger. It has the
leads ledger's shape — {"leads": {id: lead}, "updated_at", "board_built_at"} — so the bot's
existing parser, sanity gate and exact-build rule apply unchanged:

  * every bet a Production pair logs AFTER it entered Production, and only those the bot can
    route (sandbox_track.bot_route): today, a soccer side to win on a Kalshi GAME market in a
    league the bot maps
  * and only with a VERIFIED kickoff (start_source "espn"). Kalshi publishes no kickoff and
    its estimate has been a day off both ways; the bot's minutes-to-kickoff floor trusts this
    file, so a kickoff listed too late could let it buy a match in play. Held back and counted.
  * bet {"kind": "match_result", "side": "home" | "away"}, home = the Kalshi event's first
    side (sandbox_sources.kalshi_sides)
  * status pending / hit / miss / void from the Sandbox settlement
  * last_seen_at == board_built_at on every lead still open; a lead whose pair has left
    Production is dropped from the file, which the bot reads as withdrawn

An empty feed is normal until the first pair is ready: the bot treats this feed as allowed
to be empty. This file only ever changes when the tracker runs (every 3h).
"""
import datetime, html, json, os

import sandbox_sources as S
import sandbox_track as T

ROOT = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(ROOT, "data", "production_leads.json")
KEEP_SETTLED_DAYS = 7          # settled leads stay in the feed this long, for the bot's results join
STATUS = {"open": "pending", "won": "hit", "lost": "miss", "void": "void"}


def esc(x):
    return html.escape(str(x if x is not None else ""))


def production_pairs(st):
    """{"source|sport": pair} for every pair currently in Production."""
    return {k: p for k, p in (st.get("pairs") or {}).items()
            if p.get("stage") == "qa" and p.get("ready_at")}


def _kickoff(q):
    dt = datetime.datetime.fromisoformat(str(q["start"]))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def lead_from_quote(q, pair_key, built):
    """One Sandbox bet as a bot-feed lead."""
    ko = _kickoff(q)
    side = "home" if q["pick"] == "a" else "away"
    team = q["side_a"] if q["pick"] == "a" else q["side_b"]
    label = S.SOURCES.get(q["source"], {}).get("label", q["source"]).split(" (")[0]
    date = ko.date().isoformat()
    headline = f"{team} to win"
    lead = {
        "id": f"{date}|{q['side_a']}|{q['side_b']}|{headline} · {label}",
        "date": date, "kickoff": ko.strftime("%Y-%m-%dT%H:%MZ"),
        "league": S.quote_league(q), "match": f"{q['side_a']} v {q['side_b']}",
        "home": q["side_a"], "away": q["side_b"], "headline": headline,
        "bet": {"kind": "match_result", "side": side},
        "status": STATUS.get(q["status"], "void"),
        "first_seen": str(q["logged"])[:10],
        "source": q["source"], "sport": q["sport"], "pair": pair_key, "lane": "production",
        "sandbox_quote": q["id"], "price_at_log": q.get("price"), "edge_at_log": q.get("edge"),
    }
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
                    or str(q.get("logged") or "") < pair["ready_at"]):
                continue
            try:
                ko = _kickoff(q)
            except (KeyError, TypeError, ValueError):
                continue
            if q["status"] == "open" and ko <= now:
                continue                              # started: nothing left to act on
            if q["status"] != "open" and ko < now - datetime.timedelta(days=KEEP_SETTLED_DAYS):
                continue
            if not T.bot_route(q):
                skipped += 1
                continue
            if q.get("start_source") != "espn":
                unverified += 1
                continue
            lead = lead_from_quote(q, key, built)
            leads[lead["id"]] = lead
    return {
        "updated_at": built, "board_built_at": built, "stage": "production",
        # The Sandbox's own record for each pair since it became ready, at the logged price —
        # the bot shows it next to what its real fills made on the same pair.
        "pairs": {k: dict({"ready_at": p["ready_at"], "promoted_at": p.get("promoted_at")},
                          **_sandbox_record(d, k, p["ready_at"]))
                  for k, p in pairs.items()},
        "leads": leads, "unroutable_skipped": skipped, "unverified_kickoff_skipped": unverified,
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
    for key, pair in sorted(pairs.items(), key=lambda kv: kv[1]["ready_at"]):
        source, sport = key.split("|", 1)
        a = T.assess(d, source, sport, since=pair["ready_at"], venues=T.TRADEABLE_VENUES)
        mine = [l for l in blob.get("leads", {}).values() if l.get("pair") == key]
        rows.append(f"""<tr><td><b>{esc(label(key))}</b>
<div class="sm mut">ready {esc(pair['ready_at'][:10])} · in QA since {esc(str(pair.get('promoted_at'))[:10])}</div></td>
<td class="num">{sum(1 for l in mine if l['status'] == 'pending')}</td>
<td class="num">{a['n']}</td>
<td class="num"><span class="{'pos' if (a['roi'] or 0) > 0 else 'neg' if a['n'] else 'mut'}">{f"{a['roi']*100:+.1f}%" if a['roi'] is not None else '—'}</span>
<div class="sm mut">{f"{a['roi_fee']*100:+.1f}% after fees" if a['roi_fee'] is not None else ''}</div></td>
<td class="num">{f"{a['clv']*100:+.1f}¢" if a['clv'] is not None else '—'}</td></tr>""")
    table = (f"""<div class="tbl"><table><tr><th>Pair</th><th class="num">Leads open</th>
<th class="num">Settled since ready</th><th class="num">ROI</th><th class="num">CLV</th></tr>
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
<meta name="description" content="Sandbox sources that passed QA, and the leads the trading bot takes from them.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{style}</head><body><div class="wrap">

<h1>Production</h1>
<div class="sub">What the trading bot takes from the Sandbox ladder · updated {esc(now_s)}</div>
<div class="nav"><a href="./">Leads</a>
<a href="./streaks.html">Streaks</a><a href="./record.html">Record</a>
<a href="./today.html">Today</a><a href="./sandbox.html">Sandbox</a><a href="./qa.html">QA</a><a class="on" href="./production.html">Production</a></div>

<div class="note warn"><b>Sandbox → QA → Production.</b> A (source, sport) pair is in Production
while it holds the QA ready gate — the full stamp on bets made after its promotion, beating the
closing price, profitable after fees, and every bet a market the bot can place — and it has held
it for {T.READY_HOLD_DAYS} days. It leaves on the first run the gate fails. Every bet a Production pair
logs is published to <code>data/production_leads.json</code>, which the <b>trading bot reads next to
the Leads board</b> under the same checks: only leads in the latest build, inside its kickoff
window, one position per fixture, and the open-position and daily-loss caps.</div>

<div class="tiles">
<div class="tile"><b>{len(pairs)}</b><span>pairs in Production</span></div>
<div class="tile"><b>{len(open_leads)}</b><span>open leads for the bot</span></div>
<div class="tile"><b>{blob.get('unroutable_skipped', 0)}</b><span>bets the bot cannot route (not published)</span></div>
<div class="tile"><b>{blob.get('unverified_kickoff_skipped', 0)}</b><span>held back: kickoff not verified by ESPN</span></div>
</div>

<h2>Pairs</h2>
{table}

<h2>Open leads</h2>
{leads_table}

<footer>Read-only static export · rebuilt by GitHub Actions · research, not betting advice.</footer>
</div></body></html>"""
