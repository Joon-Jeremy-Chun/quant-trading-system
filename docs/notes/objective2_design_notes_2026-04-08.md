# Objective 2 Design Notes - 2026-04-08

## Purpose

Objective 2 is formulated as a prediction problem rather than a direct return-maximization problem.

The goal is to transform the outputs of the four strategy families into a signal matrix `A`, and then use that matrix to study the next-period movement of the asset.

## Core Idea

In Objective 1, the matrix contains realized daily returns from selected strategies.

In Objective 2, the matrix does **not** contain realized strategy returns. Instead, it contains daily signal scores derived from the strategies.

So:

- Objective 1: return matrix
- Objective 2: signal / predictor matrix

## Structure of the Signal Matrix

Each row corresponds to one trading date `t`.

Each row stores:

1. the strategy-based signal values available at date `t`
2. the next-period realized outcome used as the prediction target

So one row has the form:

`X_t -> y_t`

where:

- `X_t` is the signal vector at date `t`
- `y_t` is the next-day realized outcome

## Signal Columns

The current design uses four strategy-family signals.

### 1. Adaptive Band Score

This score measures the relative position of price within the adaptive band.

Interpretation:

- near the lower side of the band: positive score
- near the upper side of the band: negative score
- near the center: score close to zero

The score is clipped into `[-1, 1]`.

### 2. Moving-Average Crossover Score

This score is based on the spread between the short-term and long-term moving averages.

Definition idea:

- `short MA > long MA`: positive buying pressure
- `short MA < long MA`: negative selling pressure
- larger spread magnitude: stronger directional pressure

To make the scale comparable, the spread is normalized using a scale value estimated from the selection period.

Interpretation:

- positive score: bullish pressure
- negative score: bearish pressure
- value close to zero: weak or neutral pressure

The score is clipped into `[-1, 1]`.

### 3. Adaptive Volatility Band Score

This score measures where the daily volatility proxy lies within its adaptive volatility band.

Interpretation:

- low relative volatility: positive score
- high relative volatility: negative score
- middle area: score near zero

The score is clipped into `[-1, 1]`.

### 4. Fear-Greed Candle-Volume Score

This strategy is treated as an event-based signal rather than a smooth continuous score.

Interpretation:

- bullish event: `+1`
- neutral / no event: `0`
- bearish event: `-1`

This is intentionally discrete.

## Why the Last Score is Discrete

The fear-greed strategy is fundamentally event-driven:

- unusually strong candle behavior
- unusual volume
- price-zone condition
- confirmation logic

Because of this, forcing it into a fully continuous score would add complexity without clear interpretive benefit.

Therefore, the final design keeps it as a discrete signal in `{-1, 0, 1}`.

## Target Variables

To prepare for both regression and classification settings, two target columns are stored in the matrix.

### 1. `target_next_return`

This is the next-day realized asset return.

It is used if Objective 2 is treated as a regression problem.

### 2. `target_next_direction`

This is the next-day directional label:

- `1` if the next-day return is positive
- `0` otherwise

It is used if Objective 2 is treated as a classification problem.

## Row Interpretation

A single row should be read as:

"Given the strategy signals observed at date `t`, what happened to the asset on the next trading day?"

For example, one row may contain:

- a positive adaptive-band score
- a slightly negative moving-average score
- a strongly negative volatility-band score
- a neutral fear-greed event score

and then the next-day return and next-day up/down result.

So the row is not a return contribution from the strategy itself. It is a supervised-learning sample.

## Time Interpretation

The design respects time ordering:

- the signal vector is computed using information available up to date `t`
- the target is the realized outcome at `t+1`

This means the matrix is built in a causally valid way for prediction.

## Current Matrix Columns

The current generated matrix contains:

- `Date`
- `adaptive_band_score`
- `ma_crossover_score`
- `adaptive_volatility_band_score`
- `fear_greed_candle_volume_score`
- `target_next_return`
- `target_next_direction`

## Current Main Path

The current main path is now the return-prediction formulation.

This means:

- the main target is `target_next_return`
- the baseline model is ordinary least squares (OLS)
- the direction model remains available as a secondary comparison branch

## First Baseline Model

The first modeling step uses a linear regression of the form:

`y_t = beta_0 + beta_1 x_{1,t} + beta_2 x_{2,t} + beta_3 x_{3,t} + beta_4 x_{4,t}`

where:

- `y_t` is the next-day return
- `x_{1,t}` to `x_{4,t}` are the four strategy scores at date `t`

This is the first-pass benchmark model for Objective 2.

## Initial Empirical Reading

For the sample split:

- selection: `2024-01-01` to `2024-12-31`
- evaluation: `2025-01-01` to `2025-12-31`

the OLS coefficients were:

- intercept: `0.001135`
- adaptive band score: `-0.000661`
- MA crossover score: `-0.002350`
- adaptive volatility band score: `-0.000231`
- fear-greed score: `+0.010770`

This implies:

- the first three strategy scores entered with small negative coefficients
- the fear-greed event score entered with a positive coefficient

One possible interpretation is that, in this sample, stronger bullish pressure from the first three technical signals was associated with weaker next-day return, which is consistent with a short-horizon mean-reversion effect rather than immediate trend continuation.

## Initial Predictive Strength

The OLS return model showed weak but nonzero predictive structure.

Selection-period summary:

- correlation: `0.1506`
- directional accuracy from return sign: `0.5913`

Evaluation-period summary:

- correlation: `0.1525`
- directional accuracy from return sign: `0.5088`

This should be interpreted cautiously.

The model appears to contain a weak linear signal, but not yet a strong forecasting edge. At this stage, it is best viewed as a baseline benchmark rather than a final predictive model.

## Next Modeling Step

The next natural step is model selection inside the strategy-signal space.

Recommended candidates:

- OLS as the baseline
- Ridge regression
- Lasso
- Elastic Net

These models are useful because the feature space is small and interpretable, and the main question is not only prediction accuracy but also how the strategy-signal vector should be transformed into a predictive operator.
