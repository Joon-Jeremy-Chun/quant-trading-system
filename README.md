# Quant Trading System

This repository studies rule-based trading strategies and their combinations through a systematic research pipeline.

## Project Overview

The project focuses on building interpretable trading strategies, evaluating them across rolling time windows, and combining them in a structured way rather than relying on a single rule or a single market view.

The current research is centered on four strategy families:

- adaptive band strategy
- moving-average crossover strategy
- adaptive volatility band strategy
- fear-greed candle-volume strategy

## Current Core Objectives

### 1. Objective 1: Strategy Combination by Realized Return

Build a return matrix from representative strategies and find bounded signed weights that combine them into a stronger portfolio over a selection period, then test those weights on later evaluation periods.

### 2. Objective 2: Prediction Through Signal Matrix A

Transform each strategy into a continuous or event-based signal score and construct a predictor matrix `A` that can be used to study future gold-price direction or return prediction.

### 3. Objective 3: Reusable Research Automation

Create a repeatable research workflow that supports:

- multi-horizon optimization
- anchor-date evaluation
- representative-parameter selection
- matrix construction for both return optimization and prediction tasks

## Current Scope

The present version of the project is centered mainly on gold and on interpretable strategy research rather than black-box modeling.

## Future Directions

### 1. Expand Beyond a Single Asset

The long-term goal is not to stop at one asset, but to extend this strategy-combination framework across multiple categories and compare how combinations behave in different market structures.

Planned categories include:

- commodities: oil, copper, gold
- equities: multiple sectors
- bonds: short-term and long-term
- FX: exchange-rate and arbitrage-oriented settings
- crypto: Bitcoin and related markets

The main idea is to broaden the analysis from one market to a cross-asset strategy-combination framework.

### 2. Add Sentiment Analysis to Quantify Noise

Another future goal is to incorporate sentiment analysis so that market noise can be studied in a more structured way.

This means using sentiment-related information not just as commentary, but as an analyzable signal that may help explain:

- noisy price movement
- short-term dislocations
- emotional overreaction or underreaction
- differences between technical signals and market narrative

## Repository Writing Structure

Project writing is stored in:

- `docs/notes/` for working notes, ideas, and decision logs
- `docs/reports/` for cleaner summaries and report drafts

## Philosophy

This repository aims to keep the research process interpretable, modular, and extensible:

- interpretable strategies first
- systematic evaluation second
- cross-asset and sentiment-aware expansion next
