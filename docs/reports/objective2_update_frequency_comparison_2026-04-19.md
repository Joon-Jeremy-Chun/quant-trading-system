# Objective 2 Update-Frequency Comparison (cv_mse revision)

Date: 2026-04-19

## What Changed from Previous Report

This report supersedes `objective2_update_frequency_comparison_2026-04-17.md`.

Two key code fixes were applied before re-running:

1. **Fear-Greed look-ahead removed** — `shift(-1)` confirmation using next-day close was eliminated. Signal now fires on current-day candle pattern only.
2. **Model selection criterion changed** — from `selection_correlation` (in-sample, OLS always won) to `selection_cv_mse` (TimeSeriesSplit cross-validation). OLS no longer dominates.

## Holding Structure (unchanged)

- holding horizon: `130` trading days
- one new tranche per day
- each tranche held for the full `130` days
- long-only position sizing in `[0, 1]`

## 1M Update Results (new cv_mse code)

| Year | Buy & Hold | Strategy | Excess | Avg Exposure | Dominant Model |
|---|---:|---:|---:|---:|---|
| 2020 | +20.22% | +8.87% | -11.35% | 57.44% | lasso |
| 2021 | -6.24% | +0.76% | **+6.99%** | 29.19% | elastic_net |
| 2022 | +0.78% | -0.18% | -0.96% | 31.39% | ridge |
| 2023 | +11.76% | +4.05% | -7.71% | 32.47% | ridge |
| 2024 | +26.96% | +16.42% | -10.54% | 65.34% | lasso |

## Comparison vs Previous Code (1M, 130-day hold)

| Year | Old Strategy (correlation) | New Strategy (cv_mse) | Change |
|---|---:|---:|---:|
| 2020 | +6.76% | +8.87% | **+2.11%p** |
| 2021 | +0.00% | +0.76% | **+0.76%p** |
| 2022 | -0.30% | -0.18% | **+0.12%p** |
| 2023 | +3.01% | +4.05% | **+1.04%p** |
| 2024 | +7.40% | +16.42% | **+9.02%p** |

CV-based model selection improved every single year. 2024 saw the largest gain (+9%p).

## Key Observations

### 1. OLS no longer dominates
Previous code selected OLS nearly 100% of the time (in-sample correlation = 0.99+, perfect directional accuracy = 1.0 — clear overfitting). New code selects Ridge, Lasso, and ElasticNet depending on the month, which is the expected behavior of regularized model selection.

### 2. 2021 is the standout defensive year
The only year where strategy beat buy-and-hold (+6.99% excess). This matches the previous finding that monthly updating is most useful in defensive/negative regimes.

### 3. Strategy still lags buy-and-hold in bull years
2020, 2023, 2024 were strong GLD years and the strategy under-allocated (exposure well below 100%). This is expected in a long-only system with conservative weight scaling.

### 4. Update frequency analysis needs re-run
The previous update-frequency table (1M vs 2M vs 3M vs 6M) was computed under the old code. Those numbers are now stale. A fresh multi-frequency comparison run is needed to update the working interpretation of "which cadence is best per regime."

## Next Steps

1. Re-run `run_objective2_monthly_update_tranche_backtest.py` with `--update-interval-months 2`, `3`, `6` for all years using the new cv_mse code.
2. Rebuild the comparison table and update the working interpretation.
3. Consider whether anchor snapshots (objective1) need regeneration given the fear-greed parameter change.

## Related Files

- `objective2_update_frequency_comparison_2026-04-17.md` — previous version (selection_correlation)
- `objective2_update_frequency_one_page_summary_2026-04-17.md` — compact summary of previous results
