#!/usr/bin/env python3
"""D3 (finance_spx_nc_no, the S&P near-certain NO) in Production from 2026-11-08 (Olu): published in the Econ feed the
follower trades, on a fresh record; its paper ledger untouched. No network, nothing written."""
import copy
import datetime as dt
import sys

import daily_production as DP
import finance_nc as FN
import production as P
import sandbox_track as T

FAILS = []


def check(why, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {why}" + ("" if good else f" — got {got!r}, want {want!r}"))
    if not good:
        FAILS.append(why)


NOW = dt.datetime(2026, 11, 9, 18, 17, tzinfo=dt.timezone.utc)


def pick(**kw):
    r = dict(id='KXINXU-26NOV09H1600-T6799.9999', event='KXINXU-26NOV09H1600', series='KXINXU', name='S&P 500 above/below',
             side='no', close='2026-11-09T21:00:00Z', price=0.95, bid=0.94, yes_bid=0.05, size=500.0,
             logged=NOW.isoformat(), status='open', title='NO · 6,800 or above')
    r.update(kw)
    return r


old = pick(id='KXINXU-26NOV06H1600-T7469.9999', event='KXINXU-26NOV06H1600', close='2026-11-06T21:00:00Z',
           logged='2026-11-06T18:00:00+00:00', status='won', payout=1.0, settled='2026-11-07T01:30:00+00:00')
fin = {'picks': [old, pick()], 'last_success': NOW.isoformat(), 'error': None}
before = copy.deepcopy(fin)

print("the pair")
check("D3 is a Production pair of the Econ feed, promoted 2026-11-08 (00:00 CT)",
      (DP.FIN_PAIR in DP.pairs(), DP.pairs()[DP.FIN_PAIR]['promoted_at']), (True, '2026-11-08T06:00:00+00:00'))
check("finance_daily is a ladder sport, so a rung reaches the feed", 'finance_daily' in T.LADDER_SPORTS, True)

print("\nthe feed")
blob = DP.feed({'nc': {}}, now=NOW, fin=fin)
mine = [l for l in blob['leads'].values() if l['pair'] == DP.FIN_PAIR]
check("a fresh record: only the row logged after the promotion is published", [l['route']['market'] for l in mine],
      ['KXINXU-26NOV09H1600-T6799.9999'])
l = mine[0]
check("routed as the exact Kalshi NO on that rung", (l['route']['venue'], l['route']['outcome_side'], l['bet'], l['route']['event']),
      ('kalshi', 'no', {'kind': 'ladder', 'side': 'no'}, 'KXINXU-26NOV09H1600'))
check("named for the contract, not the ledger's 'NO ·' label", (l['headline'], l['route']['outcome']),
      ('Below 6,800 at the close', '6,800 or above'))
check("the ledger is not touched", fin, before)
check("a row outside the lane's terms (spread 5c) is not published",
      [x for x in DP.fin_quotes({'picks': [pick(bid=0.90)]}) if x], [])
check("nor one entered outside 3.5-2h before the close",
      DP.fin_quotes({'picks': [pick(logged='2026-11-09T20:00:00+00:00')]}), [])
stale = dict(fin, last_success=(NOW - dt.timedelta(hours=4)).isoformat())
check("a stale S&P scan withholds its open leads",
      [l for l in DP.feed({'nc': {}}, now=NOW, fin=stale)['leads'].values() if l['pair'] == DP.FIN_PAIR and l['status'] == 'pending'], [])

print("\nthe page record")
q = DP.fin_quotes(fin, since=None)
a = P._assess_since_kickoff({'quotes': q}, DP.FIN_PAIR, DP.pairs()[DP.FIN_PAIR])
check("the Production record counts from the promotion: the paper win before it is not in it", a.get('n'), 0)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
