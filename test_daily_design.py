"""Daily tabs reuse the current Crypto/Commodities template, not a separate design."""
import copy
import datetime as dt
import daily_build as D
import daily_track as T
import crypto_build as C
import commodities_build as M

now=dt.datetime(2026,10,13,12,tzinfo=dt.timezone.utc)
state={'lanes':{k:{'picks':[],'baseline':[],'catalog':[],'observations':[],'error':None} for k in T.LANES}}
reference=[C.build(d={'quotes':[]},st={'pairs':{}},now=now),
           M.build(d={'quotes':[]},st={'pairs':{}},now=now)]
tokens=['class="sp-head"','class="tiles sp-tiles"','class="sp-filters"',
        'class="sp-rules-list"','class="sp-tabs"','id="events-next"',
        'id="events-live"','id="events-done"','class="sp-method"',
        'src="./tables.js"','src="./sports.js"']
for key in T.LANES:
    html=D.build(key,state,now)
    for token in tokens:
        assert token in html and all(token in r for r in reference), token
    assert html.count('class="tile"')==4
    assert 'Econ Daily' in html and 'Finance Daily' in html
    assert 'Scan reasons &amp; coverage' in html
    assert '<style' not in html and 'onclick=' not in html
    assert 'No '+T.LANES[key].lower()+' rule is in Production.' in html
    sample=copy.deepcopy(state)
    sample['lanes'][key]['picks']=[dict(id='KXINX-26OCT12-T6000',event='KXINX-26OCT12',
        series='KXINX',name='S&P close',title='Above 6000',close='2026-10-12T20:00Z',
        price=.75,bid=.73,size=25,logged='2026-10-12T17:00Z',status='won',profit=31.04,settled='2026-10-12T21:00Z')]
    rendered=D.build(key,sample,now)
    assert 'Above 6000' in rendered and '1/30 market-days' in rendered
    assert 'Paper record · not graded' in rendered
    assert sample['lanes'][key]['picks'][0]['profit']==31.04
print('PASS: current shared template, four tiles, rule folds, filters, event tabs, scripts, and unchanged paper records')
