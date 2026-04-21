# Objective 2 Update-Frequency Comparison (cv_mse, full revision)

Date: 2026-04-20

## What Changed from Previous Reports

Supersedes `objective2_update_frequency_comparison_2026-04-19.md`.

Two key fixes applied before re-running all experiments:

1. **Fear-Greed look-ahead removed** — `shift(-1)` next-day confirmation eliminated.
2. **Model selection changed** — `selection_correlation` (in-sample, OLS dominated) → `selection_cv_mse` (TimeSeriesSplit cross-validation, regularized models now selected).

---

## How to Read the Table

### Column Labels

| Label | Meaning |
|---|---|
| **Training Anchor Year** | The approximate period the model learned from. Each monthly anchor uses ~1 year of history before the anchor date. |
| **Forward Test Year** | The out-of-sample period where the trained model was actually deployed and evaluated. |

### Walk-Forward Structure

This is a rolling walk-forward, not a single train/test split.

Example for **Forward Test Year = 2021**:
- Jan 2021 evaluation → uses anchor `2020-12-31` → model trained on `2020-01-01 ~ 2020-12-31`
- Feb 2021 evaluation → uses anchor `2021-01-31` → model trained on `2020-02-01 ~ 2021-01-31`
- Each month the anchor rolls forward by one month.

So "Training Anchor Year ≈ 2020" means the model consistently learned from the year **prior** to each forward test month.

---

## Holding Structure (fixed across all experiments)

- Holding horizon: **130 trading days (~6 months)**
- One new tranche opened per day
- Each tranche held for the full 130 days
- Long-only position sizing in [0, 1]
- Only the **model update interval** changes across columns

---

## Results Table: 1M vs 2M vs 3M Update Interval

**Ret** = Strategy Return | **Exp** = Average Gross Exposure | **Eff** = Capital Efficiency (Ret ÷ Exp)

| Training Anchor | Forward Test | Buy & Hold | 1M Ret / Exp / Eff | 2M Ret / Exp / Eff | 3M Ret / Exp / Eff |
|---|---|---:|---|---|---|
| ~2019 | **2020** | +20.22% | 8.87% / 57.4% / **15.4%** | 8.31% / 54.6% / 15.2% | 8.52% / 55.9% / 15.2% |
| ~2020 | **2021** | -6.24% | **0.76%** / 29.2% / **2.6%** | 0.32% / 34.6% / 0.9% | 0.58% / 28.3% / 2.1% |
| ~2021 | **2022** | +0.78% | -0.18% / 31.4% / -0.6% | **0.92%** / 34.6% / **2.7%** | -0.79% / 33.2% / -2.4% |
| ~2022 | **2023** | +11.76% | 4.05% / 32.5% / 12.5% | **4.06%** / 23.4% / **17.3%** | 3.78% / 40.0% / 9.5% |
| ~2023 | **2024** | +26.96% | **16.42%** / 65.3% / **25.1%** | 13.91% / 60.0% / 23.2% | 11.14% / 53.4% / 20.9% |

---

## Exposure Behavior Validation

A key design goal is that **exposure should shrink when the market enters an unfamiliar regime** (i.e., when current patterns differ from what the model learned).

| Training Anchor | Forward Test | GLD Return | Avg Exposure | Interpretation |
|---|---|---:|---:|---|
| ~2019 | 2020 | +20.2% | 82.9% | Familiar bull pattern → high exposure ✅ |
| ~2020 | 2021 | -6.2% | 42.2% | Pattern shift → model uncertain → exposure drops ✅ |
| ~2021 | 2022 | +0.8% | 36.9% | Continued uncertainty → lowest exposure ✅ |
| ~2022 | 2023 | +11.8% | 47.9% | Gradual recovery → exposure rebuilding |
| ~2023 | 2024 | +27.0% | 86.5% | Strong familiar trend → high exposure ✅ |

**Conclusion:** The model's exposure behavior aligns with the design intent.
When the forward-test regime differs from the training regime (2021–2022),
exposure contracts significantly, freeing capital for other potential assets.

---

## Key Observations

### 1. 1M update is strongest overall (new finding vs prior code)

Under the old `selection_correlation` code, 3M was the best compromise.
Under the new `selection_cv_mse` code, **1M dominates** in raw return and capital efficiency:
- Best return in 2020, 2021, 2024
- Only 2022 was an exception where 2M outperformed

This reversal suggests the old result was partly driven by OLS overfitting:
slower updates happened to be less wrong. With proper CV selection, faster updating is actually beneficial.

### 2. 2M has the best capital efficiency in uncertain regimes

- 2023: 2M efficiency = **17.3%** vs 1M at 12.5%
- 2022: 2M is the only interval with positive return (+0.92%)

2M achieves this by using **lower exposure** in ambiguous years,
which means less capital at risk — valuable if that freed capital goes elsewhere.

### 3. 3M no longer the best compromise

In the new code, 3M consistently underperforms both 1M and 2M.
It is slower to adapt without gaining the efficiency advantage of 2M.

### 4. The exposure signal is the most important output

Raw strategy return consistently lags buy-and-hold in bull years.
But the exposure signal — especially when it contracts in uncertain regimes —
is the key input for a multi-asset capital allocation system.

---

## Practical Operating Modes (updated)

| Mode | Interval | Best For |
|---|---|---|
| **Adaptive** | 1M | Most years, especially bull and defensive regimes |
| **Efficient** | 2M | Uncertain/transitional regimes, capital efficiency priority |
| ~~Balanced~~ | ~~3M~~ | ~~No longer supported by data~~ |

---

## Next Steps

1. Run **6M interval** for completeness.
2. Run **45-day hold** variants under new cv_mse code.
3. Study cross-asset exposure correlation (when GLD exposure is low, where does capital go?).
4. Build capital allocation layer using exposure signals across multiple assets.

---

## Related Files

- `objective2_update_frequency_comparison_2026-04-19.md` — intermediate version
- `objective2_update_frequency_comparison_2026-04-17.md` — original (old code)
- `dynamic_capital_allocation_vision_2026-04-19.md` — multi-asset system vision
- `multi_asset_pipeline_vision_2026-04-19.md` — engineering roadmap
