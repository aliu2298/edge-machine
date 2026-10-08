#!/usr/bin/env python3
"""The tennis rules are frozen (2026-10-08).

Band, window, tours, construction and the registration text of the seven live
tennis rules are pinned here. A change to any of them fails this test on
purpose: after the freeze a change does not edit a rule, it retires the rule
and starts a new one under a new name, with its own registration and clock.
"""
import hashlib
import sys
from datetime import timedelta

import sandbox_sources as S

FAILS = []


def ok(cond, msg):
    print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        FAILS.append(msg)


def eq(got, want, msg):
    ok(got == want, msg if got == want else f"{msg} — got {got!r}, want {want!r}")


FROZEN = "2026-10-08"
RULES = ("tennis_fav_band_3h",
         "tennis_combo2", "tennis_combo3", "tennis_combo4",
         "pm_combo2", "pm_combo3", "pm_combo4")
LINE = ("FROZEN 2026-10-08: no further changes to band, window, tours or construction "
        "until the planned read; a change after this date retires the rule and starts a new one.")

# The parameters every frozen rule reads, as registered on the freeze date.
PARAMS = {
    "TENNIS_3H_BAND": (0.70, 0.85),
    "TENNIS_FAV_3H": timedelta(hours=3),
    "TENNIS_FAV_KEEP": frozenset({"atp", "wtadb", "utr"}),
    "TENNIS_FAV_KEEP_SINCE": "2026-10-02T16:34:37+00:00",
    "TENNIS_COMBO_BAND_SINCE": "2026-10-04T06:46:57+00:00",
    "COMBO_LEGS": (2, 3, 4),
    "COMBO_MARKUP": {2: 0.0084, 3: 0.0106, 4: 0.0066},
    "PM_COMBO_MARKUP": {2: 0.0269, 3: 0.0339, 4: 0.0427},
    "PM_COMBO_MEASURED": {2: True, 3: False, 4: False},
    "TENNIS_FAV_RESET": frozenset({"tennis_fav_band_3h", "tennis_combo2", "tennis_combo3",
                                   "tennis_combo4", "pm_combo2", "pm_combo3"}),
    "TENNIS_COMBO_RESET": frozenset({"tennis_combo2", "tennis_combo3", "tennis_combo4",
                                     "pm_combo2", "pm_combo3"}),
}

# sha256 of each registration as it read on the freeze date: label, markets,
# the current definition (with the FROZEN line) and the dated change entries.
# Regenerate ONLY when registering a new rule, never to let a frozen one move.
DIGESTS = {
    "tennis_fav_band_3h": "4c73ce0eea903a62b96bdcb70334889d73d02351f9ed46c5a06d4d153eddec72",
    "tennis_combo2": "ffe994e4bd29275847dda25eaadcee726144b9aa749000854417ef39cb252b7b",
    "tennis_combo3": "9450fb66ddd36d555719d939c6db444443c39409385da621de1ca8964e6399c7",
    "tennis_combo4": "ed2662d3fb567a205774b53a3eefb23741f7ddb0624932199239cddb701ae4f4",
    "pm_combo2": "806f305829fd217167f915fc39f4692bebb578d8ca2877217822622013c52860",
    "pm_combo3": "814a758662cbf1f5c9d65dc69acf1f341ddf8e1d47ab2a7be734fab9b14a8491",
    "pm_combo4": "e251d4102aa876b4310b489ada53021a789fa4f87b3e3323c3be2df624df3097",
}


def digest(name):
    meta = S.SOURCES[name]
    text = "\n".join([
        str(meta.get("label")), ",".join(meta.get("sports") or []), str(meta.get("kind")),
        str(meta.get("note")), "\n".join(str(c) for c in meta.get("changes") or [])])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


print("frozen set")
eq(S.TENNIS_FROZEN, FROZEN, "the freeze date is 2026-10-08")
eq(sorted(S.TENNIS_FROZEN_RULES), sorted(RULES), "exactly the seven live tennis rules are frozen")
eq(S.TENNIS_FROZEN_LINE, LINE, "the frozen line reads as registered")
for name in RULES:
    meta = S.SOURCES[name]
    eq(meta.get("frozen"), FROZEN, f"{name} registration carries frozen={FROZEN}")
    ok(str(meta.get("note") or "").endswith(LINE), f"{name} definition ends with the FROZEN line")
    ok(meta.get("connected") is True and not meta.get("retired"),
       f"{name} is a live rule (a frozen rule is retired by name, never edited)")
    ok(isinstance(meta.get("changes"), list) and all(isinstance(c, str) and c.strip() for c in meta["changes"]),
       f"{name} keeps its dated changes as a list of entries")
    ok(all("20" in c[:40] and any(ch.isdigit() for ch in c[:40]) for c in meta["changes"]),
       f"{name} every change entry is dated near its start")
    ok("TENNIS_COMBO_BAND_SINCE" not in meta["note"]
       and all("TENNIS_COMBO_BAND_SINCE" not in c for c in meta["changes"]),
       f"{name} shows the combo clock as a time, not a constant name")

print("\nparameters")
for key, want in PARAMS.items():
    eq(getattr(S, key, None), want, f"{key} is frozen at {want!r}")

print("\nregistration text")
for name in RULES:
    got = digest(name)
    want = DIGESTS.get(name)
    ok(want is not None, f"{name} has a pinned registration digest")
    eq(got, want, f"{name} registration text is unchanged since the freeze "
                  f"(a change after {FROZEN} retires the rule and starts a new one)")

if FAILS:
    print(f"\nFAILED {len(FAILS)}")
    sys.exit(1)
print("\nPASSED")
