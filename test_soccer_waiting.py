#!/usr/bin/env python3
"""Normal fixture gaps do not demote soccer or masquerade as broken collection."""
import datetime as dt
import unittest

import control_center as C
import production as P
import sandbox_track as T

NOW=dt.datetime(2026,11,1,12,tzinfo=dt.timezone.utc)
OLD=(NOW-dt.timedelta(days=90)).isoformat()


class SoccerWaiting(unittest.TestCase):
    def test_all_soccer_scopes_keep_their_stage_between_windows(self):
        for sport in ('soccer','soccer_o15','soccer_o15_cup','soccer_o15_intl','soccer_team1_intl'):
            self.assertIsNone(T.demote_reason({'quotes':[]},'demo',sport,{'promoted_at':OLD},{'n':0},NOW))
            key='demo|'+sport
            self.assertEqual(P.pair_health(key,[],0,{key:{}},now=NOW),('ok','waiting for qualifying fixtures'))

    def test_other_sports_keep_inactivity_policy(self):
        self.assertEqual(T.demote_reason({'quotes':[]},'demo','cricket',{'promoted_at':OLD},{'n':0},NOW),'no new bet in 21 days')

    def test_poor_soccer_performance_still_demotes(self):
        reason=T.demote_reason({'quotes':[]},'demo','soccer_o15_intl',{'promoted_at':OLD},{'n':100,'z':-2},NOW)
        self.assertIn('behind the price',reason)

    def model(self, read_at=NOW, **over):
        key='team1_form_l5|soccer_team1_intl'
        d={'quotes':[],'coverage':{},'meta':{'updated':NOW.isoformat(),'lane_reads':{'soccer_team1_intl':read_at.isoformat()}}}
        st={'pairs':{key:{'stage':'production','promoted_at':OLD,'ready_at':OLD}}}
        return C.model(d,st,{'leads':{},'pairs':{key:{}}},NOW,closes={},**over)

    def test_healthy_collection_without_picks_does_not_raise_attention(self):
        m=self.model()
        self.assertEqual([i for i in m['attention'] if i.get('area')=='soccer'],[])
        soccer=next(a for a in m['areas'] if a['key']=='soccer')
        self.assertEqual(soccer['status'],'healthy')

    def test_stale_collection_still_shows_a_fault(self):
        m=self.model(NOW-dt.timedelta(hours=8))
        self.assertEqual(next(a for a in m['areas'] if a['key']=='soccer')['status'],'stale')

    def test_feed_membership_routes_and_late_leads_are_still_checked(self):
        key='demo|soccer_o15_intl'
        self.assertEqual(P.pair_health(key,[],0,{},now=NOW)[0],'bad')
        self.assertEqual(P.pair_health(key,[],0,{key:{}},now=NOW,routing={'problem':'missing market'})[0],'bad')
        timing={'late':[{'match':'Alpha v Beta','headline':'Over 1.5','minutes':26}]}
        self.assertEqual(P.pair_health(key,[],0,{key:{}},now=NOW,timing=timing)[0],'bad')


if __name__=='__main__':
    unittest.main()
