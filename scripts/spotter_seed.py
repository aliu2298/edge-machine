#!/usr/bin/env python3
"""ONE-OFF provenance script (2026-11-18): freezes the NBA spotter's model and priors into data/spotter/ from Fable's research folder
(~/edge-research/nba_stars_2026-11-18/). NOT run in CI. No refit: sp_model.json is copied byte for byte (hold + spike), the other numbers
(pull toward the middle, night spreads, the standardised-night tables) are the research's own, read out of its sp_data.py / form.py top.
python3 scripts/spotter_seed.py  ->  data/spotter/model.json, last.json, games.json"""
import collections, datetime as dt, hashlib, json, os, sys
H = os.path.expanduser('~/edge-research/nba_stars_2026-11-18'); sys.path.insert(0, H)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'spotter')
raw = json.load(open(os.path.join(H, 'tonight_dl', 'games_20261117.json'))); EXTRA_GAMES = []
for g in raw:
    h, a = g['teams']['home'], g['teams']['away']
    EXTRA_GAMES.append(dict(id=g['id'], t=dt.datetime.fromisoformat(g['date'].replace('Z', '+00:00')).timestamp(), day=g['date'][:10], season=g['season'], home=h['abbr'], away=a['abbr'], hq=h['q'], aq=a['q'], hs=h['score'], as_=a['score'], ot=len(h['q']) > 4, box=g['box']))
src = open(os.path.join(H, 'sp_data.py')).read().split('# contracts')[0].replace("ALL = sorted(S.load(), key=lambda g: g['t'])", "ALL = sorted(S.load() + [g for g in EXTRA_GAMES if g['id'] not in {x['id'] for x in S.load()}], key=lambda g: g['t'])")
ns = dict(EXTRA_GAMES=EXTRA_GAMES, __file__=os.path.join(H, 'sp_data.py')); exec(compile(src, 'sp_data_top', 'exec'), ns)
P, ALL, LAST, LINE, PHI, PA, PB, PZ, pair, n_ = (ns[k] for k in ('P', 'ALL', 'LAST', 'LINE', 'PHI', 'PA', 'PB', 'PZ', 'pair', 'n_'))
import form as FM
sp = json.load(open(os.path.join(H, 'sp_model.json')))
model = dict(frozen='2026-11-18', source='nba_stars_2026-11-18/sp_model.json (fitted Oct 20 to Nov 6 2026, no refit)', hold=sp['hold'], spike=sp['spike'],
             LINE={k: list(v) for k, v in LINE.items()}, PHI=PHI, PA=PA, PB=PB, PZ=PZ, P2=dict(a=FM.M['a'], b=FM.M['b'], zq=FM.M['zq'], phi=FM.M['phi']))
model['sha256_models'] = hashlib.sha256(json.dumps(sp, sort_keys=True).encode()).hexdigest()
json.dump(model, open(os.path.join(OUT, 'model.json'), 'w'), separators=(',', ':'))
r4 = lambda v: round(v, 4)
last = {}
for pid, rs in P.items():
    l26 = [x for x in rs if x['season'] == 2026]
    if not l26: continue
    e = dict(name=l26[-1]['name'], last40=[[x['min'], x['pts'], x['reb'], x['ast'], x['m3'], x['a3'], x['fga'], x['pf']] for x in l26[-40:]])
    if pid in LAST: e['last'] = {k: (r4(v) if isinstance(v, float) else v) for k, v in LAST[pid].items()}
    last[pid] = e
json.dump(last, open(os.path.join(OUT, 'last.json'), 'w'), separators=(',', ':'))
games = []
for g in ALL:
    if g['season'] != 2027: continue
    tm = {g['home']: collections.Counter(), g['away']: collections.Counter()}; pl = []
    for p in g['box']:
        mn = n_(p.get('MIN'))
        if not mn: continue
        fgm, fga = pair(p.get('FG')); m3, a3 = pair(p.get('3PT')); ftm, fta = pair(p.get('FT')); pts, reb, ast = n_(p.get('PTS')) or 0, n_(p.get('REB')) or 0, n_(p.get('AST')) or 0
        pl.append([p['pid'], p['name'], p['team'], 1 if p.get('starter') else 0, mn, pts, reb, ast, m3, a3, fga, n_(p.get('PF')) or 0])
        c = tm[p['team']]; c['pts'] += pts; c['reb'] += reb; c['ast'] += ast; c['m3'] += m3; c['pra'] += pts + reb + ast; c['poss'] += fga + 0.44 * fta + (n_(p.get('TO')) or 0) - (n_(p.get('OREB')) or 0)
    games.append(dict(id=g['id'], t=g['t'], day=g['day'], home=g['home'], away=g['away'], teams={k: dict(v) for k, v in tm.items()}, players=pl))
json.dump(dict(cols='pid,name,team,starter,min,pts,reb,ast,m3,a3,fga,pf', games=games), open(os.path.join(OUT, 'games.json'), 'w'), separators=(',', ':'))
print('model', model['sha256_models'][:12], 'last', len(last), 'games 2026-27', len(games), 'through', games[-1]['day'])
