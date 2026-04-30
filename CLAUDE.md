# CLAUDE.md — Quant Trading System Agent Guide

> **READ THIS FIRST.** This file contains the critical rules and full context any agent needs before starting work in this repo. Follow all rules exactly.

---

## 🔴 CRITICAL RULES (Non-Negotiable)

### 1. Git Commit Policy — Lightweight Only
**Only commit these:**
- `outputs/live/latest_<symbol>_signal.json` — live signal JSONs
- `models/live/latest_model_manifest.json` — model manifest
- Code files: `.py`, `.sh`, `.md`, `.json` config (not large data)

**Never commit:**
- `figures/` — PNG charts (generated locally, Windows only)
- `outputs/11_*`, `outputs/21_*`, `outputs/31_*`, `outputs/41_*` — strategy optimization CSVs
- `outputs/rklb/`, `outputs/qqq/`, `outputs/brkb/` — anchor snapshots (too large, use rsync)
- `models/research/` — model artifacts (.pkl, .joblib)
- Any anchor `optimization_outputs/` directories (~43MB each)
- **NEVER use `git add .` or `git add -A`**

**Why:** repo already ballooned to 6GB+ from large file commits in the past. Branch had to be rebuilt. Anchor data is transferred via rsync, not git.

### 2. Branch Check Before Any Work
Always run `git branch -a` before starting work. Confirm which branch you're on and that it matches the intended work branch.

**Why:** parallel agents/sessions have written to wrong branches before (incident 2026-04-28 with `codex-pi-live-tranche-safety`).

### 3. Never Delete Anchor Records
Never delete or overwrite anchor snapshot directories. These represent months of computation.

**Why:** anchor records allow top-N analysis to be extended (e.g., top-10 → top-20) without recomputing. Each anchor takes 5–10 minutes to compute.

### 4. Email Report Design — Keep Current Format
When modifying `jobs/send_gld_email_alert.py`, preserve:
- Per-asset color headers (GLD=gold, BRK-B=blue, QQQ=green, RKLB=red)
- Inline price chart + weight panel
- Portfolio overview + color allocation bar
- Subject line: BUY assets + execution date + signal date

### 5. Email Test Rule — Owner Only
**When sending a test/dry-run email manually (not from Pi automation), always use `--test` flag:**
```bash
python jobs/send_gld_email_alert.py --test
```
- `--test`: sends to **owner only** (`joonchun1000@gmail.com`), subject prefixed `[TEST]`
- No flag: sends to all recipients (owner + Jack + ssherwood2) — **Pi production only**

**Why:** Students (Jack, ssherwood2) should not receive test/debug emails. Production emails come from Pi automation only.

---

## System Architecture

### Windows (Research Machine)
1. Runs anchor-date backtests: Lasso/Ridge/OLS/ElasticNet, top-N strategies, training data ≤ anchor date (no look-ahead)
2. Forward analysis: evaluates which top-N is best in the post-anchor period
3. **Commits only**: manifest + live signal JSONs + code
4. Chart/CSV generation stays on Windows only

### Raspberry Pi (Autonomous Execution)
Pi runs every trading day at 13:00 PT **without Windows involvement**:
1. `git pull` — check for new manifest/signal
2. Fill any missing price data gaps (yfinance)
3. Compute today's signal using active anchor model (if `build_signal_on_pi: true`)
4. Normalize weights:
   - Sum > 100% → scale all down proportionally
   - Sum ≤ 100% → remainder is cash
5. Place Alpaca limit orders (`extended_hours=True`, limit = price × 1.005)
6. Send email report (4-asset format)

**Pi access:** `ssh joonc@joon-pi`
**Pi path:** `/home/joonc/my_github/quant-trading-system`
**Pi branch:** `main`

---

## Asset Universe & Anchor Data

| Asset | Data CSV | Anchor Root | build_signal_on_pi | Windows Anchors | Pi Anchors |
|-------|----------|-------------|--------------------|-----------------|------------|
| GLD | `data/gld_us_d.csv` | `outputs/objective1_anchor_date_multi_horizon_evaluation/` | ✅ true | 64 (2019-12 to 2024-12) | ~79 (to 2026-03) |
| BRK-B | `data/brkb_us_d.csv` | `outputs/brkb/anchor_snapshots/` | ✅ true | 1 (2024-07-31 only) | ~79 (to 2026-03) |
| QQQ | `data/qqq_us_d.csv` | `outputs/qqq/anchor_snapshots/` | ❌ false | 79 (2019-12 to 2026-03) | — |
| RKLB | `data/rklb_us_d.csv` | `outputs/rklb/anchor_snapshots/` | ❌ false | 53 (2021-11 to 2026-03) | — |

**Anchor structure:** each anchor has:
- `optimization_outputs/` — per-family top-N ranked CSVs (~43MB/anchor)
- `strategy_top_candidates.csv` — summary (~100KB)
- `evaluation_<horizon>.json` — forward eval results

**Anchor transfer:** use `rsync` (not git) for large anchor data (43MB × 79 = ~3.4GB per asset).

### rsync commands (Pi → Windows)
```bash
# From Windows PowerShell or WSL:
rsync -av joonc@joon-pi:/home/joonc/my_github/quant-trading-system/outputs/brkb/anchor_snapshots/ outputs/brkb/anchor_snapshots/
rsync -av joonc@joon-pi:/home/joonc/my_github/quant-trading-system/outputs/objective1_anchor_date_multi_horizon_evaluation/ outputs/objective1_anchor_date_multi_horizon_evaluation/
```

---

## Live Signal Files

| File | Location | Updated By |
|------|----------|------------|
| GLD signal | `outputs/live/latest_gld_signal.json` | Pi (build_signal_on_pi) |
| BRK-B signal | `outputs/live/latest_brkb_signal.json` | Pi (build_signal_on_pi) |
| QQQ signal | `outputs/live/latest_qqq_signal.json` | Windows → push |
| RKLB signal | `outputs/live/latest_rklb_signal.json` | Windows → push |
| Signal history | `outputs/live/history/<symbol>_signal_log.csv` | appended each run |

---

## Model Manifest

`models/live/latest_model_manifest.json`
- `top_n_per_family: 20` for all assets
- `target_horizon_days: 130`
- `selection_criterion: selection_cv_mse`
- `update_interval_months: 1`

---

## Active Research: Oracle / Portfolio Forward Backtest

**Goal:** Simulate the 4-asset portfolio historically (2021-11 to present):
- Each month-end anchor → fit model → compute signal for each asset
- Normalize weights across 4 assets
- Hold 1 month → compute actual portfolio return
- Track cumulative equity curve vs. buy-and-hold benchmarks

**Status (as of 2026-04-29):**
- GLD: Windows has 64 anchors (2019-12 to 2024-12) ✓
- BRK-B: Pi has all anchors, Windows has 1 — **need rsync from Pi**
- QQQ: Windows has 79 anchors ✓
- RKLB: Windows has 53 anchors ✓

**Next step:** rsync BRK-B (and GLD 2025-2026) from Pi, then build `run_portfolio_forward_backtest.py`.

---

## Pipeline Files

| File | Purpose |
|------|---------|
| `jobs/gld_daily_pipeline.py` | Main daily pipeline (Pi runs this) |
| `jobs/gld_tranche_order_job.py` | Alpaca limit order placement |
| `jobs/send_gld_email_alert.py` | 4-asset email report |
| `jobs/update_gld_daily_data.py` | Price data updater |
| `strategies/automation/run_objective2_latest_live_signal.py` | Build live signal for one asset |
| `strategies/automation/run_objective2_monthly_update_tranche_backtest.py` | Per-asset monthly backtest |
| `deploy/raspberry_pi/run_daily_pipeline.sh` | Pi wrapper script |

---

## Branch Strategy

- **Windows:** `work/pi-manifest-top20` (transitioning → `main`)
- **Pi:** `main`
- **Pending:** merge `work/pi-manifest-top20` → `main`, then both use `main`

---

## Alpaca Paper Trading

- Paper account, `TRANCHE_TOTAL_CAPITAL=10,000`
- Order type: `LimitOrderRequest`, `TimeInForce.DAY`, `extended_hours=True`, limit = price × 1.005
- `ALPACA_DRY_RUN=false` (real paper orders since 2026-04-28)
- Email: `joonchun1000@gmail.com`, `jpugh7@ucmerced.edu`
