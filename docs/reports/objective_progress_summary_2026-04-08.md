# Objective Progress Summary - 2026-04-08

## Summary

The project now has working automation for Objective 1 and a prepared signal-matrix pipeline for Objective 2.

## Objective 1

- Four strategy families are optimized individually over multiple horizons
- Representative parameter sets are selected from optimization results
- A daily strategy return matrix is constructed for the selection period
- Portfolio weights are chosen under bounded signed weights with a sum-to-one constraint
- Evaluation is run across multiple future horizons after each anchor date

## Main empirical takeaway

Across the 5-year experiment with 6-month anchor spacing, shorter evaluation horizons showed more favorable combined-strategy results than longer horizons.

- `1m` evaluation had the strongest relative behavior on average
- `3m` and `6m` were weaker but still had some positive cases
- `9m` and `12m` were generally weaker against buy-and-hold

## Objective 2

Objective 2 has been framed as a prediction problem using a signal matrix `A`.

- Column 1: adaptive band score
- Column 2: moving-average crossover spread score
- Column 3: adaptive volatility-band score
- Column 4: fear-greed event score

The next step is to generate the signal matrix and define the prediction target clearly.

## Documentation rule

This report folder should contain cleaner summaries, while `docs/notes/` should hold rougher daily thinking and intermediate decisions.
