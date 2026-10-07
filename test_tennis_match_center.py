#!/usr/bin/env python3
"""Match identity, each pick's link, real time windows, and phone layout."""
import datetime
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import sandbox_sources as S
import tennis_cards as C
import tennis_build
import site_chrome

NOW = datetime.datetime(2026, 10, 7, 12, tzinfo=datetime.timezone.utc)
def row(name):
    return dict(name=name, sport='tennis', meta=S.SOURCES[name],
                prod=True, v='waiting', a=dict(n=0, won=0), open=1)
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
quotes = [quote('market-a', rows[0]['name'], 'Alpha v Beta: Alpha wins', 24),
          quote('market-b', rows[1]['name'], 'Alpha v Beta: Beta wins', 24,
                start='2026-10-08T12:00:00Z', pick='b'),
          quote('past-day', rows[0]['name'], 'Old v Match', -30),
          quote('past-today', rows[0]['name'], 'Earlier v Today', -1),
          quote('today', rows[0]['name'], 'Today v Future', 2),
          quote('boundary', rows[0]['name'], 'Boundary v Match', 48),
          quote('beyond', rows[0]['name'], 'Beyond v Window', 48 + 1 / 3600),
          quote('later', rows[0]['name'], 'Later v Match', 72),
          quote('unknown', rows[0]['name'], 'Unknown v Time', None)]
d = {'quotes': quotes}
matches = C._match_rows(d, rows, NOW)
assert len(matches) == len(quotes) - 1
match = next(m for m in matches if m['q']['id'] == 'market-a')
html = C._match_card(match)
assert 'Alpha' in html and 'Beta' in html
assert 'href="https://polymarket.us/event/market-a"' in html
assert 'href="https://polymarket.us/event/market-b"' in html
for market, side in (('market-a', 'Alpha'), ('market-b', 'Beta')):
    links = re.findall(r'<a\b[^>]*href="https://polymarket.us/event/' + market + r'"[^>]*>([^<]+)</a>', html)
    assert links[-1].endswith(' · ' + side), links
assert len(match['rules']) == 2 and {q['pick'] for _, q in match['rules']} == {'a', 'b'}
assert C._fixture_key(quotes[0]) != C._fixture_key(dict(quotes[0], tier='wta'))
assert C._fixture_key(quotes[0]) != C._fixture_key(dict(quotes[0], start='2026-10-09T12:00:00Z'))
html = C.match_center(d, rows, NOW)
def section(anchor):
    return re.search(r'<section id="' + anchor + r'".*?</section>', html, re.S).group()
assert 'Today v Future' in section('today') and 'Earlier v Today' not in section('today')
upcoming = section('upcoming')
assert 'Alpha v Beta' in upcoming and 'Boundary v Match' in upcoming
for name in ('Old v Match', 'Earlier v Today', 'Beyond v Window', 'Later v Match', 'Unknown v Time'):
    assert name not in upcoming, name
assert 'Old v Match' in section('in-play') and 'Earlier v Today' in section('in-play')
assert all(name in section('other-open') for name in ('Beyond v Window', 'Later v Match', 'Unknown v Time'))
empty = tennis_build.build({'quotes': []}, {'pairs': {}}, NOW)
for anchor in ('today', 'upcoming', 'in-play', 'combos', 'rules', 'system'):
    assert f'id="{anchor}"' in empty, anchor

from require_browser import require_browser
playwright = require_browser('test_tennis_match_center.py')
if playwright is not None:
    with playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        document = site_chrome.document('Tennis', 'Fixture', 'tennis', (), '', html)
        def serve(route):
            name = Path(urlparse(route.request.url).path).name
            if name == 'tennis.html':
                route.fulfill(body=document, content_type='text/html')
            else:
                route.fulfill(path=str(Path(C.__file__).parent / 'public_site' / name))
        page.route('http://fixture.local/**', serve)
        page.goto('http://fixture.local/tennis.html', wait_until='load')
        for width in (1280, 390, 320):
            page.set_viewport_size({'width': width, 'height': 800})
            assert page.locator('#upcoming .tennis-match').first.is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), width
            assert page.locator('#upcoming .tennis-rule-chip a').count() == 3
        browser.close()
print('PASS tennis identity, per-pick links, time windows, empty navigation, and phone layout')
