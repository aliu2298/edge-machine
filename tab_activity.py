#!/usr/bin/env python3
"""Which sport tabs have an active lane (2026-11-05, Olu: "if nothing is running, archive it").

THE RULE, checked at build time for every sport tab:
  A lane is ACTIVE when it is not retired, not a baseline, and has a bet or an open pick in its current record window.
  A tab with no active lane is ARCHIVED: it leaves the top nav (site_chrome.nav) and gets an entry in Archives
  (sandbox.html#archived-tabs) with its retired lanes, baselines and their records. Nothing is retired or deleted:
  a registered lane keeps logging, and the tab comes back on the first run after one of its lanes logs a pick (or a
  lane is registered and fires, or un-retired).

Each tab's lanes are the ones its own page counts, read with the page's own helpers: the tracker's rows from their
record clock (sport_tab.family_rows), the chaos lanes on their fresh record, and every own ledger the page draws.
A tab whose check raises counts as ACTIVE: an error never archives a tab.

`python3 tab_activity.py` writes data/tab_activity.json, which the page builds read (the Sandbox Tracker runs it
before building the pages). The first date a tab was seen archived is kept until it comes back.
"""
import datetime as dt
import json
import os
import sys

import fmt

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "tab_activity.json")
TABS = ("nba", "nfl", "nhl", "soccer", "tennis", "cricket", "crypto", "commodities", "econ_daily", "finance_daily", "culture", "fights")
# The one line an archived tab's Archives entry carries (2026-11-05). A tab archived with no note here gets the rule's words.
NOTES = {
    "cricket": ("Archived 2026-11-05 (Olu: if nothing is running, archive it): Oddspedia and Cricket consensus are retired, "
                "and Polymarket (international) has logged no cricket bet on its current record (6 bets Sep 13-19, before "
                "its 2026-10-12 reset). It is not retired: it keeps logging, and the tab returns on its first pick."),
    "fights": ("Archived 2026-11-05 (Olu: if nothing is running, archive it): Boxing cheap dog is a baseline (blind, price band "
               "only) and UFC dog is retired; no filtered fights lane is registered. The tab returns when one logs a pick."),
}


def _row_active(r):
    """The template row rule: not retired, not a baseline, a settled count or an open pick on its record clock."""
    a = r.get("a") or {}
    return (r.get("v") != "retired" and not r.get("gone") and (r.get("meta") or {}).get("kind") != "Baseline"
            and bool(a.get("n") or a.get("n_price") or r.get("open")))


def _family(d, st, family):
    import sport_tab
    return [f'{r["name"]}|{r["sport"]}' for r in sport_tab.family_rows(d, st, family) if _row_active(r)]


def _chaos(page):
    """The page's chaos lanes on their fresh record: not retired, not a baseline, not in-sample, with a settled entry."""
    import chaos_build as CB
    import chaos_lanes as CL
    import chaos_replay as C
    lanes = CB.with_config(C.load() if os.path.exists(C.PATH) else C.empty()).get("lanes") or {}
    out = []
    for lid in CB.HOMES.get(page, ()):
        cfg = next((x for x in CL.LANES if x["id"] == lid), {})
        L = lanes.get(lid)
        if L and not (cfg.get("retired") or cfg.get("baseline") or cfg.get("insample")) and CB.split_hold(L)["entries"]:
            out.append(lid)
    return out


def _own(cfgs):
    """mentions_split-style own-ledger lanes (cheap side, fights): live configs with an entry on their ledger."""
    import mentions_split as MS
    out = []
    for cfg in cfgs:
        if cfg.get("retired") or cfg.get("baseline"):
            continue
        st = MS.load(cfg=cfg)
        if st.get("entries"):
            out.append(cfg["lane"])
    return out


def _picks_lanes(state, keys, retired=()):
    return [k for k in keys if k not in retired
            and (((state.get("rules") or {}).get(k) or {}).get("picks") or ((state.get("lanes") or {}).get(k) or {}).get("picks"))]


# ------------------------------------------------------------------ one adapter per tab
def soccer(d, st, now):
    import soccer_lanes as SL
    live, _gone, _d, _st = SL.rows_and_inputs(d, st, now)
    return _family(d, st, "Soccer") + [r["name"] for r in live if _row_active(r)]


def nba(d, st, now):
    import nba_page as P
    return _family(d, st, "NBA") + _chaos("nba") + [r["name"] for r in P.rows(*P.load_all()) if r["a"].get("n")]


def nfl(d, st, now):
    import nfl_tt as N
    import nfl_tt_build as TB
    tt = TB._state(None)
    return (_family(d, st, "NFL") + _chaos("nfl")
            + [x for x in N.LANES if x not in N.RETIRED and _row_active(TB.template_row(x, tt))])


def nhl(d, st, now):
    """The two NHL goal lanes (nhl_goal_lanes.py, 2026-11-08): active once a lane (not a baseline) has a settled entry."""
    import nhl_build as NB
    import nhl_goal_lanes as N
    state = N.load()
    return [lane for lane in NB.HEADLINES if _row_active(NB.template_row(state, lane))]


def tennis(d, st, now):
    out = _family(d, st, "Tennis") + _chaos("tennis")
    try:
        import tennis_totals as TT
        if not TT.retired(now):
            out += ["tennis_atp_low_over"]
    except Exception:                                           # noqa: BLE001
        pass
    return out


def cricket(d, st, now):
    return _family(d, st, "Cricket")


def crypto(d, st, now):
    import crypto_build
    return [f'{r["name"]}|{r["sport"]}' for r in crypto_build.page_rows(d, st) if _row_active(r)]


def commodities(d, st, now):
    import commodities_build
    import mentions_split as MS
    return [f'{r["name"]}|{r["sport"]}' for r in commodities_build.page_rows(d, st) if _row_active(r)] + _own(MS.LIVE_COMMOD)


def econ_daily(d, st, now):
    import daily_track as D
    state = D.load()
    return [k for k in D.NC_LANES if ((state.get("nc") or {}).get(k) or {}).get("picks")]


def finance_daily(d, st, now):
    import finance_nc as F
    return [F.KEY] if (F.load().get("picks") or []) else []


def culture(d, st, now):
    import culture_track as CT
    import mentions_split as MS
    state = CT.load()
    out = [k for k in CT.LANES if not CT.retired(k, now) and ((state.get("lanes") or {}).get(k) or {}).get("picks")]
    out += _own([MS.ALBUM, MS.ALBUM_NO])
    try:
        import mentions_dip_hold as DH
        state_dh = DH.load()
        if any(DH.entries(state_dh, b) for b in DH.BIDS):
            out.append(DH.LANE)
    except Exception:                                           # noqa: BLE001
        pass
    return out


def fights(d, st, now):
    import fights_split as FS
    return _own(FS.LIVE)


ADAPTERS = dict(nba=nba, nfl=nfl, nhl=nhl, soccer=soccer, tennis=tennis, cricket=cricket, crypto=crypto, commodities=commodities,
                econ_daily=econ_daily, finance_daily=finance_daily, culture=culture, fights=fights)


def check(d=None, st=None, now=None, previous=None):
    """{tab: dict(active=[lanes], archived=bool, since=date or None, error=str or None)}."""
    import sandbox_track as T
    now = now or dt.datetime.now(dt.timezone.utc)
    d = d if d is not None else T.load()
    st = st if st is not None else T.load_stages()
    prev = (previous or {}).get("tabs") or {}
    out = {}
    for tab in TABS:
        try:
            lanes = sorted(set(ADAPTERS[tab](d, st, now)))
            err = None
        except Exception as exc:                                # noqa: BLE001
            lanes, err = None, f"{type(exc).__name__}: {exc}"[:200]
        archived = lanes is not None and not lanes
        since = ((prev.get(tab) or {}).get("since") or fmt.chicago(now).date().isoformat()) if archived else None
        out[tab] = dict(active=lanes or [], archived=archived, since=since, error=err)
    return out


# ------------------------------------------------------------------ the Archives entry
FAMILY = dict(nba="NBA", nfl="NFL", soccer="Soccer", tennis="Tennis", cricket="Cricket")
LABEL = dict(nba="NBA", nfl="NFL", nhl="NHL", soccer="Soccer", tennis="Tennis", cricket="Cricket", crypto="Crypto", commodities="Commodities",
             econ_daily="Econ Daily", finance_daily="Finance Daily", culture="Culture", fights="Fights")


def _esc(x):
    import html
    return html.escape("" if x is None else str(x))


def kept_rows(tab, d=None, st=None):
    """(lane, status, record, roi, note) for every lane an archived tab keeps: its retired lanes and baselines, and a
    registered lane with no pick on its current record. Records are each engine's own, as its page shows them."""
    import sandbox_build as B
    import sport_page as SP
    out = []
    fam = FAMILY.get(tab)
    if fam:
        import sandbox_track as T
        import sport_tab
        d = d if d is not None else T.load()
        st = st if st is not None else T.load_stages()
        for r in sport_tab.family_rows(d, st, fam):
            if not _row_active(r):
                kind = "baseline" if (r.get("meta") or {}).get("kind") == "Baseline" else "registered · no pick on its current record"
                out.append((B.rule_name(r), kind, SP.record_compact(r["a"]), SP.roi_html(r), ""))
        for r in sport_tab.retired_rows(d, st, fam):
            out.append((B.rule_name(r), "retired", SP.record_compact(r["a"]), SP.roi_html(r), r.get("gone") or ""))
    if tab == "fights":
        import fights_split as FS
        import mentions_split as MS
        for cfg in list(FS.BASES) + list(FS.GONE):
            rec = MS.record(MS.counted(MS.load(cfg=cfg)))
            why = (cfg.get("baseline") or cfg.get("retired") or {})
            roi = rec.get("roi")
            out.append((cfg.get("label") or cfg["lane"], "baseline" if cfg.get("baseline") else "retired",
                        f'{rec.get("won", 0)}–{max(0, rec.get("settled_events", 0) - rec.get("won", 0))} (events)',
                        "—" if roi is None else B.pct(roi, sign=True), f'{why.get("on", "")}: {why.get("reason", "")}'.strip(": ")))
    return out


def archive_html(blob=None):
    """The Archives page's entry for every archived tab (sandbox.html#archived-tabs), or "" when none is archived."""
    blob = blob if blob is not None else load()
    tabs = [(k, v) for k, v in (blob.get("tabs") or {}).items() if v.get("archived")]
    if not tabs:
        return ""
    parts = []
    for tab, v in sorted(tabs):
        try:
            rows = kept_rows(tab)
        except Exception as exc:                                # noqa: BLE001
            rows, parts_err = [], f'<p class="sm mut">Its lanes could not be listed ({_esc(type(exc).__name__)}).</p>'
        else:
            parts_err = ""
        body = "".join(f'<tr><td><b>{_esc(n)}</b></td><td>{_esc(k)}</td><td class="num">{rec}</td><td class="num">{roi}</td>'
                       f'<td class="sm mut">{_esc(note)}</td></tr>' for n, k, rec, roi, note in rows)
        table = ('<div class="tbl"><table><thead><tr><th>Lane</th><th>Status</th><th class="num">Record</th>'
                 f'<th class="num">ROI after fees</th><th>Note</th></tr></thead><tbody>{body}</tbody></table></div>') if rows else ""
        label = LABEL.get(tab, tab)
        parts.append(f'<details class="section-disclosure" id="archived-{_esc(tab)}"><summary><b>{_esc(label)}</b>'
                     f'<span>archived since {_esc(v.get("since"))} · {len(rows)} lane{"s" if len(rows) != 1 else ""} kept with their records</span></summary>'
                     f'<p class="sm">{_esc(NOTES.get(tab) or "Archived: no lane on this tab is active (not retired, not a baseline, with a bet or an open pick on its current record).")}</p>'
                     f'{table}{parts_err}<p class="sm mut">Its page is still built: <a href="./{_esc(tab)}.html">{_esc(label)}</a>. '
                     'It returns to the top nav on the first run after one of its lanes logs a pick.</p></details>')
    return ('<section id="archived-tabs"><h2>Archived tabs</h2>'
            '<p class="sm mut">A sport tab with no active lane (not retired, not a baseline, with a bet or an open pick on its '
            'current record) leaves the top nav, checked on every build. Nothing is retired or deleted by it.</p>'
            + "".join(parts) + "</section>")


def load(path=PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def archived(path=PATH):
    """The tabs the last check archived (empty when no check has been written: then every tab shows)."""
    return {k for k, v in (load(path).get("tabs") or {}).items() if v.get("archived")}


def main(argv=None):
    prev = load()
    tabs = check(previous=prev)
    blob = dict(generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                rule="active = not retired, not a baseline, a bet or an open pick in its current record window", tabs=tabs)
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=1, sort_keys=True)
    os.replace(tmp, PATH)
    for k, v in tabs.items():
        print(f"{k:14s} {'ARCHIVED since ' + v['since'] if v['archived'] else str(len(v['active'])) + ' active'}"
              + (f"  (check failed, kept: {v['error']})" if v["error"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
