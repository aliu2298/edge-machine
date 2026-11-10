"""The Flip Side "Every Positive Setting" lanes (flipf1v2.py, flipf2v2.py, flipf3v2.py): one class, one instance each.

Each lane takes one flip strategy's trade exactly (flipside_v2.flip(w, STRAT)) and bets a window ONLY when every one
of its settings is in its market's frozen allow-list (allowgate.allowed). The lane module supplies the version, the
allow-list and its registered fingerprint, the start, the in-sample line and a settings(w) function that reads only
quotes from before the entry. A filter over the v1 hour shards; written to data/<name>_ledger.json by swing15.yml.
"""
import datetime as dt
import os
import sys

import allowgate as G
import flipside_v2 as F
import swing15 as W


class FlipEPS:
    REVIEW_AT, DECIDE_AT = 30, 100

    def __init__(self, name, version, label, strat, allow, allow_sha256, start, in_sample, settings, comp_label):
        self.NAME, self.VERSION, self.LABEL, self.STRAT = name, version, label, strat
        self.ALLOW, self.ALLOW_SHA256, self.FROM, self.IN_SAMPLE = allow, allow_sha256, start, in_sample
        self.MARKETS, self._settings, self.COMP_LABEL = tuple(allow), settings, comp_label
        self.PATH = os.path.join(W.ROOT, "data", f"{name}_ledger.json")

    def fingerprint(self, allow=None):
        return G.fingerprint(allow or self.ALLOW)

    def flip_entry(self, w):
        f = F.flip(w, self.STRAT)
        return None if not f or "skip" in f else f

    def settings(self, w):
        f = self.flip_entry(w)
        return self._settings(w, f) if f else None

    def allowed(self, w):
        return G.allowed(self.ALLOW, w.get("series"), self.settings(w))

    def in_record(self, w, start=None):
        return W._ts(w["open"]) >= W._ts(start or self.FROM) and w.get("series") in self.MARKETS

    def records(self, state, start=None):
        """{"lane": {"all", "series"}, "every": {"all", "series"}}: the filtered lane and the old flip on the same
        markets over the same windows."""
        out = {}
        for key, gate in (("lane", self.allowed), ("every", lambda w: True)):
            by = {m: [] for m in self.MARKETS}
            for w in (state.get("windows") or {}).values():
                if not self.in_record(w, start):
                    continue
                f = self.flip_entry(w)
                if f and gate(w):
                    by[w["series"]].append((w["day"], w["open"], f["won"], f["price"], f["roi"]))
            out[key] = dict(all=F._cell([r for rs in by.values() for r in rs]),
                            series={m: F._cell(rs) for m, rs in by.items()})
        return out

    def entries(self, state, start=None):
        rows = []
        for w in (state.get("windows") or {}).values():
            if self.in_record(w, start) and self.allowed(w):
                f = self.flip_entry(w)
                rows.append(dict(at=w["open"], market=w["series"], settings=self.settings(w), side=f["side"],
                                 price=f["price"], won=f["won"], roi=f["roi"]))
        return sorted(rows, key=lambda r: r["at"], reverse=True)

    def ledger(self, state, now=None):
        now = now or dt.datetime.now(dt.timezone.utc)
        slim = lambda c: None if not c else {k: c[k] for k in ("n", "hits", "hit_rate", "fair", "mean_roi", "z", "days")}
        rec = self.records(state)
        return dict(version=self.VERSION, **{"from": self.FROM}, allow=self.ALLOW, allow_sha256=self.fingerprint(),
                    never=G.never(self.ALLOW), in_sample=self.IN_SAMPLE, updated=now.isoformat(timespec="seconds"),
                    records={k: dict(all=slim(v["all"]), series={m: slim(c) for m, c in v["series"].items()})
                             for k, v in rec.items()},
                    entries=self.entries(state)[:100])

    def main(self):
        if self.fingerprint() != self.ALLOW_SHA256:
            sys.exit(f"the {self.VERSION} allow-list changed after registration: add a NEW version, never edit this one")
        now = dt.datetime.now(dt.timezone.utc)
        start = dt.datetime.fromisoformat(self.FROM).astimezone(W.ET).date()
        days = {(start + dt.timedelta(days=i)).isoformat()
                for i in range(max(0, (now.astimezone(W.ET).date() - start).days) + 1)}
        blob = self.ledger(W.load(days=days), now)
        W._write(self.PATH, blob)
        print(self.VERSION, {k: (v["all"] or {}).get("n", 0) for k, v in blob["records"].items()})
        return 0


def expose(lane, g):
    """Module-level names for a lane module (what eps_card and the tests read)."""
    for k in ("NAME", "VERSION", "LABEL", "STRAT", "ALLOW", "ALLOW_SHA256", "FROM", "IN_SAMPLE", "MARKETS", "PATH",
              "REVIEW_AT", "DECIDE_AT", "COMP_LABEL"):
        g[k] = getattr(lane, k)
    for k in ("fingerprint", "flip_entry", "settings", "allowed", "in_record", "records", "entries", "ledger", "main"):
        g[k] = getattr(lane, k)
