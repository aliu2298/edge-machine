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
        '<p class="sm mut">Sandbox, paper only, each lane on a fresh record from its first entry: review at 10 settled '
        'events (fights), decide at 30. The start is Kalshi\'s scheduled start for the fight.</p></section>')
    cards = "".join(
        f'<p class="sm" id="{e(cfg["anchor"])}-note"><b>{e(cfg["research"])}</b></p>'
        f'<p class="sm mut fights-blind">{e(FS.BLIND)}</p>' + MS.section(states[cfg["lane"]], e, cfg)
        for cfg in FS.LIVE)
    lanes = (MS.summary(FS.LIVE, states, e) + cards if FS.LIVE else
             '<p class="sm mut">No filtered fights lane yet. A filtered boxing lane must beat the baseline below.</p>')
    body = (standard
            + f'<section id="lanes"><h2>Fight lanes</h2>{lanes}{"".join(baseline_block(c, states, e) for c in FS.BASES)}</section>'
            + retired_fold(states, e)
            + '<p class="sm mut">Read hourly by GitHub Actions (fights.yml) from Kalshi public market data, minute '
              'candles and fight schedules. Paper entries at the ask with Kalshi\'s fees.</p>')
    html = C.document(TITLE, DESCRIPTION, KEY, SECTIONS, C.stamp(now), body,
                      script_src="./site.js", scripts=("./tables.js",))
    return MS.label_cells(html)


def baseline_name(cfg):
    """"Boxing cheap dog" from "Boxing · cheap dog (3-15c)": the name the Chaos baselines line uses too."""
    return cfg["label"].split(" (")[0].replace(" · ", " ")


def baseline_block(cfg, states, e):
    """A blind price-band population kept as a BASELINE (2026-11-04, Olu), in the Chaos baselines' layout: its record
    and card, no review status, not a lane. A filtered boxing lane must beat it."""
    g = cfg["baseline"]
    r = MS.record(MS.counted(states[cfg["lane"]]))
    return (f'<details class="section-disclosure baseline" data-lane="{e(cfg["lane"])}" id="baseline-{e(cfg["lane"])}" open>'
            f'<summary><b>Baseline · {e(baseline_name(cfg))} (blind, price band only)</b>'
            f'<span>{r["settled_events"]} settled events · read every hour · not a lane</span></summary>'
            f'<p class="sm mut">Registered as a baseline {e(g["on"])} at {e(g["at"])}: {e(g["reason"])}. '
            'A filtered boxing lane must beat this record. The entry and exit rules are unchanged.</p>'
            f'<p class="sm" id="{e(cfg["anchor"])}-note"><b>{e(cfg["research"])}</b></p>'
            + MS.summary((cfg,), states, e) + MS.section(states[cfg["lane"]], e, cfg) + '</details>')


def retired_fold(states, e):
    """Retired fights lanes (2026-11-03): collapsed, each with its dated record and reason, then its full card. Rows
    stay; an open entry still settles."""
    if not FS.GONE:
        return ""
    lines = "".join(f'<li data-lane="{e(c["lane"])}"><b>{e(c["label"])}</b>: retired {e(c["retired"]["on"])} at '
                    f'{e(c["retired"]["at"])}: {e(c["retired"]["reason"])}. Its rows stay; any open entry still settles.</li>'
                    for c in FS.GONE)
    cards = "".join(f'<p class="sm" id="{e(c["anchor"])}-note"><b>{e(c["research"])}</b></p>' + MS.section(states[c["lane"]], e, c)
                    for c in FS.GONE)
    return (f'<details class="fold sec" id="retired"><summary><h2>Retired</h2> <span class="mut sm">· {len(FS.GONE)} '
            f'lane{"s" if len(FS.GONE) != 1 else ""} · kept, not deleted</span></summary><ul class="sm">{lines}</ul>'
            + MS.summary(FS.GONE, states, e) + cards + '</details>')


def main():
    out = os.path.join(FS.ROOT, "public_site", "fights.html")
    with open(out, "w") as f:
        f.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
