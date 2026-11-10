"""NBA win margin BUCKET PRIORITY, bp-v2 (id wm_bucket_priority; table frozen 2026-11-09, Olu; tentative, in-sample; bp-v2 "kept" rule 2026-11-10).

Two Production lanes trade the same Kalshi win margin contracts: the YES split (lane nba_winmargin_live, versions wm-yes-*) and the NO fade
(lane nba_wm_nofade, versions wm-nofade-*). A collision is a contract on which both lanes' entry rules pass at the decision time. The
executor lets one side take it and cedes the other, by this frozen table:

    bucket 1-5    YES wins        bucket 6-10   NO wins        bucket 11-20   YES wins        21+ has no YES lane (unchanged)

How a ceded row is known: the executor writes it to its decision snapshot (data/nba_wm_decisions.json) as a decision with
outcome == "ceded", rule_ok true, `ceded_to` (the winning lane's version) and `why`. The records are read from THOSE decisions, never from
a date, so every night before the rule stays exactly as it was graded. nba_wm_v3.run (shared by the version 3 and 4 ledgers) leaves a ceded
decision out of the replay and files it under state["ceded"]; a ceded row is therefore never a win or a loss and is outside n, ROI, z and
the halves of its lane. It is counted here and shown beside the table.

bp-v2 (2026-11-10): in the 6-10 bucket YES cedes only if NO can trade the market right then (a NO plan and NO's own ask check). Otherwise YES KEEPS
the market: the executor logs "kept", and YES trades it under its own rule, so a kept row IS graded as a normal YES entry. It is only counted
(state["kept"], from decisions flagged kept / outcome "kept") so the review can see how often the NO side could not fill.

Review: once a band has 20 or more NO fills and 30 or more YES entries, the table is read again against what each side earned there.
"""
import html as _h

PRIORITY = {"1-5": "yes", "6-10": "no", "11-20": "yes"}      # bucket label (the ledgers' "1-5") -> the side that keeps the contract
BP_ID, BP_VERSION = "wm_bucket_priority", "bp-v2"
NAME = "Bucket Priority"
FROZEN_ON = "2026-11-09"
STATUS = "tentative, in-sample"
REVIEW_MIN_NO_FILLS, REVIEW_MIN_YES_ENTRIES = 20, 30
YES_LANE, NO_LANE = "nba_winmargin_live", "nba_wm_nofade"
LANE_SIDE = {YES_LANE: "yes", NO_LANE: "no"}
OUTCOME = "ceded"
KEPT_OUTCOME = "kept"


def bucket_label(ticker):
    """"1-5", "6-10", "11-20", "21+" from a ticker such as KXNBAWINMARGIN-26NOV08ATLWAS-ATL1TO5, or None."""
    import re
    m = re.search(r"-[A-Z]{3}(\d+)(TO(\d+)|PLUS)?$", str(ticker or ""))
    if not m:
        return None
    return f"{m.group(1)}-{m.group(3)}" if m.group(3) else f"{m.group(1)}+"


def winner(bucket):
    """"yes" or "no": the side that keeps a contested contract in this bucket; None where there is no table entry (21+)."""
    return PRIORITY.get(bucket)


def is_ceded(d):
    return (d or {}).get("outcome") == OUTCOME


def ceded_records(decisions, take=None):
    """{decision key: compact public record} for every decision the executor ceded; `take` filters by decision (a ledger's version)."""
    out = {}
    for k, d in (decisions or {}).items():
        if is_ceded(d) and (take is None or take(d)):
            out[k] = dict(key=k, lane=d.get("lane"), ticker=d.get("ticker"), event=d.get("event"), bucket=bucket_label(d.get("ticker")),
                          tip=d.get("tip"), ceded_to=d.get("ceded_to"), why=d.get("why"), bot_version=d.get("bot_version"),
                          bucket_priority=d.get("bucket_priority") or BP_VERSION)
    return out


def is_kept(d):
    """bp-v2: YES kept a 6-10 market NO could not fill. The decision ends as an entry flagged kept (the transient outcome is "kept")."""
    d = d or {}
    return d.get("outcome") == KEPT_OUTCOME or d.get("kept") is True


def kept_records(decisions, take=None):
    """{decision key: compact public record} for every decision YES kept; a kept row is traded and graded, this only counts it."""
    out = {}
    for k, d in (decisions or {}).items():
        if is_kept(d) and (take is None or take(d)):
            out[k] = dict(key=k, lane=d.get("lane"), ticker=d.get("ticker"), event=d.get("event"), bucket=bucket_label(d.get("ticker")),
                          tip=d.get("tip"), kept_why=d.get("kept_why") or d.get("why"), bot_version=d.get("bot_version"),
                          bucket_priority=d.get("bucket_priority") or BP_VERSION)
    return out


def kept_count(*states):
    """Kept rows over ledger states (state["kept"]); a state without the field counts zero."""
    return sum(len((s or {}).get("kept") or {}) for s in states)


def ceded_set(decisions, take=None):
    """{(lane, ticker)} the executor ceded, from the decision records."""
    return {(r["lane"], r["ticker"]) for r in ceded_records(decisions, take).values()}


def counts(*states):
    """{lane: ceded rows} over ledger states (each carries state["ceded"]); a state without the field counts zero."""
    out = {YES_LANE: 0, NO_LANE: 0}
    for s in states:
        for r in ((s or {}).get("ceded") or {}).values():
            if r.get("lane") in out:
                out[r["lane"]] += 1
    return out


def table_text():
    return ", ".join(f"{b} {PRIORITY[b].upper()}" for b in PRIORITY)


def note_html(*states):
    """The small public note: the table, its status, the review rule and each lane's ceded count."""
    c = counts(*states)
    e = _h.escape
    return (f'<p class="sm bucket-priority-note"><b>{e(NAME)} {e(BP_VERSION)}.</b> When both lanes want the same contract, one steps aside: '
            f'{e(table_text())} (21+ has no YES lane). {e(STATUS.capitalize())}, set {e(FROZEN_ON)}; it is read again once a band has '
            f'{REVIEW_MIN_NO_FILLS}+ NO fills and {REVIEW_MIN_YES_ENTRIES}+ YES entries. '
            f'YES split: {c[YES_LANE]} ceded to the other lane, not graded. NO fade: {c[NO_LANE]} ceded to the other lane, not graded. '
            f'6-10 kept by YES because NO could not fill ({e(BP_VERSION)}): {kept_count(*states)}, traded and graded as normal YES entries.</p>')
