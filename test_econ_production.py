#!/usr/bin/env python3
"""Econ Daily promotion preserves its record and independent collector clock."""
import copy
import datetime as dt
import unittest
import daily_track as D
import daily_production as DP
import production as P
import sandbox_sources as S

NOW=dt.datetime(2026,10,16,0,59,tzinfo=dt.timezone.utc)


def state():
    row=dict(id='KXAAAGASD-26OCT16-4.33',series='KXAAAGASD',event='KXAAAGASD-26OCT16',
             close='2026-10-16T03:59:00Z',logged=NOW.isoformat(),status='open',
             price=.75,bid=.73,size=25,name='US gas price up',title='Above 4.33')
    return {'lanes':{'econ_daily':dict(picks=[row],last_success=NOW.isoformat(),last_run=NOW.isoformat(),error=None)}}


class EconProduction(unittest.TestCase):
    def test_promoted_exact_yes_contract_and_no_finance(self):
        s=state();before=copy.deepcopy(s);f=DP.feed(s,now=NOW)
        self.assertEqual(s,before)
        self.assertEqual(set(f['pairs']),{DP.PAIR})
        l=next(iter(f['leads'].values()))
        self.assertEqual(l['route']['market'],s['lanes']['econ_daily']['picks'][0]['id'])
        self.assertEqual(l['route']['outcome_side'],'yes')
        self.assertEqual(l['bet'],{'kind':'ladder','side':'yes'})
        self.assertEqual(l['last_seen_at'],f['board_built_at'])
        self.assertFalse(S.lane_paused(DP.SOURCE,'econ_daily'))
        self.assertEqual(len(l['route']['market'].split('-')),3)

    def test_failed_or_stale_scan_has_no_actionable_entries(self):
        s=state();s['lanes']['econ_daily']['error']='incomplete scan'
        self.assertFalse(DP.feed(s,now=NOW)['leads'])
        self.assertFalse(DP.feed(state(),now=NOW+dt.timedelta(hours=4))['leads'])

    def test_invalid_clock_price_depth_and_unsupported_contract_do_not_publish(self):
        for field,value in [('series','KXINX'),('size',24),('bid',None),('price',.9),('logged','2026-10-15T10:00Z'),('id','bad')]:
            s=state();s['lanes']['econ_daily']['picks'][0][field]=value
            self.assertEqual(DP.quotes(s),[],(field,value))

    def test_paper_record_keeps_its_original_profit_and_settlement(self):
        s=state();r=s['lanes']['econ_daily']['picks'][0]
        r.update(status='won',payout=1.,profit=31.04,settled=(NOW+dt.timedelta(hours=4)).isoformat())
        before=copy.deepcopy(s)
        q=DP.quotes(s)[0]
        self.assertEqual(q['status'],'won')
        self.assertAlmostEqual(q['pnl'],33.33,places=2)
        self.assertEqual(s,before)
        self.assertEqual(r['profit'],31.04)

    def test_future_econ_pick_reaches_running_list(self):
        import control_center as C
        import sandbox_build as B
        s=state()
        d={'quotes':[]};st={'pairs':{}};blob={'updated_at':NOW.isoformat(),'pairs':{},'leads':{}}
        prod,index=B.production_and_index(NOW,d,st,blob,extra={'daily':s})
        self.assertIn('US gas price up',prod)
        self.assertIn('US gas price up',index)
        model=C.model(d,st,blob,NOW,daily=s)
        self.assertEqual(model['tiles']['pairs'],1)

    def test_page_merge_does_not_mutate_sports_inputs_or_reset_sports_clock(self):
        d={'quotes':[]};st={'pairs':{}};blob={'updated_at':'2026-10-15T12:00Z','pairs':{},'leads':{}}
        before=copy.deepcopy((d,st,blob))
        dd,ss,bb=DP.page_inputs(d,st,blob,state(),now=NOW)
        self.assertEqual((d,st,blob),before)
        self.assertEqual(bb['updated_at'],blob['updated_at'])
        self.assertIn(DP.PAIR,ss['pairs'])
        self.assertIn(DP.PAIR,bb['pairs'])
        self.assertEqual(len(dd['quotes']),1)
        h=P.page(d,st,blob,'',now=NOW,daily=state())
        self.assertIn('Econ Daily favourite band',h)


if __name__=='__main__':unittest.main()
