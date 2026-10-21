"""finance_spx_nc_no — S&P near-certain · NO 90-98c · 3h. A Sandbox paper lane (2026-10-20).

Back the NO on the cheapest KXINXU (S&P 500 above X, 16:00 ET close, the H1600 event only) rung
whose NO ask (1 - yes bid) is 0.90-0.98 inclusive, entered 2-3.5h before the close: the same
window and the same public reads as Finance Daily's retired favourite band (daily_track.py).
One entry per day, ties to the lower ticker. Liquidity: a two-sided quote, a spread of 3c or
less, 25+ contracts at the NO ask. Settled on Kalshi's official result with the 7% fee.

Sandbox only: not in Production, no pair override, no live orders. Public reads only.
"""
import datetime as dt
import json
import os
import urllib.parse

import daily_track as D

KEY = 'finance_spx_nc_no'
LABEL = 'S&P near-certain · NO 90–98¢ · 3h'
REGISTERED = '2026-10-20'
SERIES = 'KXINXU'
EVENT_CLOCK = 'H1600'             # the daily close; the ladder also lists intraday hours
BAND = (0.90, 0.98)               # NO ask, both edges inclusive
MAX_SPREAD = 0.03
MIN_SIZE = 25
READ_AT = 30                      # market-days
EPS = 1e-9
PATH = os.path.join(D.ROOT, 'data', 'finance_nc_ledger.json')
META = {'series': SERIES, 'name': 'S&P 500 above/below', 'lane': 'finance_daily', 'sources': []}
NOTE = ('Pre-registered 2026-10-20. Back the NO on the cheapest KXINXU (S&P 500 above X, 16:00 ET '
        'close, the H1600 event only) rung whose NO ask (1 − yes bid) is 0.90–0.98 inclusive, entered '
        '2–3.5h before the close. One entry per day, ties to the lower ticker. Liquidity: a two-sided '
        'quote, ≤3¢ spread, 25+ contracts at the NO ask. Settled on Kalshi\'s official result, 7% fee, '
        'counted per market-day. Research on 47 trading days Aug 14–Oct 20 2026, cheapest in-band '
        'contract per event, spread ≤5¢, after fee, z clustered by day: S&P NO 90–98¢ at 3h 45/46, '
        '98% @93¢, +4.8%, z +2.16, halves (split Sep 17) 23/23 +7% / 22/23 +3%. The same at 1h was '
        '42/43 +4.4%. Nasdaq was −0.9%, so S&P only. Caveats: one index, 46 bets, a thin payoff where '
        'one loss costs about 13 wins, and the research window is the one the angle came from, so the '
        'record starts at zero. Read at 30 market-days, judged against backing every in-band rung in '
        'the window (the blind baseline).')


def empty():
    return {'version': 'finance-nc-v1', 'key': KEY, 'registered': REGISTERED,
            'picks': [], 'baseline': [], 'observation': None, 'error': None}


def load(path=PATH):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return empty()


def in_scope(m, now):
    """None when the contract is an S&P 16:00 ET above-X rung inside the entry window."""
    if not str(m.get('ticker', '')).startswith(SERIES + '-'):
        return 'Not the S&P 500 above/below ladder'
    if str(m.get('event_ticker', '')).split('-')[-1][-len(EVENT_CLOCK):] != EVENT_CLOCK:
        return 'Not the 16:00 ET event'
    return D.window_reason(m, META, now)


def no_quote(book):
    """The NO side from a Kalshi book: ask = 1 - best yes bid, size = contracts at that bid."""
    b = (book or {}).get('orderbook_fp') or {}

    def side(k):
        levels = [(D.number(x[0]), D.number(x[1])) for x in b.get(k, []) if isinstance(x, list) and len(x) == 2]
        return sorted([(p, n) for p, n in levels if p is not None and n is not None and n > 0], reverse=True)
    yes, no = side('yes_dollars'), side('no_dollars')
    if not yes or not no:
        return None             # one-sided: no two-sided quote
    return dict(ask=round(1 - yes[0][0], 6), bid=no[0][0], size=yes[0][1], yes_bid=yes[0][0])


def in_band(price):
    return price is not None and BAND[0] - EPS <= price <= BAND[1] + EPS


def eligible(q):
    return bool(q and 0 < q['bid'] <= q['ask'] < 1 and in_band(q['ask'])
                and q['ask'] - q['bid'] <= MAX_SPREAD + EPS and q['size'] >= MIN_SIZE)


def listing_gate(m):
    """The market listing's own quote, before a book is read: NO ask = 1 - yes bid in band and
    the spread (yes ask - yes bid, the same on either side) within the cap."""
    bid, ask = D.number(m.get('yes_bid_dollars')), D.number(m.get('yes_ask_dollars'))
    if bid is None or ask is None or bid <= 0 or ask >= 1:
        return False
    return in_band(round(1 - bid, 6)) and ask - bid <= MAX_SPREAD + EPS


def day_of(row):
    return D.instant(row['close']).astimezone(D.ET).date()


def run(state, fetch=D.get, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat()
    state['last_run'] = stamp
    errors = []
    try:
        markets = D.pages('markets?limit=1000&status=open&series_ticker=' + SERIES, 'markets', fetch)
        counts, candidates = {}, []
        for m in markets:
            reason = in_scope(m, now)
            if not reason and not listing_gate(m):
                reason = 'Price or spread gate'
            if not reason:
                q = no_quote(fetch('markets/' + urllib.parse.quote(m['ticker'], safe='') + '/orderbook?depth=1'))
                if eligible(q):
                    candidates.append((m, q))
                    continue
                reason = 'Order-book price, spread, depth or two-sided gate'
            counts[reason] = counts.get(reason, 0) + 1
        # Only a complete scan reaches here: a failed page or book raises, and nothing is logged.
        state['observation'] = dict(at=stamp, listed=len(markets), eligible=len(candidates), reasons=counts)
        for m, q in candidates:
            if any(x['id'] == m['ticker'] for x in state['baseline']):
                continue
            state['baseline'].append(dict(
                id=m['ticker'], event=m['event_ticker'], series=SERIES, name=META['name'], side='no',
                close=m['close_time'], price=q['ask'], bid=q['bid'], yes_bid=q['yes_bid'], size=q['size'],
                logged=stamp, status='open',
                title='NO · ' + str(m.get('yes_sub_title') or m.get('subtitle') or m.get('title'))))
        days = {day_of(x) for x in state['picks']}
        for event in sorted({m['event_ticker'] for m, q in candidates}):
            pool = [(m, q) for m, q in candidates if m['event_ticker'] == event]
            if any(x['event'] == event for x in state['picks']) or D.instant(pool[0][0]['close_time']).astimezone(D.ET).date() in days:
                continue
            m, q = min(pool, key=lambda x: (x[1]['ask'], x[0]['ticker']))
            row = dict(next(x for x in state['baseline'] if x['id'] == m['ticker']))
            row['logged'] = stamp
            state['picks'].append(row)
            days.add(day_of(row))
    except Exception as e:
        errors.append('KXINXU: incomplete scan: ' + str(e))
    cache = {}
    for row in state['picks'] + state['baseline']:
        if row['status'] != 'open':
            continue
        try:
            if row['id'] not in cache:
                cache[row['id']] = fetch('markets/' + urllib.parse.quote(row['id'], safe='')).get('market', {})
            m = cache[row['id']]
            if m.get('ticker') != row['id']:
                raise ValueError('Settlement ticker mismatch')
            yes = D.payout(m)
            if yes is None:
                continue
            px = round(1 - yes, 6)          # the NO side's payout
            fee = .07 * row['price'] * (1 - row['price'])
            row.update(payout=px, profit=round(100 * (px / (row['price'] + fee) - 1), 2),
                       status='won' if px == 1 else 'lost' if px == 0 else 'no_result', settled=stamp)
        except Exception as e:
            errors.append('Settlement retained: ' + row['id'] + ': ' + str(e))
    state['error'] = '; '.join(errors)[:1200] or None
    if not state['error']:
        state['last_success'] = stamp
    return state


def record(rows):
    """Per market-day: one entry per day, so each settled pick is one market-day."""
    settled = [r for r in rows if r['status'] != 'open']
    binary = [r for r in settled if r['status'] in ('won', 'lost')]
    return dict(n=len(binary), n_price=len(settled) - len(binary), won=sum(r['status'] == 'won' for r in binary),
                expected=sum(r['price'] for r in binary), n_bets=len(settled), unit='market-day',
                roi_fee=sum(r.get('profit', 0) for r in settled) / (100 * len(settled)) if settled else None)


def baseline_record(rows):
    """The blind baseline: every in-band rung in the window, pooled per market-day."""
    by_day = {}
    for r in rows:
        if r['status'] != 'open':
            by_day.setdefault(day_of(r), []).append(r)
    days = [sum(r.get('profit', 0) for r in v) / (100 * len(v)) for v in by_day.values()]
    return dict(days=len(days), contracts=sum(len(v) for v in by_day.values()),
                roi_fee=sum(days) / len(days) if days else None)


def main():
    state = run(load())
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write('\n')
    os.replace(tmp, PATH)
    print(KEY, 'picks', len(state['picks']), 'baseline', len(state['baseline']), 'error', state['error'])
    return int(bool(state['error']))


if __name__ == '__main__':
    raise SystemExit(main())
