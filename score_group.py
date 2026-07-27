#!/usr/bin/env python3
"""score_group.py — backfill the Correct Score Group grid (grid_json) on pending picks.

Derives 6 grouped-score buckets from Sportzino/Altenar's exact "Correct score" market
(combining implied probabilities), marks the bucket the predicted score falls into, and
stores it as grid_json for the card's score-group grid.

Buckets mimic Sportzino's "Correct Score Group": {fav,dog} win 1-0/2-0/2-1, win 3-0/3-1/3-2,
draw 1-1/2-2/3-3, any other. Odds are APPROXIMATE (derived from exact scores, not the book's
own group price — that market isn't exposed via the API).

Usage:  .venv/bin/python score_group.py [YYYY-MM-DD]   (default: all pending picks)
Re-run any time markets reopen to fill odds that were dry.
"""
import sqlite3, urllib.request, json, time, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))
C = "culture=en-GB&timezoneOffset=300&integration=sportzino&deviceType=1&numFormat=en-GB&countryCode=US&stateCode=TX"
HDR = {"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120.0 Safari/537.36", "Referer": "https://sportzino.com/"}
CHAMPS = [11318, 4610, 3146, 2936, 2941, 2942, 2943, 2950, 2937]  # BRA, MLS, WC, EPL, LaLiga, SerieA, Ligue1, Bundes, Champ
HL, HB = ["1:0", "2:0", "2:1"], ["3:0", "3:1", "3:2"]
AL, AB = ["0:1", "0:2", "1:2"], ["0:3", "1:3", "2:3"]
DR = ["1:1", "2:2", "3:3"]


def _get(url, need_markets=False):
    for _ in range(4):
        try:
            j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=HDR)))
            if not need_markets or j.get("markets"):
                return j
        except Exception:
            pass
        time.sleep(1.5)
    return {}


import unicodedata
def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return [w[:5] for w in s.replace("-", " ").replace(".", " ").split() if len(w) > 2]

def event_index():
    idx = []
    for ch in CHAMPS:
        j = _get(f"https://sb2frontend-altenar2.biahosted.com/api/widget/GetEvents?{C}&champids={ch}")
        for e in j.get("events", []):
            idx.append((e["name"], e["id"]))
    return idx

def find_event(idx, match):
    if " v " not in match: return None
    h, a = [_norm(x) for x in match.split(" v ", 1)]
    for name, eid in idx:
        if " vs. " not in name: continue
        eh, ea = [_norm(x) for x in name.split(" vs. ", 1)]
        if any(t in eh for t in h) and any(t in ea for t in a):
            return eid
    return None


def derive_buckets(eid):
    j = _get(f"https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventDetails?{C}&eventId={eid}", need_markets=True)
    obj = {o["id"]: o for o in j.get("odds", [])}
    m = next((x for x in j.get("markets", []) if x.get("name", "").strip().lower() == "correct score"), None)
    if not m:
        return None
    od = {}
    for sub in m.get("desktopOddIds", []):
        for i in sub:
            if i in obj:
                od[obj[i]["name"]] = obj[i]["price"]
    if not od:
        return None
    comb = lambda ks: round(1 / sum(1 / od[k] for k in ks if k in od), 2) if any(k in od for k in ks) else None
    bucketed = set(HL + HB + AL + AB + DR)
    others = [v for k, v in od.items() if k not in bucketed]
    return {
        "home_low": comb(HL), "home_big": comb(HB),
        "away_low": comb(AL), "away_big": comb(AB),
        "draw": comb(DR), "other": round(1 / sum(1 / o for o in others), 2) if others else None,
    }


def bucket_of(h, a):
    if h == a:
        return "draw" if (h, a) in {(1, 1), (2, 2), (3, 3)} else "other"
    if h > a:
        return "home_low" if (h, a) in {(1, 0), (2, 0), (2, 1)} else "home_big" if (h, a) in {(3, 0), (3, 1), (3, 2)} else "other"
    return "away_low" if (h, a) in {(0, 1), (0, 2), (1, 2)} else "away_big" if (h, a) in {(0, 3), (1, 3), (2, 3)} else "other"


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else None
    c = sqlite3.connect(os.path.join(ROOT, "predictions.db"))
    q = "SELECT id,match,pred_score FROM predictions WHERE status='pending' AND pred_score IS NOT NULL"
    rows = c.execute(q + (" AND event_date=?" if date else ""), (date,) if date else ()).fetchall()
    idx = event_index()
    for pid, match, ps in rows:
        try:
            home, away = [x.strip() for x in match.split(" v ", 1)]
            h, a = [int(x) for x in ps.split("-")]
        except Exception:
            continue
        eid = find_event(idx, match)
        buckets = derive_buckets(eid) if eid else None
        grid = {"home": home, "away": away, "picked": bucket_of(h, a), "pred": ps, "buckets": buckets or {}}
        c.execute("UPDATE predictions SET grid_json=? WHERE id=?", (json.dumps(grid), pid))
        state = "odds OK" if buckets and any(buckets.values()) else "dry (no odds yet)"
        print(f"  {pid} {match}: picked {grid['picked']} | {state}")
    c.commit()
    c.close()


if __name__ == "__main__":
    main()
