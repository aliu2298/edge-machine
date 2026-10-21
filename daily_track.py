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
# Retired Sandbox lanes: the scan still reads (its coverage table stays honest) but logs no new
# entry or baseline row, and every row already in the ledger is kept exactly as it is.
#   finance_daily (Favourite band · 3h to the close, YES 70-80c) — RETIRED 2026-10-20. Research on
#   94 settled KXINXU/KXNASDAQ100U 16:00 ET ladders, Aug 14-Oct 20 2026, at the same settings gave
#   54/78 @73c, -6.4% after fee, halves -28% / +9%; the YES side loses in 8 of 9 price bands.
#   Replaced in the Sandbox by finance_spx_nc_no (finance_nc.py). econ_daily is not affected.
RETIRED = {'finance_daily': '2026-10-20'}
INDICES = {'KXINXDUD', 'KXNASDAQDUD', 'KXINXAB', 'KXINX', 'KXNASDAQ100', 'KXNASDAQ100Z', 'KXINXZ',
           'KXINXU', 'KXNASDAQ100U'}
# The S&P 500 and Nasdaq-100 "above X" ladders (2026-10-16). Kalshi files them as HOURLY series
# (they also list intraday closes), so the daily-frequency catalog never read them, and their
# rungs are greater_or_equal, which the contract check refused. Until then Finance Daily read
# only the range series (KXINX: 28 buckets and two tails near 1c) and logged nothing at all.
# Only their 16:00 ET event is the daily close; the index closing-clock check keeps it to that.
HOURLY_DAILY_CLOSE = {'KXINXU', 'KXNASDAQ100U'}
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
            and (s.get('frequency')=='daily' or s.get('ticker') in HOURLY_DAILY_CLOSE
                 or (s.get('category')=='Economics' and 'Econ Daily' in (s.get('tags') or [])))
            and s['ticker']!='KXGOLD']

def supported(series):
    return (series in INDICES or bool(re.fullmatch(r'KXUST(2|5|7|10|30)A', series))
            or series.startswith('KXAAAGASD') or series=='KXDIESELD')

def window_reason(m, meta, now):
    series = meta['series']
    if not supported(series): return 'Unsupported or already-observed outcome'
    if (not str(m.get('ticker','')).startswith(series+'-') or m.get('status')!='active'
            or m.get('market_type')!='binary' or m.get('strike_type') not in ('greater', 'greater_or_equal')):
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

# ---- Near-certain lanes (pre-registered 2026-10-20, Olu) ----------------------------------------
# Two Econ Daily lanes on the national AAA gas ladder and the diesel ladder only, each on its own
# fresh record, both in Production from 2026-10-20 (daily_production). The old favourite band
# above keeps running as a Sandbox lane on its whole record; nothing about it changes here.
#   econ_nc_yes  back the YES on the CHEAPEST rung whose YES ask is 0.90-0.98 (inclusive),
#                75 to 45 minutes before the verified close (up to three reads).
#   econ_nc_no   back the NO on the CHEAPEST rung whose NO ask (1 - the YES bid) is 0.85-0.95
#                (inclusive), 3.5 to 2 hours before the close (the old lane's window).
# Every other term is the old lane's: "above" threshold binaries only, a two-sided quote, spread
# at most 3c, 25+ contracts at the ask ON THE SIDE BOUGHT, one entry per event per lane, ties to
# the lower ticker, a verified close, Kalshi's official result, the 7% fee, per-market-day stats.
# ONE MARKET, ONE LANE: a ticker either lane already holds (open or settled) is never logged by
# the other; within a scan econ_nc_yes runs first, so it takes a contested rung.
# Diesel's close moved from 01:59 ET on its target date to 23:59 ET the evening before
# (Kalshi, from KXDIESELD-26OCT18), the AAA gas clock; both are accepted, each verified
# against the ticker's target date.
NC_SERIES = {'KXAAAGASD': 'US gas price (AAA national average)', 'KXDIESELD': 'Diesel price (daily)'}
NC_ORDER = ('econ_nc_yes', 'econ_nc_no')
NC_LANES = {
    'econ_nc_yes': dict(label='Near-certain · last hour · YES', side='yes', band=(0.90, 0.98),
                        minutes=(45, 75), window='75 to 45 minutes before the close'),
    'econ_nc_no': dict(label='Near-certain · 3h · NO', side='no', band=(0.85, 0.95),
                       minutes=(120, 210), window='3.5 to 2 hours before the close'),
}
NC_SPREAD, NC_SIZE, NC_FEE = 0.03, 25, 0.07
NC_REGISTERED = '2026-10-20'
NC_RULE = {
    'econ_nc_yes': ('YES on the cheapest rung whose YES ask is 90–98¢ inclusive, 75–45 minutes before '
                    'a verified close; AAA national gas (KXAAAGASD) and diesel (KXDIESELD) daily ladders '
                    'only. Above-threshold binaries, two-sided quote, spread ≤3¢, 25+ contracts at the YES '
                    'ask, one entry per event, ties to the lower ticker, Kalshi official settlement, 7% fee.'),
    'econ_nc_no': ('NO on the cheapest rung whose NO ask (1 − YES bid) is 85–95¢ inclusive, 3.5–2 hours '
                   'before a verified close; AAA national gas (KXAAAGASD) and diesel (KXDIESELD) daily '
                   'ladders only. Above-threshold binaries, two-sided quote, spread ≤3¢, 25+ contracts at '
                   'the NO ask, one entry per event, ties to the lower ticker, Kalshi official settlement, 7% fee.'),
}
NC_RESEARCH = {
    'econ_nc_yes': ('Pre-registered 2026-10-20. Research: 163 settled Kalshi econ daily ladders, Aug 11–Oct 17 '
                    '2026 (68 days), cheapest in-band contract per event, spread ≤5¢, after the fee, z clustered '
                    'by day. YES 90–98¢ at 1h before the close: 72/72, 100% at an average 94¢, +5.6%, z +6.45; '
                    'halves (split Sep 14) 28/28 +5% and 44/44 +6%; AAA gas 41/41, diesel 30/30.'),
    'econ_nc_no': ('Pre-registered 2026-10-20. Research: 163 settled Kalshi econ daily ladders, Aug 11–Oct 17 '
                   '2026 (68 days), cheapest in-band contract per event, spread ≤5¢, after the fee, z clustered '
                   'by day. NO 85–95¢ at 3h before the close: 62/63, 98% at an average 90¢, +8.1%, z +3.97; '
                   'halves (split Sep 14) 21/22 +5% and 41/41 +10%; AAA gas 37/37, diesel 23/24.'),
}
NC_WHY = ('Why: gas and diesel move cents a day, so near-certain rungs are underpriced, and longshots '
          'under 30¢ lose 40–87% on both sides.')
NC_CAVEAT = {
    'econ_nc_yes': ('Caveat: a thin payoff. One loss costs about 16 wins. The record starts from zero, and '
                    'the research window is the one the angle came from.'),
    'econ_nc_no': ('Caveat: a thin payoff. One loss costs about 10 wins. The record starts from zero, and '
                   'the research window is the one the angle came from.'),
}


def nc_window_reason(m, series, now, minutes):
    """None when market `m` is an NC-eligible contract inside `minutes` (lo, hi) before its close."""
    if series not in NC_SERIES:
        return 'Unsupported series'
    if (not str(m.get('ticker', '')).startswith(series + '-') or m.get('status') != 'active'
            or m.get('market_type') != 'binary' or m.get('strike_type') not in ('greater', 'greater_or_equal')):
        return 'Not an active above-threshold binary contract'
    close, opened = instant(m.get('close_time')), instant(m.get('open_time'))
    if not close or not opened or opened > now:
        return 'Missing or invalid contract clock'
    left = (close - now).total_seconds() / 60
    if not minutes[0] <= left <= minutes[1]:
        return 'Outside entry window'
    if re.search(r'\b(week|weekly|by|this year|this month)\b', m.get('title', ''), re.I):
        return 'Non-daily contract'
    code = re.match(r'^(\d{2})([A-Z]{3})(\d{2})', str(m.get('event_ticker', '')).split('-')[-1])
    if not code or code[2] not in MONTHS:
        return 'Unverified target date'
    try:
        target = dt.date(2000 + int(code[1]), MONTHS[code[2]], int(code[3]))
    except ValueError:
        return 'Invalid target date'
    local = close.astimezone(ET)
    lag = (target - local.date()).days
    clock = (local.hour, local.minute)
    if not ((clock == (23, 59) and lag in (0, 1)) or (series == 'KXDIESELD' and clock == (1, 59) and lag == 0)):
        return 'Unverified closing clock'
    return None


def nc_quote(book, side):
    """The side's own quote off the order book: ask, bid, and contracts at the ask. Kalshi's book
    holds bids only: the YES ask is 1 - the best NO bid (its size), the NO ask 1 - the best YES bid."""
    q = quote(book)
    if q is None:
        return None
    if side == 'yes':
        return dict(ask=q['ask'], bid=q['bid'], size=q['size'], yes_bid=q['bid'], yes_ask=q['ask'])
    b = book.get('orderbook_fp') or {}
    levels = [(number(x[0]), number(x[1])) for x in b.get('yes_dollars', []) if isinstance(x, list) and len(x) == 2]
    levels = sorted([(p, n) for p, n in levels if p is not None and n is not None and n > 0], reverse=True)
    return dict(ask=round(1 - q['bid'], 6), bid=round(1 - q['ask'], 6), size=levels[0][1],
                yes_bid=q['bid'], yes_ask=q['ask'])


def nc_eligible(q, lane):
    lo, hi = NC_LANES[lane]['band']
    return bool(q and 0 < q['bid'] <= q['ask'] < 1 and lo - 1e-9 <= q['ask'] <= hi + 1e-9
                and q['ask'] - q['bid'] <= NC_SPREAD + 1e-9 and q['size'] >= NC_SIZE)


def nc_listing_gate(m, lane):
    """The market listing's own quote, before any book is read (the book still decides)."""
    ya, yb = number(m.get('yes_ask_dollars')), number(m.get('yes_bid_dollars'))
    if ya is None or yb is None or yb <= 0 or ya >= 1 or ya - yb > NC_SPREAD + 1e-9:
        return False
    lo, hi = NC_LANES[lane]['band']
    ask = ya if NC_LANES[lane]['side'] == 'yes' else 1 - yb
    return lo - 1e-9 <= ask <= hi + 1e-9


def nc_payout(m, side):
    px = payout(m)
    if px is None:
        return None
    return px if side == 'yes' else round(1 - px, 6)


def nc_state(state):
    nc = state.setdefault('nc', {})
    for lane in NC_LANES:
        nc.setdefault(lane, {'picks': [], 'observations': [], 'error': None})
    return nc


def nc_held(nc):
    return {r['id'] for lane in nc.values() for r in lane.get('picks') or []}


def nc_run(state, fetch=get, now=None, stamp=None):
    """One read of both near-certain lanes. A failed page or book logs nothing for that series."""
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = stamp or now.isoformat()
    nc = nc_state(state)
    errors = {k: [] for k in NC_LANES}
    for lane in nc.values():
        lane['last_run'] = stamp
    for series, name in NC_SERIES.items():
        try:
            markets = pages('markets?limit=1000&status=open&series_ticker=' + urllib.parse.quote(series), 'markets', fetch)
        except Exception as e:
            for k in NC_LANES:
                errors[k].append(series + ': incomplete scan: ' + str(e))
            continue
        books = {}
        for key in NC_ORDER:
            spec, lane, counts, candidates = NC_LANES[key], nc[key], Counter(), []
            try:
                for m in markets:
                    reason = nc_window_reason(m, series, now, spec['minutes'])
                    if reason:
                        counts[reason] += 1
                        continue
                    if not nc_listing_gate(m, key):
                        counts['Price or spread gate'] += 1
                        continue
                    if m['ticker'] not in books:
                        books[m['ticker']] = fetch('markets/' + urllib.parse.quote(m['ticker'], safe='') + '/orderbook?depth=1')
                    q = nc_quote(books[m['ticker']], spec['side'])
                    if not nc_eligible(q, key):
                        counts['Order-book price, spread or depth gate'] += 1
                        continue
                    candidates.append((m, q))
                # No entry is logged when any book of this series failed: no partial ranking.
                held = nc_held(nc)
                taken = {r['event'] for r in lane['picks']}
                logged = 0
                for event in sorted({m['event_ticker'] for m, q in candidates}):
                    if event in taken:
                        continue
                    free = [(m, q) for m, q in candidates if m['event_ticker'] == event and m['ticker'] not in held]
                    if not free:
                        counts['Rung held by the other near-certain lane'] += 1
                        continue
                    m, q = min(free, key=lambda x: (x[1]['ask'], x[0]['ticker']))
                    close = instant(m['close_time'])
                    lane['picks'].append(dict(
                        id=m['ticker'], event=event, series=series, name=name, lane=key, side=spec['side'],
                        close=m['close_time'], price=q['ask'], bid=q['bid'], size=q['size'],
                        yes_bid=q['yes_bid'], yes_ask=q['yes_ask'], logged=stamp, status='open',
                        minutes_to_close=round((close - now).total_seconds() / 60, 1),
                        title=m.get('yes_sub_title') or m.get('subtitle') or m.get('title')))
                    held.add(m['ticker'])
                    logged += 1
                lane['observations'] = [x for x in lane['observations'] if x['series'] != series] + [
                    dict(series=series, at=stamp, listed=len(markets), eligible=len(candidates),
                         logged=logged, reasons=dict(counts))]
            except Exception as e:
                errors[key].append(series + ': incomplete scan: ' + str(e))
    for key, lane in nc.items():
        cache = {}
        side = NC_LANES[key]['side']
        for row in lane['picks']:
            if row['status'] != 'open':
                continue
            try:
                if row['id'] not in cache:
                    cache[row['id']] = fetch('markets/' + urllib.parse.quote(row['id'], safe='')).get('market', {})
                m = cache[row['id']]
                if m.get('ticker') != row['id']:
                    raise ValueError('Settlement ticker mismatch')
                px = nc_payout(m, side)
                if px is None:
                    continue
                fee = NC_FEE * row['price'] * (1 - row['price'])
                row.update(payout=px, profit=round(100 * (px / (row['price'] + fee) - 1), 2),
                           status='won' if px == 1 else 'lost' if px == 0 else 'no_result', settled=stamp)
            except Exception as e:
                errors[key].append('Settlement retained: ' + row['id'] + ': ' + str(e))
        lane['error'] = '; '.join(errors[key])[:1200] or None
        if not lane['error']:
            lane['last_success'] = stamp
    return state


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
            if meta['lane'] in RETIRED: continue
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
    nc_run(state, fetch, now, stamp)
    return state

def main():
    state=run(load())
    os.makedirs(os.path.dirname(PATH),exist_ok=True)
    tmp=PATH+'.tmp'
    with open(tmp,'w') as f: json.dump(state,f,indent=2,sort_keys=True);f.write('\n')
    os.replace(tmp,PATH)
    for key,lane in state['lanes'].items(): print(key,'picks',len(lane['picks']),'error',lane['error'])
    for key,lane in state.get('nc',{}).items(): print(key,'picks',len(lane['picks']),'error',lane['error'])
    return int(any(x['error'] for x in list(state['lanes'].values())+list(state.get('nc',{}).values())))

if __name__=='__main__': raise SystemExit(main())
