# CLAUDE.md

This file documents how to work safely and consistently in this project.

## Project purpose

Track marathon preparation by combining:
- football session exports (`export.csv`),
- Strava activities (synced from Garmin via Strava API),
- a structured marathon plan CSV,
- and publish a GitHub Pages dashboard (`docs/`).

## Core files

- `analisis.py`
  - Main analytics pipeline.
  - Generates outputs in `analysis_output/`.
  - Publishes web assets/data into `docs/`.
- `sync_strava.py`
  - Incremental Strava API sync (OAuth + refresh token).
  - Writes canonical activities file to `strava_sync/activities.csv`.
- `run_sync_and_analysis.bat`
  - Full scheduled pipeline:
    1) sync Strava
    2) run analysis
    3) auto-publish docs (if changed)
- `auto_publish_docs.py`
  - Git automation for `docs/` updates (commit/push only when changed).
- `docs/index.html`, `docs/styles.css`, `docs/feed.js`
  - Frontend for GitHub Pages dashboard.

## Data assumptions

- Running data is frequent (from Strava sync).
- Football data can be manually added and sparse (e.g., monthly).
- Missing football weeks must be treated as **unknown**, not zero load.
- Combined football+running metrics should be gated by football data coverage.

## Expected workflow

### Manual run

```powershell
py sync_strava.py
py analisis.py --strava "strava_sync/activities.csv" --site-dir "docs" --plan-pdf "plan_maraton_hibrido_visual.pdf"
```

### Scheduled run

```powershell
run_sync_and_analysis.bat
```

### Task setup (every 2 days)

```powershell
powershell -ExecutionPolicy Bypass -File setup_strava_task.ps1
```

## Security and secrets

- Use `.env` only for credentials:
  - `STRAVA_CLIENT_ID`
  - `STRAVA_CLIENT_SECRET`
  - optional: `GITHUB_AUTO_PUBLISH=1`
- Never hardcode secrets in scripts.
- Keep tokens/state/logs out of git:
  - `strava_sync/strava_tokens.json`
  - `strava_sync/sync_state.json`
  - `logs/`

## Output contracts

`analisis.py` should keep producing at least:
- `analysis_output/report.md`
- `analysis_output/report.html`
- `analysis_output/weekly_metrics.csv`
- `analysis_output/plan_vs_actual.csv`
- `analysis_output/target_ranges_to_october.csv`
- plots used by dashboard
- `docs/data/meta.json` with freshness/coverage fields

## Frontend behavior requirements

- Dashboard has 3 separate feeds:
  1) run-only (default),
  2) combined analysis,
  3) football-only.
- Feed switching is controlled by navbar buttons.
- Info popups explain each chart/section and what to look for.
- Combined cards must show `n/a` when football coverage is insufficient.

## Coding guidance

- Prefer minimal, deterministic changes.
- Preserve backward compatibility of CSV columns when possible.
- Add clear coverage/freshness notes instead of inventing data.
- If data sufficiency is low, prefer explicit `n/a` + explanation over noisy estimates.
