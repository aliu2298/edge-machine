"""Culture lanes (2026-10-16): paper records on Kalshi's Entertainment, Mentions and Social markets.

Registered by Olu to OBSERVE, in the Sandbox only, on its own Culture tab. Four lanes, one ledger
(data/culture_ledger.json), read hourly by .github/workflows/culture.yml:

  culture_fav_band   the favourite at 0.70-0.80, spread <=5c, 2-48h before the close; one per event
  culture_endgame    the favourite at 0.90-0.97, spread <=3c, 1-24h before the close; one per event
  mentions_rate      "What will Trump say": P(said in the time left) from his own transcripts
                     (Roll Call Factbase), bought where it beats the ask plus fee by 5c; one per market
  rt_model           Rotten Tomatoes ladders: the final Tomatometer modelled from the live critic count
                     (beta-binomial on the reviews still to come), the rung with the largest edge, 5c+

Why each, measured on 4,558 settled culture markets (2026-08-11..10-16) before anything was built:
24h out, ~70% of culture markets already sit under 5c or over 95c and most of the rest are wide,
so the 0.70-0.80 band held 8 events in two months (7-1, +18%, z +0.94) and 0.90-0.97 held 57
(98.2%, +3.3%, z +1.20). Kalshi closes a mentions market the moment the word is said, so
mentions_rate prices what is still to come. Rotten Tomatoes counts are not kept historically, so
rt_model's snapshots (data/rt_snapshots.json) ARE the collector; its model is uncalibrated until
they accumulate. Every record is paper, at the ask, with Kalshi's 7% fee; nothing is promoted.
"""
import datetime as dt
import html as _html
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter

import daily_track as D

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "culture_ledger.json")
SNAPS = os.path.join(ROOT, "data", "rt_snapshots.json")
UA = {"User-Agent": "Mozilla/5.0 (edge-machine culture research)"}
CATEGORIES = ("Entertainment", "Mentions", "Social")
FEE = 0.07
EDGE_MIN = 0.05
LANES = {
    "culture_fav_band": "Culture favourite band",
    "culture_endgame": "Culture endgame",
    "mentions_rate": "Trump mentions",
    "rt_model": "Rotten Tomatoes model",
}
RULES = {
    "culture_fav_band": "Back the favourite (YES or NO) priced 0.70-0.80 at the ask, spread 5c or less, "
                        "2 to 48 hours before the close. The cheapest qualifying contract per event, ties by "
                        "ticker. One frozen paper entry per event.",
    "culture_endgame": "Back the favourite priced 0.90-0.97 at the ask, spread 3c or less, 1 to 24 hours "
                       "before the close. One frozen paper entry per event. One loss costs about 19 wins.",
    "mentions_rate": "Kalshi 'What will Trump say' markets. P(said before the close) = 1 - (1 - r)^days left, "
                     "r = share of the last 84 days on which his Factbase transcripts hold the word (exact, "
                     "plural or possessive). Buy YES or NO where P beats the ask plus fee by 5c, only on "
                     "markets priced 10-90c. One frozen entry per market.",
    "rt_model": "Kalshi Rotten Tomatoes ladders. The final Tomatometer = (liked + X) / (reviews + M), X "
                "beta-binomial on the live critic count, M the reviews expected before the close (the "
                "collector's own measured pace, halved; no bet until 12h of snapshots exist). The rung with the largest edge after fee, 5c+, "
                "20+ reviews counted. One frozen entry per film.",
}
FAV_BAND, FAV_SPREAD, FAV_HOURS = (0.70, 0.80), 0.05, (2, 48)
END_BAND, END_SPREAD, END_HOURS = (0.90, 0.97), 0.03, (1, 24)
MENTION_SERIES = ("KXTRUMPSAY", "KXTRUMPSAYMONTH", "KXTRUMPSAYCOMPANY", "KXTRUMPSAYCOUNTRY")
RT_SERIES = ("KXRT", "KXRTTV")
RATE_DAYS = 84
RT_MIN_REVIEWS = 20
P_CLAMP = (0.05, 0.95)          # rt_model never claims more certainty than this (2026-10-20)
# One market, one side, one lane (2026-10-20). Before a lane logs, every Culture lane's picks,
# open or settled, are checked for that ticker; within one scan the lanes run in this order,
# so the more specific claim gets a market first.
PRIORITY = ("mentions_rate", "culture_endgame", "rt_model", "culture_fav_band")
FACTBASE = ("https://rollcall.com/wp-json/factbase/v1/search?media=&type=&sort=date&location=all"
            "&place=all&format=json&page={page}&q={q}")


def fee(p):
    return FEE * p * (1 - p)


def ts(raw):
    x = D.instant(raw)
    return x.astimezone(dt.timezone.utc) if x else None


def web(url, tries=3, sleep=time.sleep):
    """A public page or JSON outside Kalshi (Rotten Tomatoes, Factbase)."""
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:                                  # noqa: BLE001
            last = e
            sleep(1.5 * (i + 1))
    raise last


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "culture-v1", "lanes": {k: {"picks": [], "observations": {}, "error": None} for k in LANES},
            "rt_urls": {}, "words": {}}


def load_snaps(path=SNAPS):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def quote(m):
    """(yes_bid, yes_ask) off a market row, or None."""
    a, b = D.number(m.get("yes_ask_dollars")), D.number(m.get("yes_bid_dollars"))
    if a is None or b is None or not 0 < b < a <= 1:
        return None
    return b, a


def entry(m, ev, side, price, now, detail="", **extra):
    if isinstance(m.get("floor_strike"), (int, float)) and m.get("strike_type"):
        extra.setdefault("strike", m["floor_strike"])
        extra.setdefault("strike_type", m["strike_type"])
    return dict(id=m["ticker"], event=m.get("event_ticker") or ev.get("event_ticker"),
                series=ev.get("series_ticker"), name=ev.get("title") or m.get("title"),
                title=m.get("yes_sub_title") or m.get("title"), side=side, price=round(price, 4),
                close=m.get("close_time"), logged=now.isoformat(), status="open", detail=detail,
                category=ev.get("category"), **extra)


# ------------------------------------------------------------------ the favourite bands
def band_picks(events, now, band, spread, hours, lane):
    """Favourite in `band` per event, cheapest first, ties by ticker. -> (picks, reason counts)."""
    lo, hi = band
    counts, best = Counter(), {}
    for ev in events:
        for m in ev.get("markets") or []:
            if m.get("status") not in ("active", "open"):
                counts["not active"] += 1
                continue
            close = ts(m.get("close_time"))
            if not close or not hours[0] <= (close - now).total_seconds() / 3600 <= hours[1]:
                counts["outside the entry window"] += 1
                continue
            q = quote(m)
            if not q or q[1] - q[0] > spread + 1e-9:
                counts["no quote or spread too wide"] += 1
                continue
            got = False
            for side, px in (("yes", q[1]), ("no", round(1 - q[0], 4))):
                if lo - 1e-9 <= px <= hi + 1e-9:
                    got = True
                    key = m.get("event_ticker") or ev.get("event_ticker")
                    cand = (px, m["ticker"], side, m, ev)
                    if key not in best or cand[:2] < best[key][:2]:
                        best[key] = cand
            counts["in band" if got else "outside the band"] += 1
    return [entry(m, ev, side, px, now, detail=f"{side.upper()} {px:.2f} · {lane}")
            for px, _t, side, m, ev in sorted(best.values(), key=lambda c: (c[1],))], counts


# ------------------------------------------------------------------ Trump mentions
def terms(word):
    """'Zohran / Mamdani' -> ['Zohran', 'Mamdani']: either one satisfies the contract."""
    return [t.strip() for t in str(word or "").split("/") if t.strip()]


def term_re(term):
    """The exact term, or its plural or possessive (the contract's own rule), case-insensitive.
    Grammatical and tense inflections do not count, so nothing else is allowed."""
    core = r"\s+".join(re.escape(w) for w in term.split())
    return re.compile(r"(?<![\w])" + core + r"(?:s|es|'s|s'|’s)?(?![\w])", re.I)


def said_days(word, now, fetch=web, max_pages=12):
    """Dates (YYYY-MM-DD) in the last RATE_DAYS on which a Factbase record holds the word."""
    cutoff = (now - dt.timedelta(days=RATE_DAYS)).date().isoformat()
    days = set()
    for t in terms(word):
        rx = term_re(t)
        for page in range(1, max_pages + 1):
            raw = fetch(FACTBASE.format(page=page, q=urllib.parse.quote('"' + t + '"')))
            data = (json.loads(raw) or {}).get("data") or []
            if not data:
                break
            older = False
            for r in data:
                d = str(r.get("date") or "")[:10]
                if d and d < cutoff:
                    older = True
                    continue
                if d and r.get("candidate") in (None, "Donald Trump") and rx.search(_html.unescape(str(r.get("text") or ""))):
                    days.add(d)
            if older:
                break
    return sorted(days)


def mention_prob(days, opened, close, now):
    """P(the word is said between now and the close). Said already inside the window -> 0.98
    (the market should be closing; Factbase is day-resolution and posts hours late)."""
    if opened and any(d >= opened.date().isoformat() for d in days):
        return 0.98, "said already this window"
    left = max(0.0, (close - now).total_seconds() / 86400)
    r = len(days) / RATE_DAYS
    return 1 - (1 - r) ** left, f"said on {len(days)} of the last {RATE_DAYS} days, {left:.1f} days left"


def mention_picks(events, now, state, fetch=web):
    counts, out = Counter(), []
    cache = state.setdefault("words", {})
    for ev in events:
        if ev.get("series_ticker") not in MENTION_SERIES:
            continue
        for m in ev.get("markets") or []:
            if m.get("status") not in ("active", "open"):
                continue
            close, opened = ts(m.get("close_time")), ts(m.get("open_time"))
            if not close or (close - now).total_seconds() < 6 * 3600:
                counts["closes within 6h"] += 1
                continue
            q = quote(m)
            if not q or q[1] - q[0] > 0.05 + 1e-9:
                counts["no quote or spread too wide"] += 1
                continue
            # Near-certain prices carry what the transcripts miss: Kalshi's sources include news
            # quotes and Truth Social, and Factbase spells nicknames its own way ("Newscum" read
            # 0 days on 2026-10-16 while Kalshi sat at 99c, said). Only uncertain markets.
            if q[0] >= 0.90 or q[1] <= 0.10:
                counts["already near-certain (under 10c or over 90c)"] += 1
                continue
            word = (m.get("custom_strike") or {}).get("Word") or m.get("yes_sub_title")
            c = cache.get(word)
            if not c or (now - ts(c["at"])).total_seconds() > 6 * 3600:
                try:
                    c = cache[word] = dict(at=now.isoformat(), days=said_days(word, now, fetch))
                except Exception as e:                          # noqa: BLE001
                    counts["transcript search failed"] += 1
                    continue
            p, why = mention_prob(c["days"], opened, close, now)
            yes_edge = p - (q[1] + fee(q[1]))
            no_px = round(1 - q[0], 4)
            no_edge = (1 - p) - (no_px + fee(no_px))
            side, px, edge = ("yes", q[1], yes_edge) if yes_edge >= no_edge else ("no", no_px, no_edge)
            if edge < EDGE_MIN - 1e-9:
                counts["edge under 5c"] += 1
                continue
            counts["edge 5c+"] += 1
            out.append(entry(m, ev, side, px, now, detail=f"P(said) {p:.2f} · {why} · edge {edge:+.2f}",
                             model=round(p, 4), edge=round(edge, 4)))
    return out, counts


# ------------------------------------------------------------------ Rotten Tomatoes
RT_TITLE = re.compile(r"\s*(rotten tomatoes|tomatometer).*$", re.I)


def rt_name(ev, m):
    """The title Kalshi names: 'Street Fighter Rotten Tomatoes score?' -> 'Street Fighter'."""
    for raw in (m.get("title"), ev.get("title")):
        name = RT_TITLE.sub("", str(raw or "")).split(" · ")[0].strip(" ?:-")
        if name:
            return name
    return None


def rt_search(name, kind, fetch=web):
    """The Rotten Tomatoes URL for a title: the first exact-title result of the right kind."""
    page = fetch("https://www.rottentomatoes.com/search?search=" + urllib.parse.quote(name))
    want = "/tv/" if kind == "tv" else "/m/"
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", _html.unescape(s).lower()).strip()
    for body in re.findall(r"<search-page-media-row[^>]*>(.*?)</search-page-media-row>", page, re.S):
        href = re.search(r'href="(https://www\.rottentomatoes\.com/[^"]+)"', body)
        title = re.search(r'slot="title"[^>]*>\s*([^<]+)', body)
        if href and title and want in href.group(1) and norm(title.group(1)) == norm(name):
            return href.group(1)
    return None


def rt_counts(url, fetch=web):
    """(liked, reviews, displayed score) off a title page, or None before any review."""
    page = fetch(url)
    m = re.search(r'"criticsScore":\{(.*?)\}', page, re.S)
    if not m:
        return None
    body = m.group(1)
    num = lambda k: (lambda x: int(x.group(1)) if x else None)(re.search(r'"' + k + r'":"?(\d+)', body))
    liked, count, score = num("likedCount"), num("reviewCount") or num("ratingCount"), num("score")
    if liked is None or not count:
        return None
    return liked, count, score


def displayed(liked, count):
    """Rotten Tomatoes shows the share rounded half up (37 of 87 = 42.53 -> 43)."""
    return int(math.floor(100.0 * liked / count + 0.5))


def betabinom(m, a, b):
    """P(X = k), k = 0..m, X ~ BetaBinomial(m, a, b)."""
    lb = lambda x, y: math.lgamma(x) + math.lgamma(y) - math.lgamma(x + y)
    return [math.exp(math.lgamma(m + 1) - math.lgamma(k + 1) - math.lgamma(m - k + 1)
                     + lb(k + a, m - k + b) - lb(a, b)) for k in range(m + 1)]


def expected_reviews(history, count, hours_left):
    """Reviews still to come by the close, from the collector's own measured pace over the last
    24h of snapshots (halved for decay), or None until 12h of snapshots exist. A fixed guess was
    tried first and was badly wrong far from the close (2026-10-16: I Play Rocky, 37 of 44 with
    five weeks to go, read 92% on a rung the market held at 39c)."""
    pts = [(ts(h["at"]), h["count"]) for h in history if h.get("count")]
    pts = [p for p in pts if p[0]]
    if not pts or (pts[-1][0] - pts[0][0]).total_seconds() < 12 * 3600:
        return None
    recent = [p for p in pts if (pts[-1][0] - p[0]).total_seconds() <= 24 * 3600] or pts
    a, b = recent[0], recent[-1]
    hours = max(1.0, (b[0] - a[0]).total_seconds() / 3600)
    per_h = max(0.0, (b[1] - a[1]) / hours)
    return int(round(per_h * max(0.0, hours_left) * 0.5))


def p_above(liked, count, future, strike):
    """P(the displayed score at the close is ABOVE `strike`)."""
    pmf = betabinom(future, liked + 1, count - liked + 1) if future > 0 else [1.0]
    return sum(p for k, p in enumerate(pmf) if displayed(liked + k, count + future) > strike)


def rt_picks(events, now, state, snaps, fetch=web):
    counts, out = Counter(), []
    urls = state.setdefault("rt_urls", {})
    for ev in events:
        if ev.get("series_ticker") not in RT_SERIES:
            continue
        ms = [m for m in ev.get("markets") or [] if m.get("status") in ("active", "open")
              and isinstance(m.get("floor_strike"), (int, float)) and m.get("strike_type") == "greater"]
        if not ms:
            continue
        key = ev.get("event_ticker")
        if key not in urls:
            name = rt_name(ev, ms[0])
            try:
                urls[key] = rt_search(name, "tv" if ev.get("series_ticker") == "KXRTTV" else "movie", fetch) if name else None
            except Exception:                                   # noqa: BLE001
                counts["title search failed"] += 1
                continue
        if not urls.get(key):
            counts["no Rotten Tomatoes page found"] += 1
            continue
        try:
            got = rt_counts(urls[key], fetch)
        except Exception:                                       # noqa: BLE001
            counts["title page failed"] += 1
            continue
        ladder = {str(m["floor_strike"]): quote(m) for m in ms}
        hist = snaps.setdefault(key, [])
        hist.append(dict(at=now.isoformat(), url=urls[key], liked=got[0] if got else None,
                         count=got[1] if got else None, score=got[2] if got else None,
                         ladder={k: list(v) for k, v in ladder.items() if v}))
        del hist[:-400]                                         # ~16 days of hourly reads
        if not got or got[1] < RT_MIN_REVIEWS:
            counts["under 20 reviews counted"] += 1
            continue
        liked, count, _score = got
        best = None
        for m in ms:
            close, q = ts(m.get("close_time")), quote(m)
            if not close or close <= now or not q or q[1] - q[0] > 0.05 + 1e-9:
                continue
            future = expected_reviews(hist, count, (close - now).total_seconds() / 3600)
            if future is None:
                continue
            p = min(max(p_above(liked, count, future, m["floor_strike"]), P_CLAMP[0]), P_CLAMP[1])
            no_px = round(1 - q[0], 4)
            for side, px, e in (("yes", q[1], p - (q[1] + fee(q[1]))), ("no", no_px, (1 - p) - (no_px + fee(no_px)))):
                if best is None or e > best[0]:
                    best = (e, side, px, p, m, future)
        if not best:
            counts["collecting review pace (12h of snapshots)"] += 1
            continue
        if best[0] < EDGE_MIN - 1e-9:
            counts["edge under 5c"] += 1
            continue
        e, side, px, p, m, future = best
        counts["edge 5c+"] += 1
        out.append(entry(m, ev, side, px, now,
                         detail=(f"{liked}/{count} liked ({displayed(liked, count)}), ~{future} more reviews · "
                                 f"P(above {m['floor_strike']:g}) {p:.2f} · edge {e:+.2f}"),
                         model=round(p, 4), edge=round(e, 4), rt_url=urls[key]))
    return out, counts


# ------------------------------------------------------------------ the run
def culture_events(fetch=D.get):
    evs = D.pages("events?status=open&with_nested_markets=true&limit=200", "events", fetch)
    return [e for e in evs if e.get("category") in CATEGORIES]


def strike_of(row):
    """(strike, type) for a ladder rung: stored on the row, else the KXRT/KXRTTV ticker's suffix."""
    if isinstance(row.get("strike"), (int, float)):
        return float(row["strike"]), row.get("strike_type") or "greater"
    if row.get("series") in RT_SERIES or str(row.get("id", "")).split("-")[0] in RT_SERIES:
        tail = str(row.get("id", "")).rsplit("-", 1)[-1]
        try:
            return float(tail), "greater"
        except ValueError:
            return None
    return None


def conflicts(a, b):
    """Do two picks on DIFFERENT rungs of one ladder event bet in contradictory directions?
    YES on "above s" is bullish and NO on it bearish; a bullish and a bearish pick on one
    ladder is the same quantity bet both ways. Events without strikes (a word list, a chart
    of items) are not ladders: their markets are separate questions."""
    if a.get("event") != b.get("event") or a.get("id") == b.get("id"):
        return False
    sa, sb = strike_of(a), strike_of(b)
    if not sa or not sb:
        return False
    return a["side"] != b["side"]


def record(lane, picks, by="event", state=None, key=None, counts=None):
    """Freeze each new pick once: one per event (bands, RT) or per market (mentions).

    With `state` (the run passes it), a market any Culture lane already holds, open or settled,
    is skipped and counted "held by <lane>", and so is a pick that bets a ladder event the
    other way to a pick already held on it ("conflicts with <lane>")."""
    have = {x[by] for x in lane["picks"]}
    held = {}
    if state is not None:
        for name, other in state["lanes"].items():
            for x in other["picks"]:
                held.setdefault(x["id"], (name, x))
    for p in picks:
        if p[by] in have:
            continue
        if state is not None:
            owner = held.get(p["id"])
            if owner and owner[0] != key:
                if counts is not None:
                    counts[f"held by {owner[0]}"] += 1
                continue
            clash = next((n for n, x in held.values() if conflicts(p, x)), None)
            if clash:
                if counts is not None:
                    counts[f"conflicts with {clash} in the same event"] += 1
                continue
            held[p["id"]] = (key, p)
        lane["picks"].append(p)
        have.add(p[by])


def settle(lane, now, fetch=D.get):
    errs = []
    for row in lane["picks"]:
        if row["status"] != "open":
            continue
        try:
            m = fetch("markets/" + urllib.parse.quote(row["id"], safe="")).get("market", {})
            if m.get("ticker") != row["id"]:
                raise ValueError("settlement ticker mismatch")
            px = D.payout(m)
            if px is None:
                continue
            pay = px if row["side"] == "yes" else 1 - px
            row.update(payout=pay, profit=round(100 * (pay / (row["price"] + fee(row["price"])) - 1), 2),
                       status="won" if pay == 1 else "lost" if pay == 0 else "no_result", settled=now.isoformat())
        except Exception as e:                                  # noqa: BLE001
            errs.append(row["id"] + ": " + str(e)[:80])
    return errs


def run(state, snaps, now=None, fetch=D.get, webfetch=web):
    now = now or dt.datetime.now(dt.timezone.utc)
    for lane in state["lanes"].values():
        lane["last_run"] = now.isoformat()
    try:
        events = culture_events(fetch)
    except Exception as e:                                      # noqa: BLE001
        for lane in state["lanes"].values():
            lane["error"] = "events: " + str(e)[:200]
        return state
    steps = {
        "culture_fav_band": lambda: band_picks(events, now, FAV_BAND, FAV_SPREAD, FAV_HOURS, "favourite band"),
        "culture_endgame": lambda: band_picks(events, now, END_BAND, END_SPREAD, END_HOURS, "endgame"),
        "mentions_rate": lambda: mention_picks(events, now, state, webfetch),
        "rt_model": lambda: rt_picks(events, now, state, snaps, webfetch),
    }
    for key in PRIORITY:
        step = steps[key]
        lane = state["lanes"][key]
        errs = []
        try:
            picks, counts = step()
            record(lane, picks, by="id" if key == "mentions_rate" else "event", state=state, key=key,
                   counts=counts)
            lane["observations"] = dict(at=now.isoformat(), events=len(events), reasons=dict(counts))
        except Exception as e:                                  # noqa: BLE001
            errs.append("scan: " + type(e).__name__ + ": " + str(e)[:160])
        errs += settle(lane, now, fetch)
        lane["error"] = "; ".join(errs)[:1200] or None
        if not lane["error"]:
            lane["last_success"] = now.isoformat()
    return state


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def main():
    state, snaps = load(), load_snaps()
    run(state, snaps)
    _write(PATH, state)
    _write(SNAPS, snaps)
    for key, lane in state["lanes"].items():
        print(key, "picks", len(lane["picks"]), "open", sum(p["status"] == "open" for p in lane["picks"]),
              "reasons", lane.get("observations", {}).get("reasons"), "error", lane["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
