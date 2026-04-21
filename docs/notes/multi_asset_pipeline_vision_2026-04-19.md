# Multi-Asset Pipeline Vision

Date: 2026-04-19

## Core Idea

The full pipeline built for GLD — data ingestion → strategy optimization → anchor snapshots → model fitting → live signal — should become a **generic, reusable pipeline** applicable to any asset class.

## Target Asset Classes

- Equities (e.g. BRK.A, BRK.B, general stocks)
- Bonds / fixed income
- Crypto (24/7 markets)
- Other ETFs or commodities

Note: BRK.A, BRK.B, and RKLB data already exist in the `data/` directory, indicating this direction was anticipated early.

## Key Engineering Challenges

### 1. Asset-specific characteristics
- Equities: standard OHLCV, market hours
- Crypto: 24/7, no market close, different volatility regime
- Bonds: different data structure, yield-based pricing
- Each asset requires re-optimization of strategy parameters (k_body, ma_window, etc.)

### 2. Config-driven abstraction
- Current codebase has GLD paths and settings partially hardcoded
- Need to abstract `symbol`, `data_path`, `asset_class` into a config layer
- The GLD pipeline becomes the template; each new asset gets its own config file

## Vision

Once the GLD pipeline is stable and validated, it serves as the reference implementation.
New assets are onboarded by:
1. Providing a data CSV in the standard format
2. Running strategy optimization for that asset
3. Generating anchor snapshots
4. Running the monthly model update backtest
5. Deploying a live signal alongside GLD

## Status

- GLD pipeline: nearly complete, bugs fixed, live on Raspberry Pi
- Next asset: TBD
