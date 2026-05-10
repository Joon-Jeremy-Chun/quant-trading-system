from __future__ import annotations

import argparse
from dataclasses import dataclass
from itertools import product
from pathlib import Path
import sys
import time

# import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import Parallel, delayed


SCRIPT_DIR = Path(__file__).resolve().parent
AUTOMATION_DIR = SCRIPT_DIR / "automation"
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.append(str(AUTOMATION_DIR))

from cli_utils import add_common_optimization_args, build_horizon_config, resolve_override_path


# ============================================================
# 41_fear_greed_candle_volume_multiwindow_optimization.py
#
# Strategy 4: Fear-Greed Candle/Volume Strategy
#
# Core idea:
# - Use short-term fear/greed behavior near recent lows/highs.
# - Body-size and volume baselines are FIXED at 10 days.
# - Optimize only 3 parameters:
#     1) k_b : body multiplier threshold
#     2) k_v : volume multiplier threshold
#     3) m_p : recent price-zone window (local high/low zone)
#
# Buy setup (fear -> reversal):
# - Bullish candle (Close > Open)
# - Large body relative to recent average body
# - Large volume relative to recent average volume
# - Today occurs in recent low zone
#
# Sell setup (greed -> reversal / exit):
# - Bearish candle (Close < Open)
# - Large body relative to recent average body
# - Large volume relative to recent average volume
# - Today occurs in recent high zone
#
# This script is for TRAINING / OPTIMIZATION only.
# ============================================================


# ============================================================
# CONFIG
# ============================================================
DATA_CSV = (SCRIPT_DIR / "../data/gld_us_d.csv").resolve()
OUT_DIR = (SCRIPT_DIR / "../outputs/41_fear_greed_candle_volume_optimization").resolve()
# FIGURES_ROOT = (SCRIPT_DIR / "../figures").resolve()
STRATEGY_NAME = "fear_greed_candle_volume_strategy"

DATE_COL = "Date"
OHLCV_CANDIDATES = {
    "Open": ["Open", "open"],
    "High": ["High", "high"],
    "Low": ["Low", "low"],
    "Close": ["Adj Close", "Adj_Close", "Close", "close", "Price"],
    "Volume": ["Volume", "volume"],
}

TRAIN_END_DATE = "2024-12-31"

HORIZONS = {
    "1m": {"months": 1},
    "6m": {"months": 6},
    "1y": {"years": 1},
    "3y": {"years": 3},
    "5y": {"years": 5},
    "10y": {"years": 10},
}

# Fixed short-term windows
BODY_WINDOW = 10
VOLUME_WINDOW = 10

# Optimized parameters
K_BODY_VALUES = [1.2, 1.5, 1.8, 2.0, 2.5, 3.0]
K_VOLUME_VALUES = [1.2, 1.5, 1.8, 2.0, 2.5, 3.0]
PRICE_ZONE_WINDOWS = [3, 5, 7, 10]

TOP_N = 10
SHOW_PLOTS = False
N_JOBS = 1
MIN_VALID_ROWS_AFTER_ROLLING = 10
OPEN_TRADE_POLICY = "drop"  # "drop" | "close"
# ============================================================


@dataclass(frozen=True)
class ParamSet:
    k_body: float
    k_volume: float
    price_zone_window: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fear-Greed Candle/Volume optimization runner.")
    add_common_optimization_args(parser)
    parser.add_argument("--n-jobs", type=int, default=1, help="Parallel workers for grid search. -1 = all cores. Default=1 (serial).")
    return parser.parse_args()


def configure_from_args(args: argparse.Namespace) -> None:
    global DATA_CSV, TRAIN_END_DATE, HORIZONS, TOP_N, N_JOBS

    data_csv = resolve_override_path(args.data_csv, SCRIPT_DIR)
    if data_csv is not None:
        DATA_CSV = data_csv
    if args.train_end_date:
        TRAIN_END_DATE = args.train_end_date
    HORIZONS = build_horizon_config(args.horizons, HORIZONS)
    if args.top_n is not None:
        TOP_N = args.top_n
    N_JOBS = args.n_jobs


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
    raise ValueError(f"Could not find column for {target_name}. Tried {candidates}. Available: {list(df.columns)}")


def load_data(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if DATE_COL not in df.columns:
        raise ValueError(f"Missing date column: {DATE_COL}")

    open_col = resolve_column(df, OHLCV_CANDIDATES["Open"], "Open")
    high_col = resolve_column(df, OHLCV_CANDIDATES["High"], "High")
    low_col = resolve_column(df, OHLCV_CANDIDATES["Low"], "Low")
    close_col = resolve_column(df, OHLCV_CANDIDATES["Close"], "Close")
    volume_col = resolve_column(df, OHLCV_CANDIDATES["Volume"], "Volume")

    df[DATE_COL] = pd.to_datetime(df[DATE_COL])
    for c in [open_col, high_col, low_col, close_col, volume_col]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=[DATE_COL, open_col, high_col, low_col, close_col, volume_col]).sort_values(DATE_COL).reset_index(drop=True)
    df = df[[DATE_COL, open_col, high_col, low_col, close_col, volume_col]].rename(
        columns={open_col: "Open", high_col: "High", low_col: "Low", close_col: "Close", volume_col: "Volume"}
    )

    if df.empty:
        raise ValueError("Loaded data is empty after cleaning.")

    return df


def get_horizon_df(df: pd.DataFrame, train_end_date: str, horizon_cfg: dict) -> pd.DataFrame:
    end = pd.to_datetime(train_end_date)
    start = end - pd.DateOffset(**horizon_cfg)
    return df[(df[DATE_COL] >= start) & (df[DATE_COL] <= end)].copy().reset_index(drop=True)


def add_features(df: pd.DataFrame, params: ParamSet) -> pd.DataFrame:
    out = df.copy()

    out["Body"] = (out["Close"] - out["Open"]).abs()
    out["AvgBody"] = out["Body"].rolling(window=BODY_WINDOW, min_periods=BODY_WINDOW).mean()
    out["AvgVolume"] = out["Volume"].rolling(window=VOLUME_WINDOW, min_periods=VOLUME_WINDOW).mean()

    # Local zone references (include today for simplicity / current-state detection)
    out["RecentLow"] = out["Low"].rolling(window=params.price_zone_window, min_periods=params.price_zone_window).min()
    out["RecentHigh"] = out["High"].rolling(window=params.price_zone_window, min_periods=params.price_zone_window).max()

    out["Bullish"] = (out["Close"] > out["Open"]).astype(int)
    out["Bearish"] = (out["Close"] < out["Open"]).astype(int)

    out["LargeBody"] = (out["Body"] > params.k_body * out["AvgBody"]).astype(int)
    out["LargeVolume"] = (out["Volume"] > params.k_volume * out["AvgVolume"]).astype(int)

    # Price-zone filters
    out["InLowZone"] = (out["Low"] <= out["RecentLow"]).astype(int)
    out["InHighZone"] = (out["High"] >= out["RecentHigh"]).astype(int)

    # Candidate signal day
    out["BuyCandidate"] = (
        (out["Bullish"] == 1) &
        (out["LargeBody"] == 1) &
        (out["LargeVolume"] == 1) &
        (out["InLowZone"] == 1)
    ).astype(int)

    out["SellCandidate"] = (
        (out["Bearish"] == 1) &
        (out["LargeBody"] == 1) &
        (out["LargeVolume"] == 1) &
        (out["InHighZone"] == 1)
    ).astype(int)

    out["RawBuySignal"] = out["BuyCandidate"]
    out["RawSellSignal"] = out["SellCandidate"]

    out = out.dropna(subset=["AvgBody", "AvgVolume", "RecentLow", "RecentHigh"]).reset_index(drop=True)
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
    out["BuyEvent"] = ((out["Position"] == 1) & (out["Position"].shift(1, fill_value=0) == 0)).astype(int)
    out["SellEvent"] = ((out["Position"] == 0) & (out["Position"].shift(1, fill_value=0) == 1)).astype(int)

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


def evaluate_one_param(df_horizon: pd.DataFrame, params: ParamSet) -> dict | None:
    df_feat = add_features(df_horizon, params)
    if df_feat.empty or len(df_feat) < MIN_VALID_ROWS_AFTER_ROLLING:
        return None

    df_pos = add_position_column(df_feat)
    trades = build_trade_log(df_pos, open_policy=OPEN_TRADE_POLICY)

    strat = summarize_strategy(trades)
    bh = buy_and_hold_summary(df_pos)

    return {
        "k_body": params.k_body,
        "k_volume": params.k_volume,
        "price_zone_window": params.price_zone_window,
        "num_rows": len(df_pos),
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


def rank_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    out["win_rate"] = out["win_rate"].fillna(-1)
    out = out.sort_values(
        by=["total_return", "excess_vs_bh", "win_rate", "num_trades"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out


# def plot_top_result(df_horizon: pd.DataFrame, params: ParamSet, horizon_name: str, rank: int, out_dir: Path) -> None:
#     df_feat = add_features(df_horizon, params)
#     if df_feat.empty:
#         return
#     df_plot = add_position_column(df_feat)
#     trades = build_trade_log(df_plot, open_policy=OPEN_TRADE_POLICY)
#     strat = summarize_strategy(trades)
#     bh = buy_and_hold_summary(df_plot)
#     fig, ax1 = plt.subplots(figsize=(12, 7))
#     ax1.plot(df_plot[DATE_COL], df_plot["Close"], label="Close Price")
#     buy_idx = df_plot["BuyEvent"] == 1
#     sell_idx = df_plot["SellEvent"] == 1
#     ax1.scatter(df_plot.loc[buy_idx, DATE_COL], df_plot.loc[buy_idx, "Close"], marker="^", s=120, label="BUY", zorder=8)
#     ax1.scatter(df_plot.loc[sell_idx, DATE_COL], df_plot.loc[sell_idx, "Close"], marker="v", s=120, label="SELL", zorder=8)
#     ax1.set_xlabel("Date")
#     ax1.set_ylabel("Close Price")
#     ax2 = ax1.twinx()
#     ax2.plot(df_plot[DATE_COL], df_plot["Body"], label="Body", linestyle="--")
#     ax2.plot(df_plot[DATE_COL], df_plot["AvgBody"], label="AvgBody(10)")
#     ax2.set_ylabel("Body Size")
#     title_line1 = f"Fear-Greed Candle/Volume | horizon={horizon_name} | rank={rank}"
#     title_line2 = f"k_body={params.k_body:.1f}, k_volume={params.k_volume:.1f}, m_p={params.price_zone_window}"
#     title_line3 = (
#         f"Return={strat['total_return']*100:.2f}% | "
#         f"WinRate={strat['win_rate']*100:.2f}% | "
#         f"Trades={strat['num_trades']} | "
#         f"BH={bh['buy_hold_return']*100:.2f}%"
#     )
#     ax1.set_title(title_line1 + "\n" + title_line2 + "\n" + title_line3)
#     lines1, labels1 = ax1.get_legend_handles_labels()
#     lines2, labels2 = ax2.get_legend_handles_labels()
#     ax1.legend(lines1 + lines2, labels1 + labels2, loc="best")
#     fig.tight_layout()
#     fpath = out_dir / f"{horizon_name}_rank{rank:02d}_kb{params.k_body:.1f}_kv{params.k_volume:.1f}_mp{params.price_zone_window}.png"
#     fig.savefig(fpath, dpi=200, bbox_inches="tight")
#     if SHOW_PLOTS:
#         plt.show()
#     plt.close(fig)


def optimize_horizon(df_all: pd.DataFrame, horizon_name: str, horizon_cfg: dict) -> None:
    horizon_start_time = time.perf_counter()

    horizon_dir = OUT_DIR / horizon_name
    # plot_dir = FIGURES_ROOT / STRATEGY_NAME / horizon_name
    ensure_dir(horizon_dir)
    # ensure_dir(plot_dir)

    df_h = get_horizon_df(df_all, TRAIN_END_DATE, horizon_cfg)
    if df_h.empty:
        print(f"[WARN] Horizon {horizon_name}: empty after date filtering.")
        return

    min_needed = max(BODY_WINDOW, VOLUME_WINDOW, max(PRICE_ZONE_WINDOWS)) + 1
    if len(df_h) < min_needed:
        print(f"[WARN] Horizon {horizon_name}: not enough rows for this strategy. rows={len(df_h)}, min_needed={min_needed}")
        return

    total_combos = len(K_BODY_VALUES) * len(K_VOLUME_VALUES) * len(PRICE_ZONE_WINDOWS)

    print("\n" + "=" * 80)
    print(f"HORIZON: {horizon_name}")
    print(f"TRAIN RANGE: {df_h[DATE_COL].iloc[0].date()} -> {df_h[DATE_COL].iloc[-1].date()}")
    print(f"ROWS: {len(df_h)}")
    print(f"GRID SIZE: {len(K_BODY_VALUES)} x {len(K_VOLUME_VALUES)} x {len(PRICE_ZONE_WINDOWS)} = {total_combos}")
    print("=" * 80)

    combo_start_time = time.perf_counter()
    all_params = [
        ParamSet(k_body=float(kb), k_volume=float(kv), price_zone_window=int(mp))
        for kb, kv, mp in product(K_BODY_VALUES, K_VOLUME_VALUES, PRICE_ZONE_WINDOWS)
    ]

    if N_JOBS == 1:
        results = []
        for idx, params in enumerate(all_params, start=1):
            res = evaluate_one_param(df_h, params)
            if res is not None:
                results.append(res)
            if idx % 100 == 0 or idx == total_combos:
                elapsed = time.perf_counter() - combo_start_time
                remaining = (elapsed / idx) * (total_combos - idx)
                print(f"[{horizon_name}] progress: {idx}/{total_combos} | elapsed={format_seconds(elapsed)} | remaining={format_seconds(remaining)}")
    else:
        print(f"[{horizon_name}] running {total_combos} combos in parallel (n_jobs={N_JOBS}) ...")
        raw = Parallel(n_jobs=N_JOBS, backend="loky")(
            delayed(evaluate_one_param)(df_h, p) for p in all_params
        )
        results = [r for r in raw if r is not None]
        print(f"[{horizon_name}] parallel done in {format_seconds(time.perf_counter() - combo_start_time)}")

    res_df = pd.DataFrame(results)
    if res_df.empty:
        print(f"[WARN] Horizon {horizon_name}: no valid results.")
        return

    ranked = rank_results(res_df)
    top10 = ranked.head(TOP_N).copy()

    ranked_path = horizon_dir / f"{horizon_name}_all_ranked_results.csv"
    top10_path = horizon_dir / f"{horizon_name}_top10_results.csv"
    ranked.to_csv(ranked_path, index=False)
    top10.to_csv(top10_path, index=False)

    print("\nTOP 10 RESULTS (ranked by total_return)")
    cols_to_show = [
        "rank", "k_body", "k_volume", "price_zone_window",
        "num_trades", "win_rate", "total_return", "buy_hold_return", "excess_vs_bh"
    ]
    print(top10[cols_to_show].to_string(index=False))

    print(f"\n[OK] Saved all ranked results: {ranked_path.resolve()}")
    print(f"[OK] Saved top 10 results:     {top10_path.resolve()}")

    # for _, row in top10.iterrows():
    #     params = ParamSet(
    #         k_body=float(row["k_body"]),
    #         k_volume=float(row["k_volume"]),
    #         price_zone_window=int(row["price_zone_window"]),
    #     )
    #     plot_top_result(df_h, params, horizon_name, int(row["rank"]), plot_dir)
    #
    # print(f"[OK] Saved top 10 plots in:    {plot_dir.resolve()}")

    horizon_elapsed = time.perf_counter() - horizon_start_time
    print(f"[TIME] Horizon {horizon_name} elapsed: {horizon_elapsed:.2f} sec ({horizon_elapsed/60:.2f} min)")


def main() -> None:
    args = parse_args()
    configure_from_args(args)

    total_start_time = time.perf_counter()

    ensure_dir(OUT_DIR)
    # ensure_dir(FIGURES_ROOT / STRATEGY_NAME)

    try:
        df = load_data(DATA_CSV)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print("41_fear_greed_candle_volume_multiwindow_optimization.py START")
    print("=" * 80)
    print(f"DATA_CSV:         {DATA_CSV}")
    print(f"TRAIN_END_DATE:   {TRAIN_END_DATE}")
    print(f"BODY_WINDOW:      {BODY_WINDOW}")
    print(f"VOLUME_WINDOW:    {VOLUME_WINDOW}")
    print(f"K_BODY_VALUES:    {K_BODY_VALUES}")
    print(f"K_VOLUME_VALUES:  {K_VOLUME_VALUES}")
    print(f"PRICE_ZONE_WINS:  {PRICE_ZONE_WINDOWS}")
    print(f"TOP_N:            {TOP_N}")
    print(f"OUT_DIR:          {OUT_DIR}")
    # print(f"FIGURES_ROOT:     {FIGURES_ROOT}")
    print(f"STRATEGY_NAME:    {STRATEGY_NAME}")
    print("-" * 80)

    for horizon_name, horizon_cfg in HORIZONS.items():
        optimize_horizon(df, horizon_name, horizon_cfg)

    total_elapsed = time.perf_counter() - total_start_time

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)
    print(f"[TIME] Total script elapsed: {total_elapsed:.2f} sec ({total_elapsed/60:.2f} min)")


if __name__ == "__main__":
    main()
