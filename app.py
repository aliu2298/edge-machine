#!/usr/bin/env python3
"""
Prediction Tracker — local app (stdlib only).
Backend: http.server + sqlite3 + urllib. Auto-settle via API-Football / API-NBA / ESPN; keyless weather (Open-Meteo).
Run:  python3 app.py   ->  http://127.0.0.1:8787
"""
import json, os, sqlite3, urllib.request, urllib.error, datetime, csv, io, time, unicodedata, subprocess, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


ROOT  = os.path.dirname(os.path.abspath(__file__))
DB    = os.path.join(ROOT, "predictions.db")
INBOX = os.path.join(ROOT, "inbox.jsonl")   # appended on each request → watched live by Claude
PORT  = 8787
BANKROLL_START = 1000.0   # paper-money starting balance ($); `stake` is now a $ amount per bet

# ---- API-Football (api-sports.io) — keyed REST, no Cloudflare, no browser needed.
# Fixtures, scores, lineups, injuries, AND Asian-handicap odds on one free key (100 req/day).
APIFOOTBALL_BASE    = "https://v3.football.api-sports.io"
APINBA_BASE         = "https://v2.nba.api-sports.io"           # same key works here (separate 100/day quota)
APIFOOTBALL_KEYFILE = os.path.join(ROOT, ".apifootball_key")   # chmod 600, git-ignored
def apifootball_key():
    try:
        with open(APIFOOTBALL_KEYFILE) as f: return f.read().strip()
    except Exception:
        return os.environ.get("APIFOOTBALL_KEY", "")
def _apisports(base, path, params=None):
    """GET <base>/<path> with the stored api-sports key → parsed JSON."""
    key = apifootball_key()
    if not key: raise RuntimeError("no API-Football key set")
    qs = ("?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k,v in (params or {}).items())) if params else ""
    req = urllib.request.Request(base + "/" + path.lstrip("/") + qs, headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())
def apifootball(path, params=None): return _apisports(APIFOOTBALL_BASE, path, params)  # soccer
def apinba(path, params=None):      return _apisports(APINBA_BASE, path, params)        # NBA

# ---- Open-Meteo (keyless, free) — kickoff weather for totals (rain/wind dampen scoring)
# site.api.espn.com began 403-ing every request on 2026-08-08 (this machine AND the
# GitHub runner, any user-agent) — a server-side block, not our rate limit. site.web.api
# serves the identical payload on the identical path.
ESPN_HOST = "https://site.web.api.espn.com"

def _get_json(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "pred-tracker/1.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:   # rate limited → exponential backoff
                time.sleep(1.5 * (attempt + 1)); continue
            raise
def geocode_city(city):
    j = _get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&name=" + urllib.parse.quote(city))
    res = j.get("results") or []
    return (res[0]["latitude"], res[0]["longitude"]) if res else None
def weather_for(city, when_iso):
    """Open-Meteo hourly forecast nearest kickoff → dict (temp/precip/wind + under_lean) or None."""
    ll = geocode_city(city)
    if not ll: return None
    lat, lon = ll
    try:
        dt = datetime.datetime.fromisoformat(str(when_iso).replace("Z", "+00:00"))
    except Exception:
        return None
    day = dt.date().isoformat()
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           f"&hourly=temperature_2m,precipitation,precipitation_probability,wind_speed_10m"
           f"&start_date={day}&end_date={day}&timezone=UTC")
    h = (_get_json(url).get("hourly") or {})
    times = h.get("time") or []
    if not times: return None
    target = dt.strftime("%Y-%m-%dT%H:00")
    idx = times.index(target) if target in times else 0
    def at(k):
        a = h.get(k) or []
        return a[idx] if idx < len(a) else None
    precip, wind = at("precipitation"), at("wind_speed_10m")
    under_lean = (precip is not None and precip >= 2) or (wind is not None and wind >= 30)  # rain≥2mm or wind≥30km/h
    return {"city": city, "lat": lat, "lon": lon, "temp_c": at("temperature_2m"),
            "precip_mm": precip, "precip_prob": at("precipitation_probability"),
            "wind_kmh": wind, "under_lean": under_lean}
def af_fetch_score(fid):
    """API-Football fixture → (home, away, desc) ONLY if genuinely finished, else None.
    Anti-fabrication guard: settles only when API-Football itself reports FT/AET/PEN with real goals."""
    j = apifootball("fixtures", {"id": fid})
    arr = j.get("response") or []
    if not arr: return None
    f = arr[0]
    short = ((f.get("fixture") or {}).get("status") or {}).get("short")
    if short not in ("FT","AET","PEN"): return None        # not finished → don't settle
    ft = (f.get("score") or {}).get("fulltime") or {}       # 90-min score (correct for AH/total)
    g  = f.get("goals") or {}
    hs = ft.get("home") if ft.get("home") is not None else g.get("home")
    as_= ft.get("away") if ft.get("away") is not None else g.get("away")
    if hs is None or as_ is None: return None
    home=((f.get("teams") or {}).get("home") or {}).get("name","Home")
    away=((f.get("teams") or {}).get("away") or {}).get("name","Away")
    return int(hs), int(as_), f"{home} {int(hs)}-{int(as_)} {away} ({short})"
def nba_fetch_score(gid):
    """API-NBA game → (home_pts, away_pts, desc) ONLY if Finished, else None.
    NBA 'visitors' = the away team; home_score=home pts, away_score=visitors pts (matches grade())."""
    j = apinba("games", {"id": gid})
    arr = j.get("response") or []
    if not arr: return None
    g = arr[0]
    if ((g.get("status") or {}).get("long")) != "Finished": return None   # not final → don't settle
    sc = g.get("scores") or {}
    hp = (sc.get("home") or {}).get("points")
    ap = (sc.get("visitors") or {}).get("points")
    if hp is None or ap is None: return None
    home=((g.get("teams") or {}).get("home") or {}).get("name","Home")
    away=((g.get("teams") or {}).get("visitors") or {}).get("name","Away")
    return int(hp), int(ap), f"{away} {int(ap)} @ {home} {int(hp)} (Final)"
ESPN_PATH = {"nba": "basketball/nba", "wnba": "basketball/wnba", "mlb": "baseball/mlb", "nhl": "hockey/nhl"}  # keyless ESPN, no free-plan paywall
def espn_fetch_score(sport, event_id):
    """ESPN summary (keyless) → (home, away, desc) ONLY if STATUS_FINAL, else None. sport ∈ ESPN_PATH."""
    j = _get_json(f"{ESPN_HOST}/apis/site/v2/sports/{ESPN_PATH[sport]}/summary?event={event_id}")
    comp = ((j.get("header") or {}).get("competitions") or [{}])[0]
    if (((comp.get("status") or {}).get("type") or {}).get("name")) != "STATUS_FINAL": return None
    home=away=None; hn=an="?"
    for c in comp.get("competitors") or []:
        try: sc=int(c.get("score"))
        except Exception: sc=None
        nm=(c.get("team") or {}).get("abbreviation","?")
        if c.get("homeAway")=="home": home,hn=sc,nm
        else: away,an=sc,nm
    if home is None or away is None: return None
    return home, away, f"{an} {away} @ {hn} {home} (Final)"
def espn_games(sport, date=""):
    """ESPN scoreboard (keyless) → list of {event_id, teams, status, spread/total, scores}."""
    d=(date or "").replace("-","")
    url=f"{ESPN_HOST}/apis/site/v2/sports/{ESPN_PATH[sport]}/scoreboard"+("?dates="+d if d else "")
    out=[]
    for e in _get_json(url).get("events",[]):
        c=(e.get("competitions") or [{}])[0]; comps=c.get("competitors") or []
        sd=lambda s:next((x for x in comps if x.get("homeAway")==s),{})
        h,a=sd("home"),sd("away"); od=(c.get("odds") or [{}])[0]
        out.append({"event_id":e.get("id"),"date":e.get("date"),
            "home":(h.get("team") or {}).get("abbreviation"),"away":(a.get("team") or {}).get("abbreviation"),
            "home_name":(h.get("team") or {}).get("displayName"),"away_name":(a.get("team") or {}).get("displayName"),
            "status":((e.get("status") or {}).get("type") or {}).get("name"),
            "line":od.get("details"),"spread":od.get("spread"),"total":od.get("overUnder"),
            "home_score":h.get("score"),"away_score":a.get("score")})
    return out
def _pm_prob(field):
    """Polymarket outcomePrices come as a JSON string like '["0.66","0.34"]' → first prob as float."""
    if not field: return None
    if isinstance(field, str):
        try: field=json.loads(field)
        except Exception: return None
    try: return round(float(field[0]), 4)
    except Exception: return None
def polymarket_search(query, limit=8):
    """Polymarket Gamma public-search (read-only, keyless) → events + implied probabilities. NO account, NO trading."""
    url="https://gamma-api.polymarket.com/public-search?limit_per_type="+str(limit)+"&q="+urllib.parse.quote(query)
    d=_get_json(url); out=[]
    for e in (d.get("events") or [])[:limit]:
        mks=[]
        for m in (e.get("markets") or []):
            if m.get("closed"): continue
            mks.append({"name": m.get("groupItemTitle") or m.get("question"),
                        "prob": _pm_prob(m.get("outcomePrices"))})
        mks=[m for m in mks if m["prob"] is not None]
        mks.sort(key=lambda x: x["prob"], reverse=True)
        out.append({"event":e.get("title"),"slug":e.get("slug"),
                    "volume":round(float(e.get("volume") or 0)),"end":e.get("endDate"),"markets":mks})
    return out
# ================= Sportzino corner-bet helpers (American odds) =================
def _ts(): return datetime.datetime.now().isoformat(timespec="seconds")
def amer_implied(price):  # American odds → implied probability
    return (100.0/(price+100)) if price>0 else ((-price)/((-price)+100.0))
def amer_payout(price):   # profit per 1 unit staked on a win
    return (price/100.0) if price>0 else (100.0/(-price))
def corner_bet_dict(r):
    d=dict(r); p=d.get("price")
    d["implied"]=round(amer_implied(p),3) if p is not None else None
    s,stk=d["status"],(d["stake"] or 0)
    d["pnl"]=round(amer_payout(p)*stk,2) if s=="win" else (-stk if s=="loss" else 0.0)
    return d

# Settle soccer by MATCHUP+DATE via ESPN's keyless World Cup feed — no fixture id needed
# (API-Football's free tier paywalls WC 2026 fixtures, so this is the reliable auto-settle path).
TEAM_ALIASES = {"ivory coast":"cote d ivoire","turkiye":"turkey","usa":"united states",
                "south korea":"korea republic","republic of korea":"korea republic","czechia":"czech republic",
                # CLUB aliases — ESPN names these completely differently from our pick text,
                # and _team_match is a substring test, so nothing overlaps and the fixture
                # never settles. Each was surfaced by a health.py STUCK warning.
                "crvena zvezda":"red star belgrade", "hearts":"heart of midlothian",
                "red star":"red star belgrade"}
def _norm_team(s):
    s=unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower()
    s=" ".join("".join(ch if ch.isalnum() or ch==" " else " " for ch in s).split())
    return TEAM_ALIASES.get(s, s)
def _team_match(a,b):
    a,b=_norm_team(a),_norm_team(b)
    return bool(a) and bool(b) and (a==b or a in b or b in a)

def team_corner_rates():
    """Per-team corner + goal base rates from settled soccer picks with captured corner data.
    The data-grounded foundation for the storyline read — actuals, not archetype vibes."""
    c=db()
    rows=c.execute("SELECT match,home_score hs,away_score as_,home_corners hc,away_corners ac FROM predictions "
                   "WHERE sport='soccer' AND home_corners IS NOT NULL AND home_score IS NOT NULL").fetchall()
    c.close()
    agg={}
    def add(t,cf,ca,gf,ga):
        d=agg.setdefault(t,{"gp":0,"cf":0,"ca":0,"gf":0,"ga":0})
        d["gp"]+=1; d["cf"]+=cf; d["ca"]+=ca; d["gf"]+=gf; d["ga"]+=ga
    for r in rows:
        m=(r["match"] or "").replace(" vs "," v ")
        if " v " not in m: continue
        h,a=[x.strip() for x in m.split(" v ",1)]
        add(h,r["hc"],r["ac"],r["hs"],r["as_"]); add(a,r["ac"],r["hc"],r["as_"],r["hs"])
    # Blend the thick 2024 API-Football prior (team_history) with recent WC actuals, games-weighted.
    hist={r["team"]:dict(r) for r in db().execute("SELECT * FROM team_history").fetchall()}
    def hfor(team):
        for k,v in hist.items():
            if _team_match(team,k): return v
        return None
    teams=set(agg)|{k for k in hist if not any(_team_match(k,t) for t in agg)}
    out={}
    for t in teams:
        d=agg.get(t); h=hfor(t); wgp=d["gp"] if d else 0; hgp=h["gp"] if h else 0; tot=wgp+hgp
        if not tot: continue
        bl=lambda wcsum,hv: round(((wcsum or 0)+(hv or 0)*hgp)/tot,1)
        out[t]={"gp":tot,"gp_wc":wgp,"gp_hist":hgp,
                "cf":bl(d["cf"] if d else 0, h["cf"] if h else None),
                "ca":bl(d["ca"] if d else 0, h["ca"] if h else None),
                "gf":bl(d["gf"] if d else 0, h["gf"] if h else None),
                "ga":bl(d["ga"] if d else 0, h["ga"] if h else None)}
    return out

def storyline_read(home, away):
    """Data-grounded pre-game storyline: control side, projected corners, grind/romp type, suggested pair.
    Built from team_corner_rates() — projects each side's corners as (own corners-for + opp corners-against)/2."""
    R=team_corner_rates()
    def find(name):
        for k,v in R.items():
            if _team_match(name,k): return k,v
        return None,None
    hk,hr=find(home); ak,ar=find(away)
    miss=[n for n,r in ((home,hr),(away,ar)) if not r]
    if miss: return {"home":home,"away":away,"error":f"no corner base-rate data yet for: {', '.join(miss)} (need a settled game)","matched":{"home":hk,"away":ak}}
    proj_h=round((hr["cf"]+ar["ca"])/2,1); proj_a=round((ar["cf"]+hr["ca"])/2,1)
    cmarg=round(abs(proj_h-proj_a),1)
    corner_ctrl="home" if proj_h>proj_a else "away"
    min_gp=min(hr["gp"],ar["gp"])
    # Upstream control driver: possession (the SHARPER signal — higher-possession side won the corner
    # count 82% overall, 95% when the gap ≥15pts; corner margin ≥3.5 = 100% direction, 1.5-3.5 = 77%).
    drivers=None; poss_gap=None; poss_ctrl=None
    SR=team_stat_rates()
    def sfind(name):
        for k,v in SR.items():
            if _team_match(name,k): return v
        return None
    hs_, as_ = sfind(home), sfind(away)
    if hs_ and as_:
        def proj(a,b,k): return round(((a["for"].get(k,0)+b["against"].get(k,0))/2),1)
        ph=proj(hs_,as_,"possessionPct"); pa=proj(as_,hs_,"possessionPct")
        drivers={"projected_possession":{"home":ph,"away":pa},
                 "projected_shots":{"home":proj(hs_,as_,"totalShots"),"away":proj(as_,hs_,"totalShots")}}
        poss_gap=round(ph-pa,1); poss_ctrl="home" if poss_gap>0 else "away"
    # GRADED "clear control side" — two signals (corner margin + possession gap), POSSESSION is sharper.
    corner_strong=cmarg>=3.5; corner_mod=cmarg>=1.5
    poss_strong = poss_gap is not None and abs(poss_gap)>=15
    poss_mod    = poss_gap is not None and abs(poss_gap)>=8
    agree = poss_ctrl is None or poss_ctrl==corner_ctrl
    conflict=False
    if agree:
        ctrl=corner_ctrl
        strength = "CLEAR" if (corner_strong or poss_strong) else ("LEAN" if (corner_mod or poss_mod) else "COIN-FLIP")
    else:   # signals disagree → trust the more decisive one (possession is the sharper predictor)
        if poss_mod and not corner_mod:        # possession decisive, corners weak → trust possession
            ctrl=poss_ctrl; strength = "CLEAR" if poss_strong else "LEAN"
        elif corner_strong and not poss_mod:   # corners decisive, possession weak → trust corners
            ctrl=corner_ctrl; strength="CLEAR"
        else:                                  # both decisive & disagree → genuine conflict
            ctrl=corner_ctrl; strength="COIN-FLIP"; conflict=True
    cside, dog = (hr,ar) if ctrl=="home" else (ar,hr)
    cname = home if ctrl=="home" else away
    frustrated = cside["gf"]<=1.5          # control side scores few → sieges (corners pile up)
    dog_absorbs = dog["ca"]>=6.0           # dog ships lots of corners → stays deep / gets sieged
    dog_chases  = dog["gf"]>=2.0           # dog scores → attacks/chases → game opens (corners flatten/flip)
    # GOALS favorite (by goal differential) — distinct from the corner-control side; in a romp the
    # corner-control side is often the LOSER (chaser), so the MARGIN pair rides the goals favorite.
    gfav = "home" if (hr["gf"]-hr["ga"]) >= (ar["gf"]-ar["ga"]) else "away"
    gname = home if gfav=="home" else away
    if strength=="COIN-FLIP":
        typ="COIN-FLIP — no control edge"
        pname = (home if poss_ctrl=="home" else away) if poss_ctrl else None
        combined = proj_h+proj_a
        if conflict and pname:
            pair=(f"No model edge — corner & possession DISAGREE. Possession is the sharper signal → tiny lean {pname}, "
                  f"else PASS. Real edge here is EXOGENOUS: price vs a sharp book, or lineup news.")
        elif combined>=10:
            pair=("Even but HIGH-event (both attack) — residual lean: total-corners OVER / BTTS. No control edge; "
                  "small or PASS. Upgrade only on a price (vs sharp) or lineup edge.")
        else:
            pair=("Low-event cagey game — residual lean: UNDER goals / under team-corners. No control edge; "
                  "small or PASS. Upgrade only on a price (vs sharp) or lineup edge.")
    elif dog_chases and not (frustrated or dog_absorbs):
        soft = dog["ga"]>=2.0   # dog concedes freely → the goals leg is live; else drop it (stonewall risk)
        gleg = f" + {gname} team-total over (confirm soft D + creator)" if soft else " (skip team-total — dog not leaky enough; stonewall risk)"
        typ=f"ROMP/OPEN — corners unreliable [{strength} control]"
        pair=f"MARGIN pair: {gname} -1.5 (capped) or dog's +1.5 — 1.0–1.5 line, NEVER ±0.5{gleg}"
    else:
        line=max(3.5, round((proj_h if ctrl=='home' else proj_a)-1.5))
        sz="" if strength=="CLEAR" else " — conservative line, smaller stake (77% zone)"
        typ=f"GRIND-SIEGE [{strength} control]"
        pair=f"CORNER pair: Corner-1x2 {cname} + {cname} team-corner OVER ~{line}{sz}"
    return {"home":home,"away":away,"matched":{"home":hk,"away":ak},
            "rates":{"home":hr,"away":ar},
            "projected_corners":{"home":proj_h,"away":proj_a},
            "control_drivers":drivers,
            "control_side":cname,"corner_margin":cmarg,"possession_gap":poss_gap,
            "control_strength":strength,
            "storyline_type":typ,"suggested_pair":pair,
            "confidence":("LOW (≤1 game sample)" if min_gp<=1 else "medium" if min_gp==2 else "ok"),
            "note":"control_strength: CLEAR (poss gap≥15 or corner margin≥3.5 → ~95-100% dir) · LEAN (≥8 / ≥1.5 → ~77%) · COIN-FLIP (weak or signals conflict)"}
_ESPN_CACHE = {}   # short-TTL memo so a 2nd pick on the same game reuses one fetch (no per-row rate-limit)
def _espn_cached(tag, match, kickoff, fn):
    key = (tag, (match or "").lower().strip(), (kickoff or "")[:10])
    hit = _ESPN_CACHE.get(key)
    if hit and time.time()-hit[0] < 120: return hit[1]
    res = fn(match, kickoff)
    _ESPN_CACHE[key] = (time.time(), res)
    return res
def espn_soccer_final(match, kickoff):
    return _espn_cached("final", match, kickoff, _espn_final_compute)

# Post-WC: settle searches these ESPN league feeds in order for the matchup (WC first for history,
# then the active club competitions). Add slugs here when a new tournament enters the rotation.
ESPN_SOCCER_LEAGUES = ["fifa.world","usa.1","bra.1",
                       # QUALIFYING rounds sit under separate slugs — uefa.champions
                       # returned 0 events for the Aug 4 ties while _qual returned 8.
                       "uefa.champions","uefa.champions_qual",
                       "uefa.europa","uefa.europa_qual","uefa.europa.conf",
                       "eng.1","esp.1","ger.1","ita.1","fra.1","eng.2","mex.1",
                       "ned.1","por.1","den.1","aut.1","sui.1","swe.1","nor.1",
                       "concacaf.leagues.cup"]

def _espn_final_compute(match, kickoff):
    """Grade a soccer pick from its 'A v B' matchup + kickoff date via ESPN (FINAL only).
    Searches every league in ESPN_SOCCER_LEAGUES. Returns (home_score, away_score, desc) or None."""
    m=(match or "").replace(" vs "," v ")
    if " v " not in m: return None
    teamA,teamB=[p.strip() for p in m.split(" v ",1)]
    try: base=datetime.date.fromisoformat((kickoff or "")[:10])
    except ValueError: return None
    for d in (base, base-datetime.timedelta(days=1), base+datetime.timedelta(days=1),
              base-datetime.timedelta(days=2)):   # late-UTC games sit on the prior ESPN date;
                                                   # the wider window also tolerates a fixture
                                                   # filed a day or two off (see pick #122)
      for lg in ESPN_SOCCER_LEAGUES:
        try: data=_get_json(f"{ESPN_HOST}/apis/site/v2/sports/soccer/{lg}/scoreboard?dates="+d.strftime("%Y%m%d"))
        except Exception: continue
        for e in data.get("events",[]):
            comp=(e.get("competitions") or [{}])[0]
            if ((comp.get("status") or {}).get("type") or {}).get("name","") not in ("STATUS_FULL_TIME","STATUS_FINAL"): continue
            sc={}
            for cobj in (comp.get("competitors") or []):
                nm=(cobj.get("team") or {}).get("displayName") or ""
                try: sc[nm]=int(cobj.get("score"))
                except (TypeError, ValueError): pass
            ca=next((n for n in sc if _team_match(teamA,n)), None)
            cb=next((n for n in sc if n!=ca and _team_match(teamB,n)), None)
            if ca and cb: return (sc[ca], sc[cb], f"{teamA} {sc[ca]}-{sc[cb]} {teamB} (FT)")
    return None
def _first_scorer(summ, teamA, teamB, total_goals):
    """First team to score from ESPN keyEvents (scoringPlay) → 'home'/'away'/'none', or None if undeterminable.
    home=teamA. Returns 'none' on a confirmed 0-0. Own-goal openers → None (ambiguous attribution; leave for manual)."""
    if total_goals == 0: return "none"
    for k in (summ.get("keyEvents") or []):           # keyEvents are chronological → first scoringPlay = opener
        if not k.get("scoringPlay"): continue
        if "own goal" in (k.get("text") or "").lower(): return None   # don't risk mis-attributing an own goal
        nm=(k.get("team") or {}).get("displayName") or ""
        if _team_match(teamA, nm): return "home"
        if _team_match(teamB, nm): return "away"
        return None
    return None                                       # goals exist but no parseable event → leave pending
def espn_soccer_box(match, kickoff):
    return _espn_cached("box", match, kickoff, _espn_box_compute)
def _espn_box_compute(match, kickoff):
    """ACTUAL corners + first-scorer for a finished soccer pick via ESPN boxscore (multi-league).
    Returns {"corners":(hc,ac)|None, "first":'home'/'away'/'none'|None} aligned to 'A v B' (A=home), else None."""
    m=(match or "").replace(" vs "," v ")
    if " v " not in m: return None
    teamA,teamB=[p.strip() for p in m.split(" v ",1)]
    try: base=datetime.date.fromisoformat((kickoff or "")[:10])
    except ValueError: return None
    for d in (base, base-datetime.timedelta(days=1), base+datetime.timedelta(days=1),
              base-datetime.timedelta(days=2)):   # late-UTC games sit on the prior ESPN date;
                                                   # the wider window also tolerates a fixture
                                                   # filed a day or two off (see pick #122)
      for lg in ESPN_SOCCER_LEAGUES:
        try: data=_get_json(f"{ESPN_HOST}/apis/site/v2/sports/soccer/{lg}/scoreboard?dates="+d.strftime("%Y%m%d"))
        except Exception: continue
        for e in data.get("events",[]):
            comp=(e.get("competitions") or [{}])[0]
            if ((comp.get("status") or {}).get("type") or {}).get("name","") not in ("STATUS_FULL_TIME","STATUS_FINAL"): continue
            names=[((c.get("team") or {}).get("displayName") or "") for c in (comp.get("competitors") or [])]
            if not (any(_team_match(teamA,n) for n in names) and any(_team_match(teamB,n) for n in names)): continue
            tg=0
            for c in (comp.get("competitors") or []):
                try: tg+=int(c.get("score"))
                except (TypeError,ValueError): pass
            eid=e.get("id")
            if not eid: continue
            try: summ=_get_json(f"{ESPN_HOST}/apis/site/v2/sports/soccer/{lg}/summary?event="+str(eid))
            except Exception: return None
            cor={}; allstats={}    # allstats[team] = {statName: float} — the FULL boxscore line, not just corners
            for t in ((summ.get("boxscore") or {}).get("teams") or []):
                nm=(t.get("team") or {}).get("displayName") or ""
                if not nm: continue
                st={}
                for s in (t.get("statistics") or []):
                    name=s.get("name")
                    raw=s.get("displayValue") if s.get("displayValue") is not None else s.get("value")
                    try: st[name]=float(str(raw).replace("%",""))
                    except (TypeError,ValueError): pass
                allstats[nm]=st
                if "wonCorners" in st: cor[nm]=int(st["wonCorners"])
            ca=next((n for n in cor if _team_match(teamA,n)), None)
            cb=next((n for n in cor if n!=ca and _team_match(teamB,n)), None)
            corners=(cor[ca], cor[cb]) if (ca and cb) else None
            sa=next((n for n in allstats if _team_match(teamA,n)), None)
            sb=next((n for n in allstats if n!=sa and _team_match(teamB,n)), None)
            stats={"home":allstats.get(sa), "away":allstats.get(sb)} if (sa and sb) else None
            return {"corners":corners, "first":_first_scorer(summ, teamA, teamB, tg), "stats":stats}
    return None
def espn_soccer_corners(match, kickoff):
    """ACTUAL corners (home,away) aligned to 'A v B' (A=home), else None. Thin wrapper over espn_soccer_box."""
    b=espn_soccer_box(match, kickoff)
    return b["corners"] if b else None
def fetch_corners(row):
    """ACTUAL corners (home,away) for a settled SOCCER pick, else None. Soccer-only; WC via ESPN."""
    if row["sport"]!="soccer": return None
    try: return espn_soccer_corners(row["match"], row["kickoff"])
    except Exception: return None
def store_game_stats(match, kickoff, stats):
    """Persist the full per-team ESPN stat line for a game into game_stats (upsert on match+date)."""
    if not stats or not stats.get("home") or not stats.get("away"): return
    c=db()
    c.execute("INSERT INTO game_stats(match,date,home_json,away_json,updated_at) VALUES(?,?,?,?,?) "
              "ON CONFLICT(match,date) DO UPDATE SET home_json=excluded.home_json,away_json=excluded.away_json,updated_at=excluded.updated_at",
              (match,(kickoff or "")[:10],json.dumps(stats["home"]),json.dumps(stats["away"]),_ts()))
    c.commit(); c.close()

# The upstream control drivers we track per team (averaged for / against).
STAT_KEYS=["possessionPct","totalShots","shotsOnTarget","wonCorners","foulsCommitted","yellowCards","totalCrosses"]
def team_stat_rates():
    """Per-team averages of the full stat line (for & against) from game_stats — possession/shots/etc."""
    c=db(); rows=c.execute("SELECT match,home_json,away_json FROM game_stats").fetchall(); c.close()
    agg={}
    def add(team,st,opp):
        d=agg.setdefault(team,{"gp":0,"for":{},"against":{}}); d["gp"]+=1
        for k in STAT_KEYS:
            if k in st:  d["for"][k]=d["for"].get(k,0)+st[k]
            if k in opp: d["against"][k]=d["against"].get(k,0)+opp[k]
    for r in rows:
        m=(r["match"] or "").replace(" vs "," v ")
        if " v " not in m: continue
        h,a=[x.strip() for x in m.split(" v ",1)]
        try: hs=json.loads(r["home_json"]); as_=json.loads(r["away_json"])
        except Exception: continue
        add(h,hs,as_); add(a,as_,hs)
    # Blend the thick 2024 prior (team_history possession/shots/SoT) with WC actuals, games-weighted.
    hist={r["team"]:dict(r) for r in db().execute("SELECT * FROM team_history").fetchall()}
    HK={"possessionPct":("poss_f","poss_a"),"totalShots":("shots_f","shots_a"),"shotsOnTarget":("sot_f","sot_a")}
    def hfor(team):
        for k,v in hist.items():
            if _team_match(team,k): return v
        return None
    teams=set(agg)|{k for k in hist if not any(_team_match(k,t) for t in agg)}
    out={}
    for t in teams:
        d=agg.get(t); h=hfor(t); wgp=d["gp"] if d else 0; hgp=h["gp"] if h else 0; tot=wgp+hgp
        if not tot: continue
        fo={}; ag={}
        for k in STAT_KEYS:
            hf=ha=None
            if h and k in HK and h[HK[k][0]] is not None: hf=h[HK[k][0]]; ha=h[HK[k][1]]
            wf=(d["for"].get(k) if d else None); wa=(d["against"].get(k) if d else None)
            # blend WC sum + history avg×hgp; if a side lacks data for a stat, use the other (no dilution)
            if hf is not None and wf is not None: fo[k]=round((wf+hf*hgp)/tot,1)
            elif hf is not None: fo[k]=round(hf,1)
            elif wf is not None: fo[k]=round(wf/wgp,1)
            if ha is not None and wa is not None: ag[k]=round((wa+ha*hgp)/tot,1)
            elif ha is not None: ag[k]=round(ha,1)
            elif wa is not None: ag[k]=round(wa/wgp,1)
        out[t]={"gp":tot,"gp_wc":wgp,"gp_hist":hgp,"for":fo,"against":ag}
    return out

def _af(path, params=None, tries=6):
    """API-Football call paced under the free-tier ~10 req/min limit, with 429 backoff."""
    for a in range(tries):
        try:
            r=apifootball(path, params); time.sleep(6.5); return r   # uniform pacing on every call
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(7*(a+1)); continue
            raise
    return {"response":[]}

def _af_team_id(name):
    """Resolve an API-Football national-team id by name (prefers national=True)."""
    d=_af("teams", {"search":name})
    cands=[t["team"] for t in d.get("response",[])]
    nat=[t for t in cands if t.get("national")]
    pick=(nat or cands)
    return pick[0]["id"] if pick else None

def refresh_team_history(name, season=2024, maxfix=12):
    """Pull a national team's <season> fixtures + per-fixture stats from API-Football (free 2022-2024),
    aggregate corner/possession/shot/goal averages (for & against), and store in team_history.
    The thick prior that fixes thin WC samples. Returns a summary or {'error':...}."""
    tid=_af_team_id(name)
    if not tid: return {"error":f"no team id for {name}"}
    fx=_af("fixtures", {"team":tid,"season":season}).get("response",[])
    fx=[f for f in fx if (f.get("fixture",{}).get("status",{}) or {}).get("short") in ("FT","AET","PEN")][:maxfix]
    agg={"gp":0,"cf":0,"ca":0,"gf":0,"ga":0,"poss_f":0,"poss_a":0,"shots_f":0,"shots_a":0,"sot_f":0,"sot_a":0}
    for f in fx:
        fid=f["fixture"]["id"]; hid=f["teams"]["home"]["id"]
        ishome = hid==tid
        try: stt=_af("fixtures/statistics", {"fixture":fid}).get("response",[])
        except Exception: continue
        mine=next((t for t in stt if t["team"]["id"]==tid), None)
        opp =next((t for t in stt if t["team"]["id"]!=tid), None)
        if not mine or not opp: continue
        def g(team,typ):
            for s in team["statistics"]:
                if s["type"]==typ:
                    v=s.get("value")
                    try: return float(str(v).replace("%",""))
                    except (TypeError,ValueError): return None
            return None
        cf=g(mine,"Corner Kicks"); ca=g(opp,"Corner Kicks")
        if cf is None: continue
        agg["gp"]+=1
        agg["cf"]+=cf; agg["ca"]+=ca or 0
        agg["gf"]+=(f["goals"]["home"] if ishome else f["goals"]["away"]) or 0
        agg["ga"]+=(f["goals"]["away"] if ishome else f["goals"]["home"]) or 0
        for key,typ in (("poss","Ball Possession"),("shots","Total Shots"),("sot","Shots on Goal")):
            mv=g(mine,typ); ov=g(opp,typ)
            if mv is not None: agg[key+"_f"]+=mv
            if ov is not None: agg[key+"_a"]+=ov
    n=agg["gp"]
    if n==0: return {"error":f"no usable fixtures for {name}"}
    rec={k:round(agg[k]/n,1) for k in agg if k!="gp"}
    c=db()
    c.execute("""INSERT INTO team_history(team,season,gp,cf,ca,gf,ga,poss_f,poss_a,shots_f,shots_a,sot_f,sot_a,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(team) DO UPDATE SET
        season=excluded.season,gp=excluded.gp,cf=excluded.cf,ca=excluded.ca,gf=excluded.gf,ga=excluded.ga,
        poss_f=excluded.poss_f,poss_a=excluded.poss_a,shots_f=excluded.shots_f,shots_a=excluded.shots_a,
        sot_f=excluded.sot_f,sot_a=excluded.sot_a,updated_at=excluded.updated_at""",
        (name,str(season),n,rec["cf"],rec["ca"],rec["gf"],rec["ga"],rec["poss_f"],rec["poss_a"],
         rec["shots_f"],rec["shots_a"],rec["sot_f"],rec["sot_a"],_ts()))
    c.commit(); c.close()
    return {"team":name,"season":season,"gp":n,**rec}

def fetch_extras(row):
    """ACTUAL corners + first-scorer for grading; also PERSISTS the full stat line. Returns (corners|None, first|None)."""
    if row["sport"]!="soccer": return (None, None)
    try:
        b=espn_soccer_box(row["match"], row["kickoff"])
        if not b: return (None, None)
        if b.get("stats"): store_game_stats(row["match"], row["kickoff"], b["stats"])
        return (b["corners"], b["first"])
    except Exception:
        return (None, None)
def auto_fetch_score(row):
    """Route a pending pick to the right data source. Returns (hs,as_,desc) or None.
    Tries the attached fixture id first, then falls back to ESPN matchup lookup for soccer."""
    sp=row["sport"]
    if row["af_fixture_id"]:
        if sp in ESPN_PATH: return espn_fetch_score(sp, row["af_fixture_id"])   # ESPN: nba/wnba/mlb/nhl
        sc=af_fetch_score(row["af_fixture_id"])                                  # API-Football (soccer w/ id)
        if sc: return sc
    if sp=="soccer": return espn_soccer_final(row["match"], row["kickoff"])      # no id → ESPN by matchup+date
    return None

# ---------------------------------------------------------------- DB
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db(); c.execute("""
      CREATE TABLE IF NOT EXISTS predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT, event_date TEXT, sport TEXT, match TEXT, pick TEXT,
        market TEXT, selection TEXT, line REAL, odds REAL, stake REAL DEFAULT 1,
        tag TEXT, status TEXT DEFAULT 'pending',
        sofa_event_id INTEGER, home_score INTEGER, away_score INTEGER,
        result_note TEXT, settled_at TEXT)""")
    try: c.execute("ALTER TABLE predictions ADD COLUMN kickoff TEXT")   # migration: UTC ISO kickoff
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE predictions ADD COLUMN rationale TEXT") # migration: short reasoning
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE predictions ADD COLUMN af_fixture_id INTEGER")  # migration: API-Football fixture id
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE predictions ADD COLUMN archived INTEGER DEFAULT 0")  # migration: hide from daily board (kept in ledger)
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE predictions ADD COLUMN pred_score TEXT")  # migration: predicted correct score, e.g. "2-1" (flip-card back)
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE predictions ADD COLUMN pred_corners_home INTEGER")  # migration: predicted home-team total corners
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE predictions ADD COLUMN pred_corners_away INTEGER")  # migration: predicted away-team total corners
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE predictions ADD COLUMN home_corners INTEGER")  # migration: ACTUAL home-team corners (captured at settle)
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE predictions ADD COLUMN away_corners INTEGER")  # migration: ACTUAL away-team corners (captured at settle)
    except sqlite3.OperationalError: pass
    c.execute("""
      CREATE TABLE IF NOT EXISTS requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT, action TEXT, note TEXT,
        status TEXT DEFAULT 'open', result TEXT, done_at TEXT)""")
    c.execute("""
      CREATE TABLE IF NOT EXISTS insights(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT, summary TEXT, metrics TEXT)""")
    # Daily game slate — the next day's fixtures for the live tournament. User ticks `checked` (research this),
    # Claude sets `starred` (recommend → prod). Drives the daily pick workflow.
    c.execute("""
      CREATE TABLE IF NOT EXISTS slate(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT, date TEXT, sport TEXT DEFAULT 'soccer', tournament TEXT,
        match TEXT, event_ticker TEXT, kickoff TEXT,
        checked INTEGER DEFAULT 0, starred INTEGER DEFAULT 0, researched INTEGER DEFAULT 0, note TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS corner_bets(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, date TEXT, match TEXT, kickoff TEXT,
        side TEXT, side_name TEXT, price INTEGER, our_prob REAL, edge REAL, stake REAL DEFAULT 5,
        currency TEXT DEFAULT 'GC', status TEXT DEFAULT 'pending', hc INTEGER, ac INTEGER,
        result_side TEXT, settled_at TEXT, note TEXT)""")  # Corner-1x2 paper tracker (Sportzino directional market; Gold Coins)
    # Full per-game stat line (possession/shots/fouls/cards/crosses/corners) captured from ESPN at settle —
    # the upstream control drivers, not just corners. home_json/away_json = {statName: float}.
    c.execute("""CREATE TABLE IF NOT EXISTS game_stats(
        match TEXT, date TEXT, home_json TEXT, away_json TEXT, updated_at TEXT, PRIMARY KEY(match,date))""")
    # Thick prior from API-Football (free 2022-2024 seasons): per-team corner/possession/shot averages
    # over a full season of games — fixes the thin 1-game WC samples. for & against.
    c.execute("""CREATE TABLE IF NOT EXISTS team_history(
        team TEXT PRIMARY KEY, season TEXT, gp INTEGER,
        cf REAL, ca REAL, gf REAL, ga REAL,
        poss_f REAL, poss_a REAL, shots_f REAL, shots_a REAL, sot_f REAL, sot_a REAL, updated_at TEXT)""")
    c.commit()
    n = c.execute("SELECT COUNT(*) n FROM predictions").fetchone()["n"]
    if n == 0: seed(c)
    c.close()

def seed(c):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    rows = [
      # event_date, sport, match, pick, market, selection, line, odds, tag, status, eid, hs, as_
      ("Fri Jun 6 · Friendlies","soccer","England v New Zealand","England BTTS No","btts","no",None,1.44,"best","win",15926544,1,0),
      ("Fri Jun 6 · Friendlies","soccer","Curaçao v Aruba","Curaçao Over 2.5","total","over",2.5,1.36,"","win",16130147,4,0),
      ("Fri Jun 6 · Friendlies","soccer","Argentina v Honduras","Honduras +2.25","handicap","away",2.25,1.98,"value","win",16118858,2,0),
      ("Fri Jun 6 · Friendlies","soccer","England v New Zealand","England -2.25 (aggressive)","handicap","home",-2.25,1.83,"lean","loss",15926544,1,0),

      ("Sat Jun 7 · Friendlies","soccer","Liechtenstein v Cyprus","Cyprus -1.5","handicap","away",-1.5,1.82,"best","pending",None,None,None),
      ("Sat Jun 7 · Friendlies","soccer","Kosovo v Andorra","Kosovo Over 2.5","total","over",2.5,1.75,"","pending",16174757,None,None),
      ("Sat Jun 7 · Friendlies","soccer","Greece v Italy","Italy +0.25","handicap","away",0.25,1.95,"value","pending",16174773,None,None),
      ("Sat Jun 7 · Friendlies","soccer","Morocco v Norway","Morocco +0.25","handicap","home",0.25,1.85,"value","pending",16118859,None,None),
      ("Sat Jun 7 · Friendlies","soccer","Ecuador v Guatemala","Ecuador -1","handicap","home",-1.0,1.17,"","pending",None,None,None),
      ("Sat Jun 7 · Friendlies","soccer","Croatia v Slovenia","Croatia/Slovenia Under 2.5","total","under",2.5,1.85,"lean","pending",None,None,None),

      ("Sat Jun 7 · NBA Finals","nba","Knicks vs Spurs","Spurs +2.0","handicap","away",2.0,1.91,"best","pending",15935069,None,None),
      ("Sat Jun 7 · NBA Finals","nba","Knicks vs Spurs","Under 215.5","total","under",215.5,1.91,"","pending",15935069,None,None),

      ("Sun Jun 8 · Friendlies","soccer","Spain v Peru","Spain -1.5","handicap","home",-1.5,1.50,"best","pending",None,None,None),
      ("Sun Jun 8 · Friendlies","soccer","France v Northern Ireland","France -1.5","handicap","home",-1.5,1.50,"","pending",None,None,None),
      ("Sun Jun 8 · Friendlies","soccer","Netherlands v Uzbekistan","Netherlands -1.5","handicap","home",-1.5,1.60,"","pending",None,None,None),
      ("Sun Jun 8 · Friendlies","soccer","Panama v Jamaica","Panama/Jamaica Draw","draw","draw",None,3.20,"value","pending",None,None,None),
    ]
    for r in rows:
        c.execute("""INSERT INTO predictions
          (created_at,event_date,sport,match,pick,market,selection,line,odds,stake,tag,status,sofa_event_id,home_score,away_score,settled_at)
          VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)""",
          (now,r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9],r[10],r[11],r[12],
           now if r[9] in("win","loss","void") else None))
    c.commit()

# ---------------------------------------------------------------- grading
def _q(line, fn):
    """Evaluate a handicap/total line, splitting quarter lines into two halves."""
    r2 = round(line * 4)
    is_quarter = (r2 % 2 != 0)            # .25 or .75
    if not is_quarter:
        return {"win":"win","loss":"loss","push":"void"}[fn(line)]
    a, b = fn(line - 0.25), fn(line + 0.25)
    s = {a, b}
    if s == {"win"}: return "win"
    if s == {"loss"}: return "loss"
    if s == {"win","push"}: return "half_win"
    if s == {"loss","push"}: return "half_loss"
    return "void"

def grade(market, selection, line, hs, as_, hc=None, ac=None, first=None):
    """Grade any of the Sportzino market types. Goal markets need hs/as_; corner markets need hc/ac
    (home/away corner counts); first-goal needs `first` ('home'/'away'/'none'). Returns None when the
    data needed for that market isn't available yet (→ pick stays pending, never mis-graded)."""
    if hs is None or as_ is None: return None
    m, sel = (market or "").lower(), (selection or "").lower()
    if m in ("1x2", "win", "ml", "moneyline"):   # match-result / moneyline — a side-to-win bet; draw = loss
        res = "home" if hs>as_ else "away" if as_>hs else "draw"
        return "win" if sel==res else "loss"
    if m == "draw":
        return "win" if hs==as_ else "loss"
    if m == "btts":
        b = hs>0 and as_>0
        return ("win" if b else "loss") if sel in ("yes","y") else ("win" if not b else "loss")
    if m in ("total","totals","ou"):
        tot = hs+as_
        def one(l): return "win" if (tot>l)==(sel.startswith("o")) and tot!=l else ("push" if tot==l else "loss")
        return _q(line, one)
    if m in ("team_total","teamtotal","tt"):   # a single team's goal total; selection=home/away (+ optional _under)
        gf = hs if sel.startswith("home") else as_
        over = not sel.endswith("under")       # default OVER (the favorite team-total play); "_under" flips it
        def one(l): return "win" if (gf>l)==over and gf!=l else ("push" if gf==l else "loss")
        return _q(line, one)
    if m in ("handicap","ah","spread"):
        selsc, oppsc = (hs,as_) if sel.startswith("home") else (as_,hs)
        diff = selsc - oppsc
        def one(l):
            v = diff + l
            return "win" if v>0 else "loss" if v<0 else "push"
        return _q(line, one)
    # ---- corner markets (need actual corner counts hc/ac; None until the boxscore posts) ----
    if m in ("corners","total_corners","totalcorners","corner_total","corners_total"):   # GAME total corners O/U
        if hc is None or ac is None: return None
        tc = hc+ac
        def one(l): return "win" if (tc>l)==(sel.startswith("o")) and tc!=l else ("push" if tc==l else "loss")
        return _q(line, one)
    if m in ("team_corners","teamcorners","team_total_corners","tc"):   # a single team's corner total; selection=home/away (+ optional _under)
        if hc is None or ac is None: return None
        cf = hc if sel.startswith("home") else ac
        over = not sel.endswith("under")
        def one(l): return "win" if (cf>l)==over and cf!=l else ("push" if cf==l else "loss")
        return _q(line, one)
    if m in ("corner_1x2","corner1x2","corners_1x2","corner_result"):   # which team wins the corner count
        if hc is None or ac is None: return None
        res = "home" if hc>ac else "away" if ac>hc else "draw"
        return "win" if sel==res else "loss"
    # ---- first goal / first team to score (needs the goal timeline) ----
    if m in ("first_goal","firstgoal","first_team_to_score","ftts","first_to_score"):
        if first is None: return None
        s = "none" if sel in ("none","no","neither","draw","x") else sel
        return "win" if s==first else "loss"
    return None

def profit(status, odds, stake):
    o, s = (odds or 0), (stake or 0)
    return {"win":s*(o-1), "loss":-s, "void":0.0,
            "half_win":s/2*(o-1), "half_loss":-s/2}.get(status, 0.0)

# ---------------------------------------------------------------- stats
def compute_stats(rows):
    settled=[r for r in rows if r["status"] in ("win","loss","half_win","half_loss","void")]
    wins=sum(1 for r in rows if r["status"] in ("win","half_win"))
    loss=sum(1 for r in rows if r["status"] in ("loss","half_loss"))
    staked=sum((r["stake"] or 0) for r in settled if r["status"]!="void")
    pnl=sum(profit(r["status"], r["odds"], r["stake"]) for r in rows)
    pend=sum(1 for r in rows if r["status"]=="pending")
    decisive=wins+loss
    return {"total":len(rows),"pending":pend,"settled":len(settled),
            "wins":wins,"losses":loss,
            "win_rate": round(100*wins/decisive,1) if decisive else None,
            "staked":round(staked,2),"profit":round(pnl,2),
            "roi": round(100*pnl/staked,1) if staked else None,
            "bankroll_start":BANKROLL_START,
            "balance":round(BANKROLL_START+pnl,2),
            "growth_pct":round(100*pnl/BANKROLL_START,1)}

def compute_analysis(rows):
    """Performance breakdowns over SETTLED picks — feeds the Learn loop."""
    settled=[r for r in rows if r["status"] in ("win","loss","half_win","half_loss","void")]
    def grp(keyfn):
        out={}
        for r in settled:
            k=keyfn(r) or "—"
            g=out.setdefault(k,{"n":0,"w":0,"l":0,"staked":0.0,"pnl":0.0})
            g["n"]+=1
            if r["status"] in ("win","half_win"): g["w"]+=1
            if r["status"] in ("loss","half_loss"): g["l"]+=1
            if r["status"]!="void": g["staked"]+=(r["stake"] or 0)
            g["pnl"]+=profit(r["status"], r["odds"], r["stake"])
        for k,g in out.items():
            g["pnl"]=round(g["pnl"],2)
            g["roi"]=round(100*g["pnl"]/g["staked"],1) if g["staked"] else None
        return out
    def odds_bucket(r):
        o=r["odds"] or 0
        return "<1.6" if o<1.6 else "1.6–1.99" if o<2.0 else "2.0–2.5" if o<=2.5 else ">2.5"
    return {"settled_count":len(settled),
            "by_tag":grp(lambda r:r["tag"] or "untagged"),
            "by_market":grp(lambda r:r["market"]),
            "by_selection":grp(lambda r:r["selection"]),
            "by_sport":grp(lambda r:r["sport"]),
            "by_odds":grp(odds_bucket)}

# ---------------------------------------------------------------- HTTP
def row_dict(r):
    d=dict(r); d["profit"]=round(profit(d["status"],d["odds"],d["stake"]),3); return d

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _send(self,obj,code=200,ctype="application/json"):
        body = obj if isinstance(obj,(bytes,)) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def _body(self):
        n=int(self.headers.get("Content-Length",0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u=urlparse(self.path); p=u.path; q=parse_qs(u.query)
        if p in ("/","/index.html"):
            dist_idx=os.path.join(ROOT,"web","dist","index.html")          # React build (preferred)
            path=dist_idx if os.path.exists(dist_idx) else os.path.join(ROOT,"index.html")
            try:
                with open(path,"rb") as f:
                    return self._send(f.read(),ctype="text/html; charset=utf-8")
            except FileNotFoundError: return self._send({"error":"index.html missing"},500)
        if p=="/classic":                                                   # old vanilla dashboard (fallback/rollback)
            try:
                with open(os.path.join(ROOT,"index.html"),"rb") as f:
                    return self._send(f.read(),ctype="text/html; charset=utf-8")
            except FileNotFoundError: return self._send({"error":"index.html missing"},500)
        if p.startswith("/assets/"):                                        # React build static assets
            distdir=os.path.join(ROOT,"web","dist")
            fp=os.path.normpath(os.path.join(distdir,p.lstrip("/")))
            if not fp.startswith(distdir) or not os.path.exists(fp):
                return self._send({"error":"not found"},404)
            ctype={".js":"text/javascript",".css":"text/css",".svg":"image/svg+xml",
                   ".map":"application/json",".woff2":"font/woff2",".woff":"font/woff",
                   ".png":"image/png",".ico":"image/x-icon"}.get(os.path.splitext(fp)[1],"application/octet-stream")
            with open(fp,"rb") as f:
                return self._send(f.read(),ctype=ctype+("; charset=utf-8" if ctype.startswith("text") else ""))
        if p=="/api/predictions":
            c=db(); rows=[row_dict(r) for r in c.execute("SELECT * FROM predictions ORDER BY id").fetchall()]; c.close()
            return self._send(rows)
        if p=="/api/stats":
            c=db(); rows=c.execute("SELECT * FROM predictions").fetchall(); c.close()
            return self._send(compute_stats([dict(r) for r in rows]))
        if p=="/api/slate":   # daily game slate. ?date=YYYY-MM-DD (default: all upcoming, soonest first)
            c=db(); dt=q.get("date",[""])[0]
            sql="SELECT * FROM slate"+(" WHERE date=?" if dt else "")+" ORDER BY date,kickoff,id"
            rows=[dict(r) for r in c.execute(sql,((dt,) if dt else ())).fetchall()]; c.close()
            return self._send(rows)
        if p=="/api/requests":
            c=db(); rows=[dict(r) for r in c.execute("SELECT * FROM requests ORDER BY id DESC LIMIT 30").fetchall()]; c.close()
            return self._send(rows)
        if p=="/api/corners":   # Corner-1x2 paper tracker
            c=db(); rows=[corner_bet_dict(r) for r in c.execute("SELECT * FROM corner_bets ORDER BY id DESC").fetchall()]; c.close()
            return self._send(rows)
        if p=="/api/corner-rates":   # per-team corner+goal base rates (data-grounded storyline foundation)
            R=team_corner_rates()
            return self._send(sorted([dict(team=t,**v) for t,v in R.items()], key=lambda x:-x["cf"]))
        if p=="/api/team-stats":   # per-team full stat line (possession/shots/fouls/cards) for & against
            R=team_stat_rates()
            return self._send(sorted([dict(team=t,**v) for t,v in R.items()], key=lambda x:-(x["for"].get("possessionPct",0))))
        if p=="/api/storyline":   # data-grounded pre-game read. ?home=Tunisia&away=Japan
            h=q.get("home",[""])[0]; a=q.get("away",[""])[0]
            if not h or not a: return self._send({"error":"home and away required"},400)
            return self._send(storyline_read(h,a))
        if p=="/api/analysis":
            c=db(); rows=[dict(r) for r in c.execute("SELECT * FROM predictions").fetchall()]; c.close()
            return self._send(compute_analysis(rows))
        if p=="/api/insights":
            c=db(); rows=[dict(r) for r in c.execute("SELECT * FROM insights ORDER BY id DESC LIMIT 10").fetchall()]; c.close()
            return self._send(rows)
        if p=="/api/staged":                                                # Kalshi staged-order slate (approve in UI)
            try:
                with open(os.path.join(ROOT,"staged_orders.json")) as fh: data=json.load(fh)
            except Exception: data={"orders":[]}
            return self._send(data)
        if p=="/api/export.csv":
            c=db(); rows=c.execute("SELECT * FROM predictions ORDER BY id").fetchall(); c.close()
            buf=io.StringIO(); w=csv.writer(buf)
            cols=["id","event_date","sport","match","pick","market","selection","line","odds","stake","tag","status","home_score","away_score","result_note"]
            w.writerow(cols)
            for r in rows: w.writerow([r[k] for k in cols])
            return self._send(buf.getvalue().encode(),ctype="text/csv")
        if p=="/api/apifootball/key-set":
            return self._send({"set": bool(apifootball_key())})
        if p=="/api/apifootball/status":
            try: return self._send(apifootball("status"))
            except Exception as e: return self._send({"error":str(e)},502)
        if p=="/api/apifootball/fixtures":   # passthrough: ?date=YYYY-MM-DD or ?id= or ?team=&season= etc.
            try: return self._send(apifootball("fixtures", {k:v[0] for k,v in q.items()}))
            except Exception as e: return self._send({"error":str(e)},502)
        if p=="/api/weather":                # ?city=Lisbon&when=2026-06-11T19:00:00Z  (keyless, Open-Meteo)
            city=q.get("city",[""])[0]; when=q.get("when",[""])[0]
            if not city or not when: return self._send({"error":"city and when required"},400)
            try:
                w=weather_for(city,when); return self._send(w or {"error":"no weather data for that city/time"}, 200 if w else 404)
            except Exception as e: return self._send({"error":str(e)},502)
        if p in ("/api/wnba/games","/api/mlb/games","/api/nhl/games"):   # ESPN scoreboard (keyless). ?date=YYYY-MM-DD
            sport=p.split("/")[2]
            try: return self._send(espn_games(sport, q.get("date",[""])[0]))
            except Exception as e: return self._send({"error":str(e)},502)
        if p=="/api/polymarket":   # read-only Polymarket implied probabilities (no account/trading). ?q=world cup group a
            qq=q.get("q",[""])[0]
            if not qq: return self._send({"error":"q (search query) required"},400)
            try: return self._send(polymarket_search(qq))
            except Exception as e: return self._send({"error":str(e)},502)
        return self._send({"error":"not found"},404)

    def do_POST(self):
        u=urlparse(self.path); p=u.path
        # ===== Corner-1x2 paper tracker (Sportzino directional market) =====
        if p=="/api/corners":   # log a corner-1x2 paper bet. {date,match,kickoff,side(home/away),side_name,price(american),our_prob,stake,note}
            b=self._body()
            try: price=int(b.get("price"))
            except (TypeError,ValueError): return self._send({"error":"price (american odds int) required"},400)
            our=float(b.get("our_prob") or 0); edge=round(our-amer_implied(price),3)
            c=db(); cur=c.execute("""INSERT INTO corner_bets
                (created_at,date,match,kickoff,side,side_name,price,our_prob,edge,stake,currency,status,note)
                VALUES(?,?,?,?,?,?,?,?,?,?,?, 'pending', ?)""",
                (_ts(),b.get("date"),b.get("match"),b.get("kickoff"),b.get("side"),b.get("side_name"),
                 price,our,edge,b.get("stake",5),b.get("currency","GC"),b.get("note")))
            c.commit(); rid=cur.lastrowid
            row=c.execute("SELECT * FROM corner_bets WHERE id=?",(rid,)).fetchone(); c.close()
            return self._send(corner_bet_dict(row),201)
        if p=="/api/corners/settle-all":   # grade pending corner bets off ACTUAL corners (ESPN matchup); win if our side won the corner count
            c=db(); rows=c.execute("SELECT * FROM corner_bets WHERE status='pending'").fetchall(); done=[]
            for r in rows:
                try: cor=espn_soccer_corners(r["match"], r["kickoff"])
                except Exception: cor=None
                if not cor: continue
                hc,ac=cor; rs="home" if hc>ac else "away" if ac>hc else "draw"
                st="push" if rs=="draw" else ("win" if r["side"]==rs else "loss")
                c.execute("UPDATE corner_bets SET status=?,hc=?,ac=?,result_side=?,settled_at=? WHERE id=?",
                          (st,hc,ac,rs,_ts(),r["id"]))
                done.append({"id":r["id"],"match":r["match"],"status":st,"corners":f"{hc}-{ac}"})
            c.commit(); c.close(); return self._send({"settled":done})

        # ===== Daily game slate + board archiving =====
        if p=="/api/slate":   # populate a day's slate. {date, sport, tournament, games:[{match,event_ticker,kickoff,starred,note}]}
            b=self._body(); dt=b.get("date")
            if not dt: return self._send({"error":"date required"},400)
            c=db()
            if b.get("replace",True): c.execute("DELETE FROM slate WHERE date=?",(dt,))
            for gm in (b.get("games") or []):
                c.execute("""INSERT INTO slate(created_at,date,sport,tournament,match,event_ticker,kickoff,starred,note)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (_ts(),dt,gm.get("sport",b.get("sport","soccer")),gm.get("tournament",b.get("tournament","World Cup")),
                     gm.get("match"),gm.get("event_ticker"),gm.get("kickoff"),1 if gm.get("starred") else 0,gm.get("note")))
            c.commit()
            rows=[dict(r) for r in c.execute("SELECT * FROM slate WHERE date=? ORDER BY kickoff,id",(dt,)).fetchall()]; c.close()
            return self._send(rows,201)
        if p=="/api/slate/clear":   # {before:YYYY-MM-DD} delete older slate rows (or all if omitted)
            b=self._body(); before=b.get("before"); c=db()
            c.execute("DELETE FROM slate WHERE date<?",(before,)) if before else c.execute("DELETE FROM slate")
            c.commit(); c.close(); return self._send({"cleared":True,"before":before})
        if p.startswith("/api/slate/") and p[len("/api/slate/"):].isdigit():   # toggle flags. {checked?,starred?,researched?,note?}
            rid=int(p.split("/")[3]); b=self._body(); c=db()
            fields=[k for k in ("checked","starred","researched","note","match","event_ticker","kickoff") if k in b]
            if fields:
                sets=",".join(f"{k}=?" for k in fields)
                vals=[(1 if b[k] else 0) if k in ("checked","starred","researched") else b[k] for k in fields]
                vals.append(rid); c.execute(f"UPDATE slate SET {sets} WHERE id=?",vals); c.commit()
            row=c.execute("SELECT * FROM slate WHERE id=?",(rid,)).fetchone(); c.close()
            return self._send(dict(row) if row else {"error":"not found"}, 200 if row else 404)
        if p=="/api/predictions/archive-settled":   # hide settled picks dated before `before` from the daily board (kept in ledger/analysis)
            b=self._body(); before=b.get("before") or datetime.date.today().isoformat(); c=db()
            cur=c.execute("""UPDATE predictions SET archived=1
                WHERE status!='pending' AND COALESCE(archived,0)=0
                AND COALESCE(substr(kickoff,1,10),substr(settled_at,1,10),substr(created_at,1,10))<?""",(before,))
            c.commit(); n=cur.rowcount; c.close()
            return self._send({"archived":n,"before":before})
        if p=="/api/config/apifootball-key":
            b=self._body(); key=(b.get("key") or "").strip()
            if not (key and key.isalnum() and 20<=len(key)<=64):
                return self._send({"error":"invalid key format"},400)
            with open(APIFOOTBALL_KEYFILE,"w") as f: f.write(key)
            try: os.chmod(APIFOOTBALL_KEYFILE,0o600)
            except Exception: pass
            return self._send({"saved":True})
        if p=="/api/request":
            b=self._body(); ts=datetime.datetime.now().isoformat(timespec="seconds")
            action=b.get("action","settle_and_predict"); note=b.get("note","")
            c=db(); cur=c.execute("INSERT INTO requests(created_at,action,note,status) VALUES(?,?,?,'open')",(ts,action,note))
            c.commit(); rid=cur.lastrowid
            row=dict(c.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()); c.close()
            try:
                with open(INBOX,"a") as f: f.write(json.dumps({"id":rid,"ts":ts,"action":action,"note":note})+"\n")
            except Exception: pass
            row["dispatched"] = False   # request queued in DB + inbox; Claude fulfills on manual activation
            return self._send(row,201)
        if p in ("/api/staged/execute","/api/staged/dismiss"):
            # Kalshi staged slate. EXECUTE is only ever triggered by the USER's Approve click in the UI —
            # the server relays their decision to kalshi_client.py. Claude never calls this endpoint.
            b=self._body(); i=int(b.get("index",-1))
            spath=os.path.join(ROOT,"staged_orders.json")
            try:
                with open(spath) as fh: data=json.load(fh)
            except Exception: return self._send({"error":"no staged file"},404)
            orders=data.get("orders",[])
            if not (0<=i<len(orders)): return self._send({"error":"bad index"},400)
            o=orders[i]
            if p.endswith("dismiss"):
                o["status"]="dismissed"
            else:
                if o.get("status")=="live": return self._send({"error":"already live"},409)
                prm=o.get("params") or {}
                if not prm: return self._send({"error":"order missing params"},400)
                venvpy=os.path.join(ROOT,".venv","bin","python")
                if prm.get("cancel_order_id"):        # re-price: cancel the stale resting order first
                    rc=subprocess.run([venvpy,os.path.join(ROOT,"kalshi_client.py"),"cancel",prm["cancel_order_id"]],
                                      cwd=ROOT,capture_output=True,text=True,timeout=30)
                    if rc.returncode!=0:
                        o["status"]="error"; o["exchange_response"]={"cancel_failed":(rc.stderr or rc.stdout)[:300]}
                        with open(spath,"w") as fh: json.dump(data,fh,indent=1)
                        return self._send({"index":i,"status":"error","response":o["exchange_response"]})
                payload=json.dumps({"ticker":prm["ticker"],"action":prm["action"],
                                    "side":prm["side"],"count":prm["count"],
                                    "price_cents":prm["price_cents"],
                                    "post_only":prm.get("post_only",True),"live":True})
                venvpy=os.path.join(ROOT,".venv","bin","python")
                try:
                    r=subprocess.run([venvpy,os.path.join(ROOT,"kalshi_client.py"),"place",payload],
                                     cwd=ROOT,capture_output=True,text=True,timeout=30)
                    out=(r.stdout or "").strip()
                    try: resp=json.loads(out)
                    except Exception: resp={"raw":out[:300],"stderr":(r.stderr or "")[:300],"rc":r.returncode}
                    o["status"]="live" if r.returncode==0 else "error"
                    o["exchange_response"]=resp
                    o["executed_at"]=datetime.datetime.now().isoformat(timespec="seconds")
                except Exception as e:
                    o["status"]="error"; o["exchange_response"]={"error":str(e)[:300]}
            with open(spath,"w") as fh: json.dump(data,fh,indent=1)
            return self._send({"index":i,"status":o["status"],"response":o.get("exchange_response")})
        if p=="/api/insights":
            b=self._body(); c=db()
            cur=c.execute("INSERT INTO insights(created_at,summary,metrics) VALUES(?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"),b.get("summary",""),json.dumps(b.get("metrics",{}))))
            c.commit(); rid=cur.lastrowid
            row=dict(c.execute("SELECT * FROM insights WHERE id=?", (rid,)).fetchone()); c.close()
            return self._send(row,201)
        if p.startswith("/api/requests/") and p.endswith("/done"):
            rid=int(p.split("/")[3]); b=self._body(); c=db()
            c.execute("UPDATE requests SET status='done',result=?,done_at=? WHERE id=?",
                      (b.get("result",""),datetime.datetime.now().isoformat(timespec="seconds"),rid))
            c.commit(); row=c.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone(); c.close()
            return self._send(dict(row) if row else {"error":"not found"})
        if p=="/api/predictions":
            b=self._body(); c=db()
            cur=c.execute("""INSERT INTO predictions
              (created_at,event_date,sport,match,pick,market,selection,line,odds,stake,tag,status,sofa_event_id,af_fixture_id,kickoff,rationale,pred_score,pred_corners_home,pred_corners_away)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (datetime.datetime.now().isoformat(timespec="seconds"),
               b.get("event_date","Misc"),b.get("sport","soccer"),b.get("match",""),b.get("pick",""),
               b.get("market","other"),b.get("selection"),b.get("line"),b.get("odds"),b.get("stake",50),
               b.get("tag",""),b.get("status","pending"),b.get("sofa_event_id"),b.get("af_fixture_id"),b.get("kickoff"),b.get("rationale"),
               b.get("pred_score"),b.get("pred_corners_home"),b.get("pred_corners_away")))
            c.commit(); rid=cur.lastrowid
            row=c.execute("SELECT * FROM predictions WHERE id=?", (rid,)).fetchone(); c.close()
            return self._send(row_dict(row),201)
        if p.startswith("/api/predictions/") and p.endswith("/settle-with-score"):
            rid=int(p.split("/")[3]); b=self._body(); c=db()
            r=c.execute("SELECT * FROM predictions WHERE id=?", (rid,)).fetchone()
            if not r: c.close(); return self._send({"error":"not found"},404)
            hs,as_=b.get("home_score"),b.get("away_score")
            if hs is None or as_ is None: c.close(); return self._send({"error":"home_score and away_score required"},400)
            ko=r["kickoff"]                                   # GUARD: never settle a game that hasn't kicked off
            if ko:
                try:
                    kdt=datetime.datetime.fromisoformat(str(ko).replace("Z","+00:00"))
                    if datetime.datetime.now(datetime.timezone.utc) < kdt:
                        c.close(); return self._send({"error":f"REFUSED: kickoff {ko} is in the future — game cannot be finished. Do not fabricate scores."},409)
                except Exception: pass
            cor, fg = fetch_extras(r)                  # corners + first-scorer for control / first-goal markets
            if b.get("home_corners") is not None and b.get("away_corners") is not None:
                try: cor=(int(b["home_corners"]), int(b["away_corners"]))   # allow manual corner entry
                except (TypeError,ValueError): pass
            hc,ac = cor if cor else (None,None)
            st=grade(r["market"],r["selection"],r["line"],int(hs),int(as_),hc,ac,fg)
            if st is None: c.close(); return self._send({"error":"could not grade this market (corner/first-goal data not available yet — pass home_corners/away_corners to settle a corner market manually)"},422)
            note=b.get("result_note") or f"{r['match']} {int(hs)}-{int(as_)}"
            c.execute("UPDATE predictions SET status=?,home_score=?,away_score=?,result_note=?,settled_at=? WHERE id=?",
                      (st,int(hs),int(as_),note,datetime.datetime.now().isoformat(timespec="seconds"),rid))
            if cor: c.execute("UPDATE predictions SET home_corners=?,away_corners=? WHERE id=?",(cor[0],cor[1],rid))
            c.commit(); row=c.execute("SELECT * FROM predictions WHERE id=?", (rid,)).fetchone(); c.close()
            return self._send(row_dict(row))
        if p.startswith("/api/predictions/") and p.endswith("/settle-af"):   # autonomous settle via API-Football / API-NBA / ESPN
            rid=int(p.split("/")[3]); c=db()
            r=c.execute("SELECT * FROM predictions WHERE id=?", (rid,)).fetchone()
            if not r: c.close(); return self._send({"error":"not found"},404)
            if not r["af_fixture_id"]: c.close(); return self._send({"error":"no af_fixture_id on this pick"},400)
            try: sc=auto_fetch_score(r)
            except Exception as e: c.close(); return self._send({"error":f"api-sports fetch failed: {e}"},502)
            if not sc: c.close(); return self._send({"error":"match not finished per api-sports"},409)
            hs,as_,desc=sc
            cor, fg = fetch_extras(r); hc,ac = cor if cor else (None,None)
            st=grade(r["market"],r["selection"],r["line"],hs,as_,hc,ac,fg)
            if st is None: c.close(); return self._send({"error":"could not grade this market (corner/first-goal data not available yet)"},422)
            c.execute("UPDATE predictions SET status=?,home_score=?,away_score=?,result_note=?,settled_at=? WHERE id=?",
                      (st,hs,as_,desc,datetime.datetime.now().isoformat(timespec="seconds"),rid))
            if cor: c.execute("UPDATE predictions SET home_corners=?,away_corners=? WHERE id=?",(cor[0],cor[1],rid))
            c.commit(); row=c.execute("SELECT * FROM predictions WHERE id=?", (rid,)).fetchone(); c.close()
            return self._send(row_dict(row))
        if p=="/api/settle-all-af":   # settle every pending pick — via fixture id, or ESPN matchup lookup (soccer)
            c=db(); rows=c.execute("SELECT * FROM predictions WHERE status='pending'").fetchall()
            done=[]
            for r in rows:
                try: sc=auto_fetch_score(r)
                except Exception: continue
                if not sc: continue
                hs,as_,desc=sc
                cor, fg = fetch_extras(r); hc,ac = cor if cor else (None,None)
                st=grade(r["market"],r["selection"],r["line"],hs,as_,hc,ac,fg)
                if st is None: continue
                c.execute("UPDATE predictions SET status=?,home_score=?,away_score=?,result_note=?,settled_at=? WHERE id=?",
                          (st,hs,as_,desc,datetime.datetime.now().isoformat(timespec="seconds"),r["id"]))
                if cor: c.execute("UPDATE predictions SET home_corners=?,away_corners=? WHERE id=?",(cor[0],cor[1],r["id"]))
                done.append({"id":r["id"],"pick":r["pick"],"status":st,"score":f"{hs}-{as_}"})
            c.commit(); c.close()
            return self._send({"settled":done})
        if p=="/api/publish-site":   # re-export public_site + deploy to Netlify (finished games drop off, next pick slides in)
            site_id="999d079e-2f4f-4a3a-85b4-0b1bca946c7a"   # edge-machine-picks.netlify.app
            ex=subprocess.run(["python3", os.path.join(ROOT,"export_public.py")],
                              capture_output=True, text=True, timeout=120)
            if ex.returncode!=0:
                return self._send({"error":f"export failed: {(ex.stderr or ex.stdout)[-300:]}"},500)
            tok_path=os.path.join(ROOT,".netlify_token")
            if not os.path.exists(tok_path):
                return self._send({"exported":True,"deployed":False,
                    "note":"Exported, but no .netlify_token — save a Netlify personal access token to ~/Predictions/.netlify_token (chmod 600) to deploy from this button, or ask Claude to deploy."})
            buf=io.BytesIO(); pub=os.path.join(ROOT,"public_site")
            with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
                for fn in os.listdir(pub): z.write(os.path.join(pub,fn),fn)
            req=urllib.request.Request(f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
                data=buf.getvalue(), method="POST",
                headers={"Content-Type":"application/zip",
                         "Authorization":f"Bearer {open(tok_path).read().strip()}"})
            try:
                with urllib.request.urlopen(req,timeout=90) as f: d=json.load(f)
            except urllib.error.HTTPError as e:
                return self._send({"exported":True,"deployed":False,"error":f"netlify deploy failed: HTTP {e.code}"},502)
            return self._send({"exported":True,"deployed":True,"state":d.get("state"),
                               "url":"https://edge-machine-picks.netlify.app"})
        return self._send({"error":"not found"},404)

    def do_PATCH(self):
        u=urlparse(self.path); p=u.path
        if p.startswith("/api/predictions/"):
            rid=int(p.split("/")[3]); b=self._body(); c=db()
            fields=[k for k in ("event_date","sport","match","pick","market","selection","line","odds","stake","tag","status","home_score","away_score","sofa_event_id","af_fixture_id","result_note","kickoff","rationale","pred_score","pred_corners_home","pred_corners_away","home_corners","away_corners") if k in b]
            if fields:
                sets=",".join(f"{k}=?" for k in fields); vals=[b[k] for k in fields]
                if "status" in b and b["status"]!="pending":
                    sets+=",settled_at=?"; vals.append(datetime.datetime.now().isoformat(timespec="seconds"))
                vals.append(rid); c.execute(f"UPDATE predictions SET {sets} WHERE id=?", vals); c.commit()
            row=c.execute("SELECT * FROM predictions WHERE id=?", (rid,)).fetchone(); c.close()
            return self._send(row_dict(row) if row else {"error":"not found"}, 200 if row else 404)
        return self._send({"error":"not found"},404)

    def do_DELETE(self):
        p=urlparse(self.path).path
        if p.startswith("/api/predictions/"):
            rid=int(p.split("/")[3]); c=db(); c.execute("DELETE FROM predictions WHERE id=?", (rid,)); c.commit(); c.close()
            return self._send({"ok":True})
        if p.startswith("/api/slate/"):
            rid=int(p.split("/")[3]); c=db(); c.execute("DELETE FROM slate WHERE id=?", (rid,)); c.commit(); c.close()
            return self._send({"ok":True})
        return self._send({"error":"not found"},404)

if __name__=="__main__":
    init_db()
    print(f"Prediction Tracker → http://127.0.0.1:{PORT}  (db: {DB})")
    ThreadingHTTPServer(("0.0.0.0",PORT), H).serve_forever()  # all interfaces → reachable via Tailscale IP & LAN
