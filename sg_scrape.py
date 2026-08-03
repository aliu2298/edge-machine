#!/usr/bin/env python3
"""sg_scrape.py — pull sportsgambler.com predictions for the 10 tracked leagues.

Replaces the Lovable app's edge function. Runs server-side (GitHub Actions), so
there is no CORS problem and no dependency on the local Mac or predictions.db.

Captures exactly three things per match (user directive Aug 2 2026):
  1. projected score   — the "Correct Score Prediction" section
  2. both teams to score — the BTTS odds block (Yes/No) + supporting form line
  3. the site's own tip — the "MAIN MATCH PREDICTION" block, verbatim

Writes/merges data/sg_picks.json. Existing rows are preserved (match URL is the
unique key) so settled results are never clobbered by a re-scrape.

Usage:  python3 sg_scrape.py [--limit N] [--league mls]
"""
import json, os, re, sys, time, urllib.request, urllib.error, datetime, html as _html

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "sg_picks.json")
BASE = "https://www.sportsgambler.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

LEAGUES = {
    "premier-league": "Premier League", "la-liga": "La Liga",
    "bundesliga": "Bundesliga", "serie-a": "Serie A", "ligue-1": "Ligue 1",
    "mls": "MLS", "eredivisie": "Eredivisie", "primeira-liga": "Primeira Liga",
    "uefa-champions-league": "Champions League", "europa-league": "Europa League",
}
MATCH_RE = re.compile(
    r"/betting-tips/football/([a-z0-9-]+-vs-[a-z0-9-]+-prediction-lineups-odds-\d{4}-\d{2}-\d{2})/")
RATE_LIMIT_S = 1.0


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries - 1:
                print(f"  ! fetch failed {url}: {e}", file=sys.stderr)
                return ""
            time.sleep(2 * (i + 1))
    return ""


def text_of(h):
    """HTML → newline-ish plain text, mirroring what the page reads like."""
    h = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|td|th|span)>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = _html.unescape(h)
    h = re.sub(r"[ \t ]+", " ", h)
    return re.sub(r"\n\s*\n+", "\n", h).strip()


def american_to_decimal(a):
    """sportsgambler quotes American odds throughout. This conversion is the fix for
    the P/L bug the Lovable build had (winning picks were scored -1.00)."""
    try:
        a = int(str(a).replace("+", "").replace("−", "-"))
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return round(a / 100 + 1, 4) if a > 0 else round(100 / abs(a) + 1, 4)


def parse_match(url, raw):
    t = text_of(raw)
    d = {"url": url, "scraped_at": datetime.datetime.now(datetime.timezone.utc)
         .isoformat(timespec="seconds")}

    # --- teams / league / kickoff from the slug + header ---
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    m = re.match(r"(.+?)-vs-(.+?)-prediction-lineups-odds-(\d{4}-\d{2}-\d{2})", slug)
    if m:
        d["home"] = m.group(1).replace("-", " ").title()
        d["away"] = m.group(2).replace("-", " ").title()
        d["date"] = m.group(3)
    d["match"] = f"{d.get('home','?')} v {d.get('away','?')}"
    lg = re.search(r"\n([A-Z][A-Za-z .]+ - [A-Z][A-Za-z0-9 .]+)\n", t)
    if lg:
        d["league_raw"] = lg.group(1).strip()
    ko = re.search(r"\n((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Z][a-z]{2})\n(\d{1,2}:\d{2})\n", t)
    if ko:
        d["kickoff_text"] = f"{ko.group(1)} {ko.group(2)}"

    # NB: section headings render uppercase via CSS but are Title Case in the markup,
    # and every line break carries a trailing space ("\n Galaxy\n 0\n"). Anchor on the
    # trailing "Bet Now" so we hit the real tip block, not the page's anchor-nav list.

    # --- 1. the site's own tip (Main Match Prediction) ---
    mp = re.search(r"Main Match Prediction\s*\n\s*(.+?)\s*\n\s*Bet Now", t)
    if mp:
        tip = mp.group(1).strip()
        d["tip_text"] = tip
        od = re.search(r"@\s*([+-]\d+)", tip)
        if od:
            d["tip_odds_american"] = od.group(1)
            d["tip_odds_decimal"] = american_to_decimal(od.group(1))

    # --- 2. projected score (Correct Score Prediction) ---
    cs = re.search(r"Correct Score Prediction\s*\n\s*([A-Za-zÀ-ÿ0-9 .'&-]+?)\s*\n\s*(\d+)"
                   r"\s*\n\s*-\s*\n\s*(\d+)\s*\n\s*([A-Za-zÀ-ÿ0-9 .'&-]+?)\s*\n", t)
    if cs:
        d["proj_home_team"], d["proj_away_team"] = cs.group(1).strip(), cs.group(4).strip()
        d["proj_home"], d["proj_away"] = int(cs.group(2)), int(cs.group(3))
        d["proj_score"] = f"{d['proj_home']}-{d['proj_away']}"
        # The prose price is worded inconsistently ("available at odds of +850" vs
        # "can be backed at +650"), so read the price out of the "Latest Correct Score
        # Odds" ladder instead — that block is uniform: "2-0\n +650".
        lad = re.search(r"Latest Correct Score Odds(.{0,1200})", t[cs.end():], re.S)
        if lad:
            hit = re.search(rf"\b{d['proj_home']}-{d['proj_away']}\s*\n\s*([+-]\d+)", lad.group(1))
            if hit:
                d["proj_score_odds"] = hit.group(1)

    # --- 3. both teams to score (odds block + form line) ---
    bt = re.search(r"Both Teams to Score\s*\n\s*Yes\s*\n\s*([+-]\d+)\s*\n\s*No\s*\n\s*([+-]\d+)", t)
    if bt:
        d["btts_yes_odds"], d["btts_no_odds"] = bt.group(1), bt.group(2)
        dy, dn = american_to_decimal(bt.group(1)), american_to_decimal(bt.group(2))
        d["btts_yes_decimal"], d["btts_no_decimal"] = dy, dn
        if dy and dn:                       # shorter price = the side the market implies
            d["btts_implied"] = "Yes" if dy < dn else "No"
    form = re.findall(r"BTTS Yes in (\d+) of the previous 10 ([a-z]*) ?matches", t)
    if form:
        d["btts_form"] = [f"{n}/10 {(scope or 'overall').strip()}" for n, scope in form[:4]]

    return d


def league_matches(slug):
    raw = get(f"{BASE}/betting-tips/football/{slug}-predictions/")
    if not raw:
        return []
    seen, out = set(), []
    for m in MATCH_RE.finditer(raw):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(f"{BASE}/betting-tips/football/{m.group(1)}/")
    return out


def main():
    limit = None
    only = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--league" in sys.argv:
        only = sys.argv[sys.argv.index("--league") + 1]

    existing = {}
    if os.path.exists(OUT):
        try:
            existing = {r["url"]: r for r in json.load(open(OUT)).get("picks", [])}
        except Exception:
            existing = {}

    added = skipped = 0
    for slug, name in LEAGUES.items():
        if only and slug != only:
            continue
        urls = league_matches(slug)
        print(f"{name:<18} {len(urls)} match pages")
        time.sleep(RATE_LIMIT_S)
        for u in urls:
            if u in existing:                  # never re-scrape (protects settled rows)
                skipped += 1
                continue
            raw = get(u)
            time.sleep(RATE_LIMIT_S)
            if not raw:
                continue
            row = parse_match(u, raw)
            row["league"] = name
            row["status"] = "pending"
            existing[u] = row
            added += 1
            print(f"   + {row['match']:<42} {row.get('tip_text','(no tip)')[:38]}")
            if limit and added >= limit:
                break
        if limit and added >= limit:
            break

    picks = sorted(existing.values(), key=lambda r: (r.get("date") or "", r.get("match") or ""))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"updated_at": datetime.datetime.now(datetime.timezone.utc)
                   .isoformat(timespec="seconds"),
                   "count": len(picks), "picks": picks}, f, indent=1)
    print(f"\nwrote {OUT} — {len(picks)} total ({added} new, {skipped} already stored)")


if __name__ == "__main__":
    main()
