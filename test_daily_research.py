"""Offline regressions for Research Lab daily-v1's GitHub migration."""
import copy
import datetime as dt
import daily_track as D
import daily_build as B

now=dt.datetime(2026,10,12,17,tzinfo=dt.timezone.utc)
meta={'series':'KXINX','name':'S&P close','lane':'finance_daily','sources':[]}
def market(ticker='KXINX-26OCT12-T6000'):
    return dict(ticker=ticker,event_ticker='KXINX-26OCT12',status='active',market_type='binary',strike_type='greater',
                title='S&P closing above 6000',open_time='2026-10-12T10:00Z',close_time='2026-10-12T20:00Z',
                yes_ask_dollars='.75',yes_bid_dollars='.73')
book={'orderbook_fp':{'yes_dollars':[['.73','50']],'no_dollars':[['.25','25']]}}
assert D.window_reason(market(),meta,now) is None
for field,value in [('strike_type','between'),('close_time','2026-10-12T19:00Z'),('title','S&P this week'),('event_ticker','KXINX-26OCT11')]:
    m=market();m[field]=value;assert D.window_reason(m,meta,now)
assert D.eligible(D.quote(book))
assert not D.eligible(D.quote({'orderbook_fp':{'yes_dollars':[['.73','50']],'no_dollars':[['.25','24']]}}))
assert D.quote({}) is None
assert not D.eligible({'ask':.75,'bid':.71,'size':100})
assert D.payout({'status':'closed','result':'yes'}) is None
assert D.payout({'status':'settled','result':'yes'})==1
assert D.payout({'status':'finalized','settlement_value':50})==.5
state={'version':'daily-v1','lanes':{k:{'picks':[],'baseline':[],'catalog':[],'observations':[],'error':None} for k in D.LANES}}
def fetch(path):
    if path.startswith('series?'):return {'series':[dict(ticker='KXINX',title='S&P close',category='Financials',frequency='daily')]}
    if path.startswith('markets?'):return {'markets':[market(),market('KXINX-26OCT12-T5900')]}
    if '/orderbook' in path:return book
    return {'market':market(path.split('/')[-1])}
D.run(state,fetch,now);lane=state['lanes']['finance_daily']
assert len(lane['picks'])==1 and len(lane['baseline'])==2
assert lane['picks'][0]['id']=='KXINX-26OCT12-T5900' # deterministic tie
D.run(state,fetch,now);assert len(lane['picks'])==1
old=copy.deepcopy(lane['picks'])
def down(path):raise RuntimeError('source unavailable')
D.run(state,down,now);assert lane['picks']==old and lane['error']
fresh={'version':'daily-v1','lanes':{k:{'picks':[],'baseline':[],'catalog':[],'observations':[],'error':None} for k in D.LANES}}
def missing_book(path):
    if 'orderbook' in path:raise RuntimeError('book unavailable')
    return fetch(path)
D.run(fresh,missing_book,now);assert fresh['lanes']['finance_daily']['picks']==[]
for key in D.LANES:
    html=B.build(key,state,now);assert D.LANES[key] in html and 'Scan reasons' in html
    assert 'data/daily_ledger' not in html
import control_center as CC
extra=CC.inputs()
assert 'daily' in extra
model=CC.model({'meta':{},'quotes':[]},{},{'pairs':{},'leads':[]},now,daily=state)
assert {a['key'] for a in model['areas']} >= set(D.LANES)
assert next(a for a in model['areas'] if a['key']=='finance_daily')['status']=='attention'
# A 429 is retried with backoff and then succeeds; a 404 is final (2026-10-13).
import io, urllib.error
_calls, _slept = [], []
def _opener(seq):
    def op(req, timeout=25):
        code = seq.pop(0); _calls.append(code)
        if code != 200: raise urllib.error.HTTPError(req.full_url, code, 'x', {}, None)
        return io.BytesIO(b'{"ok": true}')
    return op
assert D.get('series', sleep=_slept.append, clock=lambda: 1e9, opener=_opener([429, 429, 200])) == {'ok': True}
assert _calls == [429, 429, 200] and [x for x in _slept if x >= 1] == [1, 2], (_calls, _slept)
_calls.clear()
try:
    D.get('series', sleep=lambda s: None, clock=lambda: 1e9, opener=_opener([404])); raise AssertionError('404 retried')
except urllib.error.HTTPError as e:
    assert e.code == 404 and _calls == [404]
print('PASS: windows, exclusions, book depth, settlement, ranking, frozen entry, partial failure retention and pages')
