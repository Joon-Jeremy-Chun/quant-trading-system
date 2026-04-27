"""
Oracle Simulation — theoretical upper bound for the multi-asset signal-ratio strategy.

Assumption: the model predicts the future 100% correctly.
The "signal" on each day is derived from the ACTUAL future 130-day return of each asset.

Two modes:
  full         : invest 100% of each slot whenever any asset has positive future return
  proportional : invest proportional to future return magnitude (bigger return -> bigger weight)

Cash rule (both modes):
  - If both assets have negative 130d future return -> hold cash (HOLD day)
  - Otherwise -> invest in positive-return assets by ratio

This gives the theoretical upper bound of the multi-asset tranche strategy.

Usage:
  python research/oracle_simulation/run_oracle_simulation.py \
    --data-csv-a data/gld_us_d.csv \
    --data-csv-b data/brkb_us_d.csv \
    --label-a GLD --label-b BRKB \
    --hold-days 130 \
    --eval-start 2020-01-01 \
    --eval-end 2024-12-31
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT  = Path(__file__).resolve().parents[2]
OUT_DIR    = Path(__file__).resolve().parent / "outputs"
sys.path.insert(0, str(REPO_ROOT / "strategies" / "automation"))

from simulate_multi_asset_tranches import simulate_multi_asset_tranches, DATE_COL
from strategy_matrix_builder import load_price_only_data


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--data-csv-a",      required=True)
    p.add_argument("--data-csv-b",      required=True)
    p.add_argument("--label-a",         default="A")
    p.add_argument("--label-b",         default="B")
    p.add_argument("--hold-days",       type=int, default=130)
    p.add_argument("--initial-capital", type=float, default=1.0)
    p.add_argument("--eval-start",      default="2020-01-01")
    p.add_argument("--eval-end",        default="2024-12-31")
    p.add_argument("--mode",            choices=["full", "proportional", "both"], default="both",
                   help="full=always 100% when positive; proportional=weight by return magnitude")
    return p.parse_args()


def load_prices(csv_path: str) -> pd.DataFrame:
    df = load_price_only_data(Path(csv_path)).rename(columns={"Price": "price"})
    return df[[DATE_COL, "price"]].sort_values(DATE_COL).reset_index(drop=True)


def compute_oracle_signals(
    prices_a: pd.DataFrame,
    prices_b: pd.DataFrame,
    hold_days: int,
    mode: str,
) -> pd.DataFrame:
    """
    For each date, look forward hold_days and compute the actual return.
    Derive oracle weights from those returns.
    """
    df = (prices_a.rename(columns={"price": "price_a"})
          .merge(prices_b.rename(columns={"price": "price_b"}), on=DATE_COL, how="inner")
          .sort_values(DATE_COL).reset_index(drop=True))

    n = len(df)
    w_a = np.zeros(n)
    w_b = np.zeros(n)

    for i in range(n):
        future_idx = i + hold_days
        if future_idx >= n:
            # not enough future data — hold cash
            continue

        ret_a = df["price_a"].iloc[future_idx] / df["price_a"].iloc[i] - 1.0
        ret_b = df["price_b"].iloc[future_idx] / df["price_b"].iloc[i] - 1.0

        pos_a = max(ret_a, 0.0)
        pos_b = max(ret_b, 0.0)

        if pos_a + pos_b == 0:
            # both negative -> hold cash
            continue

        if mode == "full":
            # invest 100% in positive assets, split by ratio (1:1 if both positive)
            w_a[i] = 1.0 if pos_a > 0 else 0.0
            w_b[i] = 1.0 if pos_b > 0 else 0.0
        else:  # proportional
            # weight = return magnitude (larger return = larger weight)
            total = pos_a + pos_b
            w_a[i] = pos_a / total
            w_b[i] = pos_b / total

    df["w_a"] = w_a
    df["w_b"] = w_b
    return df


def run_mode(df: pd.DataFrame, args: argparse.Namespace, mode: str) -> dict:
    equity_df, _ = simulate_multi_asset_tranches(
        df=df,
        weight_col_a="w_a",
        weight_col_b="w_b",
        price_col_a="price_a",
        price_col_b="price_b",
        hold_days=args.hold_days,
        initial_capital=args.initial_capital,
        label_a=args.label_a,
        label_b=args.label_b,
    )

    equity_df["year"] = equity_df[DATE_COL].dt.year
    years = sorted(equity_df["year"].unique())

    total_ret = equity_df["net_equity"].iloc[-1] / equity_df["net_equity"].iloc[0] - 1
    avg_exp   = (equity_df["gross_exposure"] / equity_df["net_equity"]).mean()
    avg_exp_a = (equity_df[f"exposure_{args.label_a}"] / equity_df["net_equity"]).mean()
    avg_exp_b = (equity_df[f"exposure_{args.label_b}"] / equity_df["net_equity"]).mean()

    year_stats = {}
    effs = []
    for y in years:
        grp = equity_df[equity_df["year"] == y]
        if len(grp) < 2: continue
        ret  = grp["net_equity"].iloc[-1] / grp["net_equity"].iloc[0] - 1
        exp  = (grp["gross_exposure"] / grp["net_equity"]).mean()
        ea   = (grp[f"exposure_{args.label_a}"] / grp["net_equity"]).mean()
        eb   = (grp[f"exposure_{args.label_b}"] / grp["net_equity"]).mean()
        bh_a = grp["price_a"].iloc[-1] / grp["price_a"].iloc[0] - 1
        bh_b = grp["price_b"].iloc[-1] / grp["price_b"].iloc[0] - 1
        eff  = ret / exp if exp > 0 else 0
        effs.append(eff)
        year_stats[int(y)] = {"return": ret, "exp": exp, "exp_a": ea, "exp_b": eb,
                               "eff": eff, "bh_a": bh_a, "bh_b": bh_b}

    arr    = np.array(effs)
    sharpe = arr.mean() / arr.std(ddof=1) if len(arr) > 1 and arr.std(ddof=1) > 0 else float("nan")
    ann    = (1 + total_ret) ** (1/5) - 1

    return dict(mode=mode, total_ret=total_ret, ann_ret=ann,
                avg_exp=avg_exp, avg_exp_a=avg_exp_a, avg_exp_b=avg_exp_b,
                avg_eff=arr.mean(), worst_eff=arr.min(), sharpe=sharpe,
                year_stats=year_stats, equity_df=equity_df)


def print_result(r: dict, label_a: str, label_b: str) -> None:
    print(f"\n{'='*65}")
    print(f"  Mode: {r['mode'].upper()}")
    print(f"{'='*65}")
    print(f"  5yr return:   {r['total_ret']:+.1%}")
    print(f"  Annualized:   {r['ann_ret']:+.1%}")
    print(f"  Avg exposure: {r['avg_exp']:.0%}  ({label_a}: {r['avg_exp_a']:.0%}  {label_b}: {r['avg_exp_b']:.0%})")
    print(f"  Avg eff:      {r['avg_eff']:+.1%}")
    print(f"  Worst year:   {r['worst_eff']:+.1%}")
    print(f"  Sharpe(eff):  {r['sharpe']:.2f}")
    print(f"\n  Year  |  Strategy  |   Exp  |  {label_a:>5}  |  {label_b:>5}  |   Eff  |  BH_{label_a}  |  BH_{label_b}")
    print(f"  {'-'*72}")
    for y, s in sorted(r["year_stats"].items()):
        print(f"  {y}  |  {s['return']:>+8.2%}  |  {s['exp']:.0%}  |  {s['exp_a']:.0%}  |  {s['exp_b']:.0%}  |  {s['eff']:>+5.1%}  |  {s['bh_a']:>+7.1%}  |  {s['bh_b']:>+7.1%}")


def main() -> None:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    prices_a = load_prices(args.data_csv_a)
    prices_b = load_prices(args.data_csv_b)

    modes = ["full", "proportional"] if args.mode == "both" else [args.mode]
    results = []

    for mode in modes:
        df = compute_oracle_signals(prices_a, prices_b, args.hold_days, mode)
        df = df[(df[DATE_COL] >= args.eval_start) & (df[DATE_COL] <= args.eval_end)].reset_index(drop=True)

        r = run_mode(df, args, mode)
        results.append(r)
        print_result(r, args.label_a, args.label_b)

        eq_path  = OUT_DIR / f"oracle_{mode}_equity_{args.label_a}_{args.label_b}.csv"
        sum_path = OUT_DIR / f"oracle_{mode}_summary_{args.label_a}_{args.label_b}.json"
        r["equity_df"].drop(columns=["year"]).to_csv(eq_path, index=False)
        payload = {k: v for k, v in r.items() if k != "equity_df"}
        with open(sum_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\n  [OK] {eq_path.name}")

    # comparison table
    if len(results) == 2:
        print(f"\n{'='*65}")
        print("  FULL vs PROPORTIONAL comparison")
        print(f"{'='*65}")
        print(f"  {'':>14}  {'FULL':>10}  {'PROPORTIONAL':>14}")
        for key, label in [("total_ret","5yr ret"), ("ann_ret","Annual ret"),
                            ("avg_exp","Avg exp"), ("avg_eff","Avg eff"),
                            ("worst_eff","Worst"), ("sharpe","Sharpe")]:
            vals = [r[key] for r in results]
            fmt = ".1%" if "ret" in key or "eff" in key or "exp" in key else ".2f"
            print(f"  {label:>14}  {vals[0]:>10{fmt}}  {vals[1]:>14{fmt}}")


if __name__ == "__main__":
    main()
