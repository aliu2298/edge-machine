"""The Fights page (2026-10-26, Olu): two Sandbox paper lanes on the cheap side + resting take-profit
standard, in the Culture and Commodities pages' layout.

Top to bottom: the standard in a few lines, one summary table (a row per lane), the two lane cards
(per-fight rows and the trade list, each fill with its minute's traded volume), a research note per
lane. The ledgers are written by fights_split.py (fights.yml, hourly); this page reads them. The
engine, tiles, tables and phone layout are mentions_split's, so the page reads like Culture.
"""
import os

import fights_split as FS
import mentions_split as MS
import site_chrome as C
import sport_page as SP

KEY = "fights"
TITLE = "Edge Machine · Fights"
DESCRIPTION = ("Kalshi boxing and UFC winner markets on paper: the cheap side about an hour before the fight, "
               "with a resting take-profit, beside the same entries held.")
SECTIONS = (("standard", "Standard"), ("lanes", "Lanes"))


def load_states():
    return {cfg["lane"]: FS.load(cfg) for cfg in FS.LANES}


def build(states=None, now=None):
    now = SP.as_utc(now)
    states = states if states is not None else load_states()
    e = C.esc
    standard = (
        '<section id="standard"><h1>Fights</h1>'
        '<p class="lede"><b>Cheap side + resting take-profit.</b></p>'
        '<ul class="sm">'
        '<li>Buy the cheap fighter about an hour before the fight starts, at the real ask.</li>'
        '<li>Rest a split sell: half at 2x, half at 3x.</li>'
        '<li>A fill counts only on a traded print in a minute candle, never the bid.</li>'
        '<li>Every lane is shown next to the same entries held.</li></ul>'
        '<p class="sm mut">Sandbox, paper only, each lane on a fresh record from its first entry: review at 10 settled, '
        'decide at 30. The start is Kalshi\'s scheduled start for the fight.</p></section>')
    cards = "".join(
        f'<p class="sm" id="{e(cfg["anchor"])}-note"><b>{e(cfg["research"])}</b></p>' + MS.section(states[cfg["lane"]], e, cfg)
        for cfg in FS.LANES)
    body = (standard
            + f'<section id="lanes"><h2>Fight lanes</h2>{MS.summary(FS.LANES, states, e)}{cards}</section>'
            + '<p class="sm mut">Read hourly by GitHub Actions (fights.yml) from Kalshi public market data, minute '
              'candles and fight schedules. Paper entries at the ask with Kalshi\'s fees.</p>')
    html = C.document(TITLE, DESCRIPTION, KEY, SECTIONS, C.stamp(now), body,
                      script_src="./site.js", scripts=("./tables.js",))
    return MS.label_cells(html)


def main():
    out = os.path.join(FS.ROOT, "public_site", "fights.html")
    with open(out, "w") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
