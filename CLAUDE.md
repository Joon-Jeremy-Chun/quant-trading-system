# CLAUDE.md — Quant Trading System Agent Guide

> **READ THIS FIRST.** This file contains the critical rules and full context any agent needs before starting work in this repo. Follow all rules exactly.

---

## 🔴 CRITICAL RULES (Non-Negotiable)

### 1. Git Commit Policy — Lightweight Only
**Only commit these:**
- `outputs/live/latest_<symbol>_signal.json` — live signal JSONs
- `outputs/live/history/<symbol>_signal_log.csv` — signal history logs
- `models/live/latest_model_manifest.json` — model manifest
- `models/live_assets/active_universe.json` — universe + override commands
- Code files: `.py`, `.sh`, `.md`, `.json` config (not large data)

**Never commit:**
- `figures/` — PNG charts (generated locally, Windows only)
- `outputs/11_*`, `outputs/21_*`, `outputs/31_*`, `outputs/41_*` — strategy optimization CSVs
- `outputs/rklb/`, `outputs/qqq/`, `outputs/brkb/`, `outputs/ita/`, `outputs/vrt/` — anchor snapshots
- `models/research/` — model artifacts (.pkl, .joblib)
- Any anchor `optimization_outputs/` directories (~43MB each)
- `outputs/bootstrap/` — bootstrap simulation outputs
- **NEVER use `git add .` or `git add -A`**

**Why:** repo already ballooned to 6GB+ from large file commits in the past.

### 2. Branch Check Before Any Work
Always run `git branch -a` before starting work.
- **Windows:** `work/pi-manifest-top20` (pushes to `origin/main`)
- **Pi:** `main`

**Why:** parallel agents/sessions have written to wrong branches before.

### 3. Never Delete Anchor Records
Never delete or overwrite anchor snapshot directories. These represent months of computation.

### 4. Email Report Design — Keep Current Format
When modifying `jobs/send_live_daily_report.py`, preserve:
- Per-asset color headers (GLD=gold, BRK-B=blue, QQQ=green, RKLB=red)
- Inline price chart + weight panel (back-predicted from active anchor model)
- Portfolio overview + color allocation bar
- Subject line: BUY assets + execution date + signal date

### 5. Email Test Rule — Owner Only
```bash
python jobs/send_live_daily_report.py --test   # owner only [TEST] prefix
python jobs/send_live_daily_report.py          # all recipients — Pi production only
```

### 6. Signal Freshness Rule — 7-Day Minimum Anchor Age
Signals must use the **most recent anchor where anchor_date ≤ today − 7 days**.
- Check with: `python scripts/check_and_refresh_signals.py --dry-run`
- Rebuild + push: `python scripts/check_and_refresh_signals.py`
- Run this monthly (especially 3 days before month-end) or when starting a session.

---

## Project Architecture (Sub-Guidelines)

### Layer Structure

| Layer | Role | Status |
|-------|------|--------|
| **Layer 0** | Asset selection via unsupervised algorithm (DTW distance) | Active research |
| **Layer 1+2** | Validate selected assets via Objective 1+2 backtests | Production |
| **Layer 3** | SINDy nonlinear position sizing | Future |

**Flow:** Layer 0 selects candidates → Layer 1+2 verifies utility → Pi executes.

### The Masterpiece Principle
**Pi reads ONE folder: `models/pi_reference/`**. This is the "masterpiece" — everything Pi needs to run independently.

```
models/pi_reference/
  GLD/
    anchor_2026-04-29/      ← latest anchor (optimization_outputs inside)
    anchor_2026-03-31/      ← fallback
  BRK-B/
    anchor_2026-04-29/
    anchor_2026-03-31/
models/live_assets/
  active_universe.json      ← which assets + override commands
models/live/
  latest_model_manifest.json
```

**Pi independence:** If Windows fails to update for weeks, Pi continues running using the last uploaded anchor in `models/pi_reference/`. No Windows dependency at runtime.

### 130-Day Delta Tranche Mechanism (Core Execution)

```
Daily order = (today_weight - weight_130d_ago) / 130 × CAPITAL

  delta > 0  → BUY
  delta < 0  → SELL
  delta ≈ 0  → HOLD
```

- **New asset entry:** bootstrap buy (full 130-day accumulated position, one-time) OR tranche backfill from `daily_weights.csv` — decided case-by-case
- **Asset removal:** full exit OR gradual — decided case-by-case
- **Override commands** in `active_universe.json` take priority:

| Command | Meaning |
|---------|---------|
| `"buy_hold"` | Hold position, skip delta (bull market hidden card) |
| `"sell_hold"` | Hold position, skip delta (defense) |
| `"force_exit"` | Immediately sell entire accumulated position |
| (none) | Automatic 130-day delta mechanism |

---

## Windows Automation (Research Machine)

### Daily/Monthly Tasks
```bash
# Check if signals are using latest valid anchor (run before sessions or monthly)
python scripts/check_and_refresh_signals.py --dry-run   # preview
python scripts/check_and_refresh_signals.py             # rebuild + push

# Bootstrap simulation (when adding new assets)
python scripts/simulate_tranche_bootstrap.py

# Monthly anchor refresh (after new month-end anchor computed)
python scripts/monthly_anchor_refresh.py
```

### When Adding a New Asset
1. Compute anchors: `run_objective1_anchor_date_multi_horizon_evaluation.py --n-jobs -1`
2. Copy latest 2 anchors to `models/pi_reference/<ASSET>/`
3. Update `models/live_assets/active_universe.json` (add to `assets`)
4. Update `models/live/latest_model_manifest.json`
5. Run `scripts/check_and_refresh_signals.py` → push
6. Decide bootstrap mode (lump sum or tranche backfill) and execute

---

## Pi Automation (Raspberry Pi)

**Pi access:** `ssh joonc@joon-pi`
**Pi path:** `/home/joonc/my_github/quant-trading-system`
**Pi branch:** `main`

### 3-Timer Daily Loop

| Time (PT) | Service | Script | Action |
|-----------|---------|--------|--------|
| 09:00 | `quant-git-pull` | `git pull` | Fetch latest masterpiece from GitHub |
| 12:45 | `quant-pipeline` | `run_daily_pipeline.sh` | Rebuild GLD/BRK-B signals using `models/pi_reference/` |
| 13:00 | `quant-order-execution` | `run_order_execution.sh` | Validate all 4 signals → delta_tranche → email |

```bash
# Check timer status on Pi:
sudo systemctl list-timers quant-* --all

# View execution logs:
journalctl -u quant-order-execution.service -n 50
journalctl -u quant-pipeline.service -n 50
```

### Signal Flow by Asset

| Asset | Signal Built By | Anchor Source |
|-------|----------------|---------------|
| GLD | Pi (12:45) | `models/pi_reference/GLD/` — latest anchor |
| BRK-B | Pi (12:45) | `models/pi_reference/BRK-B/` — latest anchor |
| QQQ | Windows → git push | `outputs/qqq/anchor_snapshots/` |
| RKLB | Windows → git push | `outputs/rklb/anchor_snapshots/` |
| ITA | Windows → git push (pending_review) | `outputs/ita/anchor_snapshots/` |
| VRT | Windows → git push (pending_review) | `outputs/vrt/anchor_snapshots/` |

### Pi Environment
- `deploy/raspberry_pi/quant-trading.env` — API keys, LIVE_SYMBOLS, ALPACA_DRY_RUN
- `ALPACA_DRY_RUN=false` (real paper orders)
- `LIVE_SYMBOLS=GLD,BRK-B,QQQ,RKLB`
- `MAX_SIGNAL_AGE_DAYS=30`, `MAX_DATASET_STALENESS_DAYS=30`
- `.venv/bin/python` — virtualenv with all dependencies

### Pi Maintenance Checklist
When Pi has issues or model needs refresh:
1. `ssh joonc@joon-pi && cd /home/joonc/my_github/quant-trading-system`
2. `git log --oneline -3` — confirm latest commits pulled
3. Check `models/pi_reference/GLD/` and `BRK-B/` have latest month-end anchor
4. If missing anchor: compute on Windows → scp to Pi → done
5. `sudo systemctl list-timers quant-* --all` — confirm timers active

---

## Asset Universe

### Active (Production)

| Asset | Data CSV | Windows Anchor Root | Anchors | Notes |
|-------|----------|---------------------|---------|-------|
| GLD | `data/gld_us_d.csv` | `outputs/objective1_anchor_date_multi_horizon_evaluation/` | 138 (2015-02 to 2026-04) | Pi reference: `models/pi_reference/GLD/` |
| BRK-B | `data/brkb_us_d.csv` | `outputs/brkb/anchor_snapshots/` | 77 (2019-12 to 2026-04) | Pi reference: `models/pi_reference/BRK-B/` |
| QQQ | `data/qqq_us_d.csv` | `outputs/qqq/anchor_snapshots/` | 75 (2019-12 to 2026-04) | Windows builds signal, pushes |
| RKLB | `data/rklb_us_d.csv` | `outputs/rklb/anchor_snapshots/` | 54 (2021-11 to 2026-04) | Windows builds signal, pushes |

### Pending Review (Forward Test Needed)

| Asset | Anchors | Notes |
|-------|---------|-------|
| ITA | 111 (2016-12 to 2026-02) | Signal computed, add to `assets` after forward validation |
| VRT | 81 (2019-07 to 2026-03) | Signal computed, add to `assets` after forward validation |

---

## Key Files

| File | Purpose |
|------|---------|
| `jobs/live_daily_pipeline.py` | Main pipeline orchestrator |
| `jobs/execute_delta_tranche_orders.py` | 130-day delta buy/sell + override handler |
| `jobs/execute_bootstrap_buy.py` | One-time bootstrap buy (new asset entry) |
| `jobs/send_live_daily_report.py` | 4-asset HTML email (back-predict weight panel) |
| `jobs/update_daily_price_data.py` | Price data updater (yfinance) |
| `deploy/raspberry_pi/run_daily_pipeline.sh` | Pi 12:45 — signal prep (GLD/BRK-B) |
| `deploy/raspberry_pi/run_order_execution.sh` | Pi 13:00 — orders + email |
| `scripts/check_and_refresh_signals.py` | Windows: check anchor freshness + auto-rebuild |
| `scripts/simulate_tranche_bootstrap.py` | Compute bootstrap position from oracle history |
| `scripts/monthly_anchor_refresh.py` | Copy new anchor to pi_reference after computation |
| `models/live_assets/active_universe.json` | Universe + override commands (Pi reads this) |
| `models/live/latest_model_manifest.json` | Per-asset model params + anchor_output_root |
| `outputs/live/tranche_log.csv` | Daily weight log (130-day rolling history) |
| `outputs/live/latest_<slug>_signal.json` | Latest live signal per asset |

---

## Tranche Log & Bootstrap

- `outputs/live/tranche_log.csv` — daily `w_GLD, w_BRK-B, w_QQQ, w_RKLB` columns
- `outputs/bootstrap/bootstrap_position.json` — one-time bootstrap quantities (gitignored, scp to Pi)
- `outputs/bootstrap/daily_weights.csv` — oracle simulation weights (for tranche backfill option)

**Bootstrap modes (decide per asset per situation):**
- **Lump sum:** buy full accumulated position once (`execute_bootstrap_buy.py`), tranche log has sim history
- **Tranche backfill:** fill `tranche_log.csv` with past simulated weights → delta mechanism takes over naturally

---

## Alpaca Paper Trading

- Paper account, `TRANCHE_TOTAL_CAPITAL=10,000`
- `LimitOrderRequest`, `TimeInForce.DAY`, `extended_hours=True`
- BUY limit = price × 1.005, SELL limit = price × 0.995
- `ALPACA_DRY_RUN=false` (live paper orders since 2026-04-28)
- Recipients: `joonchun1000@gmail.com`, `jpugh7@ucmerced.edu`, `ssherwood2@ucmerced.edu`
