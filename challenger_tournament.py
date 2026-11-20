"""The Challenger tournament, read from Kalshi's market rules (2026-11-20).

Why this exists: challenger_form.py reads the tournament from the event's product_metadata.competition ("ATP Challenger Taipei").
From 2026-11-11 Kalshi stopped filling that in: every Challenger event since carries the bare "ATP Challenger", so "has already won
a match at THIS tournament" collapsed into "won any Challenger match in the last 10 days". The tournament is still written in
every market's rules text ("... match in the 2026 ATP Challenger Helsinki Quarterfinal after a ball has been played"), open
markets included. This module reads it from there. challenger_form.py is NOT touched: the Sandbox paper lane keeps its own reading
as the control.

Checked against the named era (events through 2026-11-10, where Kalshi still gave the city): the rules-text tournament equals
product_metadata.competition on every one of the 492 events, qualifying and main draw alike (see replay() and
test_challenger_tournament.py), so the same matches count as "at this tournament" and the same players are picked.
"""
import datetime as dt
import re

import challenger_form as F

GENERIC = "ATP Challenger"
RULES = re.compile(r"match in the (?:20\d\d )?(.+?) after a ball", re.S)
# The tournament name ends where the round begins ("Helsinki Quarterfinal", "Matsuyama 1/16 Finals", "Taipei Qualification Round 1").
ROUND = re.compile(r"\s+(?:Round\b|Quarter|Semi|Final|Qualif|Q\d|R\d|\d+/\d+|1st|2nd|3rd)", re.I)


def parse_rules(text):
    """The tournament in one market's rules_primary, None when the text does not name one."""
    m = RULES.search(text or "")
    if not m:
        return None
    name = m.group(1)
    cut = ROUND.search(name)
    name = (name[:cut.start()] if cut else name).strip()
    return name or None


def tournament(event):
    """The tournament of a Kalshi event object (markets nested): the named competition when Kalshi gives one, else the rules text.
    None when the two markets disagree or no name can be read; a caller skips such an event, never guesses."""
    named = ((event.get("product_metadata") or {}).get("competition") or "").strip()
    if named and named != GENERIC:
        return named
    seen = {parse_rules(m.get("rules_primary")) for m in event.get("markets") or []}
    return seen.pop() if len(seen) == 1 and None not in seen else None


def rules_tournament(event):
    """The rules-text reading alone (the named field ignored): what the replay compares with the field."""
    seen = {parse_rules(m.get("rules_primary")) for m in event.get("markets") or []}
    return seen.pop() if len(seen) == 1 and None not in seen else None


def history(event_ticker, tourn, cut_ts, settled, reader=tournament):
    """{player: (played, won)} at `tourn` from two-player matches settled before `cut_ts`, this event excluded.
    `settled` is a list of settled events (markets nested); `reader` names each one's tournament."""
    out = {}
    for ev in settled:
        if ev.get("event_ticker") == event_ticker or reader(ev) != tourn:
            continue
        ms = ev.get("markets") or []
        done = [m for m in ms if (F._ts(m.get("settlement_ts")) or 9e12) < cut_ts and m.get("result") in ("yes", "no")]
        if len(done) != len(ms) or len(ms) != 2:
            continue
        for m in ms:
            key = F.norm(m.get("yes_sub_title"))
            p, w = out.get(key, (0, 0))
            out[key] = (p + 1, w + (m.get("result") == "yes"))
    return out


def picks(event, cut_ts, settled, reader=tournament):
    """[(market ticker, player, opponent)]: the player who already won a match here while the opponent has not played one here."""
    ms = event.get("markets") or []
    if len(ms) != 2 or not all(m.get("yes_sub_title") for m in ms):
        return []
    tourn = reader(event)
    if not tourn:
        return []
    seen = history(event.get("event_ticker"), tourn, cut_ts, settled, reader)
    out = []
    for m, other in ((ms[0], ms[1]), (ms[1], ms[0])):
        me, opp = F.norm(m["yes_sub_title"]), F.norm(other["yes_sub_title"])
        if seen.get(me, (0, 0))[1] >= 1 and seen.get(opp, (0, 0))[0] == 0:
            out.append((m["ticker"], m["yes_sub_title"], other["yes_sub_title"]))
    return out


def replay(settled, first_day, last_day, hours=1):
    """The gate: over every event dated first_day..last_day that Kalshi named, does the rules-text reading give the same
    tournament and the same picks as the named field? Returns the counts."""
    def named_only(ev):
        return ((ev.get("product_metadata") or {}).get("competition") or "").strip() or None
    n = same_t = same_p = with_pick = 0
    diffs = []
    for ev in settled:
        day = dt.datetime.strptime(ev["event_ticker"].split("-")[1][:7], "%y%b%d").date()
        field = named_only(ev)
        if not first_day <= day <= last_day or not field or field == GENERIC:
            continue
        n += 1
        same_t += rules_tournament(ev) == field
        start = min((F._ts(m.get("occurrence_datetime")) or 9e12) for m in ev.get("markets") or [{}])
        cut = start - hours * 3600
        by_field = picks(ev, cut, settled, reader=named_only)
        by_rules = picks(ev, cut, settled, reader=rules_tournament)
        with_pick += bool(by_field)
        if by_field == by_rules:
            same_p += 1
        else:
            diffs.append((ev["event_ticker"], by_field, by_rules))
    return dict(events=n, same_tournament=same_t, same_picks=same_p, events_with_a_pick=with_pick, diffs=diffs[:10])
