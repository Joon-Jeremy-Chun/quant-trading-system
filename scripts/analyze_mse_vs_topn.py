"""
MSE vs top-N curve analysis.
Extracts selection_cv_mse from monthly model logs for each top-N run.

Usage:
  python scripts/analyze_mse_vs_topn.py --horizon h130
  python scripts/analyze_mse_vs_topn.py --horizon h45
  python scripts/analyze_mse_vs_topn.py --horizon both
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKTEST_DIR = REPO_ROOT / "outputs" / "objective2_monthly_update_tranche_backtest"
TOP_N_LIST = [10, 20, 30, 40, 50, 60, 70, 80]


def load_model_log(tag: str) -> pd.DataFrame | None:
    path = BACKTEST_DIR / f"monthly_update_tranche_backtest_model_log_{tag}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def mse_stats(df: pd.DataFrame) -> dict:
    col = "selection_cv_mse"
    if col not in df.columns:
        return {}
    vals = df[col].dropna().values
    if len(vals) == 0:
        return {}
    return {
        "mean_cv_mse": vals.mean(),
        "median_cv_mse": np.median(vals),
        "std_cv_mse": vals.std(ddof=1) if len(vals) > 1 else 0.0,
        "min_cv_mse": vals.min(),
        "max_cv_mse": vals.max(),
        "n_months": len(vals),
    }


def build_mse_table(horizon_tag: str) -> pd.DataFrame:
    records = []
    for n in TOP_N_LIST:
        tag = f"top{n}_{horizon_tag}"
        df = load_model_log(tag)
        if df is None:
            continue
        stats = mse_stats(df)
        if not stats:
            continue
        records.append({"top_n": n, **stats})
    return pd.DataFrame(records)


def print_mse_table(horizon_tag: str) -> None:
    df = build_mse_table(horizon_tag)
    if df.empty:
        print(f"[WARN] No model log data for: {horizon_tag}")
        return

    print(f"\n{'='*70}")
    print(f"  MSE vs Top-N -- {horizon_tag.upper()}")
    print(f"{'='*70}")
    print(f"{'top_n':>6}  {'mean_cv_mse':>13}  {'median_cv_mse':>13}  {'min_cv_mse':>12}  {'n_months':>8}")
    for _, r in df.iterrows():
        print(f"{int(r['top_n']):>6}  {r['mean_cv_mse']:>13.6f}  {r['median_cv_mse']:>13.6f}  {r['min_cv_mse']:>12.6f}  {int(r['n_months']):>8}")

    # ASCII curve
    means = df["mean_cv_mse"].values
    lo, hi = means.min(), means.max()
    rng = hi - lo if hi > lo else 1.0
    print(f"\n  Mean CV-MSE curve (normalized, lower = better):")
    for _, r in df.iterrows():
        bar_len = int(40 * (r["mean_cv_mse"] - lo) / rng)
        bar = "#" * bar_len
        print(f"  top-{int(r['top_n']):>2}: {r['mean_cv_mse']:.6f}  |{bar}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", choices=["h130", "h45", "both"], default="both")
    args = parser.parse_args()

    if args.horizon in ("h130", "both"):
        print_mse_table("h130")
    if args.horizon in ("h45", "both"):
        print_mse_table("h45")

    if args.horizon == "both":
        t130 = build_mse_table("h130")
        t45 = build_mse_table("h45")
        if not t130.empty and not t45.empty:
            merged = pd.merge(t130[["top_n", "mean_cv_mse"]], t45[["top_n", "mean_cv_mse"]],
                              on="top_n", suffixes=("_h130", "_h45"))
            print(f"\n{'='*70}")
            print("  h130 vs h45 -- Mean CV-MSE Comparison")
            print(f"{'='*70}")
            print(f"{'top_n':>6}  {'h130 mse':>12}  {'h45 mse':>12}  {'ratio h45/h130':>14}")
            for _, r in merged.iterrows():
                ratio = r["mean_cv_mse_h45"] / r["mean_cv_mse_h130"] if r["mean_cv_mse_h130"] > 0 else float("nan")
                print(f"{int(r['top_n']):>6}  {r['mean_cv_mse_h130']:>12.6f}  {r['mean_cv_mse_h45']:>12.6f}  {ratio:>14.2f}x")


if __name__ == "__main__":
    main()
