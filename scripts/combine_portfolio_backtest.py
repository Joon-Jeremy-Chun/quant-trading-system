"""
combine_portfolio_backtest.py

Combines 4 individual asset backtests into a normalized portfolio.
Each asset contributes its portfolio_weight; sum <= 1 means remainder is cash.
If sum > 1, weights are scaled down proportionally.

Usage:
    python scripts/combine_portfolio_backtest.py --tag b
    python scripts/combine_portfolio_backtest.py --tag a
"""
import argparse
import pandas as pd
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "outputs" / "objective2_monthly_update_tranche_backtest"

ASSETS = ["gld", "brkb", "qqq", "rklb"]
LABELS = {"gld": "GLD", "brkb": "BRK-B", "qqq": "QQQ", "rklb": "RKLB"}

DATA_CSVS = {
    "gld":  "data/gld_us_d.csv",
    "brkb": "data/brkb_us_d.csv",
    "qqq":  "data/qqq_us_d.csv",
    "rklb": "data/rklb_us_d.csv",
}


def load_equity(tag_suffix: str, asset: str) -> pd.DataFrame:
    path = OUT_DIR / f"monthly_update_tranche_backtest_equity_curve_4asset_{asset}_{tag_suffix}.csv"
    df = pd.read_csv(path, parse_dates=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    df["daily_price_ret"] = df["price"].pct_change().fillna(0)
    return df[["Date", "portfolio_weight", "price", "daily_price_ret"]]


def build_portfolio(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    # Align all assets on common dates
    combined = None
    for asset, df in dfs.items():
        df = df.rename(columns={
            "portfolio_weight": f"w_{asset}",
            "daily_price_ret": f"ret_{asset}",
            "price": f"price_{asset}",
        })
        combined = df[["Date", f"w_{asset}", f"ret_{asset}", f"price_{asset}"]] if combined is None \
                   else combined.merge(df[["Date", f"w_{asset}", f"ret_{asset}", f"price_{asset}"]], on="Date", how="inner")

    # Normalize weights
    weight_cols = [f"w_{a}" for a in ASSETS if f"w_{a}" in combined.columns]
    ret_cols    = [f"ret_{a}" for a in ASSETS if f"ret_{a}" in combined.columns]
    active_assets = [a for a in ASSETS if f"w_{a}" in combined.columns]

    raw_weights = combined[weight_cols].clip(lower=0)  # long-only
    total_weight = raw_weights.sum(axis=1)
    scale = total_weight.clip(lower=1.0)  # only scale down if > 1
    norm_weights = raw_weights.div(scale, axis=0)
    cash_weight  = (1.0 - norm_weights.sum(axis=1)).clip(lower=0)

    # Daily portfolio return
    port_ret = sum(norm_weights[f"w_{a}"] * combined[f"ret_{a}"] for a in active_assets)
    combined["portfolio_daily_ret"] = port_ret
    combined["cash_weight"] = cash_weight
    combined["total_raw_weight"] = total_weight

    # Equity curve
    combined["portfolio_equity"] = (1 + combined["portfolio_daily_ret"]).cumprod()

    # Individual buy-and-hold equity curves
    for a in active_assets:
        combined[f"bh_{a}"] = (combined[f"price_{a}"] / combined[f"price_{a}"].iloc[0])

    return combined


def summarize(df: pd.DataFrame, active_assets: list[str]) -> None:
    start, end = df["Date"].iloc[0], df["Date"].iloc[-1]
    years = (end - start).days / 365.25

    def stats(equity):
        total = (equity.iloc[-1] / equity.iloc[0] - 1) * 100
        cagr  = (equity.iloc[-1] / equity.iloc[0]) ** (1/years) * 100 - 100
        mdd   = ((equity / equity.cummax()) - 1).min() * 100
        daily = equity.pct_change().dropna()
        sharpe = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else 0
        return total, cagr, mdd, sharpe

    print(f"\n{'='*62}")
    print(f"  4-Asset Portfolio Backtest  ({start.date()} ~ {end.date()}, {years:.1f}yr)")
    print(f"{'='*62}")

    # Portfolio
    pt, pc, pm, ps = stats(df["portfolio_equity"])
    avg_exp = df["total_raw_weight"].mean() * 100
    avg_cash = df["cash_weight"].mean() * 100
    print(f"\n[Portfolio Combined]")
    print(f"  Total Return : {pt:+.1f}%   CAGR: {pc:+.1f}%")
    print(f"  MDD          : {pm:.1f}%    Sharpe: {ps:.2f}")
    print(f"  Avg Exposure : {avg_exp:.1f}%  Avg Cash: {avg_cash:.1f}%")

    # Individual B&H
    print(f"\n[Individual Buy & Hold]")
    bh_rets = []
    for a in active_assets:
        t, c, m, s = stats(df[f"bh_{a}"])
        bh_rets.append(t)
        print(f"  {LABELS[a]:<8}: Total {t:+6.1f}%  CAGR {c:+5.1f}%  MDD {m:5.1f}%")

    # Equal-weight buy-and-hold
    eq_equity = sum(df[f"bh_{a}"] for a in active_assets) / len(active_assets)
    et, ec, em, es = stats(eq_equity)
    print(f"  {'EW B&H':<8}: Total {et:+6.1f}%  CAGR {ec:+5.1f}%  MDD {em:5.1f}%  (equal 25% each)")

    # Year-by-year
    df["year"] = df["Date"].dt.year
    print(f"\n[Year-by-Year]")
    print(f"{'Year':<6} {'Portfolio':>10} {'GLD':>8} {'BRK-B':>8} {'QQQ':>8} {'RKLB':>8} {'EW B&H':>8} {'Cash%':>7}")
    print("─"*67)
    for yr, g in df.groupby("year"):
        if len(g) < 5: continue
        p = (g["portfolio_equity"].iloc[-1] / g["portfolio_equity"].iloc[0] - 1) * 100
        rows = [f"{(g[f'bh_{a}'].iloc[-1]/g[f'bh_{a}'].iloc[0]-1)*100:>7.1f}%" for a in active_assets]
        ew = sum((g[f"bh_{a}"].iloc[-1]/g[f"bh_{a}"].iloc[0]-1)*100 for a in active_assets) / len(active_assets)
        cash = g["cash_weight"].mean() * 100
        print(f"{yr:<6} {p:>+9.1f}% {'  '.join(rows)}  {ew:>7.1f}%  {cash:>5.1f}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="b or a")
    args = parser.parse_args()

    dfs = {}
    for asset in ASSETS:
        path = OUT_DIR / f"monthly_update_tranche_backtest_equity_curve_4asset_{asset}_{args.tag}.csv"
        if not path.exists():
            print(f"[SKIP] {asset} ({args.tag}) — file not found: {path.name}")
            continue
        dfs[asset] = load_equity(args.tag, asset)

    if len(dfs) < 2:
        print("Not enough asset data to combine.")
        return

    active_assets = list(dfs.keys())
    port = build_portfolio(dfs)

    # Save
    out_path = OUT_DIR / f"portfolio_4asset_{args.tag}_equity.csv"
    port.to_csv(out_path, index=False)
    print(f"[OK] Saved portfolio equity: {out_path.name}")

    summarize(port, active_assets)


if __name__ == "__main__":
    main()
