#!/usr/bin/env python3
"""Offline checks for the 2026-11-06 retirement (Olu): the Econ Daily near-certain 3h NO lane (econ_nc_no). It was in Production
2026-10-20 to 2026-10-28 and paper after; it was never traded live after the move. No new entries; its rows stay and its open bets still
settle. Econ Daily's near-certain YES lane and the S&P near-certain NO lane (Finance Daily) stay."""
import datetime as dt
import html
import re
import sys

import daily_build as DB
import daily_production as DP
import daily_track as D
import finance_nc as FN
import sandbox_audit
import sandbox_build as B
import sandbox_sources as S

FAILS = []
UTC = dt.timezone.utc


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


print("the registry: retired with a dated record, rows still settle")
m = S.SOURCES["econ_nc_no"]
check("no live scope, retired on econ_daily", (m["sports"], list(m["retired_sports"])), ([], ["econ_daily"]))
check("the reason carries the date and the record", all(x in S.ECON_NC_NO_RETIRED_WHY for x in ("Retired 2026-11-06", "18 won v 18.1 priced", "−1.6%")), True)
check("its stored rows are not removed rows", S.removed_row(dict(source="econ_nc_no", sport="econ_daily")), False)
check("econ_nc_yes is untouched", (S.SOURCES["econ_nc_yes"]["sports"], "retired_sports" in S.SOURCES["econ_nc_yes"]), (["econ_daily"], False))
check("the S&P near-certain NO lane is untouched", (FN.KEY, "retired" in S.SOURCES.get(FN.KEY, {})), (FN.KEY, False))
check("the stamp-of-approval table tags it retired", B.source_retired("econ_nc_no"), True)

print("\nthe tracker: nothing new for the retired lane, the other lane still logs, open bets still settle")
check("the retired map", D.NC_RETIRED, {"econ_nc_no": "2026-11-06"})
NOW = dt.datetime(2026, 11, 6, 20, 0, tzinfo=UTC)
calls = []


def fake(path, *a, **k):
    calls.append(path)
    raise RuntimeError("offline")


state = D.load()
before = {k: len(v["picks"]) for k, v in (state.get("nc") or {}).items()}
state = D.nc_run(state, fake, NOW)
after = {k: len(v["picks"]) for k, v in state["nc"].items()}
check("no pick added to the retired lane by a run", after.get("econ_nc_no"), before.get("econ_nc_no", 0))
state["nc"]["econ_nc_no"]["picks"].append(dict(id="KXAAAGASD-26NOV05-T4.000", event="KXAAAGASD-26NOV05", series="KXAAAGASD", name="x", lane="econ_nc_no", side="no",
                                               close="2026-11-06T03:59:00Z", price=0.9, bid=0.89, size=50, yes_bid=0.1, yes_ask=0.11, logged="2026-11-05T21:00:00+00:00", status="open", title="t"))
settled = dict(ticker="KXAAAGASD-26NOV05-T4.000", status="finalized", result="no")


def settle_fetch(path, *a, **k):
    if path.startswith("markets/KXAAAGASD-26NOV05-T4.000"):
        return {"market": settled}
    raise RuntimeError("offline")


state = D.nc_run(state, settle_fetch, NOW + dt.timedelta(hours=1))
row = state["nc"]["econ_nc_no"]["picks"][-1]
check("an open bet on the retired lane still settles", (row["status"], row.get("payout")), ("won", 1))

print("\nthe Econ Daily page: Retired rules, not Production")
page = DB.build("econ_daily", D.load(), NOW)
i = page.find('<section id="retired"')
fold = page[i:page.find("</section>", i)]
text = html.unescape(re.sub(r"<[^>]+>", " ", fold))
check("the retired fold lists the lane with its dated reason", ("Near-certain · 3h · NO" in text, "Retired 2026-11-06 by Olu" in text), (True, True))
above = page[:i]
check("the lane is not above the fold as a Production or Sandbox rule", 'data-source="econ_nc_no"' in above and "Production · paper record" in re.sub(
    r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", above[above.find('data-source="econ_nc_no"'):above.find('data-source="econ_nc_no"') + 3000]))), False)
check("no row says Production for it", "Production · paper record" in fold, False)
check("the page scope says the NO lane is retired", "NO retired" in page and "NO paper" not in page, True)
check("the near-certain YES lane is still the Production rule", "Near-certain · last hour · YES" in page[:i], True)

print("\nthe feed: still only the YES lane is published (the NO lane was pulled 2026-10-28)")
check("published near-certain lanes", DP.NC_PUBLISHED, ("econ_nc_yes",))

print("\npublic copy")
check("the reason passes the copy guard", bool(sandbox_audit.COPY_RE.search(S.ECON_NC_NO_RETIRED_WHY)), False)

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("ALL PASS")
