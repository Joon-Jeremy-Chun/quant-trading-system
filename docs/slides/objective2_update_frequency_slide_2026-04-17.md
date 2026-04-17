# Slide Draft: Update Frequency

## Slide Title

**How Often Should the Model Be Updated?**

## Slide Subtitle

Fixed holding structure, varying model refresh cadence

## Speaker Message

- We fixed the holding structure and changed only the model update frequency.
- We tested two holding horizons:
  - `45-day hold`
  - `130-day hold`
- We compared four update cadences:
  - `1M`, `2M`, `3M`, `6M`
- The goal was to see whether faster updating always helps, or whether the best cadence depends on market regime.

## Slide Table

| Year | Buy & Hold | 45d Best | 130d Best |
|---|---:|---|---|
| 2020 | 20.22% | `2M` best | `6M` raw, `3M` efficient |
| 2021 | -6.24% | `3M` best | `1M` best |
| 2022 | 0.78% | `6M` best | `6M` best |
| 2023 | 11.76% | `6M` best | `6M` best |
| 2024 | 26.96% | `1M` best | `3M` best |

## Slide Takeaways

- There is **no single update frequency** that dominates every year.
- `1M` behaves like a **fast adaptive mode**.
- `3M` behaves like the most **balanced compromise**.
- `6M` works best in more **persistent trend regimes**.

## Closing Line

**Conclusion:** update frequency should be treated as a regime-dependent design choice, not a fixed universal constant.

## Optional Figure

- [update_frequency_strategy_return_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_update_frequency/update_frequency_strategy_return_2026-04-17.png)

## Source Files

- [objective2_update_frequency_one_page_summary_2026-04-17.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_update_frequency_one_page_summary_2026-04-17.md)
- [objective2_hold_update_frequency_compact_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_update_frequency_comparison/objective2_hold_update_frequency_compact_2026-04-17.csv)
