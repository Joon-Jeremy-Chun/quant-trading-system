"""
gld_rolling_forward_backtest.py

GLD 롤링 포워드 백테스트 (월별 모델 업데이트)
- 137개 앵커의 eval_1m.json을 순서대로 읽어
  각 달의 포워드 수익을 체인해서 누적 수익 곡선 생성
- 결과 CSV 저장 + 통계 출력 + (선택) 그래프 저장
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

# ============================================================
# CONFIG
# ============================================================
ANCHOR_DIR   = Path("outputs/objective1_anchor_date_multi_horizon_evaluation")
OUT_DIR      = Path("outputs/gld_rolling_forward_backtest")
FIGURES_ROOT = Path("figures/gld_rolling_forward_backtest")

RISK_FREE_RATE = 0.045          # 연 4.5%
SAVE_PLOT      = True
SHOW_PLOT      = False
# ============================================================


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_all_eval1m(anchor_dir: Path) -> pd.DataFrame:
    files = sorted(glob.glob(str(anchor_dir / "anchor_*_eval_1m.json")))
    rows = []
    for fp in files:
        with open(fp) as f:
            d = json.load(f)

        anchor_date = Path(fp).stem.replace("anchor_", "").replace("_eval_1m", "")
        es = d["evaluation_summary"]
        lo = d["long_only_optimization"]["local_best"]
        weights = lo["weights"]

        rows.append({
            "anchor_date":        anchor_date,
            "eval_start":         d["evaluation_start_date"],
            "eval_end":           d["evaluation_end_date"],
            "w_adaptive_band":    weights[0],
            "w_ma_crossover":     weights[1],
            "w_adaptive_vol":     weights[2],
            "w_fear_greed":       weights[3],
            "r_adaptive_band":    es["standalone_returns"]["adaptive_band"],
            "r_ma_crossover":     es["standalone_returns"]["ma_crossover"],
            "r_adaptive_vol":     es["standalone_returns"]["adaptive_volatility_band"],
            "r_fear_greed":       es["standalone_returns"]["fear_greed_candle_volume"],
            "portfolio_return":   es["long_only_combined_return"],
            "bh_return":          es["buy_and_hold_return"],
        })

    df = pd.DataFrame(rows)
    df["anchor_date"] = pd.to_datetime(df["anchor_date"])
    df["eval_start"]  = pd.to_datetime(df["eval_start"])
    df["eval_end"]    = pd.to_datetime(df["eval_end"])
    df = df.sort_values("anchor_date").reset_index(drop=True)
    df["excess_vs_bh"] = df["portfolio_return"] - df["bh_return"]
    return df


def compute_cumulative(returns: pd.Series) -> pd.Series:
    return (1 + returns).cumprod()


def compute_mdd(cum: pd.Series) -> float:
    roll_max = cum.cummax()
    drawdown = (cum - roll_max) / roll_max
    return float(drawdown.min())


def compute_cagr(cum: pd.Series, n_months: int) -> float:
    total = float(cum.iloc[-1])
    years = n_months / 12
    return float(total ** (1 / years) - 1)


def compute_sharpe(monthly_returns: pd.Series, rf_annual: float) -> float:
    rf_monthly = (1 + rf_annual) ** (1 / 12) - 1
    excess = monthly_returns - rf_monthly
    if excess.std() == 0:
        return float("nan")
    return float(excess.mean() / excess.std() * np.sqrt(12))


def print_stats(label: str, df: pd.DataFrame, ret_col: str) -> None:
    r = df[ret_col]
    cum = compute_cumulative(r)
    n = len(r)
    cagr  = compute_cagr(cum, n)
    mdd   = compute_mdd(cum)
    sharpe = compute_sharpe(r, RISK_FREE_RATE)
    hit_rate = float((r > 0).mean())
    beat_bh  = float((df["excess_vs_bh"] > 0).mean()) if ret_col == "portfolio_return" else float("nan")
    total_return = float(cum.iloc[-1] - 1)

    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    print(f"  기간:          {df['eval_start'].iloc[0].date()} ~ {df['eval_end'].iloc[-1].date()}")
    print(f"  월 수:         {n}개월")
    print(f"  총 수익:       {total_return*100:.1f}%")
    print(f"  CAGR:          {cagr*100:.2f}%")
    print(f"  MDD:           {mdd*100:.2f}%")
    print(f"  Sharpe:        {sharpe:.3f}")
    print(f"  월 Hit Rate:   {hit_rate*100:.1f}%")
    if not np.isnan(beat_bh):
        print(f"  BH 초과 비율: {beat_bh*100:.1f}%")


def save_plot(df: pd.DataFrame, out_path: Path) -> None:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    cum_port = compute_cumulative(df["portfolio_return"])
    cum_bh   = compute_cumulative(df["bh_return"])
    dates    = df["eval_end"]

    fig, axes = plt.subplots(3, 1, figsize=(14, 12))

    # 1. 누적 수익 곡선
    ax = axes[0]
    ax.plot(dates, (cum_port - 1) * 100, label="Portfolio (Long-Only Optimized)", linewidth=1.8)
    ax.plot(dates, (cum_bh   - 1) * 100, label="Buy & Hold (GLD)", linewidth=1.4, linestyle="--", alpha=0.8)
    ax.set_ylabel("Cumulative Return (%)")
    ax.set_title("GLD Rolling Forward Backtest — Cumulative Return\n(Monthly Model Update, Long-Only Weights)")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 2. 월별 수익 bar
    ax = axes[1]
    colors = ["steelblue" if r >= 0 else "tomato" for r in df["portfolio_return"]]
    ax.bar(dates, df["portfolio_return"] * 100, color=colors, width=20, alpha=0.8, label="Portfolio Monthly Return")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Monthly Return (%)")
    ax.set_title("Monthly Portfolio Return")
    ax.grid(alpha=0.3, axis="y")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 3. Excess vs BH
    ax = axes[2]
    colors2 = ["green" if r >= 0 else "red" for r in df["excess_vs_bh"]]
    ax.bar(dates, df["excess_vs_bh"] * 100, color=colors2, width=20, alpha=0.7, label="Excess vs BH")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Excess Return vs BH (%)")
    ax.set_title("Monthly Excess Return vs Buy & Hold")
    ax.grid(alpha=0.3, axis="y")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    if SHOW_PLOT:
        plt.show()
    plt.close(fig)
    print(f"\n[OK] 그래프 저장: {out_path.resolve()}")


def main() -> None:
    ensure_dir(OUT_DIR)

    print("GLD 롤링 포워드 백테스트 시작...")
    df = load_all_eval1m(ANCHOR_DIR)
    print(f"로드 완료: {len(df)}개월 ({df['eval_start'].iloc[0].date()} ~ {df['eval_end'].iloc[-1].date()})")

    # 결과 저장
    out_csv = OUT_DIR / "gld_rolling_forward_monthly.csv"
    df.to_csv(out_csv, index=False)
    print(f"[OK] 월별 결과 저장: {out_csv.resolve()}")

    # 누적 수익 저장
    cum_df = df[["anchor_date", "eval_start", "eval_end", "portfolio_return", "bh_return", "excess_vs_bh"]].copy()
    cum_df["cum_portfolio"] = (1 + df["portfolio_return"]).cumprod()
    cum_df["cum_bh"]        = (1 + df["bh_return"]).cumprod()
    cum_csv = OUT_DIR / "gld_rolling_forward_cumulative.csv"
    cum_df.to_csv(cum_csv, index=False)
    print(f"[OK] 누적 수익 저장: {cum_csv.resolve()}")

    # 통계 출력
    print_stats("포트폴리오 (Long-Only 최적 가중치)", df, "portfolio_return")
    print_stats("Buy & Hold (GLD)", df, "bh_return")

    # 전략별 선택 빈도
    print("\n" + "="*50)
    print("  전략별 월별 선택 비중 (평균 가중치)")
    print("="*50)
    for col, name in [
        ("w_adaptive_band",  "Adaptive Band"),
        ("w_ma_crossover",   "MA Crossover"),
        ("w_adaptive_vol",   "Adaptive Vol Band"),
        ("w_fear_greed",     "Fear-Greed Candle"),
    ]:
        avg_w = df[col].mean()
        nonzero = (df[col] > 0).mean()
        print(f"  {name:<22}: 평균 {avg_w:.3f} | 선택된 달 {nonzero*100:.0f}%")

    # 그래프
    if SAVE_PLOT:
        ensure_dir(FIGURES_ROOT)
        save_plot(df, FIGURES_ROOT / "gld_rolling_forward_backtest.png")

    print("\nDONE")


if __name__ == "__main__":
    main()
