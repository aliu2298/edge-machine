"""Research Lab daily-v1, as independent paper lanes in the GitHub pipeline.

Public Kalshi reads only. No credentials, orders, or Production feed writes.
"""
import datetime as dt
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, 'data', 'daily_ledger.json')
API = 'https://api.elections.kalshi.com/trade-api/v2/'
ET = ZoneInfo('America/New_York')
LANES = {'econ_daily': 'Econ Daily', 'finance_daily': 'Finance Daily'}
RULE = ('YES 70–80¢; spread ≤3¢; 25+ contracts at the ask; entry 2–3.5 hours '
        'before a verified supported close. Cheapest qualifying above-threshold '
        'contract per event, ties by ticker. One frozen paper entry per event. '
        'Ranges, weekly contracts, publication-lag rates and already-observed outcomes excluded.')
INDICES = {'KXINXDUD', 'KXNASDAQDUD', 'KXINXAB', 'KXINX', 'KXNASDAQ100', 'KXNASDAQ100Z', 'KXINXZ'}
MONTHS = {m:i+1 for i,m in enumerate(['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'])}

def instant(v):
    try:
        x = dt.datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return x if x.tzinfo else None
    except (ValueError, TypeError):
        return None

def number(v):
    if v is None or isinstance(v, bool) or v == '': return None
    try: return float(v) if math.isfinite(float(v)) else None
    except (ValueError, TypeError): return None

# Kalshi rate-limits a burst. The first run on GitHub's runner (2026-10-13) sent ~95 series
# reads back to back and got HTTP 429 on most of them, so every one became an incomplete
# scan. Requests are spaced, and a 429 or 5xx is retried with backoff; anything else is final.
MIN_GAP_S = 0.12
RETRY_WAITS_S = (1, 2, 4, 8, 16)
_last = [0.0]

def get(path, sleep=time.sleep, clock=time.monotonic, opener=urllib.request.urlopen):
    req = urllib.request.Request(API + path, headers={'User-Agent':'edge-machine-paper-dailies'})
    for attempt in range(len(RETRY_WAITS_S) + 1):
        wait = MIN_GAP_S - (clock() - _last[0])
        if wait > 0: sleep(wait)
        _last[0] = clock()
        try:
            with opener(req, timeout=25) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < len(RETRY_WAITS_S):
                retry_after = number(e.headers.get('Retry-After')) if e.headers else None
                sleep(max(RETRY_WAITS_S[attempt], retry_after or 0)); continue
            raise

def pages(path, key, fetch=get):
    out, seen = [], set()
    for _ in range(100):
        d = fetch(path)
        if not isinstance(d.get(key), list): raise ValueError('Incomplete ' + key + ' response')
        out.extend(d[key])
        cursor = d.get('cursor')
        if not cursor: return out
        if cursor in seen: raise ValueError('Repeated pagination cursor')
        seen.add(cursor)
        path = path.split('&cursor=')[0] + '&cursor=' + urllib.parse.quote(cursor, safe='')
    raise ValueError('Pagination limit reached; no entries from this scan')

def catalog(rows):
    return [dict(series=s['ticker'], name=s.get('title', s['ticker']),
                 lane='econ_daily' if s['category']=='Economics' else 'finance_daily',
                 sources=s.get('settlement_sources', [])) for s in rows
            if str(s.get('ticker','')).startswith('KX') and s.get('category') in ('Economics','Financials')
            and (s.get('frequency')=='daily' or (s.get('category')=='Economics' and 'Econ Daily' in (s.get('tags') or [])))
            and s['ticker']!='KXGOLD']

def supported(series):
    return (series in INDICES or bool(re.fullmatch(r'KXUST(2|5|7|10|30)A', series))
            or series.startswith('KXAAAGASD') or series=='KXDIESELD')

def window_reason(m, meta, now):
    series = meta['series']
    if not supported(series): return 'Unsupported or already-observed outcome'
    if (not str(m.get('ticker','')).startswith(series+'-') or m.get('status')!='active'
            or m.get('market_type')!='binary' or m.get('strike_type')!='greater'):
        return 'Not an active above-threshold binary contract'
    close, opened = instant(m.get('close_time')), instant(m.get('open_time'))
    if not close or not opened or opened>now: return 'Missing or invalid contract clock'
    if not 2 <= (close-now).total_seconds()/3600 <= 3.5: return 'Outside entry window'
    if re.search(r'\b(week|weekly|by|this year|this month)\b', m.get('title',''), re.I): return 'Non-daily contract'
    code = re.match(r'^(\d{2})([A-Z]{3})(\d{2})', str(m.get('event_ticker','')).split('-')[-1])
    if not code or code[2] not in MONTHS: return 'Unverified target date'
    try: target = dt.date(2000+int(code[1]), MONTHS[code[2]], int(code[3]))
    except ValueError: return 'Invalid target date'
    local = close.astimezone(ET)
    if series.startswith('KXAAAGASD'):
        return None if (target-local.date()).days in (0,1) else 'Target/close date mismatch'
    if target!=local.date(): return 'Target/close date mismatch'
    clock = (local.hour, local.minute)
    if series in INDICES and clock!=(16,0): return 'Unverified index closing clock'
    if series.startswith('KXUST') and clock!=(15,30): return 'Unverified Treasury closing clock'
    return None

def quote(book):
    b = book.get('orderbook_fp') or {}
    def side(k):
        levels = [(number(x[0]),number(x[1])) for x in b.get(k,[]) if isinstance(x,list) and len(x)==2]
        return sorted([(p,n) for p,n in levels if p is not None and n is not None and n>0], reverse=True)
    yes, no = side('yes_dollars'), side('no_dollars')
    if not yes or not no: return None
    return dict(bid=yes[0][0], ask=round(1-no[0][0],6), size=no[0][1])

def eligible(q):
    return q and 0<q['bid']<=q['ask']<=1 and .7<=q['ask']<=.8 and q['ask']-q['bid']<=.030000001 and q['size']>=25

def payout(m):
    if m.get('status') not in ('settled','finalized'): return None
    if m.get('result')=='yes': return 1.0
    if m.get('result')=='no': return 0.0
    value = number(m.get('settlement_value_dollars'))
    if value is None:
        v = number(m.get('settlement_value')); value = v/100 if v is not None else None
    return value if value is not None and 0<=value<=1 else None

def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return {'version':'daily-v1','lanes':{k:{'picks':[],'baseline':[],'catalog':[],'observations':[],'error':None} for k in LANES}}

def run(state, fetch=get, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat()
    errors = {k:[] for k in LANES}
    for lane in state['lanes'].values(): lane['last_run']=stamp
    try:
        metas = catalog(pages('series?limit=200', 'series', fetch))
        for k,lane in state['lanes'].items(): lane['catalog']=[m for m in metas if m['lane']==k]
    except Exception as e:
        metas=[]
        for k in LANES: errors[k].append('Catalog: '+str(e))
    for meta in metas:
        lane=state['lanes'][meta['lane']]; series=meta['series']; counts=Counter(); candidates=[]
        if not supported(series):
            lane['observations']=[x for x in lane['observations'] if x['series']!=series]
            lane['observations'].append(dict(series=series, at=stamp, listed=0, eligible=0, reasons={'Unsupported or already-observed outcome':1}))
            continue
        try:
            markets=pages('markets?limit=1000&status=open&series_ticker='+urllib.parse.quote(series), 'markets', fetch)
            for m in markets:
                reason=window_reason(m,meta,now)
                if reason: counts[reason]+=1; continue
                ask,bid=number(m.get('yes_ask_dollars')),number(m.get('yes_bid_dollars'))
                if ask is None or bid is None or not .7<=ask<=.8 or bid<=0 or ask-bid>.030000001:
                    counts['Price or spread gate']+=1; continue
                q=quote(fetch('markets/'+urllib.parse.quote(m['ticker'],safe='')+'/orderbook?depth=1'))
                if not eligible(q): counts['Order-book price, spread or depth gate']+=1; continue
                candidates.append((m,q))
            # No candidate is recorded if any book or page failed: no partial ranking.
            obs=dict(series=series,at=stamp,listed=len(markets),eligible=len(candidates),reasons=dict(counts))
            lane['observations']=[x for x in lane['observations'] if x['series']!=series]+[obs]
            for m,q in candidates:
                if any(x['id']==m['ticker'] for x in lane['baseline']): continue
                lane['baseline'].append(dict(id=m['ticker'],event=m['event_ticker'],series=series,name=meta['name'],
                    close=m['close_time'],price=q['ask'],bid=q['bid'],size=q['size'],logged=stamp,status='open',
                    title=m.get('yes_sub_title') or m.get('subtitle') or m.get('title'),sources=meta['sources']))
            for event in sorted({m['event_ticker'] for m,q in candidates}):
                if any(x['event']==event for x in lane['picks']): continue
                m,q=min([(m,q) for m,q in candidates if m['event_ticker']==event],key=lambda x:(x[1]['ask'],x[0]['ticker']))
                lane['picks'].append(dict(next(x for x in lane['baseline'] if x['id']==m['ticker'])))
        except Exception as e: errors[meta['lane']].append(series+': incomplete scan: '+str(e))
    for key,lane in state['lanes'].items():
        cache={}
        for row in lane['picks']+lane['baseline']:
            if row['status']!='open': continue
            try:
                if row['id'] not in cache: cache[row['id']]=fetch('markets/'+urllib.parse.quote(row['id'],safe='')).get('market',{})
                m=cache[row['id']]
                if m.get('ticker')!=row['id']: raise ValueError('Settlement ticker mismatch')
                px=payout(m)
                if px is None: continue
                # Research Lab's reference model, flat $100 stake; not a fill.
                fee=.07*row['price']*(1-row['price'])
                row.update(payout=px,profit=round(100*(px/(row['price']+fee)-1),2),
                           status='won' if px==1 else 'lost' if px==0 else 'no_result',settled=stamp)
            except Exception as e: errors[key].append('Settlement retained: '+row['id']+': '+str(e))
        lane['error']='; '.join(errors[key])[:1200] or None
        if not lane['error']: lane['last_success']=stamp
    return state

def main():
    state=run(load())
    os.makedirs(os.path.dirname(PATH),exist_ok=True)
    tmp=PATH+'.tmp'
    with open(tmp,'w') as f: json.dump(state,f,indent=2,sort_keys=True);f.write('\n')
    os.replace(tmp,PATH)
    for key,lane in state['lanes'].items(): print(key,'picks',len(lane['picks']),'error',lane['error'])
    return int(any(x['error'] for x in state['lanes'].values()))

if __name__=='__main__': raise SystemExit(main())
