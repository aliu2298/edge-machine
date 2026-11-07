"""1-min SIP RTH bars for the Kalshi Invest stocks, 2023-01-01..2026-11-06 -> bars/SYM.npz (t epoch-min, o,h,l,c,v)."""
import sys, os, json, time, urllib.parse, datetime as dt, threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np
sys.path.insert(0, "/Users/oluwarotimialiu/Predictions/.claude/worktrees/trusting-wozniak-d1a022")
import market_sources as M
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
SY = [s.strip() for s in open("symbols.txt") if s.strip()]
lock = threading.Lock(); last = [0.0]
def get(url):
    with lock:                       # ~180 req/min across threads
        w = last[0] + 0.34 - time.time()
        if w > 0: time.sleep(w)
        last[0] = time.time()
    return M._get(url, tries=5, timeout=60)
def one(sym):
    out = f"bars/{sym}.npz"
    if os.path.exists(out): return sym, "cached"
    rows, page = [], None
    while True:
        q = {"symbols": sym, "timeframe": "1Min", "start": "2023-01-01T00:00:00Z", "end": "2026-11-06T22:00:00Z",
             "limit": 10000, "feed": "sip", "adjustment": "split"}
        if page: q["page_token"] = page
        d = get(f"{M.DATA_HOST}/v2/stocks/bars?{urllib.parse.urlencode(q)}")
        for b in (d.get("bars") or {}).get(sym, []):
            t = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
            m = t.hour * 60 + t.minute
            if 570 <= m < 960:
                rows.append((int(dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).timestamp() // 60), b["o"], b["h"], b["l"], b["c"], b["v"]))
        page = d.get("next_page_token")
        if not page: break
    if not rows:
        return sym, "NO BARS"
    a = np.array(rows, dtype=float)
    np.savez_compressed(out, t=a[:, 0].astype(np.int64), o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], v=a[:, 5])
    return sym, len(rows)
with ThreadPoolExecutor(8) as ex:
    for sym, n in ex.map(one, SY):
        print(sym, n, flush=True)
print("DONE")
