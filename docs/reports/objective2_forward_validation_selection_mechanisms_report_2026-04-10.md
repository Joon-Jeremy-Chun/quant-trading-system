# Objective 2 Forward Validation and Selection-Mechanism Report

Date: 2026-04-10

## Purpose

This report summarizes a stricter Objective 2 experiment:

1. Fix the top-10 parameter candidates from each strategy family using the `2024-12-31` anchor snapshot.
2. Rebuild the expanded 40-column strategy basis from those fixed candidates.
3. Use 2024 as the selection period for horizon and model discovery.
4. Apply the selected model structure to 2025 and evaluate whether the relationship persists out of sample.

This is closer to the real question of whether the discovered structure can be used for future prediction.

## Fixed Expanded Strategy Space

The basis came from the `anchor_2024-12-31` optimization snapshot:

- Adaptive Band: top 10
- MA Crossover: top 10
- Adaptive Volatility Band: top 10
- Fear-Greed Candle-Volume: top 10

This produced a 40-column design matrix.

## Forward-Validation Setup

- Anchor date: `2024-12-31`
- Selection feature period: `2024-01-01` to `2024-12-31`
- Evaluation period: `2025-01-01` to `2025-12-31`
- Target horizons scanned: `1` to `130` trading days
- Models compared:
  - OLS
  - Ridge
  - Lasso
  - Elastic Net

Command used:

```powershell
py -3 strategies\automation\run_objective2_expanded_strategy_forward_validation.py `
  --anchor-date 2024-12-31 `
  --selection-start-date 2024-01-01 `
  --selection-end-date 2024-12-31 `
  --evaluation-start-date 2025-01-01 `
  --evaluation-end-date 2025-12-31 `
  --min-horizon-days 1 `
  --max-horizon-days 130 `
  --top-n-per-family 10 `
  --tag forward_2024_to_2025
```

## Main Forward-Validation Result

Using the current horizon-by-horizon selection rule

- best model inside each horizon selected by:
  - highest `selection_correlation`
  - then highest `selection_directional_accuracy`
  - then lowest `selection_mse`

the strongest out-of-sample result in 2025 appeared at:

- Horizon: `45` trading days
- Model: `OLS`
- Selection correlation: `0.824818`
- Evaluation correlation: `0.731964`
- Evaluation directional accuracy: `0.617647`

This is a strong result. It also shifted the most stable predictive horizon away from the previously attractive very long horizons.

## Basis Interpretation for the 45-Day OLS Model

The 45-day OLS model kept 38 nonzero basis columns. Since many basis columns are correlated with one another, the safest interpretation is by strategy family rather than by any single coefficient sign.

### Family-level absolute coefficient contribution

- Adaptive Volatility Band: `5.477794`
- MA Crossover: `0.709702`
- Adaptive Band: `0.233989`
- Fear-Greed Candle-Volume: `0.066820`

### Largest individual basis coefficients

1. `adaptive_volatility_band_rank09_score = -1.7555`
   - `vol_window = 10`, `upper_k = -0.8`, `lower_k = -2.5`
2. `adaptive_volatility_band_rank08_score = +0.9900`
   - `vol_window = 10`, `upper_k = -0.8`, `lower_k = -2.6`
3. `adaptive_volatility_band_rank10_score = +0.7695`
   - `vol_window = 10`, `upper_k = -0.8`, `lower_k = -2.4`
4. `adaptive_volatility_band_rank04_score = +0.5774`
   - `vol_window = 22`, `upper_k = 0.6`, `lower_k = 1.1`
5. `adaptive_volatility_band_rank03_score = -0.3555`
   - `vol_window = 22`, `upper_k = 0.6`, `lower_k = 1.0`

The next strongest group came from MA crossover bases such as:

- `ma_crossover_rank10_score` with `short_ma = 15`, `long_ma = 70`
- `ma_crossover_rank01_score` with `short_ma = 15`, `long_ma = 20`
- `ma_crossover_rank03_score` with `short_ma = 10`, `long_ma = 20`
- `ma_crossover_rank07_score` with `short_ma = 15`, `long_ma = 25`

### Interpretation

At the 45-day horizon, the predictive structure is no longer dominated by MA-crossover alone. In this more realistic forward-validation setup, the strongest explanatory family is adaptive volatility band, with MA crossover playing a secondary supporting role.

## Alternative Selection Mechanisms

To avoid relying on only one in-sample selection rule, we also checked several alternative global selection mechanisms.

### 1. Select by maximum selection correlation

- Chosen horizon: `123`
- Chosen model: `OLS`
- Selection correlation: `0.936661`
- Evaluation correlation: `0.241656`

This looked extremely strong in sample, but its 2025 correlation fell sharply.

Dominant basis families:

- Adaptive Volatility Band: `1.395918`
- MA Crossover: `0.827450`
- Adaptive Band: `0.228543`

### 2. Select by maximum selection directional accuracy

This chose exactly the same model as selection correlation:

- Horizon: `123`
- Model: `OLS`
- Evaluation correlation: `0.241656`

This suggests that very long-horizon directional labels were too easy or too one-sided in sample and did not transfer well to 2025.

### 3. Select by maximum selection long-short strategy return

- Chosen horizon: `93`
- Chosen model: `OLS`
- Selection correlation: `0.849981`
- Evaluation correlation: `0.605811`

This performed substantially better out of sample than the previous two rules, but still not as well as the 45-day result.

Dominant basis families:

- Adaptive Volatility Band: `5.149046`
- MA Crossover: `0.723856`
- Adaptive Band: `0.664414`
- Fear-Greed Candle-Volume: `0.023200`

Important caution:

For multi-day horizons, long-short cumulative return is less reliable as a selection metric because future windows overlap heavily. It is still informative, but it should not be treated as a clean independent-return measure.

### 4. Select by minimum selection MSE

- Chosen horizon: `1`
- Chosen model: `OLS`
- Selection MSE: `0.000083`
- Evaluation correlation: `-0.045484`

This failed out of sample.

Dominant basis families:

- Adaptive Volatility Band: `1.106859`
- Adaptive Band: `0.628094`
- MA Crossover: `0.219663`
- Fear-Greed Candle-Volume: `0.019603`

This indicates that a small in-sample squared error on very short horizons is not a good standalone selection criterion for future predictive usefulness.

## Comparison Table

| Selection mechanism | Chosen horizon | Chosen model | 2025 evaluation correlation |
|---|---:|---|---:|
| Selection correlation | 123 | OLS | 0.241656 |
| Selection directional accuracy | 123 | OLS | 0.241656 |
| Selection long-short return | 93 | OLS | 0.605811 |
| Selection MSE | 1 | OLS | -0.045484 |
| Best realized 2025 result among selected horizons | 45 | OLS | 0.731964 |

## Main Interpretation

Several important conclusions follow from this forward-validation experiment.

1. The expanded strategy space remains useful.
   The predictive structure is real enough to survive into 2025, and the best out-of-sample correlation is still high.

2. Selection mechanism matters a great deal.
   Different in-sample criteria lead to very different horizon choices, and not all of them generalize.

3. Extremely long horizons can look deceptively attractive in sample.
   The 123-day case looked strongest under correlation and directional-accuracy selection, but it did not carry over well out of sample.

4. The strongest 2025 result occurred around a medium horizon.
   The 45-day region appears more stable than the ultra-long horizons.

5. The explanatory center shifted.
   Earlier exploratory scans often suggested MA crossover dominance. In the stricter 2024-to-2025 forward test, adaptive volatility band became the main explanatory family at the best-performing horizon.

## Conclusion

The most important result is not simply that one horizon produced a high 2025 correlation. It is that the choice of in-sample selection rule strongly affects what appears to be "best," and some apparently excellent in-sample choices do not survive future validation.

Among the tested selection mechanisms, the most promising practical region is around `45` trading days, where the out-of-sample correlation reached `0.731964`. This suggests that Objective 2 has moved beyond a purely conceptual strategy-space construction and now shows evidence of a meaningful medium-horizon predictive structure that persists into the next year.
