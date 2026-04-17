# Objective 2 Update-Frequency Comparison

Date: 2026-04-16

## Purpose

This note compares how often the predictive model should be refreshed when the holding structure is kept fixed:

- holding horizon: `130` trading days
- one new tranche per day
- each tranche held for the full `130` days
- long-only position sizing in `[0, 1]`

The only thing that changes across the experiments is the **model update interval**:

- `1M` = refresh every month
- `2M` = refresh every 2 months
- `3M` = refresh every 3 months
- `6M` = refresh every 6 months

The question is:

**If the portfolio still behaves like a long-horizon 130-day system, how fast should the predictive model be updated?**

## Metric Notes

- `Return` means the full strategy return over the evaluation year.
- `Exposure` means average gross market exposure during that year.
- `100%-Eq Return` is a simple capital-efficiency proxy:

\[
\text{100%-Eq Return} \approx \frac{\text{Strategy Return}}{\text{Average Exposure}}
\]

This is **not** a true leveraged backtest. It is only a rough way to compare how efficiently each update schedule used its average market exposure.

## Table 1: Update-Frequency Comparison

| Year | Buy & Hold | 1M Return | 1M Exposure | 1M 100%-Eq | 2M Return | 2M Exposure | 2M 100%-Eq | 3M Return | 3M Exposure | 3M 100%-Eq | 6M Return | 6M Exposure | 6M 100%-Eq |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | -6.2359% | 0.0020% | 36.14% | 0.0056% | -0.0506% | 35.44% | -0.1427% | -0.5980% | 44.76% | -1.3359% | -0.2995% | 42.21% | -0.7096% |
| 2022 | 0.7782% | -0.3044% | 39.68% | -0.7671% | 1.2746% | 26.63% | 4.7865% | 0.3493% | 42.41% | 0.8235% | 2.5382% | 36.35% | 6.9834% |
| 2023 | 11.7561% | 3.0146% | 27.74% | 10.8682% | 1.5199% | 17.16% | 8.8551% | 3.6508% | 23.04% | 15.8440% | 4.2488% | 18.79% | 22.6102% |
| 2024 | 26.9557% | 7.4039% | 39.24% | 18.8674% | 4.3261% | 26.89% | 16.0887% | 9.3277% | 46.92% | 19.8803% | 5.2560% | 27.18% | 19.3392% |

## Main Observations

### 1. Faster updating is not always better

The data does **not** support a simple rule such as “update as often as possible.”

- In `2021`, the monthly update was the strongest.
- In `2022`, the semiannual update was the strongest.
- In `2023`, the semiannual update again looked best.
- In `2024`, the quarterly update was best.

This means the best update frequency is itself regime-dependent.

### 2. Two-month updating did not emerge as the best compromise

A natural intuition was that `2M` might work well because it is close to the `45-day` scale that often looked practically useful in earlier tranche tests.

However, in this fixed `130-day` holding experiment, `2M` did **not** dominate:

- it was competitive in `2022`,
- but clearly weaker in `2023`,
- and also weaker than `1M` and `3M` in `2024`.

So in this setting, “an update interval near 45 days” did not automatically become optimal.

### 3. Quarterly updating looks like the strongest general compromise so far

Across the four years:

- `3M` avoided the worst result in every year,
- was the best schedule in `2024`,
- and was consistently better than `2M` in both `2023` and `2024`.

This makes `3M` look like a credible middle-ground candidate:

- slower than `1M`, so less likely to chase noise,
- faster than `6M`, so better able to adapt during transitions.

### 4. Semiannual updating can still be very efficient

The `6M` schedule looked especially strong in:

- `2022`
- `2023`

In those years it produced the highest exposure-adjusted proxy (`100%-Eq Return`).

This suggests that when the dominant regime is persistent enough, slower model updates can be more efficient than rapid re-optimization.

### 5. Monthly updating seems best for defense and fast adaptation

The `1M` schedule was strongest in `2021`, when buy-and-hold lost over `6%`.

This supports the interpretation that rapid updating can be most useful in:

- defensive environments,
- unstable transitions,
- or periods where the model needs to react quickly to changes in direction.

## Working Interpretation

At this stage, the most natural interpretation is:

1. `1M` updating is the most adaptive and may help most in defensive or unstable years.
2. `6M` updating is slower but can be highly efficient in persistent regimes.
3. `3M` updating appears to be the best overall compromise in the current sample.
4. `2M` updating did not provide the expected advantage, despite being numerically close to the earlier `45-day` intuition.

So the current evidence points toward a useful practical distinction:

- **fast update mode**: `1M`
- **balanced mode**: `3M`
- **slow efficient mode**: `6M`

## Next Questions

The next mathematical questions now become clearer:

1. Which market features predict when `1M` should beat `3M` or `6M`?
2. Is the success of `6M` in some years due to smoother trend structure?
3. Does `3M` work best because it balances adaptation and noise reduction?
4. Can we design a regime switcher that chooses among `1M`, `3M`, and `6M` rather than using only one schedule?

## Related Files

- [objective2_multi_anchor_tranche_summary_2026-04-14.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_multi_anchor_tranche_summary_2026-04-14.md)
- [objective2_forward_validation_selection_mechanisms_report_2026-04-10.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_forward_validation_selection_mechanisms_report_2026-04-10.md)
