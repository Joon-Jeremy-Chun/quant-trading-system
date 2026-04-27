"""
Multi-asset signal-ratio tranche backtest.

Loads pre-computed daily signal CSVs for two assets (e.g. GLD + BRK-B),
merges on date, then runs the multi-asset tranche simulator.

Usage:
  python strategies/automation/run_multi_asset_tranche_backtest.py \
    --signal-csv-a  outputs/objective2_monthly_update_tranche_backtest/monthly_update_tranche_backtest_daily_signals_top50_h130.csv \
    --signal-csv-b  outputs/objective2_monthly_update_tranche_backtest/monthly_update_tranche_backtest_daily_signals_brkb_top10_h130.csv \
    --data-csv-a    data/gld_us_d.csv \
    --data-csv-b    data/brkb_us_d.csv \
    --label-a GLD --label-b BRKB \
    --hold-days 130 \
    --tag gld_brkb_top50_h130
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from simulate_multi_asset_tranches import simulate_multi_asset_tranches, DATE_COL
from strategy_matrix_builder import load_price_only_data

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT   = SCRIPT_DIR.parents[1]
DEFAULT_OUT = REPO_ROOT / "outputs" / "multi_asset_backtest"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--signal-csv-a",  required=True, help="Daily signals CSV for asset A.")
    p.add_argument("--signal-csv-b",  required=True, help="Daily signals CSV for asset B.")
    p.add_argument("--data-csv-a",    required=True, help="Price CSV for asset A.")
    p.add_argument("--data-csv-b",    required=True, help="Price CSV for asset B.")
    p.add_argument("--label-a",       default="A",   help="Label for asset A.")
    p.add_argument("--label-b",       default="B",   help="Label for asset B.")
    p.add_argument("--hold-days",     type=int, default=130)
    p.add_argument("--initial-capital", type=float, default=1.0)
    p.add_argument("--eval-start",    default=None,  help="Filter start date (YYYY-MM-DD).")
    p.add_argument("--eval-end",      default=None,  help="Filter end date (YYYY-MM-DD).")
    p.add_argument("--tag",           default=None)
    return p.parse_args()


def load_signals(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=[DATE_COL])
    return df[[DATE_COL, "portfolio_weight", "predicted_future_return"]].sort_values(DATE_COL)


def load_prices(csv_path: str) -> pd.DataFrame:
    df = load_price_only_data(Path(csv_path)).rename(columns={"Price": "price"})
    return df[[DATE_COL, "price"]].sort_values(DATE_COL)


def maybe_tagged(base: Path, stem: str, suffix: str, tag: str | None) -> Path:
    name = f"{stem}_{tag}{suffix}" if tag else f"{stem}{suffix}"
    return base / name


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    sig_a  = load_signals(args.signal_csv_a)
    sig_b  = load_signals(args.signal_csv_b)
    pri_a  = load_prices(args.data_csv_a)
    pri_b  = load_prices(args.data_csv_b)

    # merge all on date
    df = (sig_a.rename(columns={"portfolio_weight": "w_a", "predicted_future_return": "pred_a"})
          .merge(sig_b.rename(columns={"portfolio_weight": "w_b", "predicted_future_return": "pred_b"}),
                 on=DATE_COL, how="inner")
          .merge(pri_a.rename(columns={"price": "price_a"}), on=DATE_COL, how="inner")
          .merge(pri_b.rename(columns={"price": "price_b"}), on=DATE_COL, how="inner")
          .sort_values(DATE_COL).reset_index(drop=True))

    if args.eval_start:
        df = df[df[DATE_COL] >= pd.Timestamp(args.eval_start)]
    if args.eval_end:
        df = df[df[DATE_COL] <= pd.Timestamp(args.eval_end)]
    df = df.reset_index(drop=True)

    if df.empty:
        raise ValueError("No overlapping dates after filtering.")

    equity_df, tranche_history = simulate_multi_asset_tranches(
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

    # --- metrics ---
    initial_capital = args.initial_capital
    final_equity    = float(equity_df["net_equity"].iloc[-1])
    strategy_return = final_equity / initial_capital - 1.0
    avg_exp         = float((equity_df["gross_exposure"] / equity_df["net_equity"]).mean())
    avg_exp_a       = float((equity_df[f"exposure_{args.label_a}"] / equity_df["net_equity"]).mean())
    avg_exp_b       = float((equity_df[f"exposure_{args.label_b}"] / equity_df["net_equity"]).mean())

    # per-year breakdown
    equity_df["year"] = equity_df[DATE_COL].dt.year
    year_stats = {}
    for y, grp in equity_df.groupby("year"):
        if len(grp) < 2: continue
        ret  = grp["net_equity"].iloc[-1] / grp["net_equity"].iloc[0] - 1
        exp  = (grp["gross_exposure"] / grp["net_equity"]).mean()
        exp_a = (grp[f"exposure_{args.label_a}"] / grp["net_equity"]).mean()
        exp_b = (grp[f"exposure_{args.label_b}"] / grp["net_equity"]).mean()
        year_stats[int(y)] = {"return": ret, "avg_exposure": exp,
                               f"exp_{args.label_a}": exp_a, f"exp_{args.label_b}": exp_b}

    effs = [v["return"] / v["avg_exposure"] for v in year_stats.values() if v["avg_exposure"] > 0]
    arr  = np.array(effs)
    sharpe = arr.mean() / arr.std(ddof=1) if len(arr) > 1 and arr.std(ddof=1) > 0 else float("nan")

    payload = {
        "label_a": args.label_a,
        "label_b": args.label_b,
        "hold_days": args.hold_days,
        "eval_start": str(equity_df[DATE_COL].iloc[0].date()),
        "eval_end":   str(equity_df[DATE_COL].iloc[-1].date()),
        "strategy_return": strategy_return,
        "avg_gross_exposure": avg_exp,
        f"avg_exp_{args.label_a}": avg_exp_a,
        f"avg_exp_{args.label_b}": avg_exp_b,
        "avg_efficiency": float(arr.mean()) if len(arr) else float("nan"),
        "worst_efficiency": float(arr.min()) if len(arr) else float("nan"),
        "sharpe_efficiency": float(sharpe),
        "year_stats": year_stats,
    }

    # save
    equity_csv  = maybe_tagged(out_dir, "multi_asset_equity_curve",   ".csv", args.tag)
    tranche_csv = maybe_tagged(out_dir, "multi_asset_tranches",        ".csv", args.tag)
    summary_json = maybe_tagged(out_dir, "multi_asset_summary",        ".json", args.tag)

    equity_df.drop(columns=["year"]).to_csv(equity_csv, index=False)
    pd.DataFrame(tranche_history).to_csv(tranche_csv, index=False)
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    # print
    print("=" * 70)
    print("  MULTI-ASSET SIGNAL-RATIO TRANCHE BACKTEST")
    print("=" * 70)
    print(f"  Assets:          {args.label_a} + {args.label_b}")
    print(f"  Hold days:       {args.hold_days}")
    print(f"  Period:          {payload['eval_start']} -> {payload['eval_end']}")
    print(f"  Strategy return: {strategy_return:+.4f} ({strategy_return*100:+.1f}%)")
    print(f"  Avg exposure:    {avg_exp:.3f} ({avg_exp*100:.0f}%)")
    print(f"    {args.label_a}: {avg_exp_a*100:.0f}%  {args.label_b}: {avg_exp_b*100:.0f}%")
    print(f"  Avg efficiency:  {arr.mean():+.4f}" if len(arr) else "")
    print(f"  Worst year eff:  {arr.min():+.4f}" if len(arr) else "")
    print(f"  Sharpe (eff):    {sharpe:.2f}")
    print("-" * 70)
    print("  Year  |   Return  |  Exp  |  Exp_A  |  Exp_B")
    for y, s in sorted(year_stats.items()):
        print(f"  {y}  |  {s['return']:+.3f}  |  {s['avg_exposure']:.2f}  |  {s[f'exp_{args.label_a}']:.2f}  |  {s[f'exp_{args.label_b}']:.2f}")
    print(f"[OK] {equity_csv}")
    print(f"[OK] {summary_json}")


if __name__ == "__main__":
    main()
