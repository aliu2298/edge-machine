#!/usr/bin/env python3
"""A refused tour logged into a filtered lane after the new code is a warning.

NEW_CODE_SINCE is the first tracker run on the tour filter. A refused row
logged earlier is the old tracker and is not a hit. The five fixture cases
use a synthetic ledger. The live section only checks that the audit can read
the real ledger; it does not pin how many refused rows that ledger holds.
"""
import inspect

import sandbox_audit as A
import sandbox_track as T

FAILS = []
BEFORE = "2026-10-02T16:35:50+00:00"
# The same instant as NEW_CODE_SINCE. The ledger writes +00:00, the cutoff
# is spelled with Z, and the two are one instant.
AFTER = "2026-10-02T16:35:51+00:00"


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


def single(id, source, mid, logged, tier, sport="tennis"):
    return dict(id=id, source=source, sport=sport, bet=True, venue="kalshi",
                market_id=mid, pick="a", price=0.78, tier=tier, logged=logged,
                status="open", stake=100.0)


def basket(id, source, sport, logged, legs):
    return dict(id=id, source=source, sport=sport, bet=True, venue="combo",
                market_id=id.split(":", 1)[-1], pick="a", price=0.50,
                logged=logged, status="open", stake=100.0, legs=legs)


def leg(mid):
    """A basket leg as the tracker stores it: no tier field, tour read off the id."""
    return dict(market_id=mid, pick="a", venue="kalshi", name="Player",
                start=AFTER)


def fixture():
    """(a) before the cutoff, (b) a refused single, (c) a refused basket leg,
    (d) a kept tour, (e) a lane the filter does not run on."""
    kept = leg("aec-atp-aa-bb-2026-10-02")
    refused = leg("aec-wta-cc-dd-2026-10-02")
    return {
        "quotes": [
            single("pre", "tennis_fav_band_3h", "aec-wta-old-bb-2026-10-02",
                   BEFORE, "wta"),
            single("single", "tennis_fav_band_3h", "aec-wta-new-bb-2026-10-02",
                   AFTER, "wta"),
            basket("basket", "tennis_combo2", "tennis_combo", AFTER,
                   [kept, refused]),
            basket("pm4", "pm_combo4", "tennis_pmcombo", AFTER,
                   [kept, leg("aec-itfme-ee-ff-2026-10-02")]),
            single("kept", "tennis_fav_band_3h", "aec-atp-new-bb-2026-10-02",
                   AFTER, "atp"),
            basket("kept-basket", "pm_combo2", "tennis_pmcombo", AFTER,
                   [kept, leg("aec-wtadb-gg-hh-2026-10-02"),
                    leg("aec-utr-ii-jj-2026-10-02")]),
            single("other", "tennis_fav_band", "aec-wta-parent-bb-2026-10-02",
                   AFTER, "wta"),
        ],
        "_archive": [
            single("archived", "tennis_fav_band_3h", "aec-atpch-arch-bb-2026-10-02",
                   AFTER, "atpch"),
        ],
    }


print("refused-tour tripwire")
eq(getattr(A, "NEW_CODE_SINCE", None), "2026-10-02T16:35:51Z",
   "the cutoff is the first tracker run on the new code")

fx = fixture()
ids = {q.get("id") for q in A.refused_tour_rows(fx)}
ok("pre" not in ids, "(a) a refused row logged before the cutoff is not a hit")
ok("single" in ids, "(b) a refused single after the cutoff is a hit")
ok("basket" in ids and "pm4" in ids,
   "(c) a basket with one refused leg after the cutoff is a hit, "
   "including pm_combo4")
ok("kept" not in ids and "kept-basket" not in ids,
   "(d) a kept-tour row after the cutoff is not a hit")
ok("other" not in ids, "(e) a non-filtered lane with a refused tour is not a hit")
ok("archived" in ids, "a refused single that has been archived is still a hit")
eq(ids, {"single", "basket", "pm4", "archived"},
   "the fixture hits are only the refused rows on or after the cutoff")

check = getattr(A, "check_refused_tours", None)
if check is None:
    ok(False, "the audit warns when a filtered lane logs a refused tour")
else:
    rep = A.Report()
    check(fx, rep)
    warned = [m for c, m in rep.warnings if c == "tours"]
    erred = [m for c, m in rep.errors if c == "tours"]
    blob = "\n".join(warned)
    ok(not erred, "a refused-tour hit is a warning, not an error")
    ok("single" in blob and "tennis_fav_band_3h" in blob,
       "the warning names the refused single and its lane")
    ok("basket" in blob and "pm4" in blob,
       "the warning names each refused basket and its lane")
    ok("pre" not in blob and "kept" not in blob and "other" not in blob,
       "a miss is not listed in the warning")
    clean = {"quotes": [q for q in fx["quotes"] if q["id"] in ("pre", "kept", "other")]}
    quiet = A.Report()
    check(clean, quiet)
    ok(not quiet.warnings and not quiet.errors and quiet.passed,
       "a fixture with no hit passes the check")

wired = "check_refused_tours" in inspect.getsource(A.run)
ok(wired, "the audit runs the refused-tour check")

print("\nlive ledger, count not pinned")
try:
    live = T.load()
    found = A.refused_tour_rows(live)
    ok(isinstance(found, list), "the tripwire reads the live ledger")
except Exception as exc:
    found = None
    ok(False, f"the tripwire reads the live ledger — {type(exc).__name__}: {exc}")
else:
    print(f"  live refused-tour rows at or after the cutoff: {len(found)}")

try:
    audit = A.run(network=False)
    ok(isinstance(audit, A.Report), "the audit runs on the live ledger")
    ok(not any(c == "tours" for c, _ in audit.errors),
       "a live refused-tour hit does not fail the audit")
except Exception as exc:
    ok(False, f"the audit runs on the live ledger — {type(exc).__name__}: {exc}")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'refused-tour tripwire passed'}")
for item in FAILS:
    print(f"  - {item}")
raise SystemExit(1 if FAILS else 0)
