"""Live baskets must not consume verified legs with estimated or out-of-window starts."""
from datetime import datetime, timedelta, timezone
import sandbox_sources as S
import production as P

now = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)

def leg(suffix, hours, source="tennisexplorer"):
    start = now + timedelta(hours=hours)
    return dict(market_id="KXATPMATCH-26OCT12" + suffix, venue="kalshi",
                sport="tennis", side_a=suffix + " A", side_b=suffix + " B",
                start=start.isoformat(), date="2026-10-12", start_source=source,
                price_a=.75, price_b=.27, untraded=False)

rows = [leg("UNKNOWN", .5, None), leg("GOOD1", 1), leg("LATE", 3.01),
        leg("STARTED", 0), leg("GOOD2", 3)]
universe = {"tennis": rows}
pool = S.combo_legs_by_day(universe, now=now)
assert [r["market_id"] for r, _, _ in pool["2026-10-12"]] == [
    rows[1]["market_id"], rows[4]["market_id"]]
baskets = S.tennis_combo_rows(universe, now=now)
assert len(baskets) == 1
assert [r["market_id"] for r in baskets[0]["legs"]] == [
    rows[1]["market_id"], rows[4]["market_id"]]
assert P.start_verified(baskets[0])
assert baskets[0]["start"] == rows[1]["start"]
assert all(r["start_source"] == "tennisexplorer" for r in baskets[0]["legs"])
assert S.tennis_combo_rows({"tennis": rows[:2]}, now=now) == []
assert S.tennis_combo_rows(universe, now=now, used={2: {rows[1]["market_id"]}}) == []
assert rows[0]["start_source"] is None  # no retroactive verification or mutation
print("PASS: verified live window, boundary, pairing, insufficient legs and used-leg guard")
