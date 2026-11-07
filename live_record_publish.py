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
import math
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
# An own-state lane row also carries the legs it sold ("", "2x", "3x", "2x+3x", "sold"), the same entry held to settlement (YES split only)
# and where its sells come from: "fills" (the sell fills the follower logged) or "reconstructed" (data/live_reconstructed.json).
LANE_FIELDS = FIELDS | {"legs", "hold_r", "src"}
LEGS = {"", "2x", "3x", "2x+3x", "sold"}
SRCS = {"fills", "reconstructed"}
STATES = {"won", "lost", "open", "sold", "unfilled", "unconfirmed"}
RECON = os.path.join(ROOT, "data", "live_reconstructed.json")
RECON_BEFORE = "2026-11-06T18:07"      # per-sell fill logging went live on the VPS at this instant (UTC): earlier tips are reconstructed
LANES = ("o35_cheap_no", "nba_wm_yes", "nba_wm_nofade", "top5_dip")
# Kalshi's fee per contract, as the follower models it (0.07 p (1-p) rounded up to $0.0001; a resting fill pays a quarter), so the live
# record is after fees on the same footing as the paper one.
FEE_CAP, FEE_TAKER, FEE_MAKER_SHARE, FEE_GRID = 0.035, 0.07, 0.25, 0.0001
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


def fee_per_contract(price, taker=True):
    f = min(FEE_CAP, math.ceil(round(FEE_TAKER * price * (1.0 - price) / FEE_GRID, 9)) * FEE_GRID)
    return round(f if taker else f * FEE_MAKER_SHARE, 6)


def _legs(names):
    got = sorted({n for n in names if n in ("2x", "3x")})
    return "+".join(got) if got else ("sold" if names else "")


def own_trade(side, px, qty, buy_taker, sell_fills, result, split=False):
    """One own-state entry as a TRADE: ({st, r, legs, hold_r}, stake per contract basis) from the follower's logged sell fills.

    Cost is the contracts bought at the price paid plus the buy fee; proceeds are the logged sells (size x price, less their fee) plus
    the unsold remainder at the market's settled value (1 if it settled to this side, else 0; no fee at settlement). Open while a
    remainder is unsettled. Won = the realised return after fees is above zero: a bet sold at its target is won whatever the market
    later did, and a bet held to a lost settlement is lost."""
    stake = qty * px + qty * fee_per_contract(px, buy_taker)
    sells = list((sell_fills or {}).values())
    sold = min(qty, sum(float(x.get("size") or 0) for x in sells))
    proceeds = sum(float(x.get("size") or 0) * float(x.get("price") or 0) - float(x.get("fee") or 0) for x in sells)
    rem = max(0.0, qty - sold)
    legs = _legs([x.get("leg") for x in sells if float(x.get("size") or 0) > 0.004])
    if rem > 0.004 and result is None:
        return dict(st="open", r=None, legs=legs, hold_r=None), stake
    payout = 1.0 if result == side else 0.0
    ret = (proceeds + rem * payout - stake) / stake
    hold = round((qty * payout - stake) / stake, 4) if split and result else None
    return dict(st="won" if ret > 0 else "lost", r=round(ret, 4), legs=legs, hold_r=hold), stake


def load_reconstructed(path=None):
    """{(lane, ticker): row} from the committed reconstruction of the orders that predate per-sell fill logging."""
    blob = load(RECON if path is None else path, {}) or {}
    return {(r.get("lane"), r.get("id")): r for r in blob.get("rows") or []}


def lane_rows(src_dir, fetch=None, cache_path=None, recon=None):
    """The own-state lanes (o35, nba_wm, the top-5 dip), {lane: [order rows]}.

    Each row is the entry as a TRADE after fees: the lane's own buy fill, the sells the follower logged (state `sell_fills`: size and
    price of every piece) and the unsold remainder at the market's settled result from Kalshi's public API. An entry from before the
    logging (tip before RECON_BEFORE) has no sell_fills of its own; it is read from the committed reconstruction (src "reconstructed")."""
    o35 = load(os.path.join(src_dir, "o35_state.json"), {}).get("matches") or {}
    wm = load(os.path.join(src_dir, "nba_wm_state.json"), {}).get("matches") or {}
    t5 = load(os.path.join(src_dir, "top5_dip_state.json"), {}).get("matches") or {}
    recon = load_reconstructed() if recon is None else recon
    tickers = ({tk for tk, m in o35.items() if m.get("filled")} | {k.split(":", 1)[1] for k, m in wm.items() if m.get("filled")}
               | {tk for tk, m in t5.items() if m.get("filled")})
    res = results_for(tickers, fetch, cache_path)
    out = {lane: [] for lane in LANES}
    stakes = {lane: [] for lane in LANES}

    def when(t):
        return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M") if t else ""

    def row(lane, tk, ko, side, px, qty, buy_taker, m):
        base = dict(id=tk, ko=ko, side=side)
        old = recon.get((lane, tk))
        if not m.get("sell_fills") and old is not None and ko < RECON_BEFORE:
            keep = {k: old.get(k) for k in ("st", "r", "w", "legs", "hold_r") if k in old}
            if lane != "nba_wm_yes":
                keep["hold_r"] = None                 # the hold control is the YES split's (the other lanes' sells are their rule)
            out[lane].append(dict(base, src="reconstructed", **keep))
            stakes[lane].append(None)
            return
        trade, stake = own_trade(side, px, qty, buy_taker, m.get("sell_fills"), res.get(tk), split=(lane == "nba_wm_yes"))
        out[lane].append(dict(base, src="fills", w=None, **trade))
        stakes[lane].append(stake)

    for tk, m in o35.items():
        px = (m.get("bid") or {}).get("price")
        if m.get("filled") and px:
            row("o35_cheap_no", tk, when(m.get("kickoff")), "no", px, m["filled"], False, m)
    for key, m in wm.items():
        side, tk = key.split(":", 1)
        px = (m.get("bid") or {}).get("price") if side == "no" else (m.get("buy") or {}).get("ask")
        if m.get("filled") and px:
            row("nba_wm_nofade" if side == "no" else "nba_wm_yes", tk, when(m.get("tip")), side, px, m["filled"], side == "yes", m)
    for tk, m in t5.items():
        px = (m.get("bid") or {}).get("price")
        if m.get("filled") and px:
            row("top5_dip", tk, when(m.get("kickoff")), "yes", px, m["filled"], False, m)
    for lane in LANES:
        paid = sorted(s for s in stakes[lane] if s)
        med = paid[len(paid) // 2] if paid else None
        for r, s in zip(out[lane], stakes[lane]):
            if s is not None:
                r["w"] = round(s / med, 2) if med else None
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
                lane_note=("own-state lanes: each entry as a trade after fees (the lane's own fill, the sells it logged, the unsold remainder at the market's settled "
                           "result); a bet is won when its realised return is above zero. Entries with a tip before 2026-11-06 18:07Z are reconstructed "
                           "from the exchange order list; later ones use the sell fills the follower logged"))


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
            if set(r) - LANE_FIELDS or r["st"] not in STATES or any(isinstance(v, str) and (BAD.search(v) or KEYLIKE.search(v)) for v in r.values()):
                raise Refused(f"{lane}: an entry carries a field, state or value outside the whitelist")
            if r.get("legs", "") not in LEGS or r.get("src", "fills") not in SRCS:
                raise Refused(f"{lane}: legs or source outside the whitelist")
            for k, lo, hi in (("w", 0, 1000), ("r", -1.5, 100), ("hold_r", -1.5, 100)):
                v = r.get(k)
                if v is not None and not (isinstance(v, (int, float)) and lo < v < hi):
                    raise Refused(f"{lane}: {k} {v!r} is out of range")


def check_reconstructed(blob):
    """The committed reconstruction is public too: the same whitelist, and nothing but the fields written here."""
    if not isinstance(blob, dict):
        raise Refused("reconstruction is not an object")
    check_lanes({"lanes": {"reconstructed": [{k: v for k, v in r.items() if k != "lane"} for r in blob.get("rows") or []]}})
    for r in blob.get("rows") or []:
        if r.get("lane") not in LANES:
            raise Refused("reconstruction: a row names a lane outside the whitelist")
    if BAD.search(str(blob.get("header"))):
        raise Refused("reconstruction: the header carries a dollar sign or id")


def main(argv=None):
    check_reconstructed(load(RECON, {}) or {})
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
