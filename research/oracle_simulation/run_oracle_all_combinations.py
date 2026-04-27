"""
Oracle simulation across all 57 asset combinations (2~6 assets from 6-asset universe).

Assets: GLD, BRKB, SPY, QQQ, TLT, RKLB
Modes:  full (100% when any positive) / proportional (weight by return magnitude)

Usage:
  python research/oracle_simulation/run_oracle_all_combinations.py
"""
from __future__ import annotations

import sys
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR   = Path(__file__).resolve().parent / "outputs"
sys.path.insert(0, str(REPO_ROOT / "strategies" / "automation"))

from simulate_multi_asset_tranches import simulate_n_asset_tranches, DATE_COL
from strategy_matrix_builder import load_price_only_data

# ── asset registry ──────────────────────────────────────────────────────────
ASSETS = {
    "GLD":  "data/gld_us_d.csv",
    "BRKB": "data/brkb_us_d.csv",
    "SPY":  "data/spy_us_d.csv",
    "QQQ":  "data/qqq_us_d.csv",
    "TLT":  "data/tlt_us_d.csv",
    "RKLB": "data/rklb_us_d.csv",
}

HOLD_DAYS       = 130
INITIAL_CAPITAL = 1.0
EVAL_START      = "2020-01-01"
EVAL_END        = "2024-12-31"
YEARS           = [2020, 2021, 2022, 2023, 2024]


def load_prices(label: str) -> pd.DataFrame:
    path = REPO_ROOT / ASSETS[label]
    df = load_price_only_data(path).rename(columns={"Price": "price"})
    return df[[DATE_COL, "price"]].rename(columns={"price": f"price_{label}"}).sort_values(DATE_COL)


def compute_oracle_weights(df: pd.DataFrame, labels: list[str], mode: str) -> pd.DataFrame:
    n = len(df)
    for lbl in labels:
        w_col = f"w_{lbl}"
        df[w_col] = 0.0
        p = df[f"price_{lbl}"].values
        for i in range(n):
            fi = i + HOLD_DAYS
            if fi >= n:
                continue
            ret = p[fi] / p[i] - 1.0
            if mode == "full":
                df.loc[df.index[i], w_col] = 1.0 if ret > 0 else 0.0
            else:  # proportional
                df.loc[df.index[i], w_col] = max(ret, 0.0)
    return df


def run_combo(df: pd.DataFrame, labels: list[str], mode: str) -> dict:
    weight_cols = [f"w_{l}"     for l in labels]
    price_cols  = [f"price_{l}" for l in labels]

    equity_df, _ = simulate_n_asset_tranches(
        df=df, weight_cols=weight_cols, price_cols=price_cols,
        hold_days=HOLD_DAYS, initial_capital=INITIAL_CAPITAL, labels=labels,
    )

    equity_df["year"] = equity_df[DATE_COL].dt.year
    total_ret = equity_df["net_equity"].iloc[-1] / equity_df["net_equity"].iloc[0] - 1
    avg_exp   = (equity_df["gross_exposure"] / equity_df["net_equity"]).mean()

    effs, year_rets = [], {}
    for y in YEARS:
        grp = equity_df[equity_df["year"] == y]
        if len(grp) < 2: continue
        ret = grp["net_equity"].iloc[-1] / grp["net_equity"].iloc[0] - 1
        exp = (grp["gross_exposure"] / grp["net_equity"]).mean()
        eff = ret / exp if exp > 0 else 0.0
        effs.append(eff)
        year_rets[y] = ret

    arr    = np.array(effs)
    sharpe = arr.mean() / arr.std(ddof=1) if len(arr) > 1 and arr.std(ddof=1) > 0 else 0.0
    ann    = (1 + total_ret) ** (1 / 5) - 1

    return {
        "combo":      "+".join(labels),
        "n_assets":   len(labels),
        "mode":       mode,
        "5yr":        total_ret,
        "annual":     ann,
        "avg_exp":    avg_exp,
        "avg_eff":    float(arr.mean()),
        "worst_eff":  float(arr.min()),
        "sharpe":     float(sharpe),
        **{f"ret_{y}": year_rets.get(y, float("nan")) for y in YEARS},
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # load all prices once
    print("Loading price data...", flush=True)
    all_prices: dict[str, pd.DataFrame] = {}
    for lbl in ASSETS:
        try:
            all_prices[lbl] = load_prices(lbl)
            print(f"  {lbl}: {len(all_prices[lbl])} rows", flush=True)
        except Exception as e:
            print(f"  {lbl}: SKIP ({e})", flush=True)

    available = list(all_prices.keys())
    print(f"\nAvailable assets: {available}", flush=True)

    # generate all combos (size 2 to N)
    all_combos = []
    for size in range(2, len(available) + 1):
        all_combos.extend(combinations(available, size))
    print(f"Total combinations: {len(all_combos)}\n", flush=True)

    results = []
    for idx, combo in enumerate(all_combos, 1):
        labels = list(combo)

        # merge prices on date
        merged = all_prices[labels[0]].copy()
        for lbl in labels[1:]:
            merged = merged.merge(all_prices[lbl], on=DATE_COL, how="inner")
        merged = (merged.sort_values(DATE_COL)
                  .pipe(lambda d: d[(d[DATE_COL] >= EVAL_START) & (d[DATE_COL] <= EVAL_END)])
                  .reset_index(drop=True))

        if len(merged) < HOLD_DAYS * 2:
            print(f"[{idx:>2}/{len(all_combos)}] {'+'.join(labels)}: SKIP (insufficient data)")
            continue

        for mode in ["full", "proportional"]:
            df = compute_oracle_weights(merged.copy(), labels, mode)
            r  = run_combo(df, labels, mode)
            results.append(r)

        print(f"[{idx:>2}/{len(all_combos)}] {'+'.join(labels):30s}  "
              f"full={results[-2]['5yr']:+.1%}  prop={results[-1]['5yr']:+.1%}", flush=True)

    # ── leaderboard ──────────────────────────────────────────────────────────
    df_res = pd.DataFrame(results)
    df_res.to_csv(OUT_DIR / "oracle_all_combinations.csv", index=False)

    for mode in ["full", "proportional"]:
        sub = df_res[df_res["mode"] == mode].sort_values("5yr", ascending=False).reset_index(drop=True)
        print(f"\n{'='*85}")
        print(f"  LEADERBOARD — {mode.upper()} mode  (top 15 by 5yr return)")
        print(f"{'='*85}")
        print(f"  {'Rank':>4}  {'Combination':30s}  {'N':>2}  {'5yr':>7}  {'Annual':>7}  {'Worst':>7}  {'Sharpe':>7}  {'Exp':>5}")
        print(f"  {'-'*80}")
        for i, row in sub.head(15).iterrows():
            print(f"  {i+1:>4}  {row['combo']:30s}  {int(row['n_assets']):>2}  "
                  f"{row['5yr']:>+7.1%}  {row['annual']:>+7.1%}  "
                  f"{row['worst_eff']:>+7.1%}  {row['sharpe']:>7.2f}  {row['avg_exp']:>5.0%}")

        # bottom 5
        print(f"\n  Bottom 5:")
        for i, row in sub.tail(5).iterrows():
            print(f"  {i+1:>4}  {row['combo']:30s}  {row['5yr']:>+7.1%}  worst={row['worst_eff']:>+6.1%}")

    print(f"\n[OK] Saved: {OUT_DIR / 'oracle_all_combinations.csv'}")


if __name__ == "__main__":
    main()
