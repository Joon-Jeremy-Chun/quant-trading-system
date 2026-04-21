# Dynamic Capital Allocation System — Big Picture Vision

Date: 2026-04-19

## Core Insight

Raw strategy return vs buy-and-hold is not the right metric in isolation.
The correct metric is **capital efficiency**:

```
Capital Efficiency = Strategy Return / Average Exposure
```

Example:
- GLD model returns 50% of buy-and-hold but uses only 10% exposure
- The remaining 90% of capital is free to deploy elsewhere
- System-level return can far exceed any single-asset buy-and-hold

## The Exposure Signal Is the Real Output

The model's most valuable output is not the return prediction itself —
it is the **confidence-weighted exposure decision**.

- When the model is confident → high exposure
- When the model is uncertain → low exposure → capital freed up

This is a natural property of the current strategy-space model:
in ambiguous regimes, predicted weights shrink toward zero.

## Closed System Logic

Total portfolio capital is conserved (closed system).

Key implication:
- When GLD exposure is low → that capital must go somewhere
- Different assets have different regime characteristics
- GLD low-confidence periods may coincide with high-confidence periods in equities, bonds, or crypto
- This is an empirical question worth researching, but the theoretical motivation is sound

## Multi-Dimensional Extension

Each asset gets its own strategy-space model:

```
GLD model     → exposure_GLD(t)
Equity model  → exposure_EQ(t)
Bond model    → exposure_BOND(t)
Crypto model  → exposure_CRYPTO(t)
```

The system allocates capital dynamically across assets based on each model's
current exposure signal. No asset is permanently over- or under-allocated.

## Why This Is Different from Standard Multi-Asset Investing

Standard approach: fixed weights (e.g. 60/40), rebalanced periodically.

This system:
- Weights are model-driven, not fixed
- Each asset's weight reflects current predictive confidence
- The system is inherently regime-aware across all asset classes
- Low confidence in one asset automatically creates room for others

## Research Questions

1. Do GLD low-exposure periods correlate with equity high-exposure periods?
2. What is the right way to normalize exposure across asset classes?
3. How do we handle the constraint that total exposure <= 1.0 (or some leverage limit)?
4. Is there a meta-model that coordinates across assets, or do they operate independently?

## Development Roadmap

1. **Phase 1 (current):** GLD pipeline stable and live
2. **Phase 2:** Replicate pipeline for 1-2 equity assets (e.g. BRK.B, broad market ETF)
3. **Phase 3:** Study cross-asset exposure correlations
4. **Phase 4:** Build capital allocation layer on top of individual asset models
5. **Phase 5:** Live multi-asset deployment

## Related Notes

- `multi_asset_pipeline_vision_2026-04-19.md` — engineering plan for multi-asset pipeline
- `objective2_update_frequency_comparison_2026-04-19.md` — current GLD results
