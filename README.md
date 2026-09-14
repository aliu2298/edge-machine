# Edge Machine

Paper-tracked betting research: a local tracker plus a self-updating board.
Nothing here places bets — every surface is read-only, and results are recorded to test
whether an idea actually holds up.

**Board → https://aliu2298.github.io/edge-machine/**

| Board | What it is |
|---|---|
| [Leads](https://aliu2298.github.io/edge-machine/) | Upcoming fixtures where both sides' runs point at the same total |
| [Streaks](https://aliu2298.github.io/edge-machine/streaks.html) | Every tracked team's current runs, and the sides on the longest ones |
| [Record](https://aliu2298.github.io/edge-machine/record.html) | Every graded result — leads and on-fire runs — against what those teams do anyway |
| [Today](https://aliu2298.github.io/edge-machine/today.html) | Today's and tomorrow's fixtures as the leads' control group: every lead (kept after kickoff), games in play, hit/miss and P/L on every lead and book market, and a day scoreboard |
| [Sandbox](https://aliu2298.github.io/edge-machine/sandbox.html) | Which forecasters actually make money, tracked per sport at real prices |
| [QA](https://aliu2298.github.io/edge-machine/qa.html) | Sandbox pairs promoted to QA, judged only on fresh bets, closing-line value and fees |

## Architecture

```mermaid
flowchart TB
    subgraph CI["refresh-boards.yml — every 6h (17 */6)"]
        direction TB
        TS["tests · health · coverage<br/>warn-only gates"]
        SF["streaks_fetch.py<br/>12 lead leagues + 7 form feeds"]
        SB["streaks_build.py<br/>runs → leads · log · grade"]
        BT["book_track.py<br/>price every fixture inside 24h"]
        FT["fire_track.py<br/>long runs vs a shuffled null"]
        RB["record_build.py<br/>vs the teams' own rates AND the price"]
        TD["today_build.py<br/>today's fixtures (control group)"]
        TS --> SF --> SB --> BT --> FT --> RB --> TD
    end

    subgraph SX["sandbox-tracker.yml — every 6h (37 */6)"]
        direction TB
        SS["sandbox_sources.py<br/>11 forecasters + venues"]
        ST["sandbox_track.py<br/>log at price · settle · ROI"]
        SBD["sandbox_build.py<br/>per-source, per-sport board"]
        SS --> ST --> SBD
    end

    subgraph EXT["External sources (public, no auth)"]
        BOV["Kalshi + Polymarket US<br/>public prices (venue_book.py)"]
        ESPN["ESPN scoreboard<br/>results + fixtures"]
    end

    subgraph REPO["Repo (committed)"]
        SJ["data/streaks.json<br/>computed leads"]
        SLJ["data/streak_leads.json<br/>lead ledger"]
        BLJ["data/book_ledger.json<br/>every fixture, priced"]
        FRJ["data/fire_runs.json<br/>long-run ledger"]
        SXJ["data/sandbox_ledger.json<br/>forecaster ledger"]
        OUT["public_site/<br/>index (leads) · streaks · record<br/>today · sandbox"]
    end

    subgraph LOCAL["Local Mac (optional)"]
        APP["app.py :8787<br/>+ web/ React UI"]
        DB[("predictions.db<br/>GITIGNORED")]
        APP <--> DB
    end

    BOV -.link + price.-> SB
    BOV -.price every fixture.-> BT
    ESPN --> SF
    ESPN -.final scores.-> SB
    MKT["Polymarket · Kalshi · DraftKings<br/>tipsters and models"] --> SS

    SB --> SJ
    SB --> SLJ --> RB
    BT --> BLJ --> RB
    FT --> FRJ --> RB
    ST --> SXJ --> SBD
    SB --> OUT
    RB --> OUT
    TD --> OUT
    SBD --> OUT

    OUT --> PAGES["GitHub Pages<br/>aliu2298.github.io/edge-machine"]

    style DB fill:#3a1f1f,stroke:#e06c75,color:#eee
    style PAGES fill:#1f3a2a,stroke:#3fb970,color:#eee
    style CI fill:#161b26,stroke:#2b3245,color:#eee
    style SX fill:#161b26,stroke:#2b3245,color:#eee
```

The pipeline runs entirely on GitHub's servers, so the board stays current whether or not
the Mac is on. Nothing is entered by hand: every published lead is logged at publish time
and graded against ESPN final scores once its fixture is played.

## Components

| File | Role |
|---|---|
| `app.py` | Local tracker: stdlib HTTP server + SQLite. Picks, base rates, auto-settlement. Read-only; it places nothing. |
| `web/` | React + Vite + Tailwind UI for the tracker (`npm --prefix web run build`). |
| `venue_book.py` | Prices every lead and fixture on Kalshi and Polymarket US (ask + taker fee, midpoint as fair). Replaced Bovada 2026-09-13. |
| `record_build.py` | Renders the consolidated record to `public_site/record.html`. |
| `today_build.py` | Renders today's and tomorrow's fixtures to `public_site/today.html`: leads from the ledger, in-play games filled from the book/lead ledgers, results, scoreboard, why-not on form at kickoff. Tested by `test_today.py`. |
| `streaks_fetch.py` | Pulls recent + upcoming fixtures for 12 leagues from ESPN. |
| `streaks_build.py` | Finds streak confluences; renders `index.html` (Leads) and `streaks.html`. |
| `streaks_track.py` | Logs each published lead and grades it once the fixture is played. |
| `streaks_backtest.py` | Walk-forward replay of the same rules over past fixtures. |
| `model.py` | Shrunk-Poisson probability per priced market, scored against the book on Record. |
| `book_track.py` | Prices every fixture inside 24h and grades it: the book's calibration ledger, `data/book_ledger.json`. |
| `test_book.py` | Logic tests for the book ledger. |
| `test_streaks.py` | Logic tests for run detection, lead pairing, grading and the ledger. |
| `health.py` | Warn-only guardrails: lead freshness, stuck or vanished leads, dead venue feed. |
| `verify_coverage.py` | Proves every league's squad reaches the board. |
| `fire_track.py` | Logs long runs; tests them against a shuffled-schedule null. |
| `sandbox_sources.py` | One adapter per forecaster and venue: what each publishes, and how to read it. |
| `sandbox_track.py` | Logs every forecast at the price that existed, settles it, scores ROI and Brier. |
| `sandbox_build.py` | Renders the Sandbox board to `public_site/sandbox.html`: headline counts readable and stamped sources (no blended P/L); the overall record adds v blind and beat-the-close. |
| `sandbox_close.py` | Every 30 minutes: closing prices for bets about to start → `data/sandbox_closes.json`. |
| `sandbox_browser.py` | Headless fetch for the sources that need a real browser. |
| `test_sandbox.py` | Logic tests for the Sandbox adapters, staking rules and scoring. |
| `.github/workflows/refresh-boards.yml` | Three-hourly (`41 */3`; six-hourly slots started up to 7h apart): tests → health → coverage → streaks_build → book_track → fire_track → record_build → today_build → publish to Pages. |
| `.github/workflows/backup-refresh.yml` | Hourly watchdog (`53 * * * *`): snapshots Sandbox closing prices, and takes over (in the boards concurrency group, as a separate job) only when the primary has not succeeded or the live board is over 5h old. |
| `.github/workflows/sandbox-close.yml` | Every 30 minutes (`11,41 * * * *`): closing-price snapshots only; own concurrency group, no deploy. |
| `.github/workflows/sandbox-tracker.yml` | Three-hourly (`11 2-23/3`), 90 minutes clear of the boards: collect forecasts, settle, rebuild the Sandbox board. |

## Run locally

```bash
python3 app.py            # tracker UI + API on :8787
npm --prefix web run dev  # frontend dev server on :5173
```

Rebuild the public boards by hand, in the order the workflow uses (later steps read what
earlier ones write):

```bash
python3 streaks_build.py && python3 book_track.py && python3 fire_track.py \
  && python3 record_build.py && python3 today_build.py
```

The Sandbox board is a separate pipeline on its own schedule:

```bash
python3 sandbox_track.py && python3 sandbox_build.py
```

## The Picks board (retired 2026-09-12)

For two weeks the site root was a 3-card slate: three leads re-drawn automatically
(rarest first, one per fixture, one per team), locked at draw and graded on the final
score. It was retired because it only ever re-drew three of the leads the Leads board
already publishes and the Record page already grades — its 28 settled picks were a strict
subset of the leads ledger, so the section was a second, smaller read of the same
evidence. The Leads page now sits at the root; `leads.html` redirects there. The code is
in git history (`slate.py`, `slate_build.py`, `slate_backtest.py`, `test_slate.py`).

One lesson from it survives in `health.py`: a fixture that is **abandoned or postponed
vanishes from the ESPN feed** and can never grade. FC Utrecht v Go Ahead Eagles
(2026-09-05) sat pending for a week that way, so the guardrail now flags a lead that is a
day overdue *and* absent from the feed rather than waiting out the ledger's 7-day void.

## The Streaks board

Tracks 12 leagues: the big five (Premier League, La Liga, Bundesliga, Serie A, Ligue 1),
Eredivisie, Primeira Liga, Scottish Premiership, MLS, Saudi Pro League, and the
Champions/Europa Leagues.

Seven more — Belgian, Norwegian, Greek, Austrian, Danish, Cypriot and Turkish top flights —
are pulled as **competitive form feeds**. The European competitions drag in opponents from
leagues the board does not track, and those sides arrived with *no form at all*: 21 teams
in upcoming fixtures had zero games, so 48 of 273 upcoming fixtures could never produce a
lead — silently, because `find_leads` skips a fixture when either side lacks form and a
skipped fixture looks exactly like "no confluence today". With the feeds in place that gap
is now **13 of 208**, from **10** sides with no form at all (leagues ESPN does not serve:
Czech, Polish, Croatian, Ukrainian, Israeli, Bulgarian, Slovenian, Slovak, Azerbaijani,
Armenian). `verify_coverage.py` names them rather than letting the gap pass as silence.
They are real football, so they count as form and enter the baselines, but they carry
`lead_source: False`: the tracked league list is deliberate, and quietly turning seven more
leagues into lead sources would change the product rather than fix the gap.

Fourteen sides still have no form, from leagues ESPN does not serve (Czech, Polish,
Croatian, Ukrainian, Israeli, Bulgarian, Slovenian, Slovak, Azerbaijani, Armenian). That is
a data limit, and `verify_coverage.py` now names them rather than letting the gap pass as
silence.

**Leads run in two lanes, one market each: over 1.5, and (since 2026-09-12) a side to
score 2+.** Eight bet types meant every market carried a thin, separately underpowered
sample; narrowing to one pooled it completely. The team-2+ lane was added back on top as a
*priced* second lane — the board's original question ("Barcelona have scored 2-3 in six
straight and the next opponent concedes 2"), and the one market here that trades near evens
rather than at 1.20, so an edge, if one exists, would actually pay. Two pairings feed it:
the team scoring 2+ in every recent game against an opponent that has conceded 2+ in every
recent game (sharper, rare — 11 fixtures in 763 on the walk-forward) or merely conceded in
every recent game. Each lane is judged on its own claim and never pooled with the other.
Go in expecting what the walk-forward says: neither pairing beats the side's own 2+ rate
(−3 to −5pp, not significant); the test is whether the *book* misprices them.

Over 1.5 rather than over 2.5 for two reasons, one measured and one structural:

* on the ledger to date it is the only market with a **positive lift** — +4.7pp at n=19,
  **not significant** — while over 2.5 ran −12.5pp at n=14. That is thin evidence, and
  picking the leader of five markets after seeing the table is a multiple-comparisons
  trap. This was a decision taken *on top of* the numbers, not one they established.
* a lopsided line is **cheaper to test**. Binomial variance is p(1−p), so at an 85% base
  rate each graded lead carries ~1.9× the information about a fixed percentage-point lift
  than one at over 2.5's 62%. Detecting +5pp needs ~760 graded leads here versus ~1470.

The cost is that **over 1.5 lands in ~85% of matches with no flag at all**, so the board
now publishes claims that are usually right for reasons having nothing to do with streaks.
Lift against the teams' own rate is the only reading that means anything — see Record.

A **lead** is not a streak on its own — plenty of good sides score freely. Both legs must
run at least 3 games, and **the pair must imply the bet arithmetically**:

| evidence | shape |
|---|---|
| both sides score — 1 + 1 ≥ 2 | a true *confluence*: two different events about this fixture, adding up to clear the line |
| both sides' matches go over 1.5 | evidence *stacking*: each leg alone already implies the bet, since this fixture is one of each side's matches |

Only the first matches the "one side's run meets the other's" framing. Both are legitimate
evidence; they are not the same logical shape, and the board says which is which.

That rules out the pairing that looks most natural. "A have scored in N straight" plus "B
have conceded in M straight" reads like two pieces of evidence, but in a match between them
**A scoring and B conceding are the same event**, counted twice — and it only implies one
goal, so it says nothing about a 1.5 line.

**Prices come from the exchanges (since 2026-09-13).** Bovada was the book until it began
answering every request with a cookie redirect loop. `venue_book.py` now prices each lead and
every fixture inside 24h on **Kalshi and Polymarket US**, the two regulated US exchanges:
over 1.5 / 2.5 from Polymarket US's totals ladder or Kalshi `KX{LEAGUE}TOTAL`, BTTS from Kalshi
`KX{LEAGUE}BTTS`, a side to score 2+ from Kalshi `KX{LEAGUE}TEAMTOTAL`. Where both list a market
the cheaper effective price wins. `price` is decimal odds at the ask **plus taker fee** (what a
follower pays); `fair` is the book's midpoint. A one-sided book, or a spread over 10¢, is no
price. No URL is stored in a ledger — `market_url()` builds the card's Kalshi / Polymarket
button at render time. The matcher (both sides must match, same day, near-ties refused) is
kept from an earlier matcher, thresholds unchanged. Coverage is narrower than a sportsbook: when
measured, 60% of over-1.5 leads and 31% of team-2+ leads had a venue market — the
rest cannot be traded and are graded on hit rate only. Leads priced before the switch keep
their Bovada price (a price is never revised), and the Record shows how the priced sample
splits between the two.

Two design choices worth knowing:

* **Form is cross-competition, and includes preseason.** A team's last 6 games span every
  tracked competition, not just the one their next fixture belongs to — form does not reset
  when a side walks into a European tie, and early season it is the only thing that works
  at all (UCL/UEL sides have played ~2 European games). Preseason **friendlies** are pulled
  too, so a promoted club or a second-tier side in a cup tie has a form line instead of a
  blank. Friendlies are marked with dashed pills and a note, are **excluded from the
  baselines** (they are higher-scoring and less serious, and would shift the yardstick),
  never generate a lead of their own, and a run made up *entirely* of friendlies is
  discarded rather than shown as evidence.
* **Every run is shown with its base rate.** This repo has already falsified three signals
  that looked good until measured. The trap each time was reading a pattern without asking
  how often it shows up by chance, so each run is rendered next to the share of tracked
  teams currently on a run that long. A 5-game scoring streak that a fifth of the league is
  also on is not a lead, and the board says so.

Confluences are genuinely rare — whole leagues can have none on a given day. The **All teams
on a run** tab exists for that: it browses every tracked team's current runs directly,
rather than showing an empty league.

### Prices (added 2026-09-12)

Lift says whether a confluence carries information; it cannot say whether it pays, because
the sportsbook already prices what the teams do. Measured the day this was added: over 1.5
on lead fixtures traded at **~1.20 on Bovada — a break-even hit rate of 83.3%**, which is
essentially what leads hit (82.5% live, 79.7% in the walk-forward). So every lead is now
priced as well as graded:

* the line is captured the **first build it is listed** (Bovada's per-event page, one paced
  request per fixture — the bulk feed only carries the main 2.5 total), never revised, and
  **never taken after kickoff**;
* **three fixture-level markets** are logged on every lead — over 1.5 (the claim), over 2.5
  and BTTS — fixed in advance so no market is chosen after seeing which one paid;
* P/L is a flat 1 unit; the Record page shows each market's hit rate against the
  **break-even** rate the average price demands and the book's own **vig-free probability**.

A lead graded before pricing existed simply does not appear in that section.

### Model v book (added 2026-09-12)

Lift against the teams' own rate cannot be improved by tuning streak rules: a run is the
noisiest estimate of a rate there is, so selecting on one guarantees regression (the top
20% of team-games by raw 2+ rate predicted 65% and delivered 56%). The number that pays is
against the **book**, whose vig-free probability is a better estimate than any form scrape.
So `model.py` — independent Poissons on each side's attack and defence ratings, pooled
across competitions and shrunk hard toward average (`SHRINK=24`, chosen on a walk-forward
where 8 was visibly overconfident) — logs its probability for every priced market at the
moment the price is captured, never revised. The Record page scores model and book by
**Brier** on the same settled leads, and reports a **pre-registered value split**: leads
where the model beats the book's fair probability by 5pp or more, against the rest. (Since
2026-09-13 an exchange-priced quote is judged against the effective price paid — ask plus
fee — not its midpoint; Bovada-priced quotes keep the original vig-free rule. See
`streaks_track.value_edge`, shared by Today, Record and the book ledger.) If the
model carries anything the book does not, that group out-hits and out-earns the rest; if
not, the book is the better estimate and no selection rule built on form can beat it.

On the walk-forward the model beats a flat league rate only marginally (Brier −0.002 to
−0.007); the book will be a much harder yardstick. That is the honest prior.

### The book, on every fixture (added 2026-09-12)

A per-team "profitable" tag built from leads would confound the team with the streak all
over again — leads only observe a side while it is on a run, exactly when its next result
regresses — and grow at one lead a week. So `book_track.py` keeps a separate ledger: **every
competitive fixture is priced once it is inside 24h of kickoff**, whatever the form on
either side, on five markets (over 1.5, over 2.5, BTTS, each side to score 2+), with the
model's probability logged beside each price, and graded on the final score. That makes it a
calibration ledger for the book itself: hits against the hits the book's own vig-free
probabilities predicted, as **excess** and **z**, by market, by league, by home/away, by
price band, and — as a drill-down — by team. A team is tagged **PAYING** on the All-teams
tab only past 20 observations with z ≥ 2, and the page says how many teams were tested,
because with ~230 of them about six reach z = 2 by chance. Read the league and price-band
tables first; they pool dozens of teams and are readable weeks before any team row.

### Tracking and grading

Every lead is logged to `data/streak_leads.json` when it is published and graded once its
fixture is played — automatically, in the same daily job. Each pairing carries a
machine-checkable claim (`{"kind": "team_gte", "n": 2, ...}`) so grading never depends on
someone deciding after the fact what a card "meant". A lead that cannot be judged is voided,
never scored as a miss.

**What this measures is information, not profit.** The board carries no odds, so ROI is
unmeasurable — and a hit rate alone says nothing ("over 2.5 landed 60%" is meaningless
without a reference). Each lead is therefore compared against the **league-adjusted base
rate** for that same outcome. The adjustment is not cosmetic: BTTS leads cluster in
high-scoring leagues, and on the backtest a global baseline showed a +17.1pp BTTS lift that
fell to +10.7pp — and lost significance — once each lead was compared against its own
league. **Lift is the number that counts.**

`streaks_backtest.py` replays the same rules over already-played fixtures, computing each
side's form only from games *before* the fixture in question (no lookahead). It exists so
the idea is falsifiable today rather than in a month, and so the grader itself is verified.

**Current state (Sep 12 2026): the two live lanes are answered, and the answer is no.**
113 graded leads hit 75.2% overall; 738 on the walk-forward hit 79.7%. Against the teams'
own rates *and* against the price the book actually offers, both live markets are negative:

| lane | n | hit | teams' own rate | break-even at the price | edge |
|---|---|---|---|---|---|
| over 1.5 | 40 | 82.5% | 84.0% | 83.3% (≈1.20) | **−0.8pp** |
| over 2.5 | 24 | 54.2% | 65.0% | 60.4% (≈1.67) | **−5.8pp** |

Two independent references agree, which is the point of having both. The over-1.5 case is
worth understanding because it is not a tuning problem: at 1.20 you need 83.3%, and those
teams' own rate is 84.0% — the book has priced the market at essentially the teams' true
rate, leaving under a point of room, and the leads land below it. **No threshold change
recovers that**; the signal knows what the market already knows.

No edge is claimed. What the fixed cadence buys is a clean, uncorrelated, continuously
accumulating sample, and the `book_track` ledger below now measures the same question at
roughly seven times the rate.

### On-fire runs: measured against a shuffled schedule, not a base rate

Long runs get no baseline column, because three were tried and all three were wrong — the
population rate (+12.8pp, "significant": teams on scoring runs are simply good teams), the
team's own rate (−8.7pp, "significant": circular, since the run's own games are inside the
team's average), and the team's rate with the run removed (+10.3pp: over-corrects, since
deleting a run deletes only successes). Same games, three answers, two of them significant
in opposite directions.

The reference is not an average at all. **Shuffle a team's own games into a random order**
and runs carry zero information by construction — yet being "on a run" still predicts a
next-game rate 17–39pp *lower*, because a run ends the moment it fails and the games after
one are pre-selected against. That shuffled band is what "no signal" looks like, and a
result only counts if it lands outside it.

Two implementation choices turned out to matter more than the data:

* **The first `FIRE_MIN` games of every team are discarded.** No run is reachable there, so
  counting them forces that stretch entirely into the control arm — and a team's opening 8
  games hit **4.3pp lower** than its later ones. In the real order that depresses the
  control; a shuffle scatters it. Including them alone flagged three streak types
  SIGNIFICANT.
* **The test is never restricted to the teams in the ledger.** A team reaches the ledger
  only by going on a real run, so it always supplies an on-run arm in the real order and
  often none in a shuffle — culling ~25% of teams from the null and none from the
  observation. That mismatch alone produced p = 0.005–0.015.

**Current state (Sep 12 2026, n=265 graded, 80.0% extension): nothing survives
correction.** The closest is **over 1.5**, whose on-minus-off gap of −17.5pp sits just
outside a [−37.6, −20.8] shuffled band: p = 0.012, but **p adj = 0.084** across the seven
streak types tested together. It is stable across seeds (p = 0.008–0.012 at 2000
shuffles) and it is the nearest thing this repo has produced to a signal, so it is worth
watching — but it is not significant, and one marginal cell out of seven is the expected
outcome even when nothing is there.

⚠️ At **400** shuffles the same data flagged SIGNIFICANT (p adj 0.035). That was
permutation noise, which is why `PERMUTATIONS` is 2000 and why `iters`/`seed` are resolved
at call time — bound as signature defaults they silently ignored an override, and a
seed-stability audit ran the same seed four times and looked reassuring.

The tab remains a browse surface for what is happening, not a signal.

Leads are research to look at. Nothing here places or stages a bet.

## The Sandbox board

A different question from the rest of the repo. The Streaks lanes ask "does *this* signal
pay". Sandbox asks **"does anyone's signal pay"** — it logs what published forecasters say
across 14 sports, stamps each one with the price that existed at that moment, and settles
it on the real result.

Thirteen sources, staked two different ways because they are followed two different ways:

* **Tipsters name a side** (Covers, OLBG, Oddspedia, Scores24, SoccerPredictions.ai,
  SportsGambler). That side is backed at the going price, every time — high turnover, no
  Brier score, and a real ROI, because that is how a tipster is actually followed.
* **Models, books and exchanges state a probability** (ESPN FPI, DraftKings, Pinnacle,
  Kalshi, Polymarket, NWS, spot price). They are backed only when they disagree with the price by
  3pp or more, and they also get an accuracy score.

Everything is a flat $100, so nothing on the board is bet-sizing skill. Polymarket is the
spine and the settlement oracle: it supplies the price and the resolution, so most of its
rows are **price observations with zero stake**, not bets. That distinction matters when
reading the ledger — 788 quotes have produced 187 bets and 57 settled positions, and
aggregating the quotes instead of the bets would show 294 phantom zero-P/L "bets".

**The floor is judged per source, not on the total.** Every ROI cell greys itself below 30
settled bets, and the banner above the table names the best single-source count while
nothing has reached it. At 57 settled across seven sources the best is 15, so *nothing on
that board is readable yet* — an earlier version compared the lifetime total against the
floor and announced the column was readable while greying out every figure in it. A total
is not a sample; nobody bets "all sources".

**A Polymarket price needs a book behind it.** gamma's `outcomePrices` is a midpoint, and a
just-listed market shows a midpoint near 0.50 with nothing on either side. Until
2026-09-12 only an exact 0.50/0.50 was screened out, so boxing bouts were logged at 0.51
that traded at 0.88 once money arrived — against Pinnacle, logged prices were off by a mean
of 20pp in boxing and 12pp in cricket, and under 2pp in tennis. A contest is now logged
only when its spread is 5¢ or less with at least $100 on the book, and it is booked at the
**ask**, the price a follower pays (the midpoint is kept for Polymarket's own Brier score).
Nothing is logged against an unpriced book, for any source, so the contest is quoted on a
later run once it is real. Boxing, cricket and table-tennis quotes logged before the rule
were voided or, if not yet started, removed for re-quoting.

**Nothing is logged once a contest has started** — checked for every source and venue at
the moment of logging. The venue feeds keep a contest for five minutes past its start to
absorb clock skew, and that window let a SoccerPredictions.ai tip on Al Wahda v Sharjah be
logged 74 seconds after kickoff (it won, +$178). Anything logged at or after its start is
voided.

**Blind baselines.** Every sport shows what a fixed rule that ignores every source made on
the same contests — back the favourite, back the underdog, back every draw — priced at the
first moment any source looked. They are the weather a source's record is read against: on
2026-09-12 the tracked leagues drew 34% of the time, and back-the-underdog made +31% across
the weekend's soccer.

**Stages: Sandbox → QA.** Promotion is per (source, sport) and recorded in `data/stages.json`
with the evidence it was made on. The **QA entry gate** is lighter than the stamp because QA
re-tests on fresh data only — bets logged after the promotion: 30+ settled bets spanning 14+ days,
wins beat the price by z ≥ 1, beats every blind rule on the same contests, still profitable
without its biggest win. In QA the stamp is applied to the fresh record, plus positive
closing-line value and positive ROI after the taker fee (Polymarket US 0.06·p·(1−p), Kalshi
0.07): that is **production-ready**. A QA pair whose fresh record is behind the price after 30
bets is demoted and must re-qualify on bets logged after the demotion.

**QA rules, tightened 2026-09-13 before any promotion.** Production-ready needs CLV on 30+
closing prices covering at least half the fresh bets, and the ready gate must hold for 7 days
(checked every run; the mark is withdrawn, and logged, the first run it fails). A QA pair is
demoted after 30 fresh bets if it is behind the price, not beating every blind rule, or behind
the closing price — and at any count after 21 days with no new bet. Baseline sources are never
promoted. Settled bets are never lost to pruning: `prune()` copies each settled bet whole into
`data/sandbox_archive/YYYY-MM.json` (by settle month) before rolling the row up, and every
judgement reads the ledger and the archive together.

**Soccer BTTS and the form rule (2026-09-13).** The Sandbox lists Kalshi both-teams-to-score
markets as the domain `soccer_btts` (`fetch_kalshi_btts`): yes/no rows tied to an ESPN fixture
(home first, kickoff from ESPN), Yes and No at their own asks, settled as yes/no markets. Two
sources: `btts_market` (Baseline, never bets) logs the midpoint on every match; `btts_form_l10`
(kind Rule) is the pre-registered rule — back Yes where BOTH teams saw both teams score in 7+ of
their last 10 competitive games (ESPN results strictly before kickoff). No fitted threshold. Because
a rule that always backs Yes would equal "back the favourite" on its own contests, its blind rule is
the population (`baseline="population"`): backing Yes on every BTTS match over the same period.

**Soccer goals markets and three rules (2026-09-14).** `fetch_kalshi_goals` lists Kalshi over 1.5
(`KX{LEAGUE}TOTAL`) and team totals (`KX{LEAGUE}TEAMTOTAL`, one row per side) as three domains —
`soccer_o15`, `soccer_team1` (over 0.5) and `soccer_team2` (over 1.5) — each row tied to its ESPN
fixture and side. `goals_market` (Baseline) logs every midpoint; the rules are pre-registered from
research fixed before it ran (competitive games only, 10+ each, results strictly before kickoff):
`o15_form_l10` both sides' games over 1.5 in 9+ of 10; `team1_form_l5` side scored in 5/5 and the
opponent conceded in 5/5 (fast-tracked, see below); `team2_form_l10` side scored 2+ in 7+/10 and the
opponent conceded 2+ in 7+/10. Each is judged against its own market's population. Both sides of a
team total are separate outcomes (`outcome_cluster`). Kalshi lists no team totals for the Eredivisie
or Primeira Liga.

**Tennis favourite-band rule (2026-09-14).** `tennis_fav_band` (kind Rule) backs the player the
exchange prices 0.75 up to 0.90, on every tennis match listed. Found on 427 settled matches over four
days (86.4% won v 81.1% priced, +5.2% after fees, z +1.26 on 88) — the favourite-longshot bias. Its
blind rule is `baseline="favourite_population"`: backing the favourite on every tennis match over the
same period, one quote per contest, so the band must beat favourites in general. A surface-blended
Elo rule on ESPN tour-level results was researched the same day and not added: it rated only 65 of
the 427 matches (ESPN has no Challenger or ITF results), its probabilities scored worse than the
market's (Brier 0.241 v 0.212), and its 50 bets won 42% against 44% priced (−12.4%).

`mma_fav_band` runs the same band, unchanged, on MMA — not fitted there (the Sandbox had no settled,
priced MMA fight when it was added), so it tests whether the bias carries across sports.

`tt_band_55_60` is a confirmation test on table tennis: the one band that spiked in the first 129
settled matches (0.55-0.60 won 78.8% v 57.2% priced, z +2.51 on 33, with losing bands either side),
backed on every new match to see whether it is noise.

**MLB fade-the-streak rule (2026-09-14).** `mlb_fade_streak` backs the team that won 3 or fewer of its
last 10 when it plays a team that won 7 or more of its last 10 (regular season, 20+ games each, MLB
Stats API results before first pitch, `mlb_games`). Researched on every 2025 and 2026 game at Kalshi's
last price before first pitch: +3.0% on 239 games in 2025 and +4.6% on 149 in 2026 — found in one
season, repeated in the next, but small. Last-5 and last-20 windows and every run-total rule (team
5+, game 9+ over/under) were tested in the same run and did not repeat or contradicted themselves.

**Under 3.5 low-scoring rule (2026-09-14).** `soccer_u35` lists Kalshi's Over 3.5 market (side b = No,
the under). `u35_low_scoring` backs the under where both teams scored 1 or fewer in 7+ of their last 10
games in the same competition (`team_form(..., league=)`, HOF's way of counting; ESPN's counts matched
HOF's on the fixtures checked). Research: 80.5% on 41 v the teams' own 61.7%; 23 of 27 at Kalshi's
under price (~71%), +20.2% after fees. Under 4.5 on the same selection was priced at ~86% and made
+3%, so it was left out. Judged against backing the under on every Kalshi match.

**Leads v2: the over-1.5 rule change (2026-09-14).** The Leads board's over-1.5 cards now come from
`over15_form_leads` (both sides 9+ of last 10) instead of the run pairings; the team 2+ lane is
unchanged (`LEAD_PAIRINGS`). The retired pairings (`SHADOW_PAIRINGS`) still log, price and grade into
`data/streak_leads_shadow_over15.json`, never published, and the Record's rule-change table
(`rule_compare`) sets the two side by side from `RULE_CHANGE`.

**Production (2026-09-13).** `production.py`. A (source, sport) pair is in Production while it
sits in QA with `ready_at` set (held the ready gate 7 days) and leaves on the first run the gate
fails — no manual promotion. Each tracker run writes `data/production_leads.json` in the lead
ledger's shape (`leads`, `updated_at`, `board_built_at`): every bet a Production pair logged since
it entered Production that the feed can express (`placeable`: a soccer side to win on a mapped
Kalshi GAME market as `match_result` with `side` home/away, or Yes on a Kalshi over-1.5 / team-goals
market as `total_gte` / `team_gte`), `last_seen_at` = the build stamp while open, status
pending/hit/miss/void. Empty until a pair arrives. `public_site/production.html` lists the pairs
and open leads.

**Fast track (2026-09-14).** A source with `fast_track` in its registry entry (today
`team1_form_l5`, team scores 1+) is in Production on probation from its first bet, without the QA
gate, and judged by `fast_track_status` on every settled bet since `since`: under 30 bets it is on
probation; at 30+ it stays only while profitable after fees with z ≥ 1 against the prices paid.
Failing sends it back to the normal ladder on fresh evidence, and a failed fast track never
re-opens.

**QA counts only the US exchanges (2026-09-13).** QA entry, readiness and demotion read
only bets on Polymarket US, Kalshi and Kalshi yes/no (`TRADEABLE_VENUES`); polymarket.com bets
stay on the Sandbox page and in its own stamp. Production-ready also requires every fresh bet to
be a market the Production feed can publish (`placeable`: a soccer side on a Kalshi game
market, or Yes on a Kalshi soccer goals market — no draws, no other sport yet).

**Closing prices from the Mac.** GitHub throttles the frequent schedules, so
`scripts/local_closes.sh` runs `sandbox_close.py --writer mac` every 15 minutes under launchd
(`scripts/com.aliu.edge-machine-closes.plist`) from a dedicated clone at `~/edge-machine-closes`,
committing only `data/sandbox_closes/mac.json`. Log: `/tmp/edge-machine-closes.log`.

**Closing prices.** Every run refreshes, on each open bet, the same venue's current price for
the side it backed, while that book is tradeable and the contest has not started — so the
value left behind is the last snapshot before the start. Closing-line value (close minus the
price paid) says whether a source buys below where the market ends up, and it is readable
long before enough results settle to judge ROI. Because the Sandbox runs every six hours,
`sandbox_close.py` reads the venue's price for just the open bets whose deadline is in the
next 60 minutes. GitHub honours none of the schedules reliably, so it runs from three places —
`sandbox-close.yml` (`11,41 * * * *`), the hourly watchdog and every board refresh — each writing
only its own `data/sandbox_closes/<writer>.json`; the tracker merges every writer's file on its next run, the latest
snapshot before the deadline winning. The deadline is the start, or for a yes/no market its expiry
minus the domain's quoting lead (a price after that has the answer in it). Pre-registered:
a snapshot counts toward CLV only when taken within 60 minutes of the deadline; older ones
are kept and shown, never scored. The close job writes no other file and has its own
concurrency group, so it can neither conflict with nor cancel a queued board or tracker run.

**The stamp of approval** is pre-registered (2026-09-12) and identical for tipsters, models,
books and exchanges. Every criterion must hold, and it is re-judged every run:
50+ settled bets spanning 28+ days (first start to last — calendar weeks touched let a Sunday and a Monday count as two); wins beat the prices paid by z ≥ 2; ROI beats every
blind rule on the same contests; still profitable without its single biggest win; profitable
in both halves of its record. Below 30 settled bets a source is **no read**; readable and
ahead of the price but short of a gate is **watch**; readable and not ahead is **failing**.
SoccerPredictions.ai's first weekend (+24.5%) sits exactly at back-every-draw on the same
contests (+24.9%), which is why a hot ROI alone earns nothing.

**Fight nights are re-timed from Pinnacle.** Neither venue says when a *bout* starts:
Polymarket stamps every bout with the card's start, and Kalshi's estimate is three hours
before expected expiration — both safely early, but they closed Vanhouter v Akpejiori and
Opetaia v Mikaelian to logging hours before either fought. Boxing and MMA rows are kept for
up to 12 hours past their venue start while the market is open, then re-timed from
Pinnacle's per-bout commence time **minus 30 minutes** (a card runs ahead when earlier fights
end early). The event list is a free Odds API call. A row Pinnacle cannot re-time keeps its
venue start and is dropped once that passes, exactly as before; a Pinnacle match more than a
day off the venue is not trusted. Every fight quote records `start_source` and the venue's own
start for audit.

**MMA** is its own sport: UFC on Polymarket (`ufc` tag) and Kalshi (`KXUFCFIGHT`, `KXMMAFIGHT`),
Pinnacle via the Odds API's Mixed Martial Arts group, and OLBG's tips — boxing and UFC share
OLBG's one listing page, read with a single request.

**OLBG** is the boxing and MMA tipster: a community whose members post a Win Fight tip per bout, one
listing page per run. A fight is a call only when a fighter is the most popular selection with
at least three tips and a strict majority of them. Its tipsters compete on profit and often
pile onto the draw at 15/1 (10 of 14 tips on Magsayo v Cortes); the venue boxing markets are
two-way, so a draw-led fight is no call. The page also lists UFC bouts, which cannot match a
boxing contest and fall away. Boxing names are transliterated differently by every feed
("Mikaelian" / "Mikaeljan"), so boxing alone accepts a long word spelled almost identically as
the same name — both fighters must still match.

**Leads horizon and withdrawn leads (2026-09-13).** `find_leads` publishes only fixtures
kicking off inside `LEAD_HORIZON_H` = 48 hours. Every build stamps `board_built_at` on
`data/streak_leads.json` and `last_seen_at` (the same stamp) on every lead it publishes; a
pending lead the build no longer publishes, with its fixture still ahead, gets `withdrawn_at`
(cleared if it returns). The Record's hit-rate, priced and model-v-book tables count only leads
not withdrawn at kickoff, and show the withdrawn count apart. A lead is on the board now only
when its `last_seen_at` equals `board_built_at`.

**Sandbox venue (2026-09-13).** Non-soccer contests are priced and settled on **Polymarket
US** (`fetch_polymarket_us`, `resolve_polymarket_us`) — the regulated US exchange —
instead of polymarket.com, which is closed to US accounts. Each event's single two-outcome winner
market is the contest; its bid/ask quote the first outcome (side B's ask is 1 − bid); an event
not at period "NS" is in play and never quoted; settlement 1/0 = first outcome won/lost.
polymarket.com stays as the comparison source `polymarket`, backed at a 3pp disagreement with
the US ask; bets logged on it before the switch still settle there. Kalshi remains the soccer
venue and the gap-filler, with soccer starts taken from ESPN's kickoff where a fixture matches
(`apply_espn_starts`). The tracker runs every 3h (`11 2-23/3`), and Odds API pacing counts 8
runs a day. Weather quotes show their city, and a weather ladder (one series, one day) counts
as one independent outcome in z and in the sample size (`outcome_cluster`). The running and
settled lists carry every bet with a filter box.

**Pinnacle v venue on uncovered contests.** Pinnacle is planned *after* every other source
and across all sports at once: free event lists show how many listed, priced contests each
Odds API key carries that no tipster, model or book has covered, and the run's paced share of
credits is spent on the keys with the most uncovered contests first. Soccer is priced
three-way, with the draw kept in the de-vig. Lines more than 60 minutes old are skipped, and
every Pinnacle quote records whether its contest was uncovered, so the rule's own lane is
reported separately on the page. A key with no uncovered contest is never paid for, and a
sport stops getting paid calls once it has 30 Pinnacle quotes without one reaching the 3pp
edge (soccer on Kalshi retired this way: 35 quotes, largest gap 1.3pp); unspent credits stay in
the balance and the pacing passes them to later runs.

**Pinnacle** is read through The Odds API (`ODDS_API_KEY`, a repository secret) for boxing,
cricket and tennis — the three sports with no dependable tipster — de-vigged to a fair
probability. Pinnacle closed its own public API in July 2025; the pinnacle.com site's guest
endpoint also answers, but it is undocumented and Pinnacle does not serve US customers, so
it is not used. The Odds API lists Pinnacle only for major cricket and the big tennis
tournaments, not ITF or Challenger. Credits are paced to last the month: event lists are free, a
paid odds call is made only for a sport with a listed, priced contest waiting, and each run
may spend only its share of what remains — (remaining − 25 reserve) ÷ the runs left before
the credits reset on the 1st, counting eight scheduled runs a day (the tracker runs every 3h) plus 25% for manual ones,
never more than four. A simulated month of six runs a day never runs dry and still makes a
paid call every day.

Beyond sport the same machinery runs on yes/no markets where the opponent is the market
price itself — climate (National Weather Service against Kalshi's temperature buckets for
the same city and day) is the one with a genuinely independent forecaster, and it settles
overnight, so it reaches a readable sample fastest.

## Data handling

`predictions.db` is **git-ignored** and stays local, so the raw database is never
committed. `data/predictions.json` is a frozen archive of the 118 manually-entered sports picks
that predate the leads ledger; nothing writes to it any more, and stake was stripped
from it because the repo is public.

Secrets (`.apifootball_key`, `*.pem`) are git-ignored. A fresh checkout creates empty
tables on first run.

**This repo places no bets and holds no exchange credentials.** An earlier lane traded
event contracts through an authenticated, request-signing client; that client, its staged
-order endpoints, its React approval panel and the unused venue matcher were all removed
in Sep 2026. There is no order-placing code path left — every surface is read-only.

## Notes

Quarter-line Asian handicaps (`+0.25` / `+0.75`) settle as half win / half loss. Anything
that cannot be graded with confidence is marked `ungraded` with a null P/L rather than being
silently scored a loss.

## Retired lanes

Removed after measurement, not abandoned on a hunch — each was tracked to a real sample and
falsified:

* **Tips** (sportsgambler.com's published predictions, removed Aug 2026) — all three tracked
  signals measured at n≈160. The tip itself: −0.3% ROI, bootstrap CI [−0.139, +0.131], dead
  flat. BTTS implied side: 62.1% hit vs 63.2% market-implied — well-calibrated, the loss is
  just the vig. Projected exact score: −37.2% ROI, CI [−0.676, −0.017], a *significant*
  loser. No edge to keep.
* **Earnings** (company quarterlies + earnings-call mention markets on an event-contract
  exchange, removed Aug 2026; the exchange integration itself was removed Sep 2026).

Picks are research, not betting advice.
