"""Publish the follower's LIVE record per Production pair to the public repo (2026-11-04), for the Production page's "live v paper" column.

Runs on edge-vps (scripts/vps_live_record.sh), beside the follower. Reads the follower's own files (orders_placed.json for what was bought,
results.json for how each market settled, ledger.jsonl for why a lead was refused), joins them to the Production feeds' leads, and writes
data/live_record.json. Public fields only: per order a quote id (the Sandbox quote the lead came from), kickoff, side, outcome, the
return per $1 staked and the stake as a MULTIPLE of the pair's typical stake. No dollar amount, balance, order id, account or key.
It REFUSES to write (exit 1, nothing changed) if any value looks like one.

The live record is built from the follower's OWN orders (quantity x price paid + fee), never from results.json's cost column: that column
is the whole Kalshi position in the market, so when two lanes (or a hand order) hold one contract it prices one lane's bet with
the other's stake.
"""
import glob
import json
import os
import re
import sys
import datetime as dt

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "live_record.json")
FEEDS = ("production_leads", "soccer_rules_production_leads", "soccer_team_rules_production_leads", "econ_production_leads",
         "culture_production_leads", "nba_value_production_leads")
_FOUND = sorted(glob.glob(os.path.expanduser("~/poly*/orders_placed.json")))
SRC_DIR = os.path.expanduser(os.environ.get("LIVE_RECORD_DIR") or (os.path.dirname(_FOUND[0]) if _FOUND else "~/polymarket-src_dir"))

# A refused lead's reason text -> the public category. Order matters (first match wins).
REASONS = (
    (r"above max_price", "price above the cap"),
    (r"price moved", "price moved from the logged price"),
    (r"too close to kickoff", "published inside 30 min of kickoff"),
    (r"thin (book|ask)", "thin book"),
    (r"no edge", "no edge at today's price"),
    (r"entry window", "outside the entry window"),
    (r"out of band", "outside the price band"),
    (r"wide spread", "wide spread"),
    (r"already held|one order per correlated", "already held by another lane"),
    (r"no fill", "no seller at the price"),
    (r"exchange rejected|shard", "exchange rejected"),
    (r"halted|not listed", "market not open"),
)
FIELDS = {"id", "ko", "side", "st", "w", "r"}
STATES = {"won", "lost", "open", "sold", "unfilled", "unconfirmed"}
BAD = re.compile(r"\$|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
KEYLIKE = re.compile(r"[A-Za-z0-9+/_-]{64,}")


class Refused(Exception):
    pass


def category(reason):
    for rx, name in REASONS:
        if re.search(rx, reason or "", re.I):
            return name
    return "other"


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def feed_index():
    """({lead id: (pair, sandbox quote id)}, {pair: entered_at}) from the Production feeds."""
    leads, entered = {}, {}
    for name in FEEDS:
        blob = load(os.path.join(ROOT, "data", name + ".json"), {})
        for key, p in (blob.get("pairs") or {}).items():
            entered[key] = p.get("entered_at") or p.get("ready_at") or p.get("promoted_at")
        for lid, l in (blob.get("leads") or {}).items():
            if l.get("pair"):
                leads[l.get("id") or lid] = (l["pair"], l.get("sandbox_quote"))
    return leads, entered


def refusals(path, leads):
    """{quote id: category} for the last refusal of each lead, from the follower's ledger."""
    last = {}
    try:
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("kind") in ("veto", "filtered") and d.get("id") in leads:
                    last[d["id"]] = category(d.get("reason"))
    except OSError:
        pass
    return {leads[i][1]: c for i, c in last.items() if leads[i][1]}


def order_row(key, o, res, kres=None):
    lead = o.get("lead") or {}
    qty = o.get("filled")
    if qty is None:
        qty = o.get("actual_qty")
    px = o.get("avg_px") or o.get("actual_avg_px") or o.get("price")
    fee = o.get("commission") or 0.0
    state = o.get("order_state")
    base = dict(id=lead.get("sandbox_quote") or "", ko=str(lead.get("kickoff") or "")[:16], side=str(o.get("side") or "").lower() or None)
    if o.get("state") == "unfilled" or state in ("ORDER_STATE_CANCELED", "ORDER_STATE_EXPIRED") and not qty:
        return dict(base, st="unfilled", w=None, r=None), None
    if not qty or not px or state is None:
        return dict(base, st="unconfirmed", w=None, r=None), None
    stake = qty * px + fee
    row = res.get(key) or {}
    if row.get("closed_by_sale"):
        return dict(base, st="sold", w=None, r=None), stake
    market = str(o.get("market") or "")
    side = str(o.get("side") or "").lower()
    kalshi = market.startswith("KX") and side in ("yes", "no")
    got = (kres or {}).get(market) if kalshi else None
    if kalshi and got is None:
        return dict(base, st="open", w=None, r=None), stake      # not settled on the exchange yet
    if got is not None:
        # Kalshi's own settled result for the contract, against the side this order bought: a contract another lane holds on
        # the other side (A7 over 3.5 YES v the o35 NO) leaves results.json's position-wide P&L with the wrong sign.
        won = (got == "yes") == (side == "yes")
    elif row.get("resolved") and row.get("market_settled"):
        won = (row.get("realised") or 0) > 0       # older orders (no side recorded) and non-Kalshi markets
    else:
        return dict(base, st="open", w=None, r=None), stake
    pnl = qty * (1 - px) - fee if won else -(qty * px) - fee
    return dict(base, st="won" if won else "lost", r=round(pnl / stake, 4)), stake


KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets/"
CACHE = os.path.expanduser(os.environ.get("LIVE_RECORD_CACHE") or "~/live_record_results.json")


def kalshi_result(ticker):
    """'yes' / 'no' once Kalshi has settled the market, else None. A public, unauthenticated read."""
    import urllib.request
    req = urllib.request.Request(KALSHI + ticker, headers={"User-Agent": "edge-machine-live-record"})
    with urllib.request.urlopen(req, timeout=10) as r:
        m = (json.loads(r.read()) or {}).get("market") or {}
    return m.get("result") if m.get("status") in ("finalized", "settled") and m.get("result") in ("yes", "no") else None


def results_for(tickers, fetch=None, cache_path=None):
    """{ticker: 'yes'|'no'} for the tickers Kalshi has settled; settled results are cached, so each market is read once."""
    fetch = fetch or kalshi_result
    cache_path = CACHE if cache_path is None else cache_path
    cache = load(cache_path, {}) if cache_path else {}
    for tk in sorted(tickers):
        if tk not in cache:
            try:
                got = fetch(tk)
            except Exception:                                  # noqa: BLE001
                got = None
            if got:
                cache[tk] = got
    if cache_path:
        try:
            with open(cache_path, "w") as f:
                json.dump(cache, f)
        except OSError:
            pass
    return cache


def lane_rows(src_dir, fetch=None, cache_path=None):
    """The own-state lanes (o35, nba_wm), {lane: [order rows]}. Stake and price are the lane's own fill; the outcome is the
    market's settled result from Kalshi's public API, so a contract another lane also holds does not blur it. A bet with a
    sale or a resting take-profit filled is left out ('sold'). Fees are not in these rows."""
    o35 = load(os.path.join(src_dir, "o35_state.json"), {}).get("matches") or {}
    wm = load(os.path.join(src_dir, "nba_wm_state.json"), {}).get("matches") or {}
    tickers = {tk for tk, m in o35.items() if m.get("filled")} | {k.split(":", 1)[1] for k, m in wm.items() if m.get("filled")}
    res = results_for(tickers, fetch, cache_path)
    out = {"o35_cheap_no": [], "nba_wm_yes": [], "nba_wm_nofade": []}

    def row(lane, tk, ko, side, px, sold):
        base = dict(id=tk, ko=ko, side=side)
        if sold:
            out[lane].append(dict(base, st="sold", w=None, r=None))
        elif tk not in res:
            out[lane].append(dict(base, st="open", w=None, r=None))
        else:
            won = (res[tk] == "yes") == (side == "yes")
            out[lane].append(dict(base, st="won" if won else "lost", w=1.0, r=round((1 - px) / px if won else -1.0, 4)))

    def when(t):
        return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M") if t else ""

    for tk, m in o35.items():
        px = (m.get("bid") or {}).get("price")
        if m.get("filled") and px:
            row("o35_cheap_no", tk, when(m.get("kickoff")), "no", px, bool(m.get("sells")))
    for key, m in wm.items():
        side, tk = key.split(":", 1)
        px = (m.get("bid") or {}).get("price") if side == "no" else (m.get("buy") or {}).get("ask")
        if m.get("filled") and px:
            row("nba_wm_nofade" if side == "no" else "nba_wm_yes", tk, when(m.get("tip")), side, px, bool(m.get("sold_covered")))
    return {k: sorted(v, key=lambda r: (r["ko"], r["id"])) for k, v in out.items()}


def build(src_dir=SRC_DIR, fetch=None, cache_path=None):
    orders = load(os.path.join(src_dir, "orders_placed.json"), {})
    res = {r.get("pick_id"): r for r in (load(os.path.join(src_dir, "results.json"), {}).get("rows") or [])}
    leads, entered = feed_index()
    mine = {k: o for k, o in orders.items() if (o.get("lead") or {}).get("pair") in entered}
    kres = results_for({o.get("market") for o in mine.values() if str(o.get("market") or "").startswith("KX")}, fetch, cache_path)
    by_pair = {}
    for key, o in mine.items():
        by_pair.setdefault(o["lead"]["pair"], []).append(order_row(key, o, res, kres))
    out = {}
    for pair in sorted(entered):
        got = by_pair.get(pair, [])
        paid = sorted(st for _r, st in got if st)
        typical = paid[len(paid) // 2] if paid else None
        mine = []
        for row, stake in sorted(got, key=lambda g: (g[0]["ko"], str(g[0]["id"]))):
            row["w"] = round(stake / typical, 2) if stake and typical else None
            mine.append(row)
        out[pair] = dict(entered=entered[pair], orders=mine, refused={})
    refused = refusals(os.path.join(src_dir, "ledger.jsonl"), leads)
    placed = {r["id"] for blob in out.values() for r in blob["orders"] if r["st"] not in ("unfilled",)}
    for lid, (pair, quote) in leads.items():
        if pair in out and quote and quote in refused and quote not in placed:
            out[pair]["refused"][quote] = refused[quote]
    # Orders the follower placed on a pair that is NOT in a Production feed any more (pulled back to the Sandbox, or a scope that was in
    # Production and left): its own live fills, kept under its own pair name so they are never read as another scope's (2026-11-06: the Clubs
    # under 3.5 orders next to the Internationals pair, which has none).
    gone = {k: o for k, o in orders.items() if (o.get("lead") or {}).get("pair") and o["lead"]["pair"] not in entered and "|" in o["lead"]["pair"]}
    gone_res = results_for({o.get("market") for o in gone.values() if str(o.get("market") or "").startswith("KX")}, fetch, cache_path)
    pulled = {}
    for key, o in gone.items():
        row, _stake = order_row(key, o, res, gone_res)
        pulled.setdefault(o["lead"]["pair"], []).append(row)
    pulled = {p: sorted(rows, key=lambda r: (r["ko"], str(r["id"]))) for p, rows in sorted(pulled.items())}
    return dict(generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), pairs=out, pulled=pulled,
                lanes=lane_rows(src_dir, fetch, cache_path),
                lane_note="own-state lanes: the lane's own fill price; outcome from the market's settled result; sold bets left out; fees not included")


def check(blob):
    for pair, p in blob["pairs"].items():
        for r in p["orders"]:
            if set(r) - FIELDS or r["st"] not in STATES:
                raise Refused(f"{pair}: an order carries a field or state outside the whitelist")
            for k, v in r.items():
                if isinstance(v, str) and (BAD.search(v) or KEYLIKE.search(v)):
                    raise Refused(f"{pair}.{k}: dollar sign or id/key-like string")
                if k == "w" and v is not None and not 0 < v < 1000:
                    raise Refused(f"{pair}: stake multiple {v} is out of range")
                if k == "r" and v is not None and not -1.5 < v < 100:
                    raise Refused(f"{pair}: return {v} is out of range")
        for q, c in p["refused"].items():
            if BAD.search(str(q)) or c not in {n for _r, n in REASONS} | {"other"}:
                raise Refused(f"{pair}: refusal entry outside the whitelist")


def check_pulled(blob):
    for pair, rows in (blob.get("pulled") or {}).items():
        if BAD.search(pair) or KEYLIKE.search(pair):
            raise Refused(f"pulled pair name {pair!r} is outside the whitelist")
        for r in rows:
            if set(r) - FIELDS or r["st"] not in STATES or any(isinstance(v, str) and (BAD.search(v) or KEYLIKE.search(v)) for v in r.values()):
                raise Refused(f"{pair}: a pulled-pair order carries a field, state or value outside the whitelist")


def check_lanes(blob):
    for lane, rows in blob.get("lanes", {}).items():
        for r in rows:
            if set(r) - FIELDS or r["st"] not in STATES or any(isinstance(v, str) and (BAD.search(v) or KEYLIKE.search(v)) for v in r.values()):
                raise Refused(f"{lane}: an entry carries a field, state or value outside the whitelist")


def main(argv=None):
    blob = build()
    check(blob)
    check_lanes(blob)
    check_pulled(blob)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, OUT)
    print(f"live record: {sum(len(p['orders']) for p in blob['pairs'].values())} orders across {len(blob['pairs'])} pairs")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as e:
        print("refused:", e)
        sys.exit(1)
