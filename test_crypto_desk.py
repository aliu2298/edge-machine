#!/usr/bin/env python3
"""Crypto desk fixtures: stored records, unknown metrics, and watch-only quotes."""
import copy
import datetime
import os
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

import crypto_build as C
import sandbox_sources as S

NOW = datetime.datetime(2026, 10, 7, 12, tzinfo=datetime.timezone.utc)
row = {'sport': 'crypto_fav', 'prod': False, 'open': 0,
       'a': {'n': 2, 'won': 1, 'expected': 1.5, 'roi_fee': -0.1,
             'clv': None, 'clv_n': 0, 'n_bets': 5}}
with patch.object(C, 'crypto_rows', return_value=[row]), patch.object(C.B, 'sport_sections', return_value=''):
    html = C.build({'quotes': []}, {}, NOW)
    assert '1 v 1.5' in html and '-0.5 wins' in html and '5 contracts logged' in html
    unknown = copy.deepcopy(row)
    unknown['a'].update(expected=None, roi_fee=None, clv=None)
    with patch.object(C, 'crypto_rows', return_value=[unknown]):
        html = C.build({'quotes': []}, {}, NOW)
        assert '1 v —' in html and 'None' not in html
    with patch.object(C, 'crypto_rows', return_value=[]):
        html = C.build({'quotes': []}, {}, NOW)
        assert 'No crypto favourite-band record yet.' in html
        for anchor in ('today', 'performance', 'method', 'lanes'):
            assert f'id="{anchor}"' in html
    with patch.object(S, 'CRYPTO_FAV_BAND', (0.6, 0.9)), patch.object(S, 'CRYPTO_FAV_MAX_SPREAD', 0.04), patch.object(S, 'CRYPTO_FAV_CLOSE_ET', 16):
        html = C.build({'quotes': []}, {}, NOW)
        assert '60–90¢' in html and '≤4¢ spread' in html and '16:00 ET' in html
        assert '70–80¢' not in html

series = next(iter(S.COINS))
quote = dict(id='watch', source='crypto_fav_band', sport='crypto_fav',
             market_id=series + '-fixture', bet=False, status='won', price=0.75,
             logged='2026-10-07T12:00:00Z')
watch = C._coin_watch({'quotes': [quote]})[0]
assert watch[2] == 'Watching', watch
bet = dict(quote, id='bet', bet=True, status='lost', logged='2026-10-06T12:00:00Z')
watch = C._coin_watch({'quotes': [quote], '_archive': [bet]})[0]
assert watch[2] == 'Last Lost', watch
bet = dict(bet, status='open')
watch = C._coin_watch({'quotes': [quote, bet]})[0]
assert watch[2] == 'Open', watch
empty = C.build({'quotes': []}, {'pairs': {}}, NOW)
assert 'No crypto favourite-band record yet.' in empty
stored = dict(quote, id='graded', bet=True, pick='a', result='a',
              status='won', pnl=33.33, stake=100, date='2026-10-07',
              start='2026-10-07T21:00:00Z',
              price_a=0.75, price_b=0.25, side_a='Yes', side_b='No')
html = C.build({'quotes': [stored]}, {'pairs': {}}, NOW)
assert 'Last Won' in html and 'Favourite-band record' in html
from require_browser import require_browser
playwright = require_browser('test_crypto_desk.py')
if playwright is not None:
    with playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        def serve(route):
            name = Path(urlparse(route.request.url).path).name
            if name == 'crypto.html':
                route.fulfill(body=html, content_type='text/html')
            else:
                route.fulfill(path=str(Path(C.__file__).parent / 'public_site' / name))
        page.route('http://fixture.local/**', serve)
        page.goto('http://fixture.local/crypto.html', wait_until='load')
        for width in (1280, 390, 320):
            page.set_viewport_size({'width': width, 'height': 800})
            assert page.locator('.crypto-hero').is_visible()
            assert page.locator('.crypto-coin').count() == len(S.COINS)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), width
        browser.close()
print('PASS crypto desk render, nullable metrics, rule constants, and bet-only status')
