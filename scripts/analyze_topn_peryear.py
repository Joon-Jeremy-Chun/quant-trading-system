"""
Per-year breakdown analysis for top-N experiments.

Usage:
  python scripts/analyze_topn_peryear.py --horizon h130
  python scripts/analyze_topn_peryear.py --horizon h45
  python scripts/analyze_topn_peryear.py --horizon both
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKTEST_DIR = REPO_ROOT / "outputs" / "objective2_monthly_update_tranche_backtest"
EVAL_YEARS = [2020, 2021, 2022, 2023, 2024]
TOP_N_LIST = [10, 20, 30, 40, 50, 60, 70, 80]


def load_equity_curve(tag: str) -> pd.DataFrame | None:
    path = BACKTEST_DIR / f"monthly_update_tranche_backtest_equity_curve_{tag}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["Date"])
    df = df.set_index("Date").sort_index()
    return df


def year_metrics(df: pd.DataFrame, year: int) -> dict:
    mask = df.index.year == year
    sub = df[mask]
    if len(sub) < 2:
        return {}

    ret = sub["net_equity"].iloc[-1] / sub["net_equity"].iloc[0] - 1.0
    bh_ret = sub["price"].iloc[-1] / sub["price"].iloc[0] - 1.0
    avg_exp = (sub["gross_exposure"] / sub["net_equity"]).mean()
    eff = ret / avg_exp if avg_exp > 0 else float("nan")

    return {
        "return": ret,
        "bh_return": bh_ret,
        "avg_exposure": avg_exp,
        "efficiency": eff,
    }


def aggregate_metrics(rows: list[dict]) -> dict:
    rets = [r["efficiency"] for r in rows if r]
    if not rets:
        return {}
    arr = np.array(rets)
    return {
        "avg_efficiency": arr.mean(),
        "worst_efficiency": arr.min(),
        "std_efficiency": arr.std(ddof=1) if len(arr) > 1 else 0.0,
        "sharpe": arr.mean() / arr.std(ddof=1) if arr.std(ddof=1) > 0 else float("nan"),
        "avg_exposure": np.mean([r["avg_exposure"] for r in rows if r]),
    }


def build_table(horizon_tag: str, prefix: str = "") -> pd.DataFrame:
    records = []
    for n in TOP_N_LIST:
        tag = f"{prefix}top{n}_{horizon_tag}"
        df = load_equity_curve(tag)
        if df is None:
            continue

        year_rows = [year_metrics(df, y) for y in EVAL_YEARS]
        agg = aggregate_metrics([r for r in year_rows if r])
        if not agg:
            continue

        row: dict = {"top_n": n}
        for y, yr in zip(EVAL_YEARS, year_rows):
            if yr:
                row[f"ret_{y}"] = f"{yr['return']:+.1%}"
                row[f"exp_{y}"] = f"{yr['avg_exposure']:.0%}"
                row[f"eff_{y}"] = f"{yr['efficiency']:+.1%}"
                row[f"bh_{y}"] = f"{yr['bh_return']:+.1%}"
        row["avg_eff"] = f"{agg['avg_efficiency']:+.1%}"
        row["worst_eff"] = f"{agg['worst_efficiency']:+.1%}"
        row["std_eff"] = f"{agg['std_efficiency']:.1%}"
        row["sharpe"] = f"{agg['sharpe']:.2f}"
        row["avg_exp"] = f"{agg['avg_exposure']:.0%}"
        records.append(row)

    return pd.DataFrame(records)


def print_summary_table(horizon_tag: str, prefix: str = "") -> None:
    df = build_table(horizon_tag, prefix=prefix)
    if df.empty:
        print(f"[WARN] No data found for horizon: {horizon_tag}")
        return

    print(f"\n{'='*80}")
    print(f"  Top-N Per-Year Analysis -- {horizon_tag.upper()}")
    print(f"{'='*80}")

    # Per-year efficiency table
    eff_cols = ["top_n"] + [f"eff_{y}" for y in EVAL_YEARS] + ["avg_eff", "worst_eff", "sharpe", "avg_exp"]
    available = [c for c in eff_cols if c in df.columns]
    print("\n[Efficiency = Return / Avg Exposure]")
    print(df[available].to_string(index=False))

    # Per-year return table
    ret_cols = ["top_n"] + [f"ret_{y}" for y in EVAL_YEARS]
    available_ret = [c for c in ret_cols if c in df.columns]
    print("\n[Raw Return per Year]")
    print(df[available_ret].to_string(index=False))

    # B&H reference (from top-10 or first available)
    if not df.empty:
        bh_row = df.iloc[0]
        bh_vals = [bh_row.get(f"bh_{y}", "N/A") for y in EVAL_YEARS]
        print(f"\n[B&H Reference]  " + "  ".join(f"{y}: {v}" for y, v in zip(EVAL_YEARS, bh_vals)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", choices=["h130", "h45", "both"], default="both")
    parser.add_argument("--prefix", type=str, default="", help="File tag prefix, e.g. 'brkb_'")
    args = parser.parse_args()

    if args.horizon in ("h130", "both"):
        print_summary_table("h130", prefix=args.prefix)
    if args.horizon in ("h45", "both"):
        print_summary_table("h45", prefix=args.prefix)

    # Comparison summary
    if args.horizon == "both":
        t130 = build_table("h130", prefix=args.prefix)
        t45 = build_table("h45", prefix=args.prefix)
        if not t130.empty and not t45.empty:
            print(f"\n{'='*80}")
            print("  h130 vs h45 -- Summary Comparison")
            print(f"{'='*80}")
            print(f"\n{'top_n':>6}  {'h130 sharpe':>12}  {'h45 sharpe':>12}  {'h130 avg_eff':>14}  {'h45 avg_eff':>12}")
            merged = pd.merge(t130[["top_n","sharpe","avg_eff"]], t45[["top_n","sharpe","avg_eff"]],
                              on="top_n", suffixes=("_h130","_h45"))
            for _, r in merged.iterrows():
                print(f"{int(r['top_n']):>6}  {r['sharpe_h130']:>12}  {r['sharpe_h45']:>12}  {r['avg_eff_h130']:>14}  {r['avg_eff_h45']:>12}")


if __name__ == "__main__":
    main()
