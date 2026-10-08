#!/usr/bin/env python3
"""Match identity, each pick's link, the day windows, the empty line, and phone layout."""
import datetime
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import sandbox_sources as S
import tennis_cards as C
import tennis_build
import site_chrome

NOW = datetime.datetime(2026, 10, 7, 12, tzinfo=datetime.timezone.utc)   # 7 AM CT


def row(name):
    return dict(name=name, sport='tennis', meta=S.SOURCES[name],
                prod=True, v='waiting', a=dict(n=0, won=0), open=1, since=None)


rows = [row('tennis_fav_band_3h'), row('tennis_fav_band')]


def quote(pid, name, label, hours, **kwargs):
    start = (NOW + datetime.timedelta(hours=hours)).isoformat() if hours is not None else None
    q = dict(id=pid, source=name, sport='tennis', status='open', bet=True,
             market_id='aec-atp-' + pid, tier='atp', tour='atp', label=label, start=start,
             side_a='Alpha', side_b='Beta', pick='a', price=0.75, venue='polymarket_us',
             date='2026-10-07', logged='2026-10-07T10:00:00Z',
             url='https://polymarket.us/event/' + pid)
    q.update(kwargs)
    return q


quotes = [quote('market-a', rows[0]['name'], 'Alpha v Beta', 24),
          quote('market-b', rows[1]['name'], 'Alpha v Beta', 24, pick='b'),
          quote('past-day', rows[0]['name'], 'Old v Match', -30),
          quote('past-today', rows[0]['name'], 'Earlier v Today', -1),
          quote('today', rows[0]['name'], 'Today v Future', 2),
          quote('later', rows[0]['name'], 'Later v Match', 72),
          quote('unknown', rows[0]['name'], 'Unknown v Time', None),
          quote('won-today', rows[0]['name'], 'Won v Today', -5, status='won', result='a', pnl=33.33),
          quote('lost-yesterday', rows[0]['name'], 'Lost v Yesterday', -20, status='lost', result='b', pnl=-100.0)]
d = {'quotes': quotes}

picks = C.pick_rows(d, rows, NOW)
# Every open pick, plus the one settled today. Yesterday's loss is not a line.
assert [q['id'] for _r, q in picks] == [
    'past-day', 'won-today', 'past-today', 'today', 'market-a', 'market-b', 'later', 'unknown'], \
    [q['id'] for _r, q in picks]

html = C.picks_html(d, rows, NOW)
# The same contest picked by two rules is two lines, each linked to its own market and
# each naming its own side. Labels are stored with ' v '; the page prints ' vs '.
assert html.count('Alpha vs Beta') == 2 and ' v ' not in re.sub(r'<[^>]+>', ' ', html)
for market, side in (('market-a', 'Alpha'), ('market-b', 'Beta')):
    line = re.search(r'<div class="tn-pick [^"]*"[^>]*>(?:(?!tn-pick).)*?href="https://polymarket.us/event/'
                     + market + r'".*?</span></div>', html, re.S).group()
    assert f'<span class="tn-pos"><b>{side}</b></span>' in line, line
days = re.findall(r'<div class="tn-day">([^<]+)</div>', html)
assert days == ['Oct 6', 'Today · Oct 7', 'Tomorrow · Oct 8', 'Oct 10', 'Time unconfirmed'], days
states = re.findall(r'<span class="tn-state ([^"]+)">([^<]+)</span>', html)
assert states == [('is-late', 'unsettled · 30h'), ('is-won', 'W'), ('is-live', 'in play'),
                  ('is-next', 'upcoming'), ('is-next', 'upcoming'), ('is-next', 'upcoming'),
                  ('is-next', 'upcoming'), ('is-next', 'upcoming')], states
assert '<span class="tn-time">time TBC</span>' in html
assert 'No open pick' not in html

# Settled today and nothing open: the lines stay, and the one-line empty state follows.
quiet = C.picks_html({'quotes': [quotes[7]]}, rows, NOW)
assert 'Won vs Today' in quiet and quiet.count('No open pick · next check ') == 1, quiet
nothing = C.picks_html({'quotes': []}, rows, NOW)
assert nothing.startswith('<p class="tn-empty">No open pick · next check ') and 'tn-picks' not in nothing

empty = tennis_build.build({'quotes': []}, {'pairs': {}}, NOW)
for anchor in ('matches', 'rules', 'system'):
    assert f'id="{anchor}"' in empty, anchor
assert 'href="#matches"' in empty and 'href="#rules"' in empty and 'href="#system"' in empty

from require_browser import require_browser
playwright = require_browser('test_tennis_match_center.py')
if playwright is not None:
    import sandbox_build as B
    # The publish path labels every cell for the phone cards; judge that page.
    full = B.label_cells(tennis_build.build(d, {'pairs': {}}, NOW))
    with playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()

        def serve(route):
            name = Path(urlparse(route.request.url).path).name
            if name == 'tennis.html':
                route.fulfill(body=full, content_type='text/html')
            else:
                route.fulfill(path=str(Path(C.__file__).parent / 'public_site' / name))
        page.route('http://fixture.local/**', serve)
        page.goto('http://fixture.local/tennis.html', wait_until='load')
        for width in (1280, 390, 320):
            page.set_viewport_size({'width': width, 'height': 800})
            assert page.locator('#matches .tn-pick').first.is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), width
            # The match list stays a flat list at every width: one grid row per pick.
            assert page.locator('#matches .tn-pick').count() == full.count('class="tn-pick ') > 0
            assert page.evaluate("getComputedStyle(document.querySelector('.tn-pick')).display") == 'grid'
            # The rules table is cards under 760px, a table above it.
            thead_shown = page.locator('#rules table thead').first.is_visible()
            assert thead_shown == (width > 760), (width, thead_shown)
            assert page.locator('#system > details').get_attribute('open') is None
        browser.close()
print('PASS tennis identity, per-pick links, day windows, empty line, and phone layout')
