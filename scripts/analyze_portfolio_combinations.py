"""
analyze_portfolio_combinations.py

6개 자산의 모든 3-asset, 4-asset, 6-asset 조합의 포트폴리오 성과를 분석합니다.
(5-asset는 스킵)

각 자산의 사전 계산된 equity_curve CSV를 로드해서 즉시 조합 계산 — 모델 재실행 없음.

방법:
  - 매일 각 자산의 signal weight를 정규화 (합계 > 1이면 비례 축소)
  - portfolio_daily_ret = sum(norm_w_i * daily_price_ret_i)
  - equity curve 누적
  - CAGR / MDD / Sharpe / 평균현금 계산

Usage:
    python scripts/analyze_portfolio_combinations.py
    python scripts/analyze_portfolio_combinations.py --tag a --top 10
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR   = REPO_ROOT / "outputs" / "objective2_monthly_update_tranche_backtest"
RESULT_DIR= REPO_ROOT / "outputs" / "portfolio_combination_analysis"

ASSETS = ["GLD", "BRK-B", "QQQ", "RKLB", "ITA", "VRT"]
SLUG   = {"GLD":"gld","BRK-B":"brkb","QQQ":"qqq","RKLB":"rklb","ITA":"ita","VRT":"vrt"}
LABELS = {"GLD":"GLD","BRK-B":"BRKB","QQQ":"QQQ","RKLB":"RKLB","ITA":"ITA","VRT":"VRT"}


def load_asset(asset: str, tag: str) -> pd.DataFrame | None:
    slug = SLUG[asset]
    candidates = [
        OUT_DIR / f"monthly_update_tranche_backtest_equity_curve_6asset_{slug}_{tag}.csv",
        OUT_DIR / f"monthly_update_tranche_backtest_equity_curve_4asset_{slug}_{tag}.csv",
        OUT_DIR / f"monthly_update_tranche_backtest_equity_curve_6asset_{tag}_{slug}_{tag}.csv",
        OUT_DIR / f"monthly_update_tranche_backtest_equity_curve_4asset_{tag}_{slug}_{tag}.csv",
    ]
    for path in candidates:
        if path.exists():
            df = pd.read_csv(path, parse_dates=["Date"])
            df = df.sort_values("Date").reset_index(drop=True)
            df["portfolio_weight"] = pd.to_numeric(df["portfolio_weight"], errors="coerce").fillna(0).clip(lower=0)
            # Compute daily price return from price column
            if "daily_price_ret" in df.columns:
                df["daily_price_ret"] = pd.to_numeric(df["daily_price_ret"], errors="coerce").fillna(0)
            elif "price" in df.columns:
                df["daily_price_ret"] = df["price"].pct_change().fillna(0)
            else:
                continue
            return df[["Date", "portfolio_weight", "daily_price_ret"]]
    return None


def build_equity(assets: list[str], dfs: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """Merge assets, normalize weights daily, compute portfolio equity."""
    combined = None
    for a in assets:
        renamed = dfs[a].rename(columns={
            "portfolio_weight": f"w_{SLUG[a]}",
            "daily_price_ret":  f"r_{SLUG[a]}",
        })
        combined = renamed if combined is None else combined.merge(renamed, on="Date", how="inner")

    if combined is None or len(combined) < 20:
        return None

    w_cols = [f"w_{SLUG[a]}" for a in assets]
    r_cols = [f"r_{SLUG[a]}" for a in assets]

    raw   = combined[w_cols].clip(lower=0)
    total = raw.sum(axis=1)
    scale = total.clip(lower=1.0)
    norm  = raw.div(scale, axis=0)

    combined["cash_weight"]   = (1.0 - norm.sum(axis=1)).clip(lower=0)
    combined["port_daily_ret"]= sum(norm[w] * combined[r] for w, r in zip(w_cols, r_cols))
    combined["equity"]        = (1 + combined["port_daily_ret"]).cumprod()
    combined["total_raw_w"]   = total
    return combined


def stats(df: pd.DataFrame) -> dict:
    eq    = df["equity"]
    rets  = df["port_daily_ret"]
    years = (df["Date"].iloc[-1] - df["Date"].iloc[0]).days / 365.25
    if years < 0.1:
        return {}
    cagr  = (eq.iloc[-1] ** (1 / years) - 1) * 100
    mdd   = ((eq / eq.cummax()) - 1).min() * 100
    sharpe= rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    cash  = df["cash_weight"].mean() * 100
    total_ret = (eq.iloc[-1] - 1) * 100
    return {
        "cagr": round(cagr, 2),
        "mdd":  round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "avg_cash_pct": round(cash, 1),
        "total_ret_pct": round(total_ret, 1),
        "years": round(years, 2),
        "start": str(df["Date"].iloc[0].date()),
        "end":   str(df["Date"].iloc[-1].date()),
        "rows":  len(df),
    }


def combo_label(assets: list[str]) -> str:
    return "+".join(LABELS[a] for a in assets)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="a", help="CSV tag suffix (default: a)")
    p.add_argument("--top", type=int, default=10, help="Show top N per group (default: 10)")
    p.add_argument("--sizes", default="3,4,6", help="Combination sizes to test (default: 3,4,6)")
    args = p.parse_args()

    sizes = [int(s) for s in args.sizes.split(",")]

    # Load all 6 assets
    print("Loading per-asset equity curves...")
    dfs: dict[str, pd.DataFrame] = {}
    for a in ASSETS:
        df = load_asset(a, args.tag)
        if df is not None:
            dfs[a] = df
            print(f"  {a:8}: {len(df)} rows  {df.Date.iloc[0].date()} ~ {df.Date.iloc[-1].date()}")
        else:
            print(f"  {a:8}: NOT FOUND (tag={args.tag})")

    available = list(dfs.keys())
    if len(available) < 3:
        print(f"\n[ERROR] Need at least 3 assets, found {len(available)}: {available}")
        sys.exit(1)

    # Generate all combinations
    results = []
    for size in sizes:
        if size > len(available):
            print(f"\n[SKIP] size={size} (only {len(available)} assets available)")
            continue
        combos = list(itertools.combinations(available, size))
        print(f"\nTesting size={size}: {len(combos)} combinations...")
        for combo in combos:
            combo = list(combo)
            eq_df = build_equity(combo, dfs)
            if eq_df is None:
                continue
            s = stats(eq_df)
            if not s:
                continue
            results.append({
                "size":    size,
                "label":   combo_label(combo),
                "assets":  combo,
                **s,
            })

    if not results:
        print("[ERROR] No results computed.")
        return

    df_res = pd.DataFrame(results)

    # Print results by group, ranked by Sharpe
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = RESULT_DIR / f"combination_analysis_{args.tag}.csv"
    df_res.to_csv(out_csv, index=False)

    HDR = f"  {'Rank':<4} {'Combination':<28} {'1→End':>7} {'TotalRet':>9} {'CAGR':>8} {'MDD':>8} {'Sharpe':>7} {'Cash%':>6} {'Period'}"
    SEP = "  " + "-" * 90

    for size in sizes:
        grp = df_res[df_res["size"] == size].sort_values("sharpe", ascending=False)
        if grp.empty:
            continue
        n_show = min(args.top, len(grp))
        print(f"\n{'='*92}")
        print(f"  {size}-Asset Combinations  |  Top {n_show} by Sharpe")
        print(f"{'='*92}")
        print(HDR)
        print(SEP)
        for rank, (_, row) in enumerate(grp.head(n_show).iterrows(), 1):
            final = 1 + row["total_ret_pct"] / 100
            period = f"{row['start']}~{row['end']} ({row['years']:.1f}y)"
            print(f"  {rank:<4} {row['label']:<28} {final:>6.2f}x {row['total_ret_pct']:>+8.1f}% {row['cagr']:>+7.1f}% {row['mdd']:>7.1f}% {row['sharpe']:>7.2f} {row['avg_cash_pct']:>5.1f}% {period}")

        if len(grp) > n_show:
            print(f"  {'...'}")
            for _, row in grp.tail(3).iterrows():
                final = 1 + row["total_ret_pct"] / 100
                period = f"{row['start']}~{row['end']} ({row['years']:.1f}y)"
                print(f"  {'↓':<4} {row['label']:<28} {final:>6.2f}x {row['total_ret_pct']:>+8.1f}% {row['cagr']:>+7.1f}% {row['mdd']:>7.1f}% {row['sharpe']:>7.2f} {row['avg_cash_pct']:>5.1f}% {period}")

    # Overall top 20
    top_all = df_res.sort_values("sharpe", ascending=False).head(20)
    print(f"\n{'='*92}")
    print(f"  Overall Top 20 by Sharpe (all sizes combined)")
    print(f"{'='*92}")
    print(f"  {'Rank':<4} {'N':<3} {'Combination':<28} {'1→End':>7} {'TotalRet':>9} {'CAGR':>8} {'MDD':>8} {'Sharpe':>7} {'Cash%':>6} {'Period'}")
    print(SEP)
    for rank, (_, row) in enumerate(top_all.iterrows(), 1):
        final = 1 + row["total_ret_pct"] / 100
        period = f"{row['start']}~{row['end']} ({row['years']:.1f}y)"
        print(f"  {rank:<4} {int(row['size']):<3} {row['label']:<28} {final:>6.2f}x {row['total_ret_pct']:>+8.1f}% {row['cagr']:>+7.1f}% {row['mdd']:>7.1f}% {row['sharpe']:>7.2f} {row['avg_cash_pct']:>5.1f}% {period}")

    print(f"\n[OK] Full results saved: {out_csv.name}")
    print(f"     Total combinations tested: {len(df_res)}")


if __name__ == "__main__":
    main()
