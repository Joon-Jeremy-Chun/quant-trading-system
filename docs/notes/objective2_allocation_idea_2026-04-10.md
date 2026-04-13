# Objective 2 Allocation Idea - 2026-04-10

## Context

Today we translated the selected Objective 2 forward-validation model into an investable rule.

The model used:

- Anchor date: `2024-12-31`
- Expanded strategy space: top 10 candidates from each strategy family
- Selected horizon: `45` trading days
- Selected model: `OLS`
- Main out-of-sample statistic in 2025:
  - evaluation correlation: `0.731964`

## First Investment Translation

We tested a simple long-only rolling-tranche rule:

- split capital into `45` tranches
- each day, compute the model's predicted 45-day return
- convert the prediction into a portfolio weight between `0` and `1`
- allocate one tranche using that weight
- hold each tranche for `45` trading days
- recycle capital when the tranche matures

The first implementation used a prediction-to-weight scaling based on the selection-period prediction distribution.

## First Result

For 2025:

- average portfolio weight: about `31.7%`
- average gross exposure: about `31.4%`
- strategy return: about `14.1%`
- buy-and-hold return: about `23.9%`

So the strategy underperformed buy-and-hold in raw return, but this should not be read too negatively.

## Why This Result Still Matters

The key observation is:

- the strategy used only about one-third of capital on average
- yet it still produced a positive double-digit return

This suggests that the model may be more useful as a **capital-efficient allocator or filter** rather than as a full-exposure standalone trading system.

## Important Interpretation

Objective 2 may not be saying:

- "always hold gold with this model"

It may instead be saying:

- "use this model to decide when gold deserves capital"

This becomes much more meaningful in a multi-asset setting.

## Multi-Asset Research Idea

If the same pipeline is run on other assets, then the model outputs can be interpreted as capital-allocation filters across assets.

Possible asset groups:

- commodities: gold, oil, copper
- equities: sector ETFs or broad equity groups
- bonds: short-duration and long-duration
- FX
- crypto: Bitcoin and possibly other major assets

In that setting, a gold sleeve using only about 31% average exposure is not a weakness by itself. It may simply mean:

- gold is not always the best place to deploy capital
- unused capital can be routed to other assets whose models currently produce stronger signals

## Working Hypothesis

Objective 2 may be more valuable as:

- a **cross-asset signal allocator**

than as:

- a single-asset always-on trading rule

## Next Questions

1. Compare different position-translation rules for the 45-day model:
   - binary long-only
   - proportional long-only
   - long-short proportional
2. Measure risk-adjusted performance, not just raw return:
   - average exposure
   - exposure-adjusted return
   - drawdown
3. Extend the same methodology to other assets and compare:
   - signal quality
   - average exposure
   - future correlation
4. Study whether Objective 2 should ultimately be interpreted as:
   - a return predictor
   - a timing filter
   - or a multi-asset capital allocator
