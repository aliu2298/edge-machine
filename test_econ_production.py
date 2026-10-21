#!/usr/bin/env python3
"""Econ Daily Production: the two near-certain lanes (2026-10-20) publish on their own collector
clock, the favourite band is back in the Sandbox on its whole record, and nothing mutates the
saved ledgers."""
import copy
import datetime as dt
import unittest
import daily_track as D
import daily_production as DP
import production as P
import sandbox_sources as S
import sandbox_track as T

NOW=dt.datetime(2026,10,21,2,50,tzinfo=dt.timezone.utc)
YES_PAIR,NO_PAIR='econ_nc_yes|econ_daily','econ_nc_no|econ_daily'


def yes_row(**kw):
    r=dict(id='KXAAAGASD-26OCT21-4.2600',series='KXAAAGASD',event='KXAAAGASD-26OCT21',lane='econ_nc_yes',side='yes',
           close='2026-10-21T03:59:00Z',logged=NOW.isoformat(),status='open',price=.94,bid=.93,size=1599,
           yes_bid=.93,yes_ask=.94,name='US gas price (AAA national average)',title='Above 4.2600')
    r.update(kw);return r


def no_row(**kw):
    logged=(NOW-dt.timedelta(minutes=110)).isoformat()
    r=dict(id='KXDIESELD-26OCT21-T6.320',series='KXDIESELD',event='KXDIESELD-26OCT21',lane='econ_nc_no',side='no',
           close='2026-10-21T03:59:00Z',logged=logged,status='open',price=.88,bid=.86,size=51,
           yes_bid=.12,yes_ask=.14,name='Diesel price (daily)',title='Above $6.320')
    r.update(kw);return r


def old_row(**kw):
    r=dict(id='KXAAAGASDMT-26OCT21-4.4500',series='KXAAAGASDMT',event='KXAAAGASDMT-26OCT21',
           close='2026-10-21T03:59:00Z',logged='2026-10-21T00:30:00+00:00',status='open',
           price=.73,bid=.72,size=100,name='Montana gas price',title='Above 4.4500')
    r.update(kw);return r


def state(yes=True,no=True,old=True):
    s={'lanes':{'econ_daily':dict(picks=[old_row()] if old else [],last_success=NOW.isoformat(),last_run=NOW.isoformat(),error=None)},
       'nc':{'econ_nc_yes':dict(picks=[yes_row()] if yes else [],observations=[],last_success=NOW.isoformat(),error=None),
             'econ_nc_no':dict(picks=[no_row()] if no else [],observations=[],last_success=NOW.isoformat(),error=None)}}
    return s


class EconProduction(unittest.TestCase):
    def test_production_is_the_two_near_certain_lanes_and_the_band_is_demoted(self):
        self.assertEqual(set(DP.pairs()),{YES_PAIR,NO_PAIR})
        self.assertNotIn(DP.OLD_PAIR,DP.pairs())
        self.assertEqual(T.PAIR_REMOVALS[DP.OLD_PAIR],dict(removed_on='2026-10-20',keep_record=True))
        self.assertNotIn(DP.OLD_PAIR,T.PAIR_OVERRIDES)
        for pair in (YES_PAIR,NO_PAIR):
            self.assertFalse(S.lane_paused(*pair.split('|')))
            self.assertIn(pair.split('|')[0],S.SOURCES)
        self.assertEqual(D.NC_SERIES.keys(),{'KXAAAGASD','KXDIESELD'})

    def test_yes_and_no_routes_name_the_exact_contract_and_side(self):
        s=state();before=copy.deepcopy(s);f=DP.feed(s,now=NOW)
        self.assertEqual(s,before)
        self.assertEqual(set(f['pairs']),{YES_PAIR,NO_PAIR})
        live={l['pair']:l for l in f['leads'].values() if l.get('lane')!='retired'}
        self.assertEqual(set(live),{YES_PAIR,NO_PAIR})
        y,n=live[YES_PAIR],live[NO_PAIR]
        self.assertEqual((y['route']['market'],y['route']['outcome_side'],y['bet']),
                         ('KXAAAGASD-26OCT21-4.2600','yes',{'kind':'ladder','side':'yes'}))
        self.assertEqual((n['route']['market'],n['route']['outcome_side'],n['bet']),
                         ('KXDIESELD-26OCT21-T6.320','no',{'kind':'ladder','side':'no'}))
        self.assertEqual(n['price_at_log'],.88)
        self.assertEqual(n['headline'],'Not Above $6.320 at the close')
        self.assertEqual(y['last_seen_at'],f['board_built_at'])

    def test_failed_or_stale_scan_has_no_actionable_entries(self):
        s=state();s['nc']['econ_nc_no']['error']='incomplete scan'
        self.assertFalse([l for l in DP.feed(s,now=NOW)['leads'].values() if l['status']=='pending'])
        self.assertFalse([l for l in DP.feed(state(),now=NOW+dt.timedelta(hours=4))['leads'].values() if l['status']=='pending'])

    def test_rows_off_their_own_lane_terms_do_not_publish(self):
        bad=[('yes',dict(series='KXAAAGASDMT')),('yes',dict(size=24)),('yes',dict(price=.99,bid=.98)),
             ('yes',dict(price=.89,bid=.88)),('yes',dict(logged=(NOW-dt.timedelta(minutes=50)).isoformat())),
             ('yes',dict(side='no')),('yes',dict(id='bad')),('no',dict(price=.96,bid=.94)),('no',dict(price=.84,bid=.83)),
             ('no',dict(logged=(NOW-dt.timedelta(minutes=30)).isoformat())),('no',dict(yes_bid=None)),('no',dict(price=.88,bid=.84))]
        for which,kw in bad:
            s=state(yes=which=='yes',no=which=='no')
            lane='econ_nc_yes' if which=='yes' else 'econ_nc_no'
            s['nc'][lane]['picks'][0].update(kw)
            self.assertEqual(DP.quotes(s),[],(which,kw))

    def test_no_record_settles_on_the_no_side(self):
        s=state(yes=False);r=s['nc']['econ_nc_no']['picks'][0]
        r.update(status='won',payout=1.,profit=12.7,settled=(NOW+dt.timedelta(hours=12)).isoformat())
        q=DP.quotes(s)[0]
        self.assertEqual((q['pick'],q['status'],q['result']),('b','won','b'))
        self.assertAlmostEqual(q['pnl'],100*(1/.88-1),places=2)
        r.update(status='lost',payout=0.,profit=-100.)
        self.assertEqual(DP.quotes(s)[0]['result'],'a')

    def test_retired_band_keeps_settled_leads_for_grading_only(self):
        s=state(yes=False,no=False)
        s['lanes']['econ_daily']['picks'][0].update(status='won',payout=1.,profit=34.,settled=NOW.isoformat())
        f=DP.feed(s,now=NOW)
        self.assertNotIn(DP.OLD_PAIR,f['pairs'])
        retired=[l for l in f['leads'].values() if l['pair']==DP.OLD_PAIR]
        self.assertEqual([(l['lane'],l['status']) for l in retired],[('retired','hit')])
        # A pending retired lead is never published, and pages leave every retired lead out.
        self.assertFalse([l for l in DP.feed(state(yes=False,no=False),now=NOW)['leads'].values() if l['pair']==DP.OLD_PAIR])
        _d,_st,bb=DP.page_inputs({'quotes':[]},{'pairs':{}},{'pairs':{},'leads':{}},s,now=NOW)
        self.assertFalse([l for l in bb['leads'].values() if l['pair']==DP.OLD_PAIR])
        # Logged after the demotion: not a Production lead at all.
        s['lanes']['econ_daily']['picks'][0]['logged']='2026-10-22T00:30:00+00:00'
        s['lanes']['econ_daily']['picks'][0]['close']='2026-10-22T03:59:00Z'
        self.assertFalse([l for l in DP.feed(s,now=NOW)['leads'].values() if l['pair']==DP.OLD_PAIR])

    def test_future_econ_pick_reaches_running_list(self):
        import control_center as C
        import sandbox_build as B
        s=state()
        d={'quotes':[]};st={'pairs':{}};blob={'updated_at':NOW.isoformat(),'pairs':{},'leads':{}}
        prod,index=B.production_and_index(NOW,d,st,blob,extra={'daily':s})
        self.assertIn('Above 4.2600',prod)
        self.assertIn('Not Above $6.320',prod)
        self.assertNotIn('Montana gas price',prod)
        model=C.model(d,st,blob,NOW,daily=s)
        self.assertEqual(model['tiles']['pairs'],2)

    def test_page_merge_does_not_mutate_sports_inputs_or_reset_sports_clock(self):
        d={'quotes':[]};st={'pairs':{}};blob={'updated_at':'2026-10-15T12:00Z','pairs':{},'leads':{}}
        before=copy.deepcopy((d,st,blob))
        dd,ss,bb=DP.page_inputs(d,st,blob,state(),now=NOW)
        self.assertEqual((d,st,blob),before)
        self.assertEqual(bb['updated_at'],blob['updated_at'])
        self.assertEqual({YES_PAIR,NO_PAIR}&set(ss['pairs']),{YES_PAIR,NO_PAIR})
        self.assertEqual({YES_PAIR,NO_PAIR}&set(bb['pairs']),{YES_PAIR,NO_PAIR})
        self.assertEqual(len(dd['quotes']),2)
        h=P.page(d,st,blob,'',now=NOW,daily=state())
        self.assertIn('Near-certain · last hour · YES',h)
        self.assertIn('Near-certain · 3h · NO',h)


class NearCertainCollector(unittest.TestCase):
    """daily_track.nc_run against a fake Kalshi: the rungs, the sides, the windows, one lane per market."""

    def market(self,series,strike,bid,ask,close='2026-10-21T03:59:00Z'):
        ev=series+'-26OCT21'
        return dict(ticker=f'{ev}-{strike}',event_ticker=ev,status='active',market_type='binary',strike_type='greater',
                    title='Will average gas prices be above?',open_time='2026-10-20T14:00Z',close_time=close,
                    yes_bid_dollars=str(bid),yes_ask_dollars=str(ask),yes_sub_title=f'Above {strike}')

    def fetcher(self,markets,depth=100,settle=None):
        def fetch(path):
            if path.startswith('markets?'):
                series=path.split('series_ticker=')[1]
                return {'markets':[m for m in markets if m['ticker'].startswith(series+'-')]}
            if path.endswith('/orderbook?depth=1'):
                t=path.split('/')[1]
                m=next(x for x in markets if x['ticker']==t)
                b,a=float(m['yes_bid_dollars']),float(m['yes_ask_dollars'])
                return {'orderbook_fp':{'yes_dollars':[[str(b),str(depth)]],'no_dollars':[[str(round(1-a,4)),str(depth)]]}}
            t=path.split('/')[-1]
            m=next(x for x in markets if x['ticker']==t)
            return {'market':dict(m,**(settle or {}))}
        return fetch

    def ladder(self):
        return [self.market('KXAAAGASD','4.2700',.02,.03),self.market('KXAAAGASD','4.2650',.10,.12),
                self.market('KXAAAGASD','4.2600',.93,.94),self.market('KXAAAGASD','4.2550',.96,.97),
                self.market('KXAAAGASD','4.2500',.99,1.0),
                self.market('KXDIESELD','T6.320',.12,.14),self.market('KXDIESELD','T6.315',.90,.91)]

    def test_yes_lane_takes_the_cheapest_in_band_rung_in_its_last_hour_window(self):
        s={'lanes':{}}
        D.nc_run(s,self.fetcher(self.ladder()),dt.datetime(2026,10,21,2,59,tzinfo=dt.timezone.utc))
        self.assertEqual(sorted((p['id'],p['price']) for p in s['nc']['econ_nc_yes']['picks']),
                         [('KXAAAGASD-26OCT21-4.2600',.94),('KXDIESELD-26OCT21-T6.315',.91)])
        self.assertEqual(s['nc']['econ_nc_no']['picks'],[])          # 60 min out: not the NO window
        for when in (dt.datetime(2026,10,21,2,40,tzinfo=dt.timezone.utc),dt.datetime(2026,10,21,3,16,tzinfo=dt.timezone.utc)):
            s={'lanes':{}};D.nc_run(s,self.fetcher(self.ladder()),when)
            self.assertEqual(s['nc']['econ_nc_yes']['picks'],[],when)

    def test_no_lane_takes_the_cheapest_no_ask_in_band_at_3h(self):
        s={'lanes':{}}
        D.nc_run(s,self.fetcher(self.ladder()),dt.datetime(2026,10,21,0,59,tzinfo=dt.timezone.utc))
        got=sorted((p['id'],p['side'],p['price'],p['bid'],p['size']) for p in s['nc']['econ_nc_no']['picks'])
        # KXAAAGASD 4.2650: NO ask 0.90, 4.2700: NO ask 0.98 (out of band) -> 4.2650. Diesel 6.320: 0.88.
        self.assertEqual(got,[('KXAAAGASD-26OCT21-4.2650','no',.9,.88,100.),('KXDIESELD-26OCT21-T6.320','no',.88,.86,100.)])
        self.assertEqual(s['nc']['econ_nc_yes']['picks'],[])

    def test_depth_on_the_side_bought_and_one_entry_per_event(self):
        s={'lanes':{}}
        D.nc_run(s,self.fetcher(self.ladder(),depth=24),dt.datetime(2026,10,21,2,59,tzinfo=dt.timezone.utc))
        self.assertEqual(s['nc']['econ_nc_yes']['picks'],[])
        s={'lanes':{}};f=self.fetcher(self.ladder())
        D.nc_run(s,f,dt.datetime(2026,10,21,2,45,tzinfo=dt.timezone.utc))
        D.nc_run(s,f,dt.datetime(2026,10,21,3,0,tzinfo=dt.timezone.utc))
        self.assertEqual(len(s['nc']['econ_nc_yes']['picks']),2)

    def test_one_market_one_lane(self):
        s={'lanes':{}};f=self.fetcher(self.ladder())
        D.nc_state(s)['econ_nc_no']['picks'].append(dict(id='KXAAAGASD-26OCT21-4.2600',event='KXAAAGASD-26OCT20',
                                                         status='lost',price=.9,side='no'))
        D.nc_run(s,f,dt.datetime(2026,10,21,2,59,tzinfo=dt.timezone.utc))
        ids=[p['id'] for p in s['nc']['econ_nc_yes']['picks']]
        self.assertNotIn('KXAAAGASD-26OCT21-4.2600',ids)
        self.assertIn('KXAAAGASD-26OCT21-4.2550',ids)                 # the next-cheapest free rung

    def test_unverified_clock_and_non_ladder_series_are_refused(self):
        m=self.market('KXAAAGASD','4.2600',.93,.94,close='2026-10-21T02:59:00Z')
        self.assertEqual(D.nc_window_reason(m,'KXAAAGASD',dt.datetime(2026,10,21,1,59,tzinfo=dt.timezone.utc),(45,75)),
                         'Unverified closing clock')
        self.assertEqual(D.nc_window_reason(self.market('KXAAAGASDMT','4.4',.9,.91),'KXAAAGASDMT',
                         dt.datetime(2026,10,21,2,59,tzinfo=dt.timezone.utc),(45,75)),'Unsupported series')
        old=self.market('KXDIESELD','T6.29',.93,.94,close='2026-10-21T05:59:00Z')
        self.assertIsNone(D.nc_window_reason(old,'KXDIESELD',dt.datetime(2026,10,21,4,59,tzinfo=dt.timezone.utc),(45,75)))

    def test_settles_on_the_official_result_for_the_side_held(self):
        s={'lanes':{}}
        D.nc_run(s,self.fetcher(self.ladder()),dt.datetime(2026,10,21,0,59,tzinfo=dt.timezone.utc))
        D.nc_run(s,self.fetcher(self.ladder(),settle={'status':'finalized','result':'no'}),
                 dt.datetime(2026,10,21,14,0,tzinfo=dt.timezone.utc))
        p=next(r for r in s['nc']['econ_nc_no']['picks'] if r['id']=='KXDIESELD-26OCT21-T6.320')
        self.assertEqual((p['status'],p['payout']),('won',1.0))
        self.assertAlmostEqual(p['profit'],round(100*(1/(.88+.07*.88*.12)-1),2))


if __name__=='__main__':unittest.main()
