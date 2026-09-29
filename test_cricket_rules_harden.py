"""Hardening of the Kalshi cricket rules-text check.

Each assertion below fails on main at 7dd4de4, where the named sentence still
verifies, and passes once a doubtful sentence is left unverified.
"""
import json
import os
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone

import sandbox_sources as S

FAILS = []


def ok(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILS.append(msg)


def eq(a, b, msg):
    ok(a == b, f"{msg} (got {a!r}, want {b!r})")


_fx = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
with open(os.path.join(_fx, "sample_kalshi_cricket_milestones.json")) as _f:
    _ms = json.load(_f)
with open(os.path.join(_fx, "sample_kalshi_cricket_event.json")) as _f:
    _ev = json.load(_f)

IND = "KXT20MATCH-26OCT010030SRIIND"
START = datetime(2026, 10, 1, 4, 30, tzinfo=timezone.utc)
BEFORE = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
AGREE = _ev["markets"][0]["rules_primary"]


def _row():
    return dict(sport="cricket", venue="kalshi", market_id=IND, side_a="A", side_b="B",
                label="A vs B", price_a=0.4, price_b=0.6, start="2026-10-01T05:30:00+00:00",
                date="2026-10-01", tradeable={"a": True, "b": True}, untraded=False,
                volume=0.0, url="")


def _comp(extra):
    return AGREE.replace("Asian Games Men", extra, 1)


def _side_a(name):
    return AGREE.replace("If India wins the India vs", f"If {name} wins the {name} vs", 1)


def _side_b(name):
    return AGREE.replace("Sri Lanka", name, 1)


def _unverified(text, why):
    out, _ = S.apply_kalshi_cricket_starts(
        [_row()], milestones=_ms, rules={IND: [text]}, now=BEFORE)
    eq(out[0].get("start_source"), None, why)


def _verified(text, why):
    out, _ = S.apply_kalshi_cricket_starts(
        [_row()], milestones=_ms, rules={IND: [text]}, now=BEFORE)
    eq(out[0].get("start_source"), "kalshi_milestone", why)


print("\n1. deny-list words joined by hyphens or apostrophes")
for word in ("re-scheduled", "post'poned", "resched-uled", "Re-Scheduled", "POST'PONED",
             "de-layed", "deferred", "brought forward", "put back", "pushed",
             "brought-forward", "put-back"):
    _unverified(_comp(f"Cup {word}"),
                f"{word!r} in the competition stays unverified")
_unverified(_side_a("re-scheduled"),
            "re-scheduled as team A stays unverified")
_unverified(_side_b("post'poned"),
            "post'poned as team B stays unverified")
_unverified(_comp("resched-uled Cup"),
            "resched-uled in the competition stays unverified")

print("\n2. times written as words")
for word in ("noon", "midnight", "three PM IST", "(Later)", "tonight",
             "mid-night", "to-night", "AM", "PM", "(AM)", "(PM)",
             "EDT", "EST", "ET", "IST", "GMT", "UTC", "BST", "AEST", "PKT", "SLST", "NPT"):
    _unverified(_comp(f"Cup {word}"),
                f"{word!r} in a name stays unverified")
_unverified(_side_a("noon"), "noon as team A stays unverified")
_unverified(_side_b("midnight"), "midnight as team B stays unverified")
for n in ("one", "two", "three", "four", "five", "six",
          "seven", "eight", "nine", "ten", "eleven", "twelve"):
    for tail in ("o'clock", "AM", "PM"):
        _unverified(_comp(f"Cup {n} {tail}"),
                    f"{n} {tail} in a name stays unverified")

print("\n3. team A equals team B")
_unverified(AGREE.replace("If India wins the India vs Sri Lanka",
                          "If India wins the India vs India"),
            "India vs India, the same team as written, stays unverified")
_unverified(AGREE.replace("If India wins the India vs Sri Lanka",
                          "If India wins the India vs india"),
            "India vs india, the same team by case, stays unverified")
_unverified(AGREE.replace("If India wins the India vs Sri Lanka",
                          "If fi wins the fi vs \ufb01"),
            "fi vs the fi ligature, the same team after NFKC, stays unverified")

print("\n4. raw length before NFKC or the category scan")
_calls = []
_real_norm, _real_cat = unicodedata.normalize, unicodedata.category


def _norm(*a, **k):
    _calls.append("normalize")
    return _real_norm(*a, **k)


def _cat(*a, **k):
    _calls.append("category")
    return _real_cat(*a, **k)


unicodedata.normalize = _norm
unicodedata.category = _cat
try:
    _spaces = S._rules_sentence(" " * 601, START)
finally:
    unicodedata.normalize = _real_norm
    unicodedata.category = _real_cat
eq(_spaces, False, "601 spaces are refused on the raw length, before they collapse")
ok(not _calls,
   "an oversized rules_primary does not reach NFKC or the category scan"
   f" (got {len(_calls)} unicodedata calls)")

print("\n5. ReDoS timing in a subprocess with a 10s timeout")
_timing = r"""
import json, sys, time, unicodedata
sys.path.insert(0, sys.argv[1])
import sandbox_sources as S
from datetime import datetime, timezone
START = datetime(2026, 10, 1, 4, 30, tzinfo=timezone.utc)
data = json.load(sys.stdin)
failed = []
for label, text in data["cases"]:
    t0 = time.perf_counter()
    S._rules_sentence(text, START)
    dt = time.perf_counter() - t0
    print(f"TIME {label} {dt:.4f}s", flush=True)
    if dt >= 0.1:
        failed.append(label)
calls = []
real_n, real_c = unicodedata.normalize, unicodedata.category
def n(*a, **k):
    calls.append("n")
    return real_n(*a, **k)
def c(*a, **k):
    calls.append("c")
    return real_c(*a, **k)
unicodedata.normalize, unicodedata.category = n, c
over = S._rules_sentence("x" * 500000, START)
print(f"OVERSIZE result={over!r} unicodedata_calls={len(calls)}", flush=True)
if over is not False or calls:
    failed.append("oversize")
sys.exit(1 if failed else 0)
"""
_fill = "ab1 "
_head = "If India wins the India vs Sri Lanka men's professional "
_tail = (" cricket match originally scheduled for Oct 1, 2026 at 12:30 AM EDT, "
         "then the market resolves to Yes.")
_n = (590 - len(_head) - len(_tail)) // len(_fill)
_rem = 590 - len(_head) - len(_tail) - _n * len(_fill)
_chars590 = _head + _fill * _n + ("x" * _rem) + _tail
_tok100 = _head + " ".join(["ab1"] * 100) + _tail
_root = os.path.dirname(os.path.abspath(__file__))
try:
    _proc = subprocess.run(
        [sys.executable, "-c", _timing, _root],
        input=json.dumps({"cases": [
            [f"100 ab1 tokens ({len(_tok100)} chars)", _tok100],
            ["590-char near-miss", _chars590],
        ]}),
        timeout=10, capture_output=True, text=True,
    )
except subprocess.TimeoutExpired as _exc:
    _out = (_exc.stdout or b"")
    if isinstance(_out, bytes):
        _out = _out.decode("utf-8", "replace")
    print(_out)
    ok(False, "the ReDoS timing subprocess hung past 10s and counts as a FAIL")
else:
    print(_proc.stdout, end="" if _proc.stdout.endswith("\n") or not _proc.stdout else "\n")
    if _proc.returncode != 0 and _proc.stderr:
        print(_proc.stderr[-500:])
    ok(_proc.returncode == 0,
       "the timing subprocess finished under 10s and refused oversized text before any scan")

print("\n6. stems, time words, and spelled numbers that still verified")
for word in ("postponement", "reschedule", "delay", "delays", "revised", "changed",
             "shifted", "evening", "hours", "(Delay)"):
    _unverified(_comp(f"Cup {word}"),
                f"{word!r} in the competition stays unverified")
_unverified(_comp("Cup fifteen hundred hours"),
            "'fifteen hundred hours' in the competition stays unverified")
for word in ("one", "two", "three", "four", "five", "six",
             "seven", "eight", "nine", "ten", "eleven", "twelve",
             "hundred", "thousand"):
    _unverified(_comp(f"Cup {word}"),
                f"the spelled number {word!r} in the competition stays unverified")

print("\n7. 'new' is a name; 'new time', 'new date' and 'new start' are not")
_verified(_side_a("New Zealand"),
          "New Zealand vs Sri Lanka still verifies")
_verified(_comp("New South Wales"),
          "a New South Wales competition still verifies")
_verified(_side_a("Newcastle"),
          "Newcastle vs Sri Lanka still verifies")
for phrase in ("new time", "new date", "new start"):
    _unverified(_comp(f"Cup {phrase}"),
                f"{phrase!r} in the competition stays unverified")

print()
if FAILS:
    print(f"FAILED: {len(FAILS)}")
    sys.exit(1)
print("all cricket rules hardening tests passed")
