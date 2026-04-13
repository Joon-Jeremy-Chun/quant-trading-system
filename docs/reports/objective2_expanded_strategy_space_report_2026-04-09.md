# Objective 2 Expanded Strategy Space Report

Date: 2026-04-09

## Purpose

This experiment extends the original Objective 2 strategy space from 4 representative strategy signals to a larger basis of top candidate signals. The goal is to make model selection closer to the polynomial-basis selection exercise from class: instead of fixing one representative signal per strategy family, we allow the model to choose from a richer function space.

## Expanded Strategy Space Design

We constructed an expanded basis with the top 10 parameter candidates from each strategy family:

- Adaptive Band: top 10 from the `1y` optimization results
- MA Crossover: top 10 from the `6m` optimization results
- Adaptive Volatility Band: top 10 from the `3m` optimization results
- Fear-Greed Candle-Volume: top 10 from the `1m` optimization results

This produced a 40-column strategy design matrix:

- 10 columns from adaptive band
- 10 columns from MA crossover
- 10 columns from adaptive volatility band
- 10 columns from fear-greed candle-volume

Each column is still a numerically evaluated strategy function. Therefore, the mathematical interpretation remains the same as before: rows are dates, columns are basis functions, and each matrix entry is the value of one strategy signal on one date.

## Experimental Setup

- Selection period: 2024-01-01 to 2024-12-31
- Evaluation period: 2025-01-01 to 2025-12-31
- Target horizon: 97 trading days
- Target variable: cumulative future return over the next 97 trading days
- Models compared:
  - OLS
  - Ridge
  - Lasso
  - Elastic Net

Command used:

```powershell
py -3 strategies\automation\run_objective2_expanded_strategy_model_selection.py `
  --selection-start-date 2024-01-01 `
  --selection-end-date 2024-12-31 `
  --evaluation-start-date 2025-01-01 `
  --evaluation-end-date 2025-12-31 `
  --target-horizon-days 97 `
  --top-n-per-family 10 `
  --tag expanded_top10_h97
```

## Main Results

| Model | Evaluation Correlation | Evaluation MAE | Nonzero Count |
|---|---:|---:|---:|
| Lasso | 0.694669 | 0.101100 | 1 |
| Elastic Net | 0.694669 | 0.101209 | 1 |
| Ridge | 0.691826 | 0.101314 | 38 |
| OLS | 0.554923 | 0.102364 | 38 |

## Comparison with Earlier Objective 2 Results

Earlier best results were:

- 4 representative-strategy combination best: `0.660914`
- Best single representative signal (`ma_crossover_score`): `0.662071`

The expanded strategy space improved on both:

- Expanded strategy space + Lasso: `0.694669`
- Expanded strategy space + Elastic Net: `0.694669`

This means the richer basis was useful. The improvement did not come from averaging many signals together. Instead, it came from allowing sparse model selection over a larger strategy basis.

## Which Basis Was Selected?

Both Lasso and Elastic Net selected exactly one nonzero basis:

- `ma_crossover_rank06_score`

Its source parameters were:

- Strategy family: MA Crossover
- Source horizon: `6m`
- Rank inside family top set: `6`
- Parameters:
  - `short_ma = 5`
  - `long_ma = 25`

## Interpretation

This result is important for the logic of Objective 2.

The strategy-space construction itself appears mathematically and empirically justified. Once we expanded the basis, model selection found a better predictive representation than the original 4-column setup. However, the best result did not come from a dense linear combination of many strategies. Instead, it came from sparse selection within a larger strategy function space.

In other words:

- Building the strategy space was a valid step.
- Expanding the basis made the model-selection problem more meaningful.
- The best predictive signal at the 97-day horizon was not the original 4-signal combination.
- It was a single selected MA crossover basis, specifically the `(5, 25)` crossover score.

## Conclusion

The expanded strategy-space experiment supports the original conceptual direction of Objective 2. Treating strategy signals as basis functions and letting a regularized model choose among them was more effective than restricting the model to one representative signal per strategy family.

At the same time, the result also shows that "more strategies combined together" is not automatically the best outcome. In this sample, the main advantage of the expanded design was not diversification across many strategy columns, but the ability to discover a better basis element inside the larger strategy function space.
