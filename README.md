# Quant Trading System

This repository studies interpretable trading strategies, their combinations, and their predictive structure through a systematic research pipeline.

## Project Overview

The project is built around a simple idea: instead of relying on a single trading rule, we construct a strategy space, evaluate it across rolling anchor dates, and study how different combinations or predictive operators behave across time.

The current research is centered on four strategy families:

- adaptive band strategy
- moving-average crossover strategy
- adaptive volatility band strategy
- fear-greed candle-volume strategy

The present implementation is focused mainly on gold (`GLD`) as the first research asset.

## Current Research State

The repository now contains an end-to-end workflow for:

- parameter optimization across multiple lookback horizons
- anchor-date based rolling evaluation
- representative top-candidate extraction for each strategy family
- return-based strategy combination
- signal-matrix construction for prediction
- expanded strategy-space modeling with top-10 candidates per family
- forward validation from one anchor period into the next evaluation period
- rolling-tranche simulation for practical portfolio translation

This means the project has moved beyond simple backtests and now includes:

- in-sample model selection
- out-of-sample forward validation
- horizon discovery
- allocation-oriented simulation

## Core Objectives

### 1. Objective 1: Strategy Combination by Realized Return

Build a return matrix from selected representative strategies and find combination weights under explicit constraints.

Current variants include:

- signed weights in `[-1, 1]` with sum equal to `1`
- long-only weights in `[0, 1]` with sum equal to `1`

The main purpose is to test whether combining strategy families improves realized return over a selection period and whether those weights generalize to later evaluation windows.

### 2. Objective 2: Prediction Through Strategy-Space Matrix `A`

Transform strategies into numerical signal scores and treat them as basis functions in a strategy-space design matrix.

Current Objective 2 work includes:

- continuous signal scoring for adaptive band, MA crossover, and adaptive volatility band
- discrete event scoring for fear-greed candle-volume
- return prediction over multiple future horizons
- comparison of `OLS`, `Ridge`, `Lasso`, and `Elastic Net`
- expanded basis construction from top-10 candidates in each strategy family
- forward validation across semiannual anchor dates
- practical tranche simulations such as `45-day` and `130-day` rolling implementations

In this view, the matrix is not just a collection of strategy returns. It is a numerical representation of a strategy function space evaluated on market states.

### 3. Objective 3: Reusable Research Automation

Create a repeatable framework that supports large-scale rolling experiments without rebuilding logic by hand each time.

The current automation layer supports:

- multi-horizon strategy optimization
- anchor-date snapshots
- reuse of previously computed optimization outputs
- expanded strategy-basis construction
- forward-validation experiments
- result summaries, tables, and figures for documentation

## Main Current Findings

At the current stage of the project, several practical patterns have emerged.

### Objective 1

- Strategy combination is meaningful, but not uniformly dominant.
- Long-only combinations are often more stable than signed combinations.
- Shorter evaluation horizons tend to be more favorable than very long ones.

### Objective 2

- The useful predictive horizon is not constant across anchor dates.
- Some periods favor medium horizons such as `45-73` trading days.
- Other periods favor much longer horizons around `120-128` trading days.
- Across many anchor dates, `OLS` has been the strongest forward-validation model.
- In practical simulation, `45-day` tranche structures tend to react faster, while `130-day` tranche structures tend to behave more defensively with lower exposure.

These findings suggest that horizon choice, update frequency, and regime behavior may be just as important as model choice itself.

## Current Scope and Philosophy

This repository is intentionally focused on interpretable modeling rather than black-box prediction.

The working philosophy is:

- interpretable strategies first
- systematic rolling evaluation second
- predictive structure over strategy space third
- multi-asset expansion after the gold pipeline is well understood

This is closer to a mathematical research workflow than to a purely performance-chasing trading repository.

## Future Directions

### 1. Expand Beyond a Single Asset

The long-term goal is to move from a single-asset research pipeline to a broader cross-asset framework.

Planned categories include:

- commodities: oil, copper, gold
- equities: multiple sectors
- bonds: short-term and long-term
- FX: exchange-rate and arbitrage-oriented settings
- crypto: Bitcoin and related markets

The main question is whether the same strategy-space logic behaves differently across asset classes and market regimes.

### 2. Add Sentiment Analysis to Quantify Noise

Another major direction is to incorporate sentiment and narrative information as structured signals.

The purpose is not to use sentiment as informal commentary, but to convert it into analyzable information that may help explain:

- noisy price movement
- short-term dislocations
- emotional overreaction or underreaction
- gaps between technical signals and market narrative

### 3. Study Update Frequency and Regime Adaptation

Recent results suggest that update frequency may itself be a research variable.

Future work should test:

- semiannual versus monthly anchor updates
- slower versus faster horizon adaptation
- whether more frequent recalibration captures transitions earlier
- whether frequent updates simply overfit sideways noise

## Repository Structure

Key writing and documentation folders:

- `docs/notes/` for working notes, ideas, and decision logs
- `docs/reports/` for polished summaries, experiment writeups, and report drafts

Representative result folders:

- `outputs/` for numerical experiment results
- `figures/` for generated plots and visual summaries
- `strategies/automation/` for reusable research scripts

## Suggested Reading Order

If you are new to the repository, a practical reading path is:

1. this `README.md`
2. [docs/README.md](/C:/Users/joonc/My_github/quant-trading-system/docs/README.md)
3. [objective_progress_summary_2026-04-08.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective_progress_summary_2026-04-08.md)
4. [objective2_return_baseline_report_2026-04-08.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_return_baseline_report_2026-04-08.md)
5. [objective2_expanded_strategy_space_report_2026-04-09.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_expanded_strategy_space_report_2026-04-09.md)
6. [objective2_forward_validation_selection_mechanisms_report_2026-04-10.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_forward_validation_selection_mechanisms_report_2026-04-10.md)
7. [objective2_multi_anchor_tranche_summary_2026-04-14.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_multi_anchor_tranche_summary_2026-04-14.md)
