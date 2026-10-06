# Edge Machine

Paper-tracked prediction research: every idea is logged at the price that existed, settled on
the real result, and moved up a ladder only when the numbers hold. Nothing in this repo places
bets or holds exchange credentials.

**Board → https://aliu2298.github.io/edge-machine/**

| Page | What it is |
|---|---|
| [Sandbox](https://aliu2298.github.io/edge-machine/sandbox.html) | Every forecaster and rule under test, one row per (source, sport), sorted into working / not working / too early |
| [QA](https://aliu2298.github.io/edge-machine/qa.html) | Pairs that cleared the Sandbox, re-tested before Production |
| [Production](https://aliu2298.github.io/edge-machine/production.html) | The pairs that earned their place, their open leads, and a green or red light each — also published as `data/production_leads.json` |
| [Leads](https://aliu2298.github.io/edge-machine/) | Upcoming fixtures (next 48h) on two lanes: over 1.5, and a side to score 2+ |
| [Record](https://aliu2298.github.io/edge-machine/record.html) · [Streaks](https://aliu2298.github.io/edge-machine/streaks.html) · [Today](https://aliu2298.github.io/edge-machine/today.html) | Earlier lanes, still measured, no longer the focus |

The live pages are the state of the project. This file describes how it works and is kept free
of figures that go stale.

## The ladder

Sandbox asks **"does anyone's signal pay?"** It logs what published forecasters and
pre-registered rules say, stamps each call with the price that existed at that moment, and
settles it on the real result. Each **(source, sport) pair** is judged on its own — a tipster
can be working for MLB and failing for soccer — and climbs **Sandbox → QA → Production**.

**How a call is logged.** Tipsters and rules name a side and are backed every time at the going
price; models, books and exchanges state a probability and are backed only on a 3pp disagreement,
and also get a Brier score. Everything is a flat $100. A price needs a real book (spread ≤ 10¢)
and is booked at the ask. Nothing is logged once a contest has started. Soccer kickoffs come from
ESPN, fight times from Pinnacle, MMA and cricket starts from Kalshi's own milestone feed. Closing
prices are taken in the hour before each start by four writers into `data/sandbox_closes/`, and
only a snapshot within 60 minutes of the deadline counts toward CLV. Bets leave the ledger after
45 days into `data/sandbox_archive/YYYY-MM.json`, so no judgement changes.

**How a pair is judged** — always against a reference, never a bare hit rate: wins against the
wins the prices implied (z); ROI against backing the favourite / underdog / draw on the same
contests, or against a rule's own **population** baseline; and the closing price beside it, never
instead of it. Readable only at 30+ settled bets. Nested ladders (commodities, crypto, soccer
corners) are judged per market-day on money, because a day's rungs are one bet, not eight.

| Gate | Standard sports | Tennis, table tennis |
|---|---|---|
| **Sandbox → QA** | 30+ bets over 14+ days, z ≥ 1, beats every blind rule, profitable without its biggest win | **50+** bets, no day span, **z ≥ 1.5** |
| **QA → ready** | 50+ bets over 28+ days, z ≥ 2, beats every blind rule, profitable without its biggest win, both halves — plus beats the close, profitable after fees, every bet publishable, held 7 days | **50+** bets, no day span, **z ≥ 2.5** |
| **Demoted** | after 30 bets: behind the price or not beating every blind rule; or 21 days without a bet | after **50** bets, same reasons |

**Nothing is promoted automatically.** A pair reaches Production because it is listed by hand in
`PAIR_OVERRIDES`, and that decision is the owner's. The gates above stay because they are the
honest summary of a record, and demotion still uses them. `data/stages.json` records every move.

## Production

`production.py` publishes every bet a Production pair logs after entering Production, in the
Leads ledger's shape, to `data/production_leads.json` — but only bets the feed can express: a
soccer result (home, away or draw) or Yes on a Kalshi soccer goals market in a mapped league, a
tennis, MLB, NFL, MMA, boxing or cricket side, and only with a verified kickoff. Bet shapes are
`match_result`, `total_gte` and `team_gte`.

Two columns keep the gap visible rather than hidden: **Reaches the feed** says how much of a
pair's record the feed could actually express, and **Live** is a green or red light per pair —
red when it is in Production but nothing is getting out, so a silent stall cannot pass for
quiet. The promotion gate still judges the whole record, not the reachable part.

## Pipeline

GitHub Actions builds and publishes everything; a public repo is required for Pages.

* `sandbox-tracker.yml` — every 3h: tests → `sandbox_track` → `sandbox_build` → `production`
* `refresh-boards.yml` — every 3h: the earlier lanes' boards
* `sandbox-close.yml` — every 30 min: closing prices
* `backup-refresh.yml` — hourly: closing prices, and takes the board over if it is stale
* `lane-preflight.yml` — asks Kalshi's public API whether each league lane's series is listed,
  has an empty book, or is open but outside the board's horizon
* `sandbox-audit.yml` — read-only: freshness, coverage, and the phrases the public pages are
  kept free of

An always-on server runs `scripts/local_closes.sh` every 15 minutes (it writes only
`data/sandbox_closes/mac.json` on the Mac, `vps.json` on edge-vps — the writer follows the host) and dispatches a workflow GitHub's scheduler skipped. GitHub
silently drops scheduled runs when it is busy; every run that starts succeeds, so boards are only
delayed — but a closing price has to be taken in the hour before a start, and those were being
missed. Nothing is entered by hand.

## Components

| File | Role |
|---|---|
| `sandbox_sources.py` | One adapter per forecaster, venue, market and rule (`SOURCES`, `CHALLENGERS`). **The research record lives here**: every lane carries a note with its pre-registration, its weak parts, and what has since been retracted. |
| `sandbox_track.py` | Logs every forecast at the price, settles, judges (`assess`), moves pairs between stages |
| `sandbox_build.py` | The Sandbox and QA pages |
| `sandbox_close.py` | Closing prices for bets about to start, one shard per writer |
| `production.py` | Production pairs, their lights, and `data/production_leads.json` |
| `sandbox_audit.py` | Read-only audit of the repo and the published pages |
| `lane_preflight.py` | Kalshi pre-flight for the league lanes. Public API, no key |
| `health.py`, `verify_coverage.py` | Warn-only guardrails: freshness, stuck leads, feed and league coverage |
| `streaks_*.py`, `book_track.py`, `model.py`, `fire_track.py`, `record_build.py`, `today_build.py` | The earlier lanes behind Leads, Record, Streaks and Today |
| `test_*.py` | Logic tests; the workflows refuse to publish when they fail |
| `app.py`, `web/` | Optional local tracker UI (read-only) |

## Run locally

```bash
python3 sandbox_track.py && python3 sandbox_build.py   # Sandbox, QA and Production
python3 lane_preflight.py                              # league lanes, public Kalshi API
python3 sandbox_audit.py                               # read-only audit
python3 test_sandbox.py                                # the gate the workflows use
```

Generated pages under `public_site/` are rebuilt by the workflows; commit code, not pages, or a
running workflow can collide with you on the rebase.

## Researched and rejected

Recorded because a falsified idea is a result. Tennis surface Elo (worse than the market); soccer
forecasting from form (worse than a constant); BTTS from tier or Poisson mispricing; the +1.5
spread rules; every MLB run-total and last-5 / last-20 window; WNBA and NBA fade-the-streak,
favourite-band and spread rules; NBA first-half and first-quarter overs (thin books); commodity
ladders in their ordinary bands; the NHL moneyline in every slice tried; "tired teams mean overs"
(back-to-backs go slightly under); conditioning on a streak at all, which is −17 to −39pp even
under pure chance; and CLV as a lane metric, which looks predictive and is hindsight. Retired
lanes: the sportsgambler tips lane (three signals at n≈160, one a significant loser), earnings
markets, the National Weather Service, SportsGambler, and the table tennis 0.55–0.60 band. Each
retired source keeps its record under the Sandbox page's Reference section.

## Data handling

`predictions.db` is **git-ignored** and stays local. `data/predictions.json` is a frozen archive
of 118 manually-entered picks that predate the ledger; nothing writes to it, and stake was
stripped because the repo is public. Secrets (`ODDS_API_KEY`, `.apifootball_key`, `*.pem`) are
git-ignored or held as repository secrets and never printed.

**This repo places no bets and holds no exchange credentials.** The server holds only a GitHub
token limited to starting this repo's workflows, and a deploy key used only to push the
closing-price file. An earlier lane traded event contracts through an authenticated client; that
client, its staged-order endpoints, its approval panel and the unused venue matcher were all
removed in Sep 2026. There is no order-placing code path left — every surface is read-only.

Quarter-line Asian handicaps (`+0.25` / `+0.75`) settle as half win / half loss. Anything that
cannot be graded with confidence is marked `ungraded` with a null P/L rather than silently scored
a loss.

Picks are research, not betting advice.
