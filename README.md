# Edge Machine

Paper-tracked betting research: a local tracker plus a self-updating public board.
Nothing here places bets — every surface is read-only, and results are recorded to test
whether an idea actually holds up.

**Live boards → https://aliu2298.github.io/edge-machine/**

| Board | What it is |
|---|---|
| [Sports](https://aliu2298.github.io/edge-machine/) | Picks made in the local tracker |
| [Earnings](https://aliu2298.github.io/edge-machine/earnings.html) | Kalshi company-quarterly (KPI) positions |
| [Tips](https://aliu2298.github.io/edge-machine/tips.html) | sportsgambler.com's published predictions, scraped and graded |

The three boards are deliberately **separate** — different sources, different edges, no merging.

## Architecture

```mermaid
flowchart TB
    subgraph CI["GitHub Actions — daily cron, free on public repos"]
        direction TB
        SC["sg_scrape.py<br/>10 league index pages → match pages"]
        SE["sg_settle.py<br/>grade vs final scores"]
        SB["sg_build.py<br/>render tips board"]
        EX["export_public.py<br/>render sports + earnings boards"]
        SC --> SE --> SB --> EX
    end

    subgraph EXT["External sources (public, no auth)"]
        SG["sportsgambler.com<br/>projected score · BTTS · tip"]
        ESPN["ESPN scoreboard<br/>final scores"]
        KAL["Kalshi public API<br/>market links"]
    end

    subgraph REPO["Repo (committed)"]
        SGJ["data/sg_picks.json"]
        PJ["data/predictions.json<br/>mirror of predictions table only"]
        OUT["public_site/<br/>index · earnings · tips"]
    end

    subgraph LOCAL["Local Mac (optional)"]
        APP["app.py :8787<br/>+ web/ React UI"]
        DB[("predictions.db<br/>GITIGNORED")]
        APP <--> DB
    end

    SG --> SC
    ESPN --> SE
    KAL -.link lookup.-> SB
    KAL -.link lookup.-> EX

    SC --> SGJ
    SGJ --> SE --> SGJ
    SGJ --> SB --> OUT
    PJ --> EX --> OUT
    DB -.mirrors predictions table.-> PJ

    OUT --> PAGES["GitHub Pages<br/>aliu2298.github.io/edge-machine"]

    style DB fill:#3a1f1f,stroke:#e06c75,color:#eee
    style PAGES fill:#1f3a2a,stroke:#3fb970,color:#eee
    style CI fill:#161b26,stroke:#2b3245,color:#eee
```

The pipeline runs entirely on GitHub's servers, so the boards stay current whether or not
the Mac is on. The local tracker is where picks get made; the mirror is how they reach CI.

## Components

| File | Role |
|---|---|
| `app.py` | Local tracker: stdlib HTTP server + SQLite. Picks, slate, base rates, auto-settlement. |
| `web/` | React + Vite + Tailwind UI for the tracker (`npm --prefix web run build`). |
| `sg_scrape.py` | Scrapes sportsgambler for 10 leagues — projected score, BTTS odds, published tip. |
| `sg_settle.py` | Grades scraped tips against ESPN final scores. |
| `sg_build.py` | Renders `public_site/tips.html`. |
| `export_public.py` | Renders the sports + earnings boards; mirrors the predictions table to JSON. |
| `.github/workflows/refresh-tips.yml` | Daily cron: scrape → settle → build → publish to Pages. |

## Run locally

```bash
python3 app.py            # tracker UI + API on :8787
npm --prefix web run dev  # frontend dev server on :5173
```

Rebuild the public boards by hand:

```bash
python3 sg_scrape.py && python3 sg_settle.py && python3 sg_build.py && python3 export_public.py
```

## Data handling

`predictions.db` is **git-ignored** and stays local. It holds `kalshi_orders`, `kalshi_bets`
and `kalshi_config` alongside the picks, so the raw database is never committed. Only the
`predictions` table is mirrored to `data/predictions.json` — the same pick, odds, stake and
result fields already shown on the public boards, with no keys, tokens or balances.

Secrets (`.apifootball_key`, `.kalshi_key`, `.kalshi_pem`, `*.pem`) are git-ignored. A fresh
checkout creates empty tables on first run.

## Notes

Odds from sportsgambler are American and converted to decimal on ingest. Quarter-line Asian
handicaps (`+0.25` / `+0.75`) settle as half win / half loss. Anything that cannot be graded
with confidence is marked `ungraded` with a null P/L rather than being silently scored a loss.

Picks are research, not betting advice.
