# Objective 2 Hold/Update and Block-Behavior Report

Date: 2026-04-17

## Purpose

This note extends the earlier hold/update and block-behavior analysis to include `2020`, so the sample now covers `2020~2024`.

It consolidates three layers of analysis:

1. A large comparison table over:
   - holding horizon `45` vs `130`
   - update frequency `1M`, `2M`, `3M`, `6M`
   - years `2020` to `2024`
2. Exposure-adjusted efficiency using a simple `100%-equivalent` proxy
3. Block-level behavior analysis, asking whether the system reduced exposure in weaker buy-and-hold segments and increased exposure in stronger ones

The broader motivation is multi-asset deployment. In a multi-asset system, a model does not need to beat buy-and-hold in absolute return every time in order to be useful. It may still be valuable if it:

- uses capital efficiently,
- avoids heavy exposure in weak periods,
- and frees capital for other assets when its own signal is weak.

## Large Comparison Table

The full combined table was saved here:

- [objective2_hold_update_frequency_wide_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_update_frequency_comparison/objective2_hold_update_frequency_wide_2026-04-17.csv)

The long-format version was also saved:

- [objective2_hold_update_frequency_long_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_update_frequency_comparison/objective2_hold_update_frequency_long_2026-04-17.csv)

The table includes, for each run:

- buy-and-hold return
- strategy return
- average exposure
- a simple exposure-adjusted proxy:

\[
\text{100%-Eq Return} \approx \frac{\text{Strategy Return}}{\text{Average Exposure}}
\]

This is not a true leveraged backtest. It is a practical proxy for capital efficiency.

## Main Visuals

These figures summarize the update-frequency comparisons:

- [update_frequency_strategy_return_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_update_frequency/update_frequency_strategy_return_2026-04-17.png)
- [update_frequency_average_exposure_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_update_frequency/update_frequency_average_exposure_2026-04-17.png)
- [update_frequency_efficiency_proxy_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_update_frequency/update_frequency_efficiency_proxy_2026-04-17.png)

## Question 1: Did Any Scenario Beat Buy-and-Hold in Raw Return?

Yes.

Across all tested runs:

- total runs: `40`
- runs that beat buy-and-hold in raw final return: `10`
- runs where buy-and-hold still won in raw final return: `30`

So raw outperformance exists, but it is still the minority outcome.

## Question 2: Did Any Scenario Beat Buy-and-Hold on Efficiency?

Yes, more often.

Across all tested runs:

- runs that beat buy-and-hold on the `100%-equivalent` efficiency proxy: `17`
- runs where buy-and-hold still won on that proxy: `23`

This is still a meaningful result for multi-asset deployment.

Even when the strategy did not beat buy-and-hold in total return, it sometimes achieved:

- lower capital usage,
- decent return,
- and therefore higher return per unit of average market exposure

This keeps the system interesting as a component in a larger allocator rather than only as a single-asset replacement for buy-and-hold.

## Question 3: Did the Model Reduce Exposure in Weak Periods and Raise It in Strong Periods?

This was tested by re-aggregating the daily results into `45-day` and `130-day` blocks.

Saved outputs:

- [objective2_run_level_summary_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_block_behavior_analysis/objective2_run_level_summary_2026-04-17.csv)
- [objective2_block_level_summary_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_block_behavior_analysis/objective2_block_level_summary_2026-04-17.csv)
- [objective2_block_behavior_summary_2026-04-17.csv](/C:/Users/joonc/My_github/quant-trading-system/outputs/objective2_block_behavior_analysis/objective2_block_behavior_summary_2026-04-17.csv)

Figures:

- [block_exposure_gap_45dayblocks_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_block_behavior/block_exposure_gap_45dayblocks_2026-04-17.png)
- [block_bh_vs_exposure_scatter_2026-04-17.png](/C:/Users/joonc/My_github/quant-trading-system/figures/objective2_block_behavior/block_bh_vs_exposure_scatter_2026-04-17.png)

### Result

The answer is still: **partially, but not consistently enough yet.**

For `45-day` blocks:

- runs where exposure was higher in positive buy-and-hold blocks: `14`
- runs where exposure was higher in negative buy-and-hold blocks: `26`

For `130-day` blocks:

- runs where exposure was higher in positive buy-and-hold blocks: `8`
- runs where exposure was higher in negative buy-and-hold blocks: `16`

So after adding `2020`, the exposure-control pattern looks even more mixed than before.

This means the system does **not** yet show a stable and universal tendency to always:

- reduce exposure in bad blocks
- increase exposure in good blocks

## Interpretation

### 1. Absolute outperformance exists, but is not yet dominant

There are clear examples where the strategy beats buy-and-hold, especially in difficult years. But there is not yet one configuration that wins cleanly across all conditions.

### 2. Efficiency remains the stronger argument

The capital-efficiency argument is still stronger than the absolute-return argument.

This matters because in a multi-asset framework:

- low exposure in one asset is not wasted if another asset can use that capital better
- the system only needs to provide a useful conditional allocation signal

### 3. Exposure control remains the key next frontier

The most important open problem is no longer only “which update frequency is best?”

It is now:

**“Can the model reliably raise exposure when local opportunity is strong and reduce exposure when local opportunity is weak?”**

That question matters more than pure single-asset outperformance if the long-term plan is a multi-asset system involving:

- gold
- oil
- equities
- bonds
- currencies
- crypto

## Working Conclusion

At this stage:

1. The strategy space and update-frequency experiments continue to produce meaningful structure.
2. Buy-and-hold can be beaten in some scenarios, but not most.
3. Exposure-adjusted efficiency is still the stronger case for the system.
4. The system remains promising as a multi-asset allocation component.
5. But the block-level evidence shows that exposure control is not yet consistent enough to claim robust regime-aware behavior.

So the next mathematical and practical step is still clear:

**we should focus on modeling and testing the relationship between local opportunity and local exposure more directly.**

## Related Files

- [objective2_hold_update_block_behavior_report_2026-04-16.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_hold_update_block_behavior_report_2026-04-16.md)
- [objective2_update_frequency_comparison_2026-04-17.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_update_frequency_comparison_2026-04-17.md)
- [objective2_multi_anchor_tranche_summary_2026-04-14.md](/C:/Users/joonc/My_github/quant-trading-system/docs/reports/objective2_multi_anchor_tranche_summary_2026-04-14.md)
