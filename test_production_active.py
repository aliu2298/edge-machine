#!/usr/bin/env python3
"""Production pairs must be active at the actual fetch and logging gates."""
import unittest
from unittest.mock import patch

import production as P
import sandbox_sources as S
import sandbox_track as T


class ProductionActive(unittest.TestCase):
    def test_registry_has_no_paused_production_pair(self):
        pairs = P.production_pairs(T.load_stages())
        # The daily collector owns its own Production registry and publication clock.
        try:
            import daily_production
            pairs.update(daily_production.pairs())
        except ImportError:
            pass
        self.assertTrue(pairs)
        paused = [key for key in pairs if S.lane_paused(*key.split('|', 1))]
        self.assertEqual(paused, [], 'Production must contain active rules only')

    def test_hand_promoted_pairs_are_not_paused(self):
        self.assertEqual([key for key in T.PAIR_OVERRIDES
                          if S.lane_paused(*key.split('|', 1))], [])

    def test_club_form_rule_fetches_and_logs(self):
        self.assertFalse(S.fetch_skipped('o15_form_l10', 'soccer_o15'))
        self.assertFalse(S.source_fully_paused('o15_form_l10'))
        self.assertFalse(S.lane_paused('o15_form_l10', 'soccer_o15'))
        # Exercise publish with a qualifying adapter opinion, no network.
        from datetime import datetime, timedelta, timezone
        now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        row = dict(market_id='KXEPLTOTAL-26OCT15AB-2', venue='kalshi_binary',
                   start=(now+timedelta(hours=3)).isoformat(), date='2026-10-15',
                   sport='soccer_o15', side_a='Over 1.5 goals', side_b='Under 1.5 goals',
                   label='Alpha vs Beta', price_a=.75, price_b=.26, price_draw=None,
                   tradeable={'a':True,'b':True}, untraded=False, url='',
                   league='Premier League', espn_home='Alpha', espn_away='Beta',
                   start_source='espn')
        data={'quotes':[], 'meta':{}}
        with patch.object(S, 'CHALLENGERS', {'o15_form_l10':lambda sport:[{'market_id':row['market_id'], 'pick':'a'}]}), \
             patch.object(S, 'plan_pinnacle', return_value={}), \
             patch.object(T, 'snap_closing', return_value=0):
            T.publish(data, {'soccer_o15':[row]}, {}, verbose=False, now=now)
        self.assertEqual(len([q for q in data['quotes'] if q.get('bet') and q['source']=='o15_form_l10']),1)

    def test_nonproduction_variants_remain_paused(self):
        for sport in ('soccer_o15_cup', 'soccer_o15_intl'):
            self.assertTrue(S.lane_paused('o15_form_l10',sport))


if __name__=='__main__':
    unittest.main()
