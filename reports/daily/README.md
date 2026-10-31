# Daily health reports

The twice-daily cloud health check (7:30 AM and 7:30 PM Central) writes one file here per run and
emails the same text to Olu. The Sandbox page's "Daily health" card is built from the newest file.

## File name

`YYYY-MM-DD-am.md` for the morning run and `YYYY-MM-DD-pm.md` for the evening run, dated in Central time.
One file per run; a rerun of the same slot replaces its file.

## Format

```
All green
Checked 2026-10-31 07:30 CT
- green · Trading engine · running, LIVE, cycle 41210, last beat 40 s ago
- amber · Sandbox Tracker · last run 4.6 h ago (expected every 3 h)
- red · Chaos replay · failed on its last run
```

1. **Line 1, the verdict:** exactly `All green`, or `N red, N amber` (for example `1 red, 2 amber`, or
   `0 red, 1 amber`).
2. **Line 2:** `Checked YYYY-MM-DD HH:MM CT`.
3. **Every later line is one component:** `- <green|amber|red> · <component> · <detail>`, all lower case for
   the status and separated by ` · `. One line per component, reds first, then ambers, then greens.

Nothing else goes in the file. The card shows line 1, the time, and every red and amber line.

## What a report must never carry

edge-machine is a public repository. A report carries **status only**:

- **No money amounts.** No balances, P&L, fees, positions or loss figures, and no `$` anywhere. Say a
  balance is `OK` or `LOW` and P&L is `up`, `down` or `flat`, as `data/bot_health.json` does.
- **No secrets or identifiers.** No keys, tokens, account ids or order ids.

`test_bot_health.py` fails on any file here with a `$` amount or a key-like string, so a report that breaks
this rule turns the tests red until it is fixed.

## The engine's part: data/bot_health.json

edge-vps publishes `data/bot_health.json` every hour at :23 (`edge-health.timer`, `scripts/vps_bot_health.sh`,
`bot_health.py`). It holds status only:

- the engine's state, LIVE or dry, its cycle and last beat
- orders in the last 24 h by venue
- open errors (scope and short text, numbers removed), the count cleared since, and warning counts by type
- each feed's age and lead counts
- whether the daily loss cap is blocking orders (yes or no)
- each venue's balance as `OK` or `LOW`, from the engine's own day-start read. The threshold is set on the
  server only (`BOT_HEALTH_LOW_USD`, $50 by default) and is never published.
- the sign of today's and yesterday's P&L
- disk use, free memory, the newest backup's age, each scheduled job's last result, and `published_at`

A `published_at` more than about 2 hours old means the publisher itself has stopped: report that as red.
