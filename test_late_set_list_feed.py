"""late_set / save_feed accept a feed whose leads are a list (o35, NBA win margin), as well as the dict feed."""
import json, os, tempfile
import production as P

fails = 0
def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else f" -- got {got!r}, want {want!r}"))

late = {"id": "x", "pair": "p|s", "route": {"market": "M1"}, "published_late": True, "kickoff": "2026-11-02T00:00:00+00:00"}
check("a list feed is read", sorted(P.late_set({"leads": [late, {"id": "y"}, "junk"]})), ["p|s|M1"])
check("a dict feed still works", sorted(P.late_set({"leads": {"x": late}})), ["p|s|M1"])
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "production_o35_leads.json")
    P.save_feed({"lane": "o35", "leads": [{"id": "a", "ticker": "T"}]}, path)
    check("save_feed writes a list feed", json.load(open(path))["leads"][0]["id"], "a")
    check("no sidecar for a feed with no late lead", os.path.exists(P.late_path(path)), False)
raise SystemExit(1 if fails else 0)
