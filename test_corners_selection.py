#!/usr/bin/env python3
"""One total/team corners selection per fixture, locked through later reads."""
import copy
import datetime as dt
import unittest
from unittest.mock import patch

import production as P
import sandbox_sources as S
import sandbox_track as T

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 15, 17, tzinfo=UTC)


def row(ticker='KXUCLCORNERS-26OCT15ROMRMA-9', price=.4, model=.2):
    return dict(market_id=ticker, venue='kalshi_binary', sport='soccer_corners',
                start='2026-10-15T19:00:00+00:00', date='2026-10-15',
                espn_home='AS Roma', espn_away='Real Madrid', start_source='espn', league='Champions League',
                side_a='9+ corners', side_b='No', label='AS Roma vs Real Madrid',
                price_a=1-price, price_b=price, price_draw=None, untraded=False,
                tradeable={'a': True, 'b': True}, url='', model=model)


def lead(lid, ticker, status='pending'):
    return dict(id=lid, sport='soccer_corners', bet={'kind': 'corners_lte', 'n': 8},
                route={'market': ticker}, status=status)


class CornersSelection(unittest.TestCase):
    def test_best_edge_across_total_and_team_and_other_fixture(self):
        rows = [row(), row('KXUCLTCORNERS-26OCT15ROMRMA-RMA6', .3),
                row('KXUCLCORNERS-26OCT15AVLFEN-9')]
        with patch.object(S, 'corners_model', side_effect=lambda f,r,k:r['model']):
            picks = S.fetch_corners_under('soccer_corners', {'soccer_corners': rows}, [], NOW)
            flipped = S.fetch_corners_under('soccer_corners', {'soccer_corners': rows[::-1]}, [], NOW)
        self.assertEqual(picks, flipped)
        self.assertEqual({p['market_id'] for p in picks}, {rows[1]['market_id'], rows[2]['market_id']})

    def test_tie_break_and_untradeable_best(self):
        a, b = row('KXUCLCORNERS-26OCT15ROMRMA-8'), row()
        with patch.object(S, 'corners_model', return_value=.2):
            self.assertEqual(S.fetch_corners_under('soccer_corners', {'soccer_corners':[b,a]}, [], NOW)[0]['market_id'], a['market_id'])
            a['untraded'] = True
            self.assertEqual(S.fetch_corners_under('soccer_corners', {'soccer_corners':[a,b]}, [], NOW)[0]['market_id'], b['market_id'])

    def publish(self, data, rows):
        picks = [dict(market_id=r['market_id'], pick='b') for r in rows]
        with patch.object(S, 'CHALLENGERS', {'corners_under': lambda sport:picks}), \
             patch.object(S, 'plan_pinnacle', return_value={}), \
             patch.object(T, 'snap_closing', return_value=0):
            T.publish(data, {'soccer_corners': rows}, {}, verbose=False, now=NOW)

    def test_logging_blocks_team_total_same_pass_and_later_refresh(self):
        a, b = row(), row('KXUCLTCORNERS-26OCT15ROMRMA-RMA6')
        data = {'quotes':[], 'meta':{}}
        self.publish(data, [a,b])
        bets = lambda: [q for q in data['quotes'] if q.get('bet') and q['source']=='corners_under']
        self.assertEqual(len(bets()), 1)
        original = copy.deepcopy(bets()[0])
        self.publish(data, [b])
        self.assertEqual(bets(), [original])
        data['_archive'] = [original]
        data['quotes'] = []
        data['_archive'][0]['status'] = 'void'
        self.publish(data, [b])
        self.assertEqual(bets(), [])

    def test_build_feed_wires_durable_selection(self):
        data = {'quotes': [], 'meta': {}}
        self.publish(data, [row()])
        first = next(q for q in data['quotes'] if q.get('bet'))
        extra = dict(first, id='corners_under:extra', market_id='KXUCLTCORNERS-26OCT15ROMRMA-RMA6', team='Real Madrid')
        data['quotes'].append(extra)  # Simulate a legacy ledger with two rungs.
        stages = {'pairs': {'corners_under|soccer_corners': {'stage':'production', 'ready_at':'2026-10-14T00:00:00+00:00'}}}
        feed = P.build_feed(data, stages, now=NOW)
        self.assertEqual(len(feed['leads']), 1)
        self.assertEqual(len(feed['corners_selections']), 1)
        refreshed = P.build_feed(data, stages, now=NOW+dt.timedelta(minutes=10), previous=feed)
        self.assertEqual(set(refreshed['leads']), set(feed['leads']))
        self.assertEqual(refreshed['corners_selections'], feed['corners_selections'])

    def test_feed_locks_missing_selection_and_preserves_history(self):
        a = lead('a', 'KXUCLCORNERS-26OCT15ROMRMA-9')
        b = lead('b', 'KXUCLTCORNERS-26OCT15ROMRMA-RMA6')
        c = lead('c', 'KXUCLCORNERS-26OCT15AVLFEN-9')
        leads = {'b':b, 'a':a, 'c':c}
        locks = P._one_corners_per_match(leads, {'a':('2026-10-15T16:00Z', .4), 'b':('2026-10-15T17:00Z', .3)})
        self.assertEqual(set(leads), {'a','c'})
        refreshed = {'b':b}
        locks = P._one_corners_per_match(refreshed, {}, {'leads':{}, 'corners_selections':locks})
        self.assertEqual(refreshed, {})
        historical = {'a':dict(a,status='miss'), 'b':dict(b,status='miss')}
        P._one_corners_per_match(historical, {}, {'corners_selections':locks})
        self.assertEqual(len(historical), 2)

    def test_feed_migration_uses_first_published_and_unknown_fails_closed(self):
        a = lead('a', 'KXUCLCORNERS-26OCT15ROMRMA-9')
        b = lead('b', 'KXUCLTCORNERS-26OCT15ROMRMA-RMA6')
        previous = {'leads': {'a':dict(a,published_at='2026-10-15T16:00Z')}}
        leads = {'a':a,'b':b,'unknown':lead('unknown','bad')}
        P._one_corners_per_match(leads, {'b':('2026-10-15T15:00Z',.3)}, previous)
        self.assertEqual(set(leads), {'a'})


if __name__ == '__main__':
    unittest.main()
