# Objective 2 Multi-Anchor Tranche Summary

Date: 2026-04-14

## Purpose

This note consolidates the recent Objective 2 results across the full set of semiannual anchor dates from `2020-06-30` to `2024-12-31`.

The main goals were:

1. Build the expanded strategy space from the top-10 candidates of each strategy family.
2. Run forward validation from each anchor into the following evaluation period.
3. Compare a fixed `45-day` rolling-tranche implementation with a representative long-horizon `130-day` rolling-tranche implementation.
4. Identify the best predictive horizon, model type, and number of active strategy bases at each anchor.

## Setup

For each anchor date:

- We used the precomputed Objective 1 optimization snapshot.
- We constructed an expanded 40-column strategy basis:
  - Adaptive Band: top 10
  - MA Crossover: top 10
  - Adaptive Volatility Band: top 10
  - Fear-Greed Candle-Volume: top 10
- We ran Objective 2 forward validation across horizons `1` to `130`.
- We selected the strongest row by evaluation correlation from the forward-validation selected-model file.
- We separately ran two practical tranche simulations:
  - `45-day tranche`
  - `130-day tranche`

The tranche simulations used:

- long-only weights in `[0, 1]`
- prediction-scaled sizing from the selected model output
- one new tranche entered per day
- each tranche held for either `45` or `130` trading days

## Table 1: Fixed 45-Day vs Fixed 130-Day Tranche Simulations

Important note:

- The reported buy-and-hold return is computed over the effective valid evaluation rows for each scenario.
- Because the valid row set depends on the target horizon and holding structure, buy-and-hold can differ slightly between the `45-day` and `130-day` rows even at the same anchor.

| Anchor Date | Evaluation Window | Scenario | Buy & Hold | Strategy Return | Avg Exposure |
|---|---|---|---:|---:|---:|
| 2020-06-30 | 2020-07-01 ~ 2021-06-30 | 130-day tranche | -4.4519% | -0.5241% | 21.66% |
| 2020-06-30 | 2020-07-01 ~ 2021-06-30 | 45-day tranche | -8.8709% | -4.0588% | 54.18% |
| 2020-12-31 | 2021-01-01 ~ 2021-12-31 | 130-day tranche | 2.3470% | -0.4992% | 19.62% |
| 2020-12-31 | 2021-01-01 ~ 2021-12-31 | 45-day tranche | 3.2932% | 0.4263% | 64.54% |
| 2021-06-30 | 2021-07-01 ~ 2022-06-30 | 130-day tranche | 0.5487% | 0.0049% | 0.63% |
| 2021-06-30 | 2021-07-01 ~ 2022-06-30 | 45-day tranche | 5.7554% | -0.0035% | 1.04% |
| 2021-12-31 | 2022-01-01 ~ 2022-12-31 | 130-day tranche | -1.8373% | -0.0911% | 5.05% |
| 2021-12-31 | 2022-01-01 ~ 2022-12-31 | 45-day tranche | -3.9955% | -3.1292% | 48.87% |
| 2022-06-30 | 2022-07-01 ~ 2023-06-30 | 130-day tranche | 5.0862% | 2.6907% | 22.67% |
| 2022-06-30 | 2022-07-01 ~ 2023-06-30 | 45-day tranche | 15.0096% | 8.4832% | 29.68% |
| 2022-12-31 | 2023-01-01 ~ 2023-12-31 | 130-day tranche | -5.9087% | 0.0000% | 0.00% |
| 2022-12-31 | 2023-01-01 ~ 2023-12-31 | 45-day tranche | -3.1626% | -0.0880% | 2.35% |
| 2023-06-30 | 2023-07-01 ~ 2024-06-30 | 130-day tranche | 11.1965% | 1.0112% | 14.13% |
| 2023-06-30 | 2023-07-01 ~ 2024-06-30 | 45-day tranche | 26.8858% | 10.1107% | 38.49% |
| 2023-12-31 | 2024-01-01 ~ 2024-12-31 | 130-day tranche | -1.2634% | -0.0013% | 0.04% |
| 2023-12-31 | 2024-01-01 ~ 2024-12-31 | 45-day tranche | 17.6591% | 0.0813% | 1.45% |
| 2024-06-30 | 2024-07-01 ~ 2025-06-30 | 130-day tranche | -2.5854% | -0.7292% | 13.02% |
| 2024-06-30 | 2024-07-01 ~ 2025-06-30 | 45-day tranche | 25.4306% | 9.7152% | 33.68% |
| 2024-12-31 | 2025-01-01 ~ 2025-12-31 | 130-day tranche | 3.5614% | 0.0969% | 15.38% |
| 2024-12-31 | 2025-01-01 ~ 2025-12-31 | 45-day tranche | 23.8936% | 14.0658% | 31.37% |

## Table 2: Best Forward-Validation Horizon by Anchor

This table reports, for each anchor, the strongest selected forward-validation row by evaluation correlation.

| Anchor Date | Best Horizon (days) | Best Model | Selection Corr | Evaluation Corr | Eval Dir Acc | Nonzero Basis |
|---|---:|---|---:|---:|---:|---:|
| 2020-06-30 | 120 | OLS | 0.9307 | 0.4054 | 0.3068 | 40 |
| 2020-12-31 | 61 | OLS | 0.8144 | 0.8371 | 0.4173 | 30 |
| 2021-06-30 | 73 | OLS | 0.6911 | 0.6700 | 0.2571 | 30 |
| 2021-12-31 | 110 | OLS | 1.0000 | 0.7314 | 0.0000 | 28 |
| 2022-06-30 | 127 | OLS | 0.9155 | 0.9065 | 0.7200 | 40 |
| 2022-12-31 | 126 | OLS | 0.9914 | 0.6676 | 0.4182 | 30 |
| 2023-06-30 | 128 | OLS | 0.9803 | 0.8597 | 0.9828 | 32 |
| 2023-12-31 | 122 | OLS | 0.9496 | 0.6098 | 0.0000 | 30 |
| 2024-06-30 | 127 | OLS | 0.9027 | 0.7046 | 1.0000 | 30 |
| 2024-12-31 | 45 | OLS | 0.8248 | 0.7320 | 0.6176 | 38 |

## Table 3: Monthly Model Update with Fixed 130-Day Holding

This table keeps the `130-day` tranche structure fixed while updating the predictive model once per month using the latest monthly anchor snapshot.

| Evaluation Year | Buy & Hold | Monthly-Update 130d Return | Excess vs B&H | Avg Exposure | Interpretation |
|---|---:|---:|---:|---:|---|
| 2021 | -6.2359% | 0.0020% | 6.2380% | 36.14% | Defensive success: almost flat while the market fell |
| 2022 | 0.7782% | -0.3044% | -1.0826% | 39.68% | More active than fixed 130d, but little net alpha |
| 2023 | 11.7561% | 3.0146% | -8.7415% | 27.74% | Meaningful participation, but still behind a rising market |
| 2024 | 26.9557% | 7.4039% | -19.5519% | 39.24% | Monthly updating revived the slow model, but not enough to match the strong uptrend |

### What Table 3 Adds

The fixed `130-day` tranche was often so slow that it barely entered the market at all. The monthly-update experiment asks a different question: can we keep the long `130-day` holding philosophy, but make it more adaptive by refreshing the model every month?

So far, the answer looks mixed but promising:

- In `2021`, monthly updating clearly helped as a defensive filter.
- In `2022`, monthly updating increased participation, but the added exposure did not convert into meaningful excess return.
- In `2023` and `2024`, monthly updating transformed the strategy from near-idle to meaningfully active.
- Across these years, the monthly-update version appears more realistic than a fully fixed `130-day` model, even when it does not beat buy-and-hold.

## Main Observations

### 1. The best predictive horizon is not constant

The preferred horizon changed materially across anchor dates.

- Some anchors favored medium horizons:
  - `2020-12-31 -> 61`
  - `2021-06-30 -> 73`
  - `2024-12-31 -> 45`
- Other anchors favored long horizons near `120-128` days:
  - `2022-06-30 -> 127`
  - `2022-12-31 -> 126`
  - `2023-06-30 -> 128`
  - `2024-06-30 -> 127`

This suggests that the market regime affects which predictive time scale is most stable.

### 2. OLS remained the dominant model

Across all anchors, the best selected row was always `OLS`.

This does not mean the basis space was unimportant. It means that, within the expanded strategy space, the broad linear combination consistently explained future returns better than the regularized alternatives at the best row for each anchor.

### 3. The 130-day tranche behaves like a slower defensive filter

The `130-day tranche` generally:

- used lower exposure
- responded more slowly
- performed better in defensive or uncertain environments

Examples:

- `2022-12-31`: `0.00%` average exposure and `0.0000%` return while buy-and-hold lost `-5.9087%`
- `2024-06-30`: `13.02%` average exposure and `-0.7292%` return while buy-and-hold lost `-2.5854%`

### 4. The 45-day tranche reacts faster and participates more

The `45-day tranche` generally:

- used more exposure
- reacted faster to transitions
- captured more upside in rising regimes

Examples:

- `2023-06-30`: `10.1107%` return at `38.49%` exposure
- `2024-06-30`: `9.7152%` return at `33.68%` exposure
- `2024-12-31`: `14.0658%` return at `31.37%` exposure

This supports the earlier interpretation that the `45-day` setup is better suited to catching sideways-to-up transitions, while `130-day` behaves more like a confirmation-based defensive model.

### 5. Very high directional-accuracy values should be interpreted carefully

Several anchors produced extreme directional-accuracy values such as `0.0000` or `1.0000` at the best horizon.

This suggests that some long-horizon targets may be partially degenerate or heavily regime-driven. These cases are still interesting, but they require extra care in the later mathematical analysis.

### 6. Monthly updating makes the slow 130-day structure more realistic

The fixed `130-day` tranche often behaved like an extremely conservative filter. In contrast, the monthly-update `130-day` setup:

- kept the same long holding horizon,
- but refreshed the predictive model every month,
- leading to much higher and more realistic market participation.

This did not guarantee excess return, but it consistently moved the system closer to a usable live-investment framework.

## Current Interpretation

The recent experiments suggest the following working picture:

1. Strategy-space construction is valid.
2. The useful predictive horizon is regime-dependent rather than universal.
3. A fixed `45-day` implementation is often practically attractive because it reacts faster.
4. A fixed `130-day` implementation is often more defensive and lower-exposure.
5. The full problem is no longer only about model selection. It is now also about:
   - horizon selection
   - update frequency
   - regime detection
   - how prediction should be translated into position sizing

## Next Mathematical Questions

The next stage should focus on more formal analysis of why the best horizon shifts across anchors.

The most natural questions are:

1. Which price-regime features are associated with a shorter best horizon versus a longer one?
2. How much of the long-horizon performance is genuine predictive structure, and how much is due to one-sided future targets?
3. Why does OLS keep winning despite the large and correlated basis space?
4. Should practical deployment use:
   - a fixed horizon such as `45`,
   - a fixed defensive horizon such as `130`,
   - or a slower regime-dependent switching rule between them?
5. How often should the predictive model be updated when the holding horizon remains long?

## Related Files

- [objective2_forward_validation_selection_mechanisms_report_2026-04-10.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_forward_validation_selection_mechanisms_report_2026-04-10.md)
- [objective2_expanded_strategy_space_report_2026-04-09.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_expanded_strategy_space_report_2026-04-09.md)
- [objective2_horizon_scan_report_2026-04-09.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_horizon_scan_report_2026-04-09.md)
