# Objective 1 Weight-Constraint Analysis - 2026-04-08

## Purpose

This note summarizes an additional comparison inside Objective 1 after introducing a second weight constraint setting.

The original setting used signed weights:

- `w_i in [-1, 1]`
- `sum(w_i) = 1`

The additional setting used long-only weights:

- `w_i in [0, 1]`
- `sum(w_i) = 1`

In both cases, the representative strategy parameters were kept fixed for each anchor date. Only the portfolio-weight constraint was changed.

## Experimental Setup

For each anchor date:

1. The previous 1-year window was used as the selection period.
2. Representative parameters for the four strategy families were taken from the precomputed optimization results.
3. Portfolio weights were estimated on the selection-period strategy return matrix.
4. The learned weights were then applied to the following evaluation horizons:
   - `1m`
   - `3m`
   - `6m`
   - `9m`
   - `12m`

The analysis was performed over 10 anchor dates spaced at 6-month intervals.

## Main Findings

### 1. The long-only constraint was often more stable than the signed constraint

The signed setting performed well on the selection period because it could simultaneously overweight strong strategies and assign negative weights to weak ones. However, this flexibility did not always carry over well to later evaluation periods.

In contrast, the long-only setting was usually more stable out of sample, especially at medium and long horizons.

Average evaluation excess return relative to buy-and-hold:

| Horizon | Signed (`[-1,1]`) | Long-only (`[0,1]`) |
|---|---:|---:|
| 1m  | +0.0147 | -0.0061 |
| 3m  | -0.0197 | -0.0141 |
| 6m  | -0.0129 | +0.0003 |
| 9m  | -0.0669 | -0.0247 |
| 12m | -0.1258 | -0.0417 |

This suggests that the signed constraint was more aggressive, while the long-only constraint was more robust across longer evaluation windows.

### 2. Signed weights were stronger only at the shortest horizon

At the 1-month horizon, the signed model remained superior on average:

- signed average excess return: `+0.0147`
- long-only average excess return: `-0.0061`

This indicates that allowing negative weights may help at very short horizons, where reversing weak signals can sometimes improve performance.

### 3. Long-only outperformed signed in many medium- and long-horizon cases

Number of cases in which long-only beat signed:

| Horizon | Long-only better than signed |
|---|---:|
| 1m  | 3 / 10 |
| 3m  | 5 / 10 |
| 6m  | 6 / 10 |
| 9m  | 6 / 10 |
| 12m | 7 / 10 |

This pattern shows that the long-only model became increasingly competitive as the evaluation horizon lengthened.

## Interpretation

The result is economically intuitive.

The signed setting can treat some strategies as “anti-signals” by assigning negative weights to them. This can produce strong in-sample results, but it also increases sensitivity to regime changes. If a strategy that looked weak during selection stops behaving like a reliable negative signal later, the signed portfolio can deteriorate quickly.

The long-only setting avoids this problem. It simply reallocates capital among the available strategies without explicitly betting against any one of them. As a result, it appears to be more conservative and more stable in out-of-sample evaluation.

## Combination vs. Single Strategy

The combination model was often useful, but the result should be interpreted carefully.

- In some cases, the combined portfolio outperformed buy-and-hold.
- In some cases, combining strategies was better than relying on a single rule.
- However, the combined model did not consistently beat the best standalone strategy in each evaluation window.

Across the 50 evaluation cases:

- the signed combination beat the best standalone strategy in `9 / 50` cases
- the long-only combination beat the best standalone strategy in `0 / 50` cases

This means the combination framework was still informative, but its main value at this stage is not that it always dominates the best single strategy. Instead, its value lies more in structured diversification, interpretability, and the ability to compare different constraint settings systematically.

## Conclusion

The additional constraint test produced a clear message:

- the signed model was more aggressive and worked better at the shortest horizon
- the long-only model was more stable at medium and long horizons
- combining strategies can be helpful, but its benefit is conditional rather than universal

Therefore, for Objective 1, the long-only coverage is a meaningful complement to the original signed-weight framework and provides a more realistic benchmark for out-of-sample portfolio construction.
