"""Publish the S&P 500 opening sweep executor's decision snapshots to the public repo (2026-11-17, for the live-vs-paper read).

Runs on edge-vps from the SAME user crontab entry as the NBA and top-5 snapshots (scripts/vps_nba_wm_decisions.sh calls it after the others), so no
crontab line is added: it reads the executor's own file (sp_sweep_decisions.json, never its ledger), checks it against a WHITELIST, and writes
data/sp_sweep_decisions.json. It REFUSES to write (exit 1, nothing changed) if any record carries a field outside the whitelist, a value that is
not a plain string, number or boolean, a dollar sign, an order-id-like or key-like string, or a number outside a sane range. Public market
fields only: prices as fractions of 1, contract counts, seconds, no balance, order id, account, shard or dollar figure.
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
_FOUND = sorted(glob.glob(os.path.expanduser("~/poly*/sp_sweep_decisions.json")))
SRC = os.path.expanduser(os.environ.get("SP_SWEEP_DECISIONS") or (_FOUND[0] if _FOUND else "~/sp_sweep_decisions.json"))
OUT = os.path.join(ROOT, "data", "sp_sweep_decisions.json")
FIELDS = {"lane", "bot_version", "ticker", "day", "open", "decided_at", "outcome", "why", "rule_ok", "rest_s", "fill_side", "fill_s", "fill_price",
          "qty", "sold", "sold_price", "exit", "result", "limit", "target", "crossed"}
LANES = {"sp_sweep_10c"}
OUTCOMES = {"entered", "no_fill", "veto", "late"}
TICKER = re.compile(r"^KXINX15M-[0-9]{2}[A-Z]{3}[0-9]{6}-[A-Z0-9]+$")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
KEYLIKE = re.compile(r"[A-Za-z0-9+/_-]{32,}")
PRICE_FIELDS = {"fill_price", "sold_price", "limit", "target"}


class Refused(Exception):
    pass


def check_record(key, r):
    if not isinstance(r, dict):
        raise Refused(f"{key}: not a record")
    extra = set(r) - FIELDS
    if extra:
        raise Refused(f"{key}: fields outside the whitelist: {sorted(extra)}")
    if r.get("lane") not in LANES or r.get("outcome") not in OUTCOMES or not TICKER.match(str(r.get("ticker"))):
        raise Refused(f"{key}: lane, outcome or ticker is not a known one")
    for k, v in r.items():
        if v is None or isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            if k in PRICE_FIELDS and not 0.0 <= v <= 1.0:
                raise Refused(f"{key}.{k}: {v} is not a price")
            if k not in PRICE_FIELDS and not -100000 <= v <= 100000:
                raise Refused(f"{key}.{k}: {v} is out of range")
            continue
        if isinstance(v, list):
            if not all(isinstance(x, str) and x in ("yes", "no") for x in v):
                raise Refused(f"{key}.{k}: not a plain value")
            continue
        if not isinstance(v, str):
            raise Refused(f"{key}.{k}: not a plain value")
        if "$" in v or UUID.search(v) or (k not in ("ticker",) and KEYLIKE.search(v)):
            raise Refused(f"{key}.{k}: carries a dollar sign or an id/key-like string")


def sanitise(blob):
    if not isinstance(blob, dict) or not isinstance(blob.get("decisions"), dict):
        raise Refused("no decisions block")
    out = {}
    for key in sorted(blob["decisions"]):
        check_record(key, blob["decisions"][key])
        out[key] = blob["decisions"][key]
    return dict(version=1, updated_at=blob.get("updated_at"), decisions=out)


def main(argv=None):
    try:
        with open(SRC) as f:
            blob = json.load(f)
    except FileNotFoundError:
        print("no S&P sweep decisions file yet; nothing to publish")
        return 0
    except (OSError, ValueError) as e:
        print("S&P sweep decisions file unreadable:", type(e).__name__)
        return 1
    try:
        clean = sanitise(blob)
    except Refused as e:
        print("REFUSED:", e)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(clean, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, OUT)
    print("published", len(clean["decisions"]), "S&P sweep decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
