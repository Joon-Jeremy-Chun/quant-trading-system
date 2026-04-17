# Objective 2 Update-Frequency Comparison

Date: 2026-04-17

## Purpose

This note extends the earlier update-frequency comparison to include `2020`, so the sample now covers:

- `2020`
- `2021`
- `2022`
- `2023`
- `2024`

The holding structure is fixed while the model refresh cadence changes:

- holding horizon: `130` trading days
- one new tranche per day
- each tranche held for the full `130` days
- long-only position sizing in `[0, 1]`

The only thing that changes across the experiments is the **model update interval**:

- `1M` = refresh every month
- `2M` = refresh every 2 months
- `3M` = refresh every 3 months
- `6M` = refresh every 6 months

The question remains:

**If the portfolio still behaves like a long-horizon 130-day system, how fast should the predictive model be updated?**

## Metric Notes

- `Return` means the full strategy return over the evaluation year.
- `Exposure` means average gross market exposure during that year.
- `100%-Eq Return` is a simple capital-efficiency proxy:

\[
\text{100%-Eq Return} \approx \frac{\text{Strategy Return}}{\text{Average Exposure}}
\]

This is **not** a true leveraged backtest. It is only a rough way to compare how efficiently each update schedule used its average market exposure.

## Table 1: 130-Day Hold, Update-Frequency Comparison

| Year | Buy & Hold | 1M Return | 1M Exposure | 1M 100%-Eq | 2M Return | 2M Exposure | 2M 100%-Eq | 3M Return | 3M Exposure | 3M 100%-Eq | 6M Return | 6M Exposure | 6M 100%-Eq |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 20.2211% | 6.7614% | 45.2789% | 14.9327% | 9.4044% | 53.3081% | 17.6416% | 10.0860% | 55.4897% | 18.1764% | 10.9232% | 63.0398% | 17.3275% |
| 2021 | -6.2359% | 0.0020% | 36.1391% | 0.0056% | -0.0506% | 35.4424% | -0.1428% | -0.5980% | 44.7598% | -1.3360% | -0.2995% | 42.2052% | -0.7096% |
| 2022 | 0.7782% | -0.3044% | 39.6831% | -0.7670% | 1.2746% | 26.6312% | 4.7863% | 0.3493% | 42.4060% | 0.8237% | 2.5382% | 36.3462% | 6.9833% |
| 2023 | 11.7561% | 3.0146% | 27.7378% | 10.8683% | 1.5199% | 17.1571% | 8.8587% | 3.6508% | 23.0441% | 15.8429% | 4.2488% | 18.7912% | 22.6107% |
| 2024 | 26.9557% | 7.4039% | 39.2416% | 18.8674% | 4.3261% | 26.8949% | 16.0852% | 9.3277% | 46.9183% | 19.8807% | 5.2560% | 27.1777% | 19.3393% |

## Main Observations

### 1. Faster updating is still not universally better

The extended sample still does **not** support a simple rule such as “update as often as possible.”

- `2020`: `3M` looked best on efficiency, while `6M` had the best absolute return
- `2021`: `1M` looked best
- `2022`: `6M` looked best
- `2023`: `6M` looked best
- `2024`: `3M` looked best

So even after adding one more year, the best update frequency remains regime-dependent.

### 2. Two-month updating still does not dominate

The intuition that `2M` might work well because it is numerically close to the practical `45-day` scale still does **not** emerge as a dominant pattern in the fixed `130-day` holding experiment.

- It was respectable in `2020` and `2022`
- It lagged `3M` and `6M` in `2023`
- It also lagged `1M` and `3M` in `2024`

So a refresh cadence near 45 calendar days does not automatically become optimal just because it is numerically close to the shorter trading horizon.

### 3. Quarterly updating still looks like the best broad compromise

Across `2020~2024`, `3M` continues to look like a strong middle-ground candidate.

- It was the most efficient schedule in `2020`
- It was the best schedule in `2024`
- It stayed competitive in `2022` and `2023`

This keeps the same qualitative interpretation:

- slower than `1M`, so less likely to chase noise
- faster than `6M`, so better able to adapt during transitions

### 4. Semiannual updating still benefits from persistent regimes

`6M` remained strongest in `2022` and `2023`, and it also had the highest **absolute** return in `2020`.

This reinforces the earlier reading:

- when the dominant regime is persistent enough,
- slower re-optimization can be more efficient,
- and sometimes even stronger in raw return.

### 5. Monthly updating remains the most adaptive / defensive mode

`1M` was still strongest in `2021`, the year where buy-and-hold was clearly negative.

That keeps the same practical interpretation:

- `1M` is the most adaptive mode
- it may help most in defensive environments or unstable transitions

## Working Interpretation

At this stage, the extended evidence still points toward the same practical split:

1. `1M` updating is the most adaptive and may help most in defensive or unstable years.
2. `6M` updating is slower but can be highly efficient in persistent regimes.
3. `3M` updating looks like the best overall compromise in the current sample.
4. `2M` updating remains plausible, but it has not yet earned the role of best default.

So the current evidence still supports three practical operating modes:

- **fast update mode**: `1M`
- **balanced mode**: `3M`
- **slow efficient mode**: `6M`

## Saved Outputs

- [objective2_hold_update_frequency_wide_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_update_frequency_comparison/objective2_hold_update_frequency_wide_2026-04-17.csv)
- [objective2_hold_update_frequency_long_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_update_frequency_comparison/objective2_hold_update_frequency_long_2026-04-17.csv)
- [update_frequency_strategy_return_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_update_frequency/update_frequency_strategy_return_2026-04-17.png)
- [update_frequency_average_exposure_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_update_frequency/update_frequency_average_exposure_2026-04-17.png)
- [update_frequency_efficiency_proxy_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_update_frequency/update_frequency_efficiency_proxy_2026-04-17.png)

## Related Files

- [objective2_update_frequency_comparison_2026-04-16.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_update_frequency_comparison_2026-04-16.md)
- [objective2_hold_update_block_behavior_report_2026-04-16.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_hold_update_block_behavior_report_2026-04-16.md)
- [objective2_multi_anchor_tranche_summary_2026-04-14.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_multi_anchor_tranche_summary_2026-04-14.md)
