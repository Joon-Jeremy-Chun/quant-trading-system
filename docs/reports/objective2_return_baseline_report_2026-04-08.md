# Objective 2 Return-Prediction Baseline Report - 2026-04-08

## Summary

Objective 2 has now moved from design to first-stage modeling.

The signal matrix was successfully constructed from the four strategy families, and a baseline return-prediction model was estimated using ordinary least squares (OLS).

The main target is now the next-day asset return.

## Objective 2 Framework

Objective 2 is not a strategy-combination problem in the same sense as Objective 1.

Instead, it treats each strategy as a signal-generating function and places the resulting daily scores into a shared strategy-signal space. A row of the matrix represents the strategy-state vector observed at time `t`, while the target records the realized market outcome at `t+1`.

Thus, the problem is framed as:

`X_t -> y_t`

where:

- `X_t` is the four-dimensional strategy signal vector
- `y_t` is the next-day realized return

## Signal Matrix

The predictor matrix contains four columns:

- adaptive band score
- moving-average crossover score
- adaptive volatility band score
- fear-greed candle-volume event score

The last signal is discrete in `{-1, 0, 1}`, while the first three are clipped continuous scores in `[-1, 1]`.

## Baseline Model

The first baseline model is linear regression:

`y_t = beta_0 + beta' X_t`

This is the simplest way to ask whether the strategy-signal vector contains linearly usable information about next-day returns.

For the sample split:

- selection: `2024-01-01` to `2024-12-31`
- evaluation: `2025-01-01` to `2025-12-31`

the fitted coefficients were:

- intercept: `0.001135`
- adaptive band score: `-0.000661`
- MA crossover score: `-0.002350`
- adaptive volatility band score: `-0.000231`
- fear-greed score: `+0.010770`

## Interpretation of Coefficients

The coefficient pattern suggests that, in this sample, the first three technical signals were negatively related to next-day return, while the fear-greed event signal was positively related.

This can be interpreted in the following way:

- stronger technical buying pressure did not immediately translate into stronger next-day return
- instead, the market often behaved more like a short-horizon mean-reversion process
- the fear-greed event signal appeared to retain a more directly positive next-day relationship

This does not necessarily mean that the strategies are wrong. It may instead mean that their natural horizon is longer than one day, while the target in this baseline model is specifically the next-day return.

## Predictive Performance

Selection-period results:

- MSE: `0.0000919`
- MAE: `0.007335`
- correlation: `0.1506`
- directional accuracy from predicted return sign: `0.5913`
- long-short strategy return from sign trading: `0.4664`

Evaluation-period results:

- MSE: `0.0001633`
- MAE: `0.009371`
- correlation: `0.1525`
- directional accuracy from predicted return sign: `0.5088`
- long-short strategy return from sign trading: `0.2598`

## Assessment

The baseline OLS model appears to contain weak but nonzero predictive structure.

This should be interpreted carefully:

- the correlation remains positive in both selection and evaluation
- however, the magnitude is small
- the evaluation directional accuracy is only slightly above chance

Therefore, the current model should be treated as a first benchmark, not as a final predictive system.

## Relation to Direction Prediction

A direction-based model was also tested as a secondary comparison branch.

In this single anchor experiment, the direction model looked slightly better than the return model on evaluation metrics. However, the difference was small, and the current project direction still keeps return prediction as the main path because:

- it preserves more information than a binary label
- it is better aligned with the original goal of modeling market movement strength
- it gives a cleaner foundation for later extensions such as regularized linear models

## Next Step

The next step is model selection inside the strategy-signal space.

The most natural candidates are:

- OLS
- Ridge regression
- Lasso
- Elastic Net

These models are appropriate because the feature dimension is small, the signals are interpretable, and the project is interested not only in prediction but also in how strategy-space operators should be defined and compared.
