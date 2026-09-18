# Edge Pick Settler — refinement spec (paste into Lovable)

The sportsgambler scraping already works — the app correctly ingested and settled 10 MLS
matches on 1 Aug 2026. This spec changes **what is displayed**, fixes a **P/L bug**, and makes
**settlement + daily refresh** reliable. Do not rebuild the ingestion from scratch.

---

## 1. BUG FIX (highest priority): American odds are not parsed

Every price on sportsgambler.com is **American format** (`-110`, `+850`, `-222`, `+155`).
The app currently stores these as null — the odds column renders "—" and the P/L calculation
falls back to `-1.00` **even on winning picks**.

Observed: "Red Bulls To Win @ +114" settled WIN but scored −1.00. Same for
"Philadelphia To Win @ -149". Result: the dashboard reports a 66.7% win rate alongside
−13.80% ROI, which is self-contradictory. Correct figures are ≈ +2.43 profit, ≈ +24% ROI.

**Fix — convert American → decimal on ingest and store both:**
```
if (american > 0)  decimal = american / 100 + 1            // +114 -> 2.14
else               decimal = 100 / Math.abs(american) + 1  // -149 -> 1.671
```
P/L on a win = `stake * (decimal - 1)`; on a loss = `-stake`; push = `0`.
Never default a settled WIN to a negative P/L — if odds are missing, show "—" and leave P/L
blank rather than assuming a loss.

---

## 2. DISPLAY — show only these three things per match

Strip the app's own derived BTTS / Over-2.5 "lean". The app is a **mirror of what
sportsgambler publishes**, not an independent analyst. Each card shows exactly:

1. **Projected score** — from the `Correct Score Prediction` section.
   Page renders as `Galaxy 0 - 1 Dallas` plus its price (e.g. `+850`).
   Store `proj_home`, `proj_away`, `proj_score_odds`.
2. **Both teams to score** — from the odds table block titled `Both Teams to Score`,
   which lists `Yes <price>` / `No <price>` (e.g. `Yes -222`, `No +155`).
   Store `btts_yes_odds`, `btts_no_odds`, and derive `btts_implied` = the side with the
   shorter price. Also capture the supporting stat line when present:
   `"BTTS Yes in 8 of the previous 10 matches"` → store `btts_form_home` / `btts_form_away`.
3. **The site's prediction** — the `MAIN MATCH PREDICTION` block, verbatim tip + price
   (e.g. `Dallas Asian Hcp +0.25 @ -110`). Store `tip_text`, `tip_odds_american`,
   `tip_odds_decimal`.

Plus the match header already parsed: league (`USA - MLS`), teams, venue, kickoff
(`Sat 1 Aug 21:30`). Nothing else on the card — no player props, no corners, no bet builder.

---

## 3. SETTLEMENT — must run on its own

After kickoff + ~2.5 hours, re-fetch the match page (it updates in place with the final
score) or the league results page `/fixtures-results/football/<league-slug>/`.

Grade and store `final_home`, `final_away`, `settled_at`, and a result per displayed item:
- **Projected score** — `hit` only on an exact scoreline match, else `miss`.
- **BTTS** — compare the implied side to reality: both teams scored ≥1 → Yes.
- **Main prediction** — grade by market type: moneyline, Asian handicap (incl. quarter-lines
  `+0.25` / `+0.75` → half-win / half-loss), totals. If a market can't be graded
  confidently, mark `ungraded` — **do not guess, and never silently score it a loss.**

Run settlement automatically on the daily job, and on app load if any pick is past kickoff
and still unsettled.

---

## 4. REFRESH — daily

Replace the current cadence with a **once-daily** scheduled run (plus a manual "Refresh now"
button, and a load-if-stale check older than 24h). Each run:
1. Fetch the 10 league index pages, extract match-page links
   (`/betting-tips/football/<home>-vs-<away>-prediction-lineups-odds-YYYY-MM-DD/`).
2. Skip matches already stored (match URL = unique key); skip anything marked `Expired`
   on the index that isn't already in the DB.
3. Parse new match pages, insert as active picks.
4. Settle anything past kickoff.

Rate-limit to ~1 request/second, server-side fetch through the Supabase Edge Function with a
normal browser User-Agent (the browser cannot fetch sportsgambler directly — CORS).

---

## 5. Leagues (unchanged — only these 10)
Premier League, La Liga, Bundesliga, Serie A, Ligue 1, MLS, Eredivisie, Primeira Liga,
Champions League, Europa League.

Index URLs: `https://www.sportsgambler.com/betting-tips/football/<slug>-predictions/`
where slug ∈ `premier-league, la-liga, bundesliga, serie-a, ligue-1, mls, eredivisie,
primeira-liga, uefa-champions-league, europa-league`.

**Note:** an empty Active queue is often legitimate — e.g. on 2 Aug every MLS fixture read
`Expired`. Show "No upcoming fixtures in the selected leagues" rather than implying a fetch
failure, and surface `last_refreshed_at` on screen so a genuinely stalled job is visible.

---

## 6. Out of scope
Read-only. No wagering actions, no bet placement, no account links. This app does not ingest
`picks.json` from Edge Machine any more — it is fully self-contained.
