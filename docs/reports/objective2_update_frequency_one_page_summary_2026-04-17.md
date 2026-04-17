# Objective 2 Update-Frequency One-Page Summary

Date: 2026-04-17

## Purpose

This is a compact one-page summary of the update-frequency experiments over `2020~2024`.

The goal is to answer a simple practical question:

**If we keep the holding structure fixed, which update cadence looked best each year?**

Two holding structures are compared:

- `45-day hold`
- `130-day hold`

Update cadence candidates:

- `1M`
- `2M`
- `3M`
- `6M`

## Compact Summary Table

| Year | Buy & Hold | 45d Best Return | 45d Best Eff. | 130d Best Return | 130d Best Eff. |
|---|---:|---|---|---|---|
| 2020 | 20.2211% | `2M`, 7.8473% at 47.1591% exp. | `2M`, 16.6401% | `6M`, 10.9232% at 63.0398% exp. | `3M`, 18.1764% |
| 2021 | -6.2359% | `3M`, 0.5901% at 30.0731% exp. | `3M`, 1.9622% | `1M`, 0.0020% at 36.1391% exp. | `1M`, 0.0056% |
| 2022 | 0.7782% | `6M`, 0.7595% at 38.5186% exp. | `6M`, 1.9718% | `6M`, 2.5382% at 36.3462% exp. | `6M`, 6.9833% |
| 2023 | 11.7561% | `6M`, 3.9617% at 27.2618% exp. | `6M`, 14.5321% | `6M`, 4.2488% at 18.7912% exp. | `6M`, 22.6107% |
| 2024 | 26.9557% | `1M`, 10.0075% at 32.3955% exp. | `1M`, 30.8915% | `3M`, 9.3277% at 46.9183% exp. | `3M`, 19.8807% |

## Quick Read

- `45-day hold`
  - `2020`: `2M` was best
  - `2021`: `3M` was best
  - `2022`: `6M` was best
  - `2023`: `6M` was best
  - `2024`: `1M` was best

- `130-day hold`
  - `2020`: raw return favored `6M`, but efficiency favored `3M`
  - `2021`: `1M` was best
  - `2022`: `6M` was best
  - `2023`: `6M` was best
  - `2024`: `3M` was best

## Main Takeaway

There is still **no single update frequency that dominates all years**.

But the broad pattern is now clearer:

- `1M` = most adaptive, especially helpful in defensive or fast-transition years
- `3M` = strongest balanced compromise
- `6M` = strongest in persistent regimes

For practical use, the current evidence still supports:

- **fast mode**: `1M`
- **balanced mode**: `3M`
- **slow efficient mode**: `6M`

## Saved Files

- [objective2_hold_update_frequency_compact_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_update_frequency_comparison/objective2_hold_update_frequency_compact_2026-04-17.csv)
- [objective2_hold_update_frequency_wide_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_update_frequency_comparison/objective2_hold_update_frequency_wide_2026-04-17.csv)
- [update_frequency_strategy_return_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_update_frequency/update_frequency_strategy_return_2026-04-17.png)

## Related Reports

- [objective2_update_frequency_comparison_2026-04-17.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_update_frequency_comparison_2026-04-17.md)
- [objective2_hold_update_block_behavior_report_2026-04-17.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_hold_update_block_behavior_report_2026-04-17.md)
