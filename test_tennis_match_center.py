#!/usr/bin/env python3
"""Match identity, each pick's link, the tabs' windows, the empty state, and phone layout."""
import datetime
import re
from pathlib import Path
from urllib.parse import urlparse

import sandbox_sources as S
import sport_page as SP
import tennis_cards as C
import tennis_build

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

events = C.events(d, rows, NOW)
nxt, later, live, done = SP.bucket(events, NOW)
# The same contest picked by two rules is one event with two picks, each linked to its
# own market and each naming its own side. Labels are stored with ' v '; the page prints ' vs '.
alpha = [e for e in nxt if e['label'] == 'Alpha vs Beta']
assert len(alpha) == 1 and len(alpha[0]['picks']) == 2, [(e['label'], len(e['picks'])) for e in nxt]
assert sorted((p['href'], p['text']) for p in alpha[0]['picks']) == [
    ('https://polymarket.us/event/market-a', 'Alpha'), ('https://polymarket.us/event/market-b', 'Beta')]
assert ' v ' not in ' '.join(e['label'] for e in events)
assert [e['label'] for e in nxt] == ['Today vs Future', 'Alpha vs Beta', 'Unknown vs Time'], [e['label'] for e in nxt]
assert [e['label'] for e in later] == ['Later vs Match']
assert [e['label'] for e in live] == ['Old vs Match', 'Earlier vs Today']
assert [e['label'] for e in done] == ['Won vs Today', 'Lost vs Yesterday']
assert SP.pick_state(live[0]['picks'][0], NOW) == ('unsettled · 30h', 'is-late')
assert SP.pick_state(live[1]['picks'][0], NOW) == ('in play', 'is-live')
assert SP.pick_state(nxt[2]['picks'][0], NOW) == ('upcoming', 'is-next')

# The page on the fixture's own rows (the registry no longer lists the older band as a
# live lane, so the built page would carry one rule): the template takes rows directly.
spec = SP.spec(family='Tennis', key='tennis', title='Edge Machine · Tennis', description='t', scope='s',
               rows=rows, events=C.events, rule_name=C.rule_name, market=C.market,
               definition=C.definition, recent=C.recent_html, method=C.method(''))
html = SP.page(spec, d, {'pairs': {}}, NOW, rows=rows)
ev = re.search(r'<section id="events"[^>]*>(.*?)(?=<section id="|<footer)', html, re.S).group(1)
days = re.findall(r'<h4 class="sp-day-head">([^<]+)', ev.split('id="events-live"', 1)[0])
assert days == ['Wed Oct 7', 'Thu Oct 8', 'Sat Oct 10'], days
# A pick with a date but no readable time sits under its day, as time TBC.
assert ev.find('Wed Oct 7') < ev.find('Unknown vs Time') < ev.find('Thu Oct 8')
states = re.findall(r'<span class="sp-state ([^"]+)">([^<]+)</span>', ev)
assert sorted(states) == sorted([('is-late', 'unsettled · 30h'), ('is-won', 'W'), ('is-live', 'in play'),
                                 ('is-lost', 'L'), ('is-next', 'upcoming'), ('is-next', 'upcoming'),
                                 ('is-next', 'upcoming'), ('is-next', 'upcoming'), ('is-next', 'upcoming')]), states
assert '<span class="sp-tbc">time TBC</span>' in ev
assert 'data-empty="next"' not in ev

# Settled only: the Next 24h and In progress tabs say why they are empty, Completed starts selected.
quiet = tennis_build.build({'quotes': [quotes[7]]}, {'pairs': {}}, NOW)
assert 'Won vs Today' in quiet and quiet.count('No pick starts in the next 24 hours') == 1, quiet.count('No pick starts')
assert 'next check ' in quiet and 'data-default-tab="done"' in quiet
nothing = tennis_build.build({'quotes': []}, {'pairs': {}}, NOW)
assert 'data-empty="next"' in nothing and 'data-empty="done"' in nothing and 'class="sp-pick' not in nothing

for anchor in ('events', 'rules', 'method'):
    assert f'id="{anchor}"' in nothing, anchor
assert 'href="#events"' in nothing and 'href="#rules"' in nothing and 'href="#method"' in nothing

from require_browser import require_browser
playwright = require_browser('test_tennis_match_center.py')
if playwright is not None:
    # The published shape: the registry's own rows, so the Sandbox table is on the page.
    full = tennis_build.build(d, {'pairs': {}}, NOW)
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
            assert page.locator('#events-next .sp-pick').first.is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), width
            # The events stay a flat list at every width: one grid row per pick.
            assert page.locator('#events-next .sp-pick:visible').count() == 3, page.locator('#events-next .sp-pick:visible').count()
            assert page.evaluate("getComputedStyle(document.querySelector('.sp-pick')).display") == 'grid'
            # The Sandbox table is cards under 760px, a table above it.
            page.locator('details.sp-sandbox').evaluate('e => e.open = true')
            thead_shown = page.locator('#rules table thead').first.is_visible()
            assert thead_shown == (width > 760), (width, thead_shown)
            assert page.locator('#method > details').get_attribute('open') is None
        browser.close()
print('PASS tennis identity, per-pick links, the tabs, the empty state, and phone layout')
