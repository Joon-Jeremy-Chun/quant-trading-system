from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
AUTOMATION_DIR = SCRIPT_DIR / "automation"
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.append(str(AUTOMATION_DIR))

from cli_utils import add_common_forward_args, build_horizon_list, resolve_override_path


# ============================================================
# 32_adaptive_volatility_band_forward_test.py
#
# Strategy 3: Adaptive Volatility Band Strategy
#
# Goal:
# 1) Load top-10 optimized parameter sets from script 31.
# 2) Apply each parameter set to a forward test period.
# 3) Print forward-test results.
# 4) Save ranked forward-test results.
# 5) Save two plots for each tested parameter set:
#    (a) Close Price + Buy/Sell + Volatility Bands
#    (b) Cumulative Return: Strategy vs Buy & Hold
# 6) Print and save global top 3 across all horizons.
#
# IMPORTANT FIX:
# Raw buy/sell signals are NOT treated as actual trades.
# Actual BuyEvent / SellEvent are generated from Position changes.
# ============================================================


# ============================================================
# CONFIG
# ============================================================
DATA_CSV = Path("../data/gld_us_d.csv")
OPTIMIZATION_DIR = Path("../outputs/31_adaptive_volatility_band_optimization")
OUT_DIR = Path("../outputs/32_adaptive_volatility_band_forward_test")
FIGURES_ROOT = Path("../figures")
STRATEGY_NAME = "adaptive_volatility_band_forward_test"

DATE_COL = "Date"
OHLC_CANDIDATES = {
    "Open": ["Open", "open"],
    "High": ["High", "high"],
    "Low": ["Low", "low"],
    "Close": ["Adj Close", "Adj_Close", "Close", "close", "Price"],
}

TRAIN_END_DATE = "2024-12-31"
TEST_START_DATE = "2025-01-01"
TEST_END_DATE = "2025-12-31"

TOP_N = 10
SHOW_PLOTS = False
OPEN_TRADE_POLICY = "drop"   # "drop" | "close"

HORIZONS = ["1m", "6m", "1y", "3y", "5y", "10y"]
# ============================================================


@dataclass(frozen=True)
class ParamSet:
    vol_window: int
    upper_k: float
    lower_k: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Adaptive Volatility Band forward-test runner.")
    add_common_forward_args(parser)
    return parser.parse_args()


def configure_from_args(args: argparse.Namespace) -> None:
    global DATA_CSV, OPTIMIZATION_DIR, TRAIN_END_DATE, TEST_START_DATE, TEST_END_DATE, HORIZONS, TOP_N

    data_csv = resolve_override_path(args.data_csv, SCRIPT_DIR)
    optimization_dir = resolve_override_path(args.optimization_dir, SCRIPT_DIR)

    if data_csv is not None:
        DATA_CSV = data_csv
    if optimization_dir is not None:
        OPTIMIZATION_DIR = optimization_dir
    if args.train_end_date:
        TRAIN_END_DATE = args.train_end_date
    if args.test_start_date:
        TEST_START_DATE = args.test_start_date
    if args.test_end_date:
        TEST_END_DATE = args.test_end_date
    HORIZONS = build_horizon_list(args.horizons, HORIZONS)
    if args.top_n is not None:
        TOP_N = args.top_n


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds/60:.1f}m"


def resolve_column(df: pd.DataFrame, candidates: list[str], target_name: str) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(
        f"Could not find column for {target_name}. Tried {candidates}. Available: {list(df.columns)}"
    )


def load_data(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if DATE_COL not in df.columns:
        raise ValueError(f"Missing date column: {DATE_COL}")

    open_col = resolve_column(df, OHLC_CANDIDATES["Open"], "Open")
    high_col = resolve_column(df, OHLC_CANDIDATES["High"], "High")
    low_col = resolve_column(df, OHLC_CANDIDATES["Low"], "Low")
    close_col = resolve_column(df, OHLC_CANDIDATES["Close"], "Close")

    df[DATE_COL] = pd.to_datetime(df[DATE_COL])
    for c in [open_col, high_col, low_col, close_col]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = (
        df.dropna(subset=[DATE_COL, open_col, high_col, low_col, close_col])
          .sort_values(DATE_COL)
          .reset_index(drop=True)
    )

    df = df[[DATE_COL, open_col, high_col, low_col, close_col]].rename(
        columns={open_col: "Open", high_col: "High", low_col: "Low", close_col: "Close"}
    )

    if df.empty:
        raise ValueError("Loaded data is empty after cleaning.")

    return df


def get_test_df(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    out = df[(df[DATE_COL] >= s) & (df[DATE_COL] <= e)].copy().reset_index(drop=True)
    return out


def add_features(df: pd.DataFrame, params: ParamSet) -> pd.DataFrame:
    out = df.copy()

    if params.vol_window > len(out):
        return pd.DataFrame()

    out["VolProxy"] = (out["High"] - out["Low"]) / out["Close"]
    out["VolMean"] = out["VolProxy"].rolling(
        window=params.vol_window,
        min_periods=params.vol_window
    ).mean()
    out["VolSigma"] = out["VolProxy"].rolling(
        window=params.vol_window,
        min_periods=params.vol_window
    ).std(ddof=0)

    out["UpperBand"] = out["VolMean"] + params.upper_k * out["VolSigma"]
    out["LowerBand"] = out["VolMean"] - params.lower_k * out["VolSigma"]

    # Raw signals only
    out["RawSellSignal"] = (out["VolProxy"] > out["UpperBand"]).astype(int)
    out["RawBuySignal"] = (out["VolProxy"] < out["LowerBand"]).astype(int)

    out = out.dropna(
        subset=["VolProxy", "VolMean", "VolSigma", "UpperBand", "LowerBand"]
    ).reset_index(drop=True)

    return out


def add_position_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    pos = np.zeros(len(out), dtype=int)
    state = 0

    raw_buy = out["RawBuySignal"].fillna(0).astype(int).to_numpy()
    raw_sell = out["RawSellSignal"].fillna(0).astype(int).to_numpy()

    for i in range(len(out)):
        if state == 1 and raw_sell[i] == 1:
            state = 0
        elif state == 0 and raw_buy[i] == 1:
            state = 1
        pos[i] = state

    out["Position"] = pos

    # Actual trade events from position changes only
    out["BuyEvent"] = (
        (out["Position"] == 1) &
        (out["Position"].shift(1, fill_value=0) == 0)
    ).astype(int)

    out["SellEvent"] = (
        (out["Position"] == 0) &
        (out["Position"].shift(1, fill_value=0) == 1)
    ).astype(int)

    return out


def build_trade_log(df: pd.DataFrame, open_policy: str = "drop") -> pd.DataFrame:
    buys = df.index[df["BuyEvent"] == 1].to_list()
    sells = df.index[df["SellEvent"] == 1].to_list()

    trades = []
    sell_ptr = 0
    trade_id = 1

    for b in buys:
        while sell_ptr < len(sells) and sells[sell_ptr] <= b:
            sell_ptr += 1

        if sell_ptr >= len(sells):
            if open_policy == "close":
                s = len(df) - 1
            else:
                break
        else:
            s = sells[sell_ptr]
            sell_ptr += 1

        buy_date = df.loc[b, DATE_COL]
        buy_price = float(df.loc[b, "Close"])
        sell_date = df.loc[s, DATE_COL]
        sell_price = float(df.loc[s, "Close"])

        holding_days = int((sell_date - buy_date).days)
        pnl = sell_price - buy_price
        ret = (sell_price / buy_price) - 1.0 if buy_price != 0 else np.nan

        trades.append({
            "TradeID": trade_id,
            "BuyDate": buy_date,
            "BuyPrice": buy_price,
            "SellDate": sell_date,
            "SellPrice": sell_price,
            "HoldingDays": holding_days,
            "PnL": pnl,
            "Return": ret,
        })
        trade_id += 1

    return pd.DataFrame(trades)


def summarize_strategy(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "num_trades": 0,
            "total_pnl": 0.0,
            "total_return": 0.0,
            "win_rate": np.nan,
            "avg_trade_return": np.nan,
            "avg_holding_days": np.nan,
        }

    total_return = float((1.0 + trades["Return"]).prod() - 1.0)
    return {
        "num_trades": int(len(trades)),
        "total_pnl": float(trades["PnL"].sum()),
        "total_return": total_return,
        "win_rate": float((trades["PnL"] > 0).mean()),
        "avg_trade_return": float(trades["Return"].mean()),
        "avg_holding_days": float(trades["HoldingDays"].mean()),
    }


def buy_and_hold_summary(df: pd.DataFrame) -> dict:
    p0 = float(df["Close"].iloc[0])
    p1 = float(df["Close"].iloc[-1])
    r = (p1 / p0) - 1.0 if p0 != 0 else np.nan
    return {
        "start_date": df[DATE_COL].iloc[0],
        "end_date": df[DATE_COL].iloc[-1],
        "start_price": p0,
        "end_price": p1,
        "buy_hold_return": float(r),
        "buy_hold_pnl": float(p1 - p0),
    }


def add_equity_curve_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["AssetReturn"] = out["Close"].pct_change().fillna(0.0)
    out["StrategyDailyReturn"] = out["Position"].shift(1, fill_value=0) * out["AssetReturn"]
    out["StrategyEquity"] = (1.0 + out["StrategyDailyReturn"]).cumprod()
    out["BuyHoldEquity"] = (1.0 + out["AssetReturn"]).cumprod()
    return out


def load_top10_params(horizon_name: str) -> pd.DataFrame:
    top10_path = OPTIMIZATION_DIR / horizon_name / f"{horizon_name}_top10_results.csv"
    if not top10_path.exists():
        raise FileNotFoundError(
            f"Missing top10 results CSV for horizon {horizon_name}: {top10_path}"
        )

    df = pd.read_csv(top10_path)
    required = {"rank", "vol_window", "upper_k", "lower_k"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Top10 CSV missing required columns for {horizon_name}: {missing}"
        )

    return df.head(TOP_N).copy()


def evaluate_forward_one(
    df_test: pd.DataFrame,
    row: pd.Series,
    horizon_name: str
) -> tuple[dict | None, pd.DataFrame | None, pd.DataFrame | None]:
    params = ParamSet(
        vol_window=int(row["vol_window"]),
        upper_k=float(row["upper_k"]),
        lower_k=float(row["lower_k"]),
    )

    df_feat = add_features(df_test, params)
    if df_feat.empty:
        return None, None, None

    df_pos = add_position_column(df_feat)
    df_eq = add_equity_curve_columns(df_pos)
    trades = build_trade_log(df_eq, open_policy=OPEN_TRADE_POLICY)

    strat = summarize_strategy(trades)
    bh = buy_and_hold_summary(df_eq)

    result = {
        "horizon_name": horizon_name,
        "original_rank": int(row["rank"]),
        "vol_window": params.vol_window,
        "upper_k": params.upper_k,
        "lower_k": params.lower_k,
        "train_end_date": TRAIN_END_DATE,
        "test_start_date": TEST_START_DATE,
        "test_end_date": TEST_END_DATE,
        "num_rows": len(df_eq),
        "num_trades": strat["num_trades"],
        "total_pnl": strat["total_pnl"],
        "total_return": strat["total_return"],
        "win_rate": strat["win_rate"],
        "avg_trade_return": strat["avg_trade_return"],
        "avg_holding_days": strat["avg_holding_days"],
        "buy_hold_return": bh["buy_hold_return"],
        "buy_hold_pnl": bh["buy_hold_pnl"],
        "excess_vs_bh": strat["total_return"] - bh["buy_hold_return"],
    }
    return result, df_eq, trades


def rank_forward_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    out["win_rate"] = out["win_rate"].fillna(-1)
    out = out.sort_values(
        by=["total_return", "excess_vs_bh", "win_rate", "num_trades"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    out["forward_rank"] = np.arange(1, len(out) + 1)
    return out


def plot_price_vol_forward(
    df_eq: pd.DataFrame,
    horizon_name: str,
    original_rank: int,
    forward_rank: int,
    result_row: pd.Series,
    out_dir: Path
) -> None:
    fig, ax1 = plt.subplots(figsize=(12, 7))

    ax1.plot(df_eq[DATE_COL], df_eq["Close"], label="Close Price")

    buy_idx = df_eq["BuyEvent"] == 1
    sell_idx = df_eq["SellEvent"] == 1

    ax1.scatter(
        df_eq.loc[buy_idx, DATE_COL],
        df_eq.loc[buy_idx, "Close"],
        marker="^",
        s=120,
        label="BUY",
        zorder=8,
    )
    ax1.scatter(
        df_eq.loc[sell_idx, DATE_COL],
        df_eq.loc[sell_idx, "Close"],
        marker="v",
        s=120,
        label="SELL",
        zorder=8,
    )

    ax1.set_xlabel("Date")
    ax1.set_ylabel("Close Price")

    ax2 = ax1.twinx()
    ax2.plot(df_eq[DATE_COL], df_eq["VolProxy"], label="VolProxy", linestyle="--")
    ax2.plot(df_eq[DATE_COL], df_eq["VolMean"], label="VolMean")
    ax2.plot(df_eq[DATE_COL], df_eq["UpperBand"], label="UpperBand")
    ax2.plot(df_eq[DATE_COL], df_eq["LowerBand"], label="LowerBand")
    ax2.set_ylabel("Volatility Proxy")

    title_line1 = (
        f"Forward Test | horizon={horizon_name} | "
        f"original_rank={original_rank} | forward_rank={forward_rank}"
    )
    title_line2 = (
        f"vol_window={int(result_row['vol_window'])}, "
        f"upper_k={result_row['upper_k']:.1f}, "
        f"lower_k={result_row['lower_k']:.1f}"
    )
    title_line3 = (
        f"Test={result_row['test_start_date']}~{result_row['test_end_date']} | "
        f"Return={result_row['total_return']*100:.2f}% | "
        f"WinRate={result_row['win_rate']*100:.2f}% | "
        f"Trades={int(result_row['num_trades'])} | "
        f"BH={result_row['buy_hold_return']*100:.2f}%"
    )

    ax1.set_title(title_line1 + "\n" + title_line2 + "\n" + title_line3)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best")

    fig.tight_layout()

    fpath = out_dir / (
        f"{horizon_name}_orig{original_rank:02d}_"
        f"fwd{forward_rank:02d}_price_vol.png"
    )
    fig.savefig(fpath, dpi=200, bbox_inches="tight")

    if SHOW_PLOTS:
        plt.show()

    plt.close(fig)


def plot_equity_curve_forward(
    df_eq: pd.DataFrame,
    horizon_name: str,
    original_rank: int,
    forward_rank: int,
    result_row: pd.Series,
    out_dir: Path
) -> None:
    fig, ax = plt.subplots(figsize=(12, 7))

    ax.plot(df_eq[DATE_COL], df_eq["StrategyEquity"], label="Strategy Equity")
    ax.plot(df_eq[DATE_COL], df_eq["BuyHoldEquity"], label="Buy & Hold Equity")

    title_line1 = (
        f"Forward Equity Curve | horizon={horizon_name} | "
        f"original_rank={original_rank} | forward_rank={forward_rank}"
    )
    title_line2 = (
        f"Strategy={result_row['total_return']*100:.2f}% | "
        f"BH={result_row['buy_hold_return']*100:.2f}% | "
        f"Excess={result_row['excess_vs_bh']*100:.2f}%"
    )

    ax.set_title(title_line1 + "\n" + title_line2)
    ax.set_xlabel("Date")
    ax.set_ylabel("Growth of $1")
    ax.legend()

    fig.tight_layout()

    fpath = out_dir / (
        f"{horizon_name}_orig{original_rank:02d}_"
        f"fwd{forward_rank:02d}_equity_curve.png"
    )
    fig.savefig(fpath, dpi=200, bbox_inches="tight")

    if SHOW_PLOTS:
        plt.show()

    plt.close(fig)


def forward_test_horizon(df_all: pd.DataFrame, horizon_name: str) -> None:
    horizon_start_time = time.perf_counter()

    horizon_out_dir = OUT_DIR / horizon_name
    horizon_fig_dir = FIGURES_ROOT / STRATEGY_NAME / horizon_name
    ensure_dir(horizon_out_dir)
    ensure_dir(horizon_fig_dir)

    df_test = get_test_df(df_all, TEST_START_DATE, TEST_END_DATE)
    if df_test.empty:
        print(
            f"[WARN] Horizon {horizon_name}: test data empty for "
            f"{TEST_START_DATE} ~ {TEST_END_DATE}"
        )
        return

    top10_df = load_top10_params(horizon_name)

    print("\n" + "=" * 80)
    print(f"FORWARD TEST HORIZON: {horizon_name}")
    print(f"TEST RANGE: {TEST_START_DATE} -> {TEST_END_DATE}")
    print(f"TEST ROWS:  {len(df_test)}")
    print(f"TOP PARAMS LOADED: {len(top10_df)}")
    print("=" * 80)

    results = []
    eq_map: dict[int, pd.DataFrame] = {}
    loop_start_time = time.perf_counter()

    for idx, row in top10_df.iterrows():
        result, df_eq, _trades = evaluate_forward_one(df_test, row, horizon_name)
        if result is not None and df_eq is not None:
            results.append(result)
            eq_map[int(row["rank"])] = df_eq

        completed = idx + 1
        elapsed = time.perf_counter() - loop_start_time
        avg_per_case = elapsed / completed
        remaining = avg_per_case * (len(top10_df) - completed)
        print(
            f"[{horizon_name}] tested {completed}/{len(top10_df)} | "
            f"elapsed={format_seconds(elapsed)} | "
            f"estimated remaining={format_seconds(remaining)}"
        )

    result_df = pd.DataFrame(results)
    if result_df.empty:
        print(f"[WARN] Horizon {horizon_name}: no valid forward-test results.")
        return

    ranked = rank_forward_results(result_df)

    all_results_path = horizon_out_dir / f"{horizon_name}_forward_all_results.csv"
    ranked_path = horizon_out_dir / f"{horizon_name}_forward_ranked_results.csv"

    result_df.to_csv(all_results_path, index=False)
    ranked.to_csv(ranked_path, index=False)

    print("\nFORWARD TEST RESULTS (ranked by total_return)")
    cols_to_show = [
        "forward_rank", "original_rank", "vol_window", "upper_k", "lower_k",
        "num_trades", "win_rate", "total_return", "buy_hold_return", "excess_vs_bh"
    ]
    print(ranked[cols_to_show].to_string(index=False))

    print(f"\n[OK] Saved forward all results:   {all_results_path.resolve()}")
    print(f"[OK] Saved forward ranked file:  {ranked_path.resolve()}")

    for _, row in ranked.iterrows():
        original_rank = int(row["original_rank"])
        forward_rank = int(row["forward_rank"])
        df_eq = eq_map.get(original_rank)
        if df_eq is None:
            continue

        plot_price_vol_forward(
            df_eq, horizon_name, original_rank, forward_rank, row, horizon_fig_dir
        )
        plot_equity_curve_forward(
            df_eq, horizon_name, original_rank, forward_rank, row, horizon_fig_dir
        )

    print(f"[OK] Saved forward plots in:     {horizon_fig_dir.resolve()}")

    horizon_elapsed = time.perf_counter() - horizon_start_time
    print(
        f"[TIME] Horizon {horizon_name} elapsed: "
        f"{horizon_elapsed:.2f} sec ({horizon_elapsed/60:.2f} min)"
    )


def main() -> None:
    args = parse_args()
    configure_from_args(args)

    total_start_time = time.perf_counter()

    ensure_dir(OUT_DIR)
    ensure_dir(FIGURES_ROOT / STRATEGY_NAME)

    try:
        df = load_data(DATA_CSV)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print("32_adaptive_volatility_band_forward_test.py START")
    print("=" * 80)
    print(f"DATA_CSV:        {DATA_CSV}")
    print(f"OPTIMIZATION_DIR:{OPTIMIZATION_DIR}")
    print(f"OUT_DIR:         {OUT_DIR}")
    print(f"FIGURES_ROOT:    {FIGURES_ROOT}")
    print(f"STRATEGY_NAME:   {STRATEGY_NAME}")
    print(f"TRAIN_END_DATE:  {TRAIN_END_DATE}")
    print(f"TEST_START_DATE: {TEST_START_DATE}")
    print(f"TEST_END_DATE:   {TEST_END_DATE}")
    print(f"TOP_N:           {TOP_N}")
    print("-" * 80)

    all_horizon_ranked = []

    for horizon_name in HORIZONS:
        forward_test_horizon(df, horizon_name)

        ranked_path = OUT_DIR / horizon_name / f"{horizon_name}_forward_ranked_results.csv"
        if ranked_path.exists():
            try:
                tmp = pd.read_csv(ranked_path)
                if not tmp.empty:
                    all_horizon_ranked.append(tmp)
            except Exception as e:
                print(f"[WARN] Could not read ranked results for {horizon_name}: {e}")

    if all_horizon_ranked:
        combined = pd.concat(all_horizon_ranked, ignore_index=True)
        combined = combined.sort_values(
            by=["total_return", "excess_vs_bh", "win_rate", "num_trades"],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)

        combined["global_forward_rank"] = np.arange(1, len(combined) + 1)

        combined_path = OUT_DIR / "all_horizons_forward_ranked_results.csv"
        top3_path = OUT_DIR / "all_horizons_forward_top3.csv"

        combined.to_csv(combined_path, index=False)
        combined.head(3).to_csv(top3_path, index=False)

        print("\n" + "=" * 80)
        print("GLOBAL TOP 3 ACROSS ALL HORIZONS (ranked by total_return)")
        print("=" * 80)
        cols_to_show = [
            "global_forward_rank", "horizon_name", "forward_rank", "original_rank",
            "vol_window", "upper_k", "lower_k", "num_trades", "win_rate",
            "total_return", "buy_hold_return", "excess_vs_bh"
        ]
        print(combined.head(3)[cols_to_show].to_string(index=False))
        print(f"\n[OK] Saved combined forward ranked results: {combined_path.resolve()}")
        print(f"[OK] Saved combined forward top 3:          {top3_path.resolve()}")

    total_elapsed = time.perf_counter() - total_start_time

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)
    print(f"[TIME] Total script elapsed: {total_elapsed:.2f} sec ({total_elapsed/60:.2f} min)")


if __name__ == "__main__":
    main()
