"""The Edge Machine leaderboard (2026-10-30, Olu): which NAMED teams, players and assets keep paying on cheap contracts.

Paper and read-only. Every number comes from ledgers the trackers and lanes already write; nothing is fetched, no
rule is created, no order is placed. This module turns those ledgers into one flat list of CONTRACTS, maps each to
the ENTITIES it belongs to, and ranks the entities.

A CONTRACT is one cheap entry that can be judged: a sport, a market type, an event, a day, whether the traded price
reached 2x and 3x of the entry, and the split (half at 2x, half at 3x) and hold ROI after fees. Only entries whose
ask was real count (the #253 ask check: a lane's own `ask_check.status == "verified"`, or the same print test on a
tracker row); everything else is left out and counted in `skipped`.

ENTITY MAPPING (documented here, tested in test_leaderboard.py):
  NBA        the team in the ticker suffix (KXNBAGAME-...-UTA, KXNBATEAMTOTAL-...-DET120, KXNBASPREAD-...-WAS11).
             A team's win-margin rungs, spreads, team totals and moneyline side all belong to that team.
  Soccer     over 3.5 NO bids (o35_cheap_no): BOTH teams of the match, shown as a match contract. Team names come
             from the Sandbox ledger's ESPN names for the same fixture; a fixture with no name there is unmapped.
  Tennis     the player code in the ticker (Kalshi's surname abbreviation, e.g. MAN). Names are not in the ledgers.
  Football   the team code in the ticker (college football).
  Commodities  WTI (KXWTI), AAA gas (KXAAAGASD, KXAAAGASW).
  Culture    the speaker for Trump mentions (KXTRUMPSAY -> Trump); an album by its Kalshi code or title.
  Fights     the fighter (the market's `word`).
  Crypto     no cheap-side ledger exists yet, so no crypto entity can appear. COIN_BY_SERIES maps the coin tickers
             in case one is added.

A ledger entry that cannot be mapped is counted in `unmapped` by source and never silently dropped into a guess.

METRICS per entity: verified contracts and distinct events, contracts per week, reached 2x / 3x (fair is 50% / 33%:
a cheap contract at price p hits 2p about half the time at fair odds), split and hold ROI (mean per contract, after
fees), the median contracts traded at 2x+ where the source carries it, and HOLDS UP (reached-2x in the entity's
older half of events v the newer half).

SCORE = (wins + PRIOR_N x market average) / (n + PRIOR_N) - 0.5, where wins is the number of contracts that reached
2x, n the contracts where 2x was reachable and the market average is the pooled reached-2x of that sport and market
type. PRIOR_N = 20 contracts, so 3-for-3 cannot top the board. An entity ranks only with MIN_CONTRACTS verified
contracts across MIN_EVENTS events; below that it is "watching".

PERSISTENCE: each week, last week's top-quarter v bottom-quarter entities, compared on THIS week's reached-2x, plus
a split-half rank correlation. The board is a description of where spikes happened until that test is positive.
"""
import datetime as dt
import json
import os
import re
import statistics

import chaos_replay as C

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

PRIOR_N = 20
MIN_CONTRACTS = 15
MIN_EVENTS = 5
FAIR_2X, FAIR_3X = 0.5, 1 / 3
HALF_MIN = 4            # contracts needed in each half before "holds up" is judged
WEEK_MIN = 3            # contracts an entity needs in a week to be ranked for the persistence test
WEEK_ENTITIES_MIN = 8   # entities needed in a week for a top-quarter v bottom-quarter comparison
SPORTS = ("NBA", "Soccer", "Crypto", "Commodities", "Culture", "Fights", "Tennis", "Football")
TOP_N, BOTTOM_N = 10, 5

NBA_TEAMS = {
    "ATL": "Atlanta Hawks", "BKN": "Brooklyn Nets", "BOS": "Boston Celtics", "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons", "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers",
    "PHX": "Phoenix Suns", "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}
COIN_BY_SERIES = {"KXBTCD": "Bitcoin", "KXBTC": "Bitcoin", "KXETHD": "Ethereum", "KXETH": "Ethereum",
                  "KXSOLD": "Solana", "KXSOL": "Solana", "KXXRPD": "XRP", "KXXRP": "XRP", "KXHYPED": "HYPE"}
COMMODITY_BY_SERIES = {"KXWTI": "WTI", "KXAAAGASD": "AAA gas", "KXAAAGASW": "AAA gas"}
SPEAKER_BY_SERIES = {"KXTRUMPSAY": "Trump"}

# Chaos lanes read, in priority order (a contract seen by two lanes counts once, for the first). The NBA win
# margin lanes are NOT read: the win margin tracker holds the same markets with their own prints.
CHAOS_LANES = (
    ("nba_ml_dog_tp50", "NBA", "Moneyline underdog"),
    ("challenger_cheap_split", "Tennis", "Challenger match winner"),
    ("cfb_dog_tp50", "Football", "Game winner underdog"),
    ("atp_coinflip_tp30", "Tennis", "ATP match winner"),
    ("challenger_dog_tp30", "Tennis", "Challenger match winner"),
    ("nba_tt_cheap_tp30", "NBA", "Team total"),
)
# Cheap-side ledgers in the mentions_split shape: file -> (sport, market label, mapper name).
LEDGERS = (
    ("wti_cheap_yes_ledger.json", "Commodities", "WTI above ladders", "series"),
    ("gas_cheap_no_ledger.json", "Commodities", "AAA gas daily NO", "series"),
    ("gas_week_cheap_no_ledger.json", "Commodities", "AAA gas weekly NO", "series"),
    ("album_cheap_no_ledger.json", "Culture", "Album sales NO", "album"),
    ("album_cheap_rungs_ledger.json", "Culture", "Album sales rungs", "album"),
    ("mentions_split_ledger.json", "Culture", "Mentions", "series"),
    ("mentions_split_wide_ledger.json", "Culture", "Mentions", "series"),
    ("mentions_month_split_ledger.json", "Culture", "Mentions", "series"),
    ("mentions_month_split_wide_ledger.json", "Culture", "Mentions", "series"),
    ("boxing_cheap_dog_ledger.json", "Fights", "Boxing fighter", "word"),
    ("ufc_dog_ledger.json", "Fights", "UFC fighter", "word"),
)


def load(name):
    try:
        with open(os.path.join(DATA, name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _day(text):
    return str(text or "")[:10]


def series_of(ticker):
    return str(ticker or "").split("-")[0]


def team_code(suffix):
    """'DET120' -> 'DET', 'WAS11' -> 'WAS', 'UTA' -> 'UTA'."""
    hit = re.match(r"[A-Z]+", str(suffix or ""))
    return hit.group(0) if hit else None


def nba_name(code):
    return NBA_TEAMS.get(code, code)


def contract(uid, sport, market, event, day, entities, kind="team", reach2=None, reach3=None, split=None, hold=None,
             vol2=None, source=""):
    return dict(uid=uid, sport=sport, market=market, event=event, day=day, entities=list(entities), kind=kind,
                reach2=reach2, reach3=reach3, split=split, hold=hold, vol2=vol2, source=source)


# ---------------------------------------------------------------- collectors

def collect_chaos(chaos, skipped):
    """Cheap-side chaos lanes: one contract per entry that has BOTH a hold row and a split row, ask verified."""
    out, seen = [], set()
    lanes = (chaos or {}).get("lanes") or {}
    for lane_id, sport, market in CHAOS_LANES:
        entries = {}
        for t in (lanes.get(lane_id) or {}).get("trades") or []:
            entries.setdefault((t["ticker"], t["side"], t["hours"]), {})[t["exit_key"]] = t
        for (ticker, side, hours), rows in sorted(entries.items(), key=lambda kv: (kv[0][2], kv[0][0])):
            uid = (ticker, side)
            if uid in seen:
                continue
            hold, split = rows.get("hold"), rows.get("split")
            if not hold or not split:
                skipped["no split row yet"] = skipped.get("no split row yet", 0) + 1
                continue
            if (hold.get("ask") or {}).get("status") != "verified":
                skipped["unverified ask"] = skipped.get("unverified ask", 0) + 1
                continue
            suffix = ticker.rsplit("-", 1)[-1]
            if side != "yes":
                skipped["not a yes side"] = skipped.get("not a yes side", 0) + 1
                continue
            code = team_code(suffix) if sport in ("NBA", "Football") else suffix
            name = nba_name(code) if sport == "NBA" else code
            if not name:
                skipped["no entity"] = skipped.get("no entity", 0) + 1
                continue
            seen.add(uid)
            out.append(contract(uid, sport, market, hold["event"], hold.get("night") or "", [name],
                                reach2=bool(split.get("filled_2x")), reach3=bool(split.get("filled_3x")),
                                split=split.get("roi"), hold=hold.get("roi"), source=lane_id))
    return out


def tracker_ask_ok(row):
    """The #253 print test on a tracker row: 10+ contracts traded at or under the ask within the hour after the
    entry (the entry is one hour before the tip, so tip-relative seconds -3600..0). A row stamped `ask_ok`
    when its path was still kept keeps that answer after the path is cleared."""
    if row.get("ask_ok") is not None:
        return bool(row["ask_ok"])
    path = row.get("path") or []
    if not path:
        return None
    ask = (row.get("ask") or 0) * 100 + 1e-6
    return sum(size for t, price, size in path if -3600 <= t <= 0 and price <= ask) >= 10


def _legged(ask, won, reach2, reach3):
    """(split ROI, hold ROI) for a taker entry at `ask`: half rests at 2x, half at 3x (capped .98), a leg not
    reached is held to settlement; maker fee on a filled leg (chaos_replay's own formulas)."""
    c = C.cost(ask)
    pay = 1.0 if won else 0.0
    proceeds = 0.0
    for mult, reached in ((2.0, reach2), (3.0, reach3)):
        target = round(min(ask * mult, C.SPLIT_CAP), 2)
        proceeds += 0.5 * ((target - C.maker_fee(target)) if reached else pay)
    return round((proceeds - c) / c, 4), round((pay - c) / c, 4)


def collect_tracker(tracker, chaos, skipped):
    """NBA win margin buckets and spreads (nba_winmargin_tracker): eligible rows whose ask verified, by the row's own
    print test or its path-cleared `ask_ok` stamp, else by the win margin chaos lane's check on the same ticker."""
    checked = {}
    for lane_id in ("nba_winmargin_split_insample", "nba_winmargin_split"):
        for t in ((chaos or {}).get("lanes") or {}).get(lane_id, {}).get("trades") or []:
            if t["exit_key"] == "hold":
                checked[t["ticker"]] = (t.get("ask") or {}).get("status")
    out = []
    for kind, rows in (("Win margin", tracker.get("rows") or []), ("Spread", tracker.get("spread_rows") or [])):
        for r in rows:
            if not r.get("eligible") or not r.get("m"):
                continue
            ok = tracker_ask_ok(r)
            if ok is None:
                ok = {"verified": True, "unverified": False}.get(checked.get(r["id"]))
            if ok is None:
                skipped["tracker: ask not checkable (path cleared)"] = skipped.get("tracker: ask not checkable (path cleared)", 0) + 1
                continue
            if not ok:
                skipped["unverified ask"] = skipped.get("unverified ask", 0) + 1
                continue
            code = team_code(r["id"].rsplit("-", 1)[-1]) if kind == "Spread" else r.get("team")
            if not code or r.get("won") is None:
                skipped["no entity"] = skipped.get("no entity", 0) + 1
                continue
            market = "Comeback spread" if r.get("comeback") else kind + ("s" if kind == "Spread" else " buckets")
            reach2, reach3 = r["m"].get("reach2"), r["m"].get("reach3")
            split = hold = None
            if r.get("ask") and reach2 is not None:
                split, hold = _legged(r["ask"], bool(r["won"]), bool(reach2), bool(reach3))
            out.append(contract((r["id"], "yes"), "NBA", market, r["event"], r.get("night") or "",
                                [nba_name(code)], reach2=reach2, reach3=reach3, split=split, hold=hold,
                                vol2=r["m"].get("vol2") if reach2 else None, source="nba_winmargin_tracker"))
    return out


def match_names(sandbox):
    """{'26OCT28VENINT': ('Venezia', 'Internazionale')} from the Sandbox ledger's fixtures (ESPN names)."""
    out = {}
    for q in (sandbox or {}).get("quotes") or []:
        event = q.get("event") or str(q.get("market_id") or "").rsplit("-", 1)[0]
        if event.startswith("KX") and "-" in event and q.get("espn_home") and q.get("espn_away"):
            out.setdefault(event.split("-", 1)[1], (q["espn_home"], q["espn_away"]))
    return out


def collect_o35(o35, names, skipped, unmapped):
    """Over 3.5 cheap NO: the 10c resting bid (the lane's headline) when it filled and was not a dead fill. Reached 2x
    / 3x is the lane's own sell flags (50-contract floor already applied); the match counts for both teams."""
    out = []
    for e in (o35 or {}).get("entries") or []:
        bid = (e.get("bids") or {}).get("10")
        if not bid or bid.get("fill_at") is None:
            continue
        if bid.get("dead"):
            skipped["dead fill"] = skipped.get("dead fill", 0) + 1
            continue
        pair = names.get(str(e["event"]).split("-", 1)[-1])
        if not pair:
            unmapped["o35_cheap_no (fixture has no team names)"] = unmapped.get("o35_cheap_no (fixture has no team names)", 0) + 1
            continue
        sells = bid.get("sells") or {}
        flag = {k: bool((sells.get(k) or {}).get("filled")) and not (sells.get(k) or {}).get("thin") for k in ("2", "3")}
        limit = bid["limit"]
        pay = bid.get("payout")
        if pay is None:
            pay = 1.0 if e.get("result") == "no" else 0.0
        cost = limit + C.maker_fee(limit)
        proceeds = 0.0
        for k, mult in (("2", 2.0), ("3", 3.0)):
            target = (sells.get(k) or {}).get("target") or round(limit * mult, 2)
            proceeds += 0.5 * ((target - C.maker_fee(target)) if flag[k] else pay)
        vols = [(sells.get("2") or {}).get("volume")] if flag["2"] else []
        out.append(contract((e["id"], "no"), "Soccer", "Over 3.5 NO bid", e["event"], e.get("night") or "",
                            list(pair), kind="match", reach2=flag["2"], reach3=flag["3"],
                            split=round((proceeds - cost) / cost, 4), hold=round((pay - cost) / cost, 4),
                            vol2=vols[0] if vols else None, source="o35_cheap_no"))
    return out


def ledger_entity(entry, how):
    event = str(entry.get("event") or "")
    series = series_of(event)
    if how == "word":
        return entry.get("word")
    if how == "album":
        return entry.get("word") or event.rsplit("-", 1)[-1] or None
    if series in COMMODITY_BY_SERIES:
        return COMMODITY_BY_SERIES[series]
    if series in SPEAKER_BY_SERIES:
        return SPEAKER_BY_SERIES[series]
    return COIN_BY_SERIES.get(series)


def collect_ledgers(skipped, unmapped, loader=load):
    """The mentions_split-shaped cheap-side ledgers: settled entries, ask verified, legs carry the 2x/3x fills."""
    out = []
    for name, sport, market, how in LEDGERS:
        state = loader(name)
        rule = bool(state.get("ask_rule_since"))
        for e in state.get("entries") or []:
            if e.get("payout") is None and e.get("status") not in ("settled", "won", "lost"):
                continue                                     # still open: not judged yet
            status = (e.get("ask_check") or {}).get("status")
            if rule and status != "verified":
                skipped["unverified ask"] = skipped.get("unverified ask", 0) + 1
                continue
            entity = ledger_entity(e, how)
            if not entity:
                unmapped[name] = unmapped.get(name, 0) + 1
                continue
            legs = {int(round(l["multiple"])): l for l in e.get("legs") or []}
            r2 = bool((legs.get(2) or {}).get("filled_at"))
            r3 = bool((legs.get(3) or {}).get("filled_at"))
            out.append(contract((e["id"], e.get("side") or ""), sport, market, e["event"], _day(e.get("entry_at")),
                                [str(entity)], reach2=r2, reach3=r3, split=e.get("roi"), hold=e.get("roi_held"),
                                source=name))
    return out


def collect_all(loader=load):
    skipped, unmapped = {}, {}
    chaos, tracker = loader("chaos_ledger.json"), loader("nba_winmargin_tracker.json")
    contracts = collect_chaos(chaos, skipped) + collect_tracker(tracker, chaos, skipped)
    contracts += collect_o35(loader("o35_cheap_no_ledger.json"), match_names(loader("sandbox_ledger.json")), skipped, unmapped)
    contracts += collect_ledgers(skipped, unmapped, loader)
    uniq, seen = [], set()
    for c in contracts:                                      # one contract once, whatever lane saw it
        if c["uid"] in seen:
            continue
        seen.add(c["uid"])
        uniq.append(c)
    return uniq, skipped, unmapped


# ---------------------------------------------------------------- statistics

def market_means(contracts):
    """{(sport, market): pooled reached-2x} over unique contracts where 2x was reachable."""
    tot = {}
    for c in contracts:
        if c["reach2"] is None:
            continue
        w, n = tot.get((c["sport"], c["market"]), (0, 0))
        tot[(c["sport"], c["market"])] = (w + bool(c["reach2"]), n + 1)
    return {k: w / n for k, (w, n) in tot.items()}


def shrunk_score(wins, n, prior_mean, prior_n=PRIOR_N):
    """Reached-2x excess over fair (0.5), shrunk toward the market's own average with a prior worth prior_n contracts."""
    return (wins + prior_n * prior_mean) / (n + prior_n) - FAIR_2X


def rate(rows, key):
    known = [c for c in rows if c[key] is not None]
    return (sum(bool(c[key]) for c in known) / len(known)) if known else None


def mean_of(rows, key):
    vals = [c[key] for c in rows if c[key] is not None]
    return sum(vals) / len(vals) if vals else None


def older_newer(rows):
    """Split an entity's contracts by event order: the older half of its events v the newer half."""
    events = sorted({(c["day"], c["event"]) for c in rows})
    if len(events) < 2:
        return rows, []
    older = set(events[:len(events) // 2])
    return [c for c in rows if (c["day"], c["event"]) in older], [c for c in rows if (c["day"], c["event"]) not in older]


def holds_up(rows):
    """(older reached-2x, newer reached-2x, ok): ok is True when both halves beat fair, None when a half is too small."""
    old, new = older_newer(rows)
    if sum(c["reach2"] is not None for c in old) < HALF_MIN or sum(c["reach2"] is not None for c in new) < HALF_MIN:
        return rate(old, "reach2"), rate(new, "reach2"), None
    a, b = rate(old, "reach2"), rate(new, "reach2")
    return a, b, bool(a > FAIR_2X and b > FAIR_2X)


def per_week(rows):
    days = sorted(c["day"] for c in rows if c["day"])
    if not days:
        return None
    span = (dt.date.fromisoformat(days[-1]) - dt.date.fromisoformat(days[0])).days + 1
    return len(rows) / max(span / 7.0, 1.0)


def entity_rows(contracts):
    """{(sport, entity): [contracts]}. A match contract appears under both teams."""
    out = {}
    for c in contracts:
        for name in dict.fromkeys(c["entities"]):
            out.setdefault((c["sport"], name), []).append(c)
    return out


def summarize_entity(sport, name, rows, means):
    known = [c for c in rows if c["reach2"] is not None]
    wins = sum(bool(c["reach2"]) for c in known)
    prior = (sum(means[(c["sport"], c["market"])] for c in known) / len(known)) if known else FAIR_2X
    old_rate, new_rate, ok = holds_up(rows)
    vols = [c["vol2"] for c in rows if c["reach2"] and c["vol2"] is not None]
    by_market = {}
    for c in rows:
        by_market.setdefault(c["market"], []).append(c)
    return dict(
        sport=sport, name=name, n=len(rows), events=len({c["event"] for c in rows}), per_week=per_week(rows),
        r2=rate(rows, "reach2"), r3=rate(rows, "reach3"), split=mean_of(rows, "split"), hold=mean_of(rows, "hold"),
        vol=statistics.median(vols) if vols else None, old=old_rate, new=new_rate, holds=ok,
        score=shrunk_score(wins, len(known), prior) if known else None, matches=any(c["kind"] == "match" for c in rows),
        markets=[dict(market=m, n=len(v), events=len({c["event"] for c in v}), r2=rate(v, "reach2"), r3=rate(v, "reach3"),
                      split=mean_of(v, "split"), hold=mean_of(v, "hold"),
                      vol=(statistics.median([c["vol2"] for c in v if c["reach2"] and c["vol2"] is not None])
                           if any(c["reach2"] and c["vol2"] is not None for c in v) else None),
                      match=any(c["kind"] == "match" for c in v))
                 for m, v in sorted(by_market.items(), key=lambda kv: -len(kv[1]))])


def qualifies(s):
    return s["n"] >= MIN_CONTRACTS and s["events"] >= MIN_EVENTS and s["score"] is not None


def spearman(xs, ys):
    """Rank correlation with average ranks for ties; None under 3 pairs or no spread."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    if not sx or not sy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy)


def iso_week(day):
    y, w, _ = dt.date.fromisoformat(day).isocalendar()
    return f"{y}-W{w:02d}"


def persistence(contracts):
    """Last week's top-quarter v bottom-quarter entities, on THIS week's reached-2x; and the split-half rank correlation.

    A week's ranking uses entities with WEEK_MIN+ contracts that week and needs WEEK_ENTITIES_MIN of them; the
    quarter is a quarter of those entities (at least one). Both groups are then read on the next calendar week's
    contracts (pooled), and a week is only tested when both groups have contracts there."""
    ents = entity_rows([c for c in contracts if c["day"] and c["reach2"] is not None])
    weeks = sorted({iso_week(c["day"]) for rows in ents.values() for c in rows})
    tested = []
    for a, b in zip(weeks, weeks[1:]):
        if dt.date.fromisocalendar(int(b[:4]), int(b[6:]), 1) - dt.date.fromisocalendar(int(a[:4]), int(a[6:]), 1) != dt.timedelta(days=7):
            continue
        last = {k: [c for c in rows if iso_week(c["day"]) == a] for k, rows in ents.items()}
        last = {k: v for k, v in last.items() if len(v) >= WEEK_MIN}
        if len(last) < WEEK_ENTITIES_MIN:
            continue
        order = sorted(last, key=lambda k: (-rate(last[k], "reach2"), k))
        q = max(1, len(order) // 4)
        top, bottom = order[:q], order[-q:]
        this = lambda keys: [c for k in keys for c in ents[k] if iso_week(c["day"]) == b]      # noqa: E731
        t_rows, b_rows = this(top), this(bottom)
        if not t_rows or not b_rows:
            continue
        tr, br = rate(t_rows, "reach2"), rate(b_rows, "reach2")
        tested.append(dict(last=a, this=b, top=tr, bottom=br, beat=tr > br, tie=tr == br, n_top=len(t_rows), n_bottom=len(b_rows)))
    xs, ys = [], []
    for rows in ents.values():
        if len(rows) < 2 * HALF_MIN:
            continue
        old, new = older_newer(rows)
        if len(old) >= HALF_MIN and len(new) >= HALF_MIN:
            xs.append(rate(old, "reach2"))
            ys.append(rate(new, "reach2"))
    rho = spearman(xs, ys)
    beats = sum(t["beat"] for t in tested)
    proven = bool(len(tested) >= 4 and beats / len(tested) > 0.5 and rho is not None and rho > 0)
    return dict(weeks=tested, beats=beats, tested=len(tested), rho=rho, rho_n=len(xs), proven=proven)


def board(contracts):
    means = market_means(contracts)
    stats = [summarize_entity(s, n, rows, means) for (s, n), rows in entity_rows(contracts).items()]
    ranked = sorted((s for s in stats if qualifies(s)), key=lambda s: (-s["score"], -s["n"], s["name"]))
    watching = sorted((s for s in stats if not qualifies(s)), key=lambda s: (-s["n"], s["name"]))
    top = ranked[:TOP_N]
    bottom = [s for s in reversed(ranked) if s not in top][:BOTTOM_N]
    by_sport = {sp: [s for s in ranked if s["sport"] == sp][:TOP_N] for sp in SPORTS}
    return dict(ranked=ranked, watching=watching, top=top, bottom=bottom, by_sport=by_sport, means=means,
                persistence=persistence(contracts), contracts=len(contracts), entities=len(stats))
