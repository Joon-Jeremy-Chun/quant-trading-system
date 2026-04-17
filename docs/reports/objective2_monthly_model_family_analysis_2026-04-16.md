# Objective 2 Monthly Model Family Analysis

Date: 2026-04-16

## Purpose

This note asks a more structural question about the monthly-updated Objective 2 models:

1. Among the 40 basis columns (`10 x 4` strategy families), which family was most frequently dominant?
2. Did this pattern differ between `45-day hold` and `130-day hold` systems?
3. Which model-selection mechanism actually chose the active monthly model?

The analysis below uses the monthly model logs from the tranche backtests. Because the monthly logs store `top_abs_coefficients`, the notion of a "dominant family" here is based on the sum of absolute coefficient magnitudes among the logged top coefficients for each month.

Saved outputs:

- [objective2_monthly_model_family_dominance_h45_2026-04-16.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_model_family_analysis/objective2_monthly_model_family_dominance_h45_2026-04-16.csv)
- [objective2_monthly_model_family_dominance_h130_2026-04-16.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_model_family_analysis/objective2_monthly_model_family_dominance_h130_2026-04-16.csv)
- [objective2_monthly_model_family_summary_2026-04-16.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_model_family_analysis/objective2_monthly_model_family_summary_2026-04-16.csv)
- [objective2_monthly_model_family_mechanisms_2026-04-16.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_model_family_analysis/objective2_monthly_model_family_mechanisms_2026-04-16.csv)

## Selection Mechanism

The monthly update runs were extremely consistent in terms of model-selection mechanism:

| Hold Days | Active Model | Selection Criterion | Months |
|---|---|---|---:|
| 45 | OLS | `selection_correlation` | 48 |
| 130 | OLS | `selection_correlation` | 48 |

So for both hold horizons, every monthly active model was selected as:

- `OLS`
- using `selection_correlation`

## 130-Day Hold: Which Family Dominated?

### Overall Counts

| Family | Dominant Months |
|---|---:|
| `ma_crossover` | 28 |
| `adaptive_band` | 11 |
| `adaptive_volatility_band` | 9 |
| `fear_greed_candle_volume` | 0 |

### By Year

| Year | Adaptive Band | MA Crossover | Adaptive Volatility Band | Fear-Greed |
|---|---:|---:|---:|---:|
| 2021 | 4 | 7 | 1 | 0 |
| 2022 | 4 | 5 | 3 | 0 |
| 2023 | 0 | 8 | 4 | 0 |
| 2024 | 3 | 8 | 1 | 0 |

Interpretation:

- `ma_crossover` was the backbone of the `130-day hold` system.
- `adaptive_band` appeared as a secondary family, especially in 2021 and 2022.
- `adaptive_volatility_band` took over in a limited number of months, often during transitions.
- `fear_greed_candle_volume` never became the dominant monthly family in this setup.

## 45-Day Hold: Which Family Dominated?

### Overall Counts

| Family | Dominant Months |
|---|---:|
| `ma_crossover` | 17 |
| `adaptive_volatility_band` | 17 |
| `adaptive_band` | 14 |
| `fear_greed_candle_volume` | 0 |

### By Year

| Year | Adaptive Band | MA Crossover | Adaptive Volatility Band | Fear-Greed |
|---|---:|---:|---:|---:|
| 2021 | 4 | 6 | 2 | 0 |
| 2022 | 4 | 4 | 4 | 0 |
| 2023 | 1 | 2 | 9 | 0 |
| 2024 | 5 | 5 | 2 | 0 |

Interpretation:

- The `45-day hold` system was much less concentrated in a single family.
- `ma_crossover` and `adaptive_volatility_band` were tied overall.
- `2023` was especially volatility-band-driven.
- `2024` looked balanced between `adaptive_band` and `ma_crossover`.

## Comparison: 45-Day vs 130-Day

This is the clearest structural difference:

- `130-day hold` was strongly `ma_crossover`-centric.
- `45-day hold` was more mixed, with a much larger role for `adaptive_volatility_band`.

This makes intuitive sense:

- a longer holding system tends to favor slower trend-following structure,
- while a shorter holding system can be more sensitive to transitional volatility and shorter-term band dynamics.

## Main Takeaways

1. The active monthly models were not chosen by a changing mix of statistical mechanisms; they were always `OLS` under `selection_correlation`.
2. The important variation came not from the selection mechanism itself, but from which strategy family dominated the coefficients.
3. For `130-day hold`, the system mostly leaned on `ma_crossover`.
4. For `45-day hold`, the system was more balanced and gave a much larger role to `adaptive_volatility_band`.
5. `fear_greed_candle_volume` did not dominate any monthly model in these runs, which suggests it may still be useful as a supporting signal but not as the main driver in the current gold-only setup.
