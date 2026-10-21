"""Finance Daily, 2026-10-20: the favourite band retired, and finance_spx_nc_no (S&P near-certain ·
NO 90-98c · 3h) as a pre-registered Sandbox paper lane. Offline: every read is a stub."""
import copy
import datetime as dt
import daily_track as D
import daily_build as B
import finance_nc as N

fails = []
def ok(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: fails.append(msg)

NOW = dt.datetime(2026, 10, 12, 17, tzinfo=dt.timezone.utc)      # 13:00 ET, 3h before the 16:00 close
EVENT = 'KXINXU-26OCT12H1600'

def market(strike, yes_bid, spread=.01, event=EVENT, series='KXINXU', close='2026-10-12T20:00Z'):
    return dict(ticker=f'{series}-{event.split("-", 1)[1]}-T{strike}', event_ticker=event, status='active',
                market_type='binary', strike_type='greater_or_equal', title='S&P 500 above', yes_sub_title=f'{strike} or above',
                open_time='2026-10-12T10:00Z', close_time=close,
                yes_bid_dollars=str(yes_bid), yes_ask_dollars=str(round(yes_bid + spread, 4)))

def book(yes_bid, size=25, spread=.01, two_sided=True):
    return {'orderbook_fp': {'yes_dollars': [[str(yes_bid), str(size)]],
                             'no_dollars': [[str(round(1 - yes_bid - spread, 4)), '40']] if two_sided else []}}

def fetcher(markets, books=None, settle=None):
    books = books or {}
    def fetch(path):
        if path.startswith('markets?'): return {'markets': markets}
        if '/orderbook' in path:
            t = path.split('/')[1]
            m = next(x for x in markets if x['ticker'] == t)
            return books.get(t) or book(float(m['yes_bid_dollars']))
        t = path.split('/')[-1]
        m = dict(next((x for x in markets if x['ticker'] == t), {'ticker': t}))
        if settle and t in settle: m.update(status='finalized', result=settle[t])
        return {'market': m}
    return fetch

def run(markets, books=None, state=None, now=NOW, settle=None):
    state = state if state is not None else N.empty()
    return N.run(state, fetcher(markets, books, settle), now)

print('the NO price and the band')
q = N.no_quote(book(.06, size=30))
ok(q['ask'] == .94 and q['size'] == 30 and q['yes_bid'] == .06, 'NO ask = 1 - yes bid; size is the contracts at that yes bid')
ok(N.no_quote(book(.06, two_sided=False)) is None, 'a one-sided book has no quote')
ok(N.in_band(.90) and N.in_band(.98) and N.in_band(1 - .10) and N.in_band(1 - .02), 'both band edges are inclusive (float edges too)')
ok(not N.in_band(.899) and not N.in_band(.981), 'just outside either edge is out')
ok(N.eligible(dict(ask=.94, bid=.91, size=25)), 'a 3c spread and 25 contracts qualify')
ok(not N.eligible(dict(ask=.94, bid=.909, size=25)), 'a spread over 3c does not')
ok(not N.eligible(dict(ask=.94, bid=.93, size=24)), '24 contracts at the NO ask do not')

print('\nselection')
s = run([market('7700', .05), market('7690', .08), market('7680', .15), market('7710', .01)])
ok(len(s['picks']) == 1 and s['picks'][0]['id'] == 'KXINXU-26OCT12H1600-T7690', 'the cheapest in-band NO is picked (0.92, not 0.95)')
ok(s['picks'][0]['price'] == .92 and s['picks'][0]['side'] == 'no', 'the entry price is the NO ask')
ok(sorted(x['id'][-5:] for x in s['baseline']) == ['T7690', 'T7700'], 'the blind baseline is every in-band rung (0.85 and 0.99 out)')
ok(s['observation']['eligible'] == 2 and s['error'] is None, 'the scan is recorded')
tie = run([market('7700', .08), market('7650', .08)])
ok(tie['picks'][0]['id'] == 'KXINXU-26OCT12H1600-T7650', 'a tie on price goes to the lower ticker')
edge = run([market('7700', .02), market('7600', .10)])
ok(edge['picks'][0]['price'] == .90 and len(edge['baseline']) == 2, 'a 0.90 and a 0.98 NO both qualify; 0.90 is the cheaper')

print('\nscope and window')
ok(N.in_scope(market('29500', .05, series='KXNASDAQ100U', event='KXNASDAQ100U-26OCT12H1600'), NOW)
   == 'Not the S&P 500 above/below ladder', 'Nasdaq is out: S&P only')
ok(N.in_scope(dict(market('7700', .05), ticker='KXINX-26OCT12H1600-B7700'), NOW) is not None, 'the S&P range series is out')
hourly = market('7700', .05, event='KXINXU-26OCT12H1500', close='2026-10-12T19:00Z')
ok(N.in_scope(hourly, NOW - dt.timedelta(hours=1)) == 'Not the 16:00 ET event', 'an intraday H1500 event is out')
ok(run([market('29500', .05, series='KXNASDAQ100U'), hourly])['picks'] == [], 'neither logs an entry')
ok(N.in_scope(market('7700', .05), NOW - dt.timedelta(minutes=31)) == 'Outside entry window', 'earlier than 3.5h before the close is out')
ok(N.in_scope(market('7700', .05), NOW + dt.timedelta(minutes=61)) == 'Outside entry window', 'later than 2h before the close is out')
ok(N.in_scope(market('7700', .05), NOW - dt.timedelta(minutes=30)) is None and N.in_scope(market('7700', .05), NOW + dt.timedelta(hours=1)) is None,
   'exactly 3.5h and exactly 2h are inside')

print('\nliquidity')
thin = run([market('7700', .05)], books={'KXINXU-26OCT12H1600-T7700': book(.05, size=24)})
ok(thin['picks'] == [] and thin['observation']['reasons'], 'under 25 contracts at the NO ask: no entry')
wide = run([market('7700', .05, spread=.04)])
ok(wide['picks'] == [], 'a listing spread over 3c: no entry')
wide_book = run([market('7700', .05)], books={'KXINXU-26OCT12H1600-T7700': book(.05, spread=.04)})
ok(wide_book['picks'] == [], 'a book spread over 3c: no entry')
one_sided = run([market('7700', .05)], books={'KXINXU-26OCT12H1600-T7700': book(.05, two_sided=False)})
ok(one_sided['picks'] == [], 'a one-sided book: no entry')

print('\none per day, frozen, settlement')
day = run([market('7700', .05)])
later = run([market('7700', .03), market('7690', .09)], state=copy.deepcopy(day), now=NOW + dt.timedelta(minutes=30))
ok(len(later['picks']) == 1 and later['picks'][0]['price'] == .95, 'a later read the same day adds no entry and never re-picks')
ok(len(later['baseline']) == 2, 'the baseline still logs a rung first seen in band on the later read')
other = dict(market('7700', .05), event_ticker='KXINXU-26OCT12H1600X', ticker='KXINXU-26OCT12H1600X-T7700')
ok(len(run([other], state=copy.deepcopy(day))['picks']) == 1, 'a second event closing the same day is still one entry per day')
won = run([market('7700', .05)], state=copy.deepcopy(day), settle={'KXINXU-26OCT12H1600-T7700': 'no'},
          now=NOW + dt.timedelta(hours=5))
p = won['picks'][0]
fee = .07 * .95 * .05
ok(p['status'] == 'won' and p['payout'] == 1 and p['profit'] == round(100 * (1 / (.95 + fee) - 1), 2),
   'a NO result wins the NO, after the 7% fee')
lost = run([market('7700', .05)], state=copy.deepcopy(day), settle={'KXINXU-26OCT12H1600-T7700': 'yes'},
           now=NOW + dt.timedelta(hours=5))
ok(lost['picks'][0]['status'] == 'lost' and lost['picks'][0]['profit'] == -100.0, 'a YES result loses the NO stake')
a = N.record(won['picks'])
ok((a['n'], a['won'], a['unit']) == (1, 1, 'market-day'), 'the record counts per market-day')
def down(path): raise RuntimeError('source unavailable')
kept = copy.deepcopy(day); N.run(kept, down, NOW + dt.timedelta(minutes=30))
ok(kept['picks'] == day['picks'] and kept['error'], 'a failed read keeps every record and says so')

print('\nretirement: Finance Daily favourite band')
ok(D.RETIRED.get('finance_daily') == '2026-10-20' and 'econ_daily' not in D.RETIRED, 'finance_daily retired; econ_daily is not')
ladder = dict(market('7700', .73, spread=.02), yes_ask_dollars='.75')
gas = dict(ladder, ticker='KXAAAGASD-26OCT12-4.3300', event_ticker='KXAAAGASD-26OCT12', close_time='2026-10-12T20:00Z',
           strike_type='greater')
fav_book = {'orderbook_fp': {'yes_dollars': [['.73', '50']], 'no_dollars': [['.25', '25']]}}
old_row = dict(id='KXINXU-26OCT09H1600-T7600', event='KXINXU-26OCT09H1600', series='KXINXU', name='S&P', title='x',
               close='2026-10-09T20:00Z', price=.74, bid=.73, size=25, logged='2026-10-09T17:00Z', status='won', profit=32.72)
state = {'version': 'daily-v1', 'lanes': {k: {'picks': [], 'baseline': [], 'catalog': [], 'observations': [], 'error': None} for k in D.LANES}}
state['lanes']['finance_daily']['picks'] = [dict(old_row)]
state['lanes']['finance_daily']['baseline'] = [dict(old_row)]
def fav_fetch(path):
    if path.startswith('series?'):
        return {'series': [dict(ticker='KXINXU', title='S&P', category='Financials', frequency='hourly'),
                           dict(ticker='KXAAAGASD', title='Gas', category='Economics', frequency='daily')]}
    if path.startswith('markets?'):
        return {'markets': [ladder] if 'KXINXU' in path else [gas]}
    if '/orderbook' in path: return fav_book
    return {'market': {'ticker': path.split('/')[-1]}}
D.run(state, fav_fetch, NOW)
fin, eco = state['lanes']['finance_daily'], state['lanes']['econ_daily']
ok(fin['picks'] == [old_row] and fin['baseline'] == [old_row], 'the retired lane logs no new entry or baseline row; its rows are unchanged')
ok(any(o['series'] == 'KXINXU' and o['eligible'] == 1 for o in fin['observations']), 'its scan still reads (coverage stays honest)')
ok(len(eco['picks']) == 1 and len(eco['baseline']) == 1, 'econ_daily still logs its favourite band')

print('\nthe page')
nc = copy.deepcopy(won); nc['last_success'] = NOW.isoformat()
html = B.build('finance_daily', state, NOW + dt.timedelta(hours=5), nc=nc)
ok('S&amp;P near-certain · NO 90–98¢ · 3h' in html and 'Favourite band · 3h to the close' in html, 'both rules are on the page')
ok('data-verdict="retired">Retired<' in html, 'the old lane shows as retired')
ok('<span class="badge stage">Retired</span>' in html, 'with the Retired badge')
ok('Sandbox rules' in html and 'No finance daily rule is in Production.' in html, 'both sit under Sandbox rules')
ok('Paper record · not graded' in html, 'the new lane keeps the family verdict chip')
ok('1/30 market-days' in html, 'the new lane counts its evidence in market-days')
ok('<b>1–0</b><span>Sandbox record · paper' in html, 'the headline record tile is the live Sandbox rule (the retired one is left out)')
ok('ROI after fees · Sandbox, paper' in html and 'Production record' not in html, 'and the ROI tile is the Sandbox, never Production')
ok('Retired 2026-10-20' in html and '54/78' in html, 'the retirement reason is in the old rule\'s details')
ok('Pre-registered 2026-10-20' in html and '45/46' in html, 'the registration is in the new rule\'s details')
empty_html = B.build('finance_daily', state, NOW, nc=N.empty())
ok('<b>—</b><span>Sandbox record · paper' in empty_html, 'before any settled entry the record tile is a dash')
econ = B.build('econ_daily', state, NOW)
ok('Production · paper record' in econ and 'near-certain' not in econ and 'data-verdict="retired"' not in econ,
   'Econ Daily is unchanged')

print()
if fails:
    raise SystemExit(f'{len(fails)} FAILED')
print('ALL PASS: finance_spx_nc_no and the favourite band retirement')
