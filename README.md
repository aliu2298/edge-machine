# Edge Machine

Paper-tracked prediction research. Every signal is logged **before the event**, at the available price, settled on the real result, and judged against a reference.

**Live board:** https://aliu2298.github.io/edge-machine/

## How it works

**Sandbox → Production**

- **Sandbox** records published forecasts and pre-registered rules by source and sport.
- Calls are timestamped at the available price; late calls are rejected.
- Tipsters/rules are tracked at the going price. Probability sources are scored only when they differ by at least 3 percentage points and also receive a Brier score.
- Results are judged against price-implied performance, blind baselines, ROI and closing-line value.
- Records are readable after 30 settled bets.
- **Production is manual:** a pair enters only through `PAIR_OVERRIDES`. It is not promoted automatically.
- Production publishes only feed-expressible leads with verified event times.

## Current pages

- **Sandbox** — active research and performance
- **Production** — selected pairs, status lights and published leads
- **Leads** — upcoming feed-expressible opportunities
- **Record / Streaks / Today** — legacy lanes kept for historical records

## Automation

GitHub Actions runs the research and publishing pipeline:

- `sandbox-tracker.yml` — tests, collect/settle, build and production feed
- `refresh-boards.yml` — refreshes closing prices and GitHub Pages
- `sandbox-close.yml` — frequent closing-price snapshots
- `backup-refresh.yml` — freshness/watchdog backup
- `lane-preflight.yml` — checks public Kalshi league-market availability
- `sandbox-audit.yml` — read-only health and publication audit

An always-on VPS also captures closing prices so scheduled GitHub runs cannot silently create stale CLV data.

## Key files

| File | Purpose |
|---|---|
| `sandbox_sources.py` | Sources, rules and research notes |
| `sandbox_track.py` | Record, settle and score the Sandbox |
| `sandbox_build.py` | Build Sandbox and Production pages |
| `sandbox_close.py` | Closing-price snapshots |
| `production.py` | Production selection, status and leads |
| `lane_preflight.py` | Kalshi league-market preflight |
| `sandbox_audit.py` | Read-only audit |
| `test_*.py` | Automated logic tests |

## Run locally

```bash
python3 sandbox_track.py
python3 sandbox_build.py
python3 lane_preflight.py
python3 sandbox_audit.py
python3 test_sandbox.py
```

Generated pages are rebuilt by Actions; normally commit source/data changes, not generated pages.

## Safety

This repository **does not place bets and holds no exchange credentials**. Secrets are kept out of git. The tracker uses flat $100 paper stakes, rejects ungradable results instead of inventing losses, and keeps the research record append-only/idempotent.

**Research only — not betting advice.**
