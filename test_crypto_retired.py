#!/usr/bin/env python3
"""crypto_eth_fav_both and crypto_sol_fav_both are retired (Olu, 2026-10-31) and shown on the Crypto page.

They were pulled from Production on 2026-10-27 (PAIR_REMOVALS, record kept) and then appeared nowhere on crypto.html.
They stop logging, keep their rows, and sit in the page's Retired fold with their records. The Production crypto
pair and the other Sandbox lanes are untouched."""
import re
import sys

import crypto_build as CB
import sandbox_sources as S
import sandbox_track as T

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


BOTH = ("crypto_eth_fav_both", "crypto_sol_fav_both")
print("the lanes")
for lane in BOTH:
    m = S.SOURCES[lane]
    check(f"{lane}: nothing left to fetch, scope retired with a dated reason",
          (m["sports"], list(m["retired_sports"])), ([], ["crypto_fav"]))
    why = m["retired_sports"]["crypto_fav"]
    check(f"{lane}: the reason names the Production pull and the retirement date",
          all(w in why for w in ("pulled from Production 2026-10-27", "Retired 2026-10-31")), True)
    check(f"{lane}: the reason is accurate for this lane",
          ("lost live (3-4, -36.2%)" in why) if "eth" in lane else
          ("3-1, +4.1% over 4 market-days, too small to read" in why and "retired with the ETH twin" in why and "lost live" not in why), True)
    check(f"{lane}: the Production removal keeps its record", T.PAIR_REMOVALS[f"{lane}|crypto_fav"],
          dict(removed_on="2026-10-27", keep_record=True))
check("the live crypto lanes still fetch", all(S.SOURCES[n]["sports"] == ["crypto_fav"] for n in
                                               ("crypto_fav_band", "crypto_fav_band_below", "crypto_fav_band_60", "crypto_fav_band_below_60")), True)
check("the Production crypto pair is still moved on 2026-10-20",
      T.PAIR_OVERRIDES["crypto_fav_band_below|crypto_fav"]["moved_on"], "2026-10-20")

print("the page")
d, st = T.load(), T.load_stages()
html = CB.build(d, st)
retired = html.split('id="retired"', 1)[1] if 'id="retired"' in html else ""
check("the page has a Retired fold", "Retired rules" in html and bool(retired), True)
text = re.sub(r"<[^>]+>", " ", retired)
check("both lanes are in it, with their records", all(n in text for n in ("ETH favourite, both sides", "SOL favourite, both sides")), True)
check("their record is shown (won-lost and ROI)", len(re.findall(r"\d+[–-]\d+", text)) >= 2 and "%" in text, True)
check("each lane's own reason is on the page", "lost live (3-4, -36.2%)" in html and "too small to read" in html, True)
live = html.split('id="retired"', 1)[0]
check("neither lane is in the live list", "both sides" not in re.sub(r"<[^>]+>", " ", live.split('id="rules"', 1)[-1]), True)
check("the live lanes are", all(n in html for n in ("Favourite band, below", "Favourite band 60")), True)
check("their rows stay on file", all(sum(q["source"] == n for q in d["quotes"]) > 0 for n in BOTH), True)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
