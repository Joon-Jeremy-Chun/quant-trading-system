# Objective 2 Horizon-Scan Report - 2026-04-09

## Summary

Objective 2 was extended so that the prediction target is no longer restricted to the next trading day.

Instead, the same four-dimensional strategy-signal matrix is kept fixed, while the future return target is allowed to vary by horizon.

The purpose of this experiment is to identify whether the strategy-signal space is more strongly related to short-term, medium-term, or longer-term future price movement.

## Fixed Strategy Configuration

The horizon scan was performed using the following representative strategy parameters:

- adaptive band
  - source horizon: `1y`
  - `ma_window = 10`
  - `upper_k = 1.8`
  - `lower_k = -2.4`

- moving-average crossover
  - source horizon: `6m`
  - `short_ma = 15`
  - `long_ma = 20`

- adaptive volatility band
  - source horizon: `3m`
  - `vol_window = 22`
  - `upper_k = 0.6`
  - `lower_k = 1.2`

- fear-greed candle-volume
  - source horizon: `1m`
  - `k_body = 1.2`
  - `k_volume = 1.2`
  - `price_zone_window = 3`

These parameters were held fixed while the target horizon was varied.

## Horizon-Scan Design

The experiment used:

- selection period: `2024-01-01` to `2024-12-31`
- evaluation period: `2025-01-01` to `2025-12-31`

The future return target was scanned from:

- `1` trading day ahead
- up to `130` trading days ahead

The main ranking criterion was:

- `evaluation_correlation`

This was chosen because the main purpose of the scan is to identify which target horizon shows the strongest linear relationship with the strategy-signal matrix.

## Top 10 Horizons by Evaluation Correlation

The top horizons were:

| Rank | Target Horizon (days) | Evaluation Correlation |
|---|---:|---:|
| 1 | 97  | 0.6609 |
| 2 | 96  | 0.6569 |
| 3 | 98  | 0.6559 |
| 4 | 99  | 0.6487 |
| 5 | 95  | 0.6388 |
| 6 | 100 | 0.6168 |
| 7 | 94  | 0.6131 |
| 8 | 101 | 0.5893 |
| 9 | 93  | 0.5873 |
|10 | 102 | 0.5762 |

## Main Finding

The strongest return correlation did not occur at the 1-day horizon.

Instead, the best-performing horizons were concentrated in the range of roughly `93` to `102` trading days ahead, with the highest evaluation-period correlation appearing at `97` trading days.

This supports the hypothesis that the strategy-signal vector may contain information that is more strongly aligned with medium- to longer-horizon price movement than with immediate next-day return.

## Important Interpretation Note

The horizon scan also reported very large directional-accuracy and long-short return numbers at long horizons.

These should be interpreted with caution.

In the highest-correlation region, the future-direction labels became degenerate in this sample: for example, at the `97`-day horizon, the future direction was positive for every row in both the selection and evaluation sets.

Therefore:

- the directional-accuracy values in that region are not informative for classification
- the long-short compounded return values are not reliable as standalone economic evidence
- the correlation statistic is the main meaningful output of the horizon scan

## Best Return-Correlation Horizon

Under the current design, the best horizon by return correlation is:

- `97` trading days ahead

with:

- selection correlation: `0.5514`
- evaluation correlation: `0.6609`

This does not mean that 97 days is automatically the best final predictive target in every sense. It means that, for this sample and this fixed strategy configuration, the strongest linear return relationship appeared at that horizon.

## Model Comparison at the Best Horizon

A separate model-selection run was performed at `97` trading days ahead using:

- OLS
- Ridge
- Lasso
- Elastic Net

The results were all broadly similar. No single model dominated decisively.

Approximate evaluation correlations:

- OLS: `0.6609`
- Ridge: `0.6592`
- Lasso: `0.6631`
- Elastic Net: `0.6632`

This suggests that the target-horizon choice may currently matter more than the exact linear model choice.

## Conclusion

The horizon scan produced a clear result:

- the strongest predictive relationship in return space was not at the shortest horizon
- the most informative target horizons were concentrated around `97` trading days
- model choice among standard linear methods mattered less than the target-horizon definition

Therefore, the current evidence suggests that Objective 2 should continue with return prediction as the main path, while treating target-horizon selection as one of the most important modeling decisions.
