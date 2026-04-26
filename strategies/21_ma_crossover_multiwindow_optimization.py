from __future__ import annotations

import argparse
from dataclasses import dataclass
from itertools import product
from pathlib import Path
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import Parallel, delayed


SCRIPT_DIR = Path(__file__).resolve().parent
AUTOMATION_DIR = SCRIPT_DIR / "automation"
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.append(str(AUTOMATION_DIR))

from cli_utils import add_common_optimization_args, build_horizon_config, resolve_override_path


# ============================================================
# 21_ma_crossover_multiwindow_optimization.py
#
# Strategy 2: Moving Average Crossover Strategy
#
# Goal:
# 1) For each training horizon ending at TRAIN_END_DATE,
#    search MA crossover parameter grid and rank the best parameter sets.
# 2) Print results to screen.
# 3) Save full results + top 10 results.
# 4) Save plots for the top 10 parameter sets of each horizon.
#
# Trading logic:
# - Buy when short MA crosses ABOVE long MA
# - Sell when short MA crosses BELOW long MA
#
# This script is for the TRAINING / OPTIMIZATION stage only.
# Forward test for 2025 should be done in the next script.
# ============================================================


# ============================================================
# CONFIG
# ============================================================
DATA_CSV = Path("../data/gld_us_d.csv")
OUT_DIR = Path("../outputs/21_ma_crossover_optimization")
FIGURES_ROOT = Path("../figures")
STRATEGY_NAME = "ma_crossover"

DATE_COL = "Date"
PRICE_COL_CANDIDATES = ["Adj Close", "Adj_Close", "Close", "Price"]

TRAIN_END_DATE = "2024-12-31"

HORIZONS = {
    "1m": {"months": 1},
    "6m": {"months": 6},
    "1y": {"years": 1},
    "3y": {"years": 3},
    "5y": {"years": 5},
    "10y": {"years": 10},
}

MA_VALUES = list(range(5, 201, 5))   # 5, 10, ..., 200
TOP_N = 10
SHOW_PLOTS = False
N_JOBS = 1
MIN_VALID_ROWS_AFTER_ROLLING = 10
OPEN_TRADE_POLICY = "drop"   # "drop" | "close"
# ============================================================


@dataclass(frozen=True)
class ParamSet:
    short_ma: int
    long_ma: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MA Crossover optimization runner.")
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


def resolve_price_col(df: pd.DataFrame) -> str:
    for c in PRICE_COL_CANDIDATES:
        if c in df.columns:
            return c
    raise ValueError(
        f"Could not find price column. Tried: {PRICE_COL_CANDIDATES}. Available: {list(df.columns)}"
    )


def load_data(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if DATE_COL not in df.columns:
        raise ValueError(f"Missing date column: {DATE_COL}")

    price_col = resolve_price_col(df)

    df[DATE_COL] = pd.to_datetime(df[DATE_COL])
    df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
    df = df.dropna(subset=[DATE_COL, price_col]).sort_values(DATE_COL).reset_index(drop=True)
    df = df[[DATE_COL, price_col]].rename(columns={price_col: "Price"})

    if df.empty:
        raise ValueError("Loaded data is empty after cleaning.")

    return df


def get_horizon_df(df: pd.DataFrame, train_end_date: str, horizon_cfg: dict) -> pd.DataFrame:
    end = pd.to_datetime(train_end_date)
    start = end - pd.DateOffset(**horizon_cfg)
    out = df[(df[DATE_COL] >= start) & (df[DATE_COL] <= end)].copy().reset_index(drop=True)
    return out


def get_valid_ma_pairs(df_horizon: pd.DataFrame, ma_values: list[int]) -> list[tuple[int, int]]:
    """
    Build valid (short_ma, long_ma) pairs inside the current horizon.

    Conditions:
    - short_ma < long_ma
    - long_ma <= number of rows in horizon
    - enough remaining rows after rolling
    """
    n = len(df_horizon)
    valid_values = [ma for ma in ma_values if ma > 0 and ma <= n and (n - ma + 1) >= MIN_VALID_ROWS_AFTER_ROLLING]

    pairs = []
    for short_ma, long_ma in product(valid_values, valid_values):
        if short_ma < long_ma:
            pairs.append((short_ma, long_ma))
    return pairs


def add_features(df: pd.DataFrame, params: ParamSet) -> pd.DataFrame:
    out = df.copy()

    out["ShortMA"] = out["Price"].rolling(window=params.short_ma, min_periods=params.short_ma).mean()
    out["LongMA"] = out["Price"].rolling(window=params.long_ma, min_periods=params.long_ma).mean()

    out = out.dropna(subset=["ShortMA", "LongMA"]).reset_index(drop=True)
    if out.empty:
        return out

    # Cross signals
    prev_short = out["ShortMA"].shift(1)
    prev_long = out["LongMA"].shift(1)

    out["BuyEvent"] = ((prev_short <= prev_long) & (out["ShortMA"] > out["LongMA"])) .astype(int)
    out["SellEvent"] = ((prev_short >= prev_long) & (out["ShortMA"] < out["LongMA"])) .astype(int)

    return out


def add_position_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    pos = np.zeros(len(out), dtype=int)
    state = 0

    buy_event = out["BuyEvent"].fillna(0).astype(int).to_numpy()
    sell_event = out["SellEvent"].fillna(0).astype(int).to_numpy()

    for i in range(len(out)):
        if state == 1 and sell_event[i] == 1:
            state = 0
        elif state == 0 and buy_event[i] == 1:
            state = 1
        pos[i] = state

    out["Position"] = pos
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
        buy_price = float(df.loc[b, "Price"])
        sell_date = df.loc[s, DATE_COL]
        sell_price = float(df.loc[s, "Price"])

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
    p0 = float(df["Price"].iloc[0])
    p1 = float(df["Price"].iloc[-1])
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

    result = {
        "short_ma": params.short_ma,
        "long_ma": params.long_ma,
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
    return result


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


def plot_top_result(df_horizon: pd.DataFrame, params: ParamSet, horizon_name: str, rank: int, out_dir: Path) -> None:
    df_feat = add_features(df_horizon, params)
    if df_feat.empty:
        return

    df_plot = add_position_column(df_feat)
    trades = build_trade_log(df_plot, open_policy=OPEN_TRADE_POLICY)
    strat = summarize_strategy(trades)
    bh = buy_and_hold_summary(df_plot)

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.plot(df_plot[DATE_COL], df_plot["Price"], label="Price")
    ax.plot(df_plot[DATE_COL], df_plot["ShortMA"], label=f"Short MA ({params.short_ma})")
    ax.plot(df_plot[DATE_COL], df_plot["LongMA"], label=f"Long MA ({params.long_ma})")

    buy_idx = df_plot["BuyEvent"] == 1
    sell_idx = df_plot["SellEvent"] == 1

    ax.scatter(df_plot.loc[buy_idx, DATE_COL], df_plot.loc[buy_idx, "Price"], marker="^", s=120, label="BUY", zorder=8)
    ax.scatter(df_plot.loc[sell_idx, DATE_COL], df_plot.loc[sell_idx, "Price"], marker="v", s=120, label="SELL", zorder=8)

    title_line1 = f"MA Crossover | horizon={horizon_name} | rank={rank}"
    title_line2 = f"short_ma={params.short_ma}, long_ma={params.long_ma}"
    title_line3 = (
        f"Return={strat['total_return']*100:.2f}% | "
        f"WinRate={strat['win_rate']*100:.2f}% | "
        f"Trades={strat['num_trades']} | "
        f"BH={bh['buy_hold_return']*100:.2f}%"
    )
    ax.set_title(title_line1 + "\n" + title_line2 + "\n" + title_line3)
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.legend()
    fig.tight_layout()

    fpath = out_dir / f"{horizon_name}_rank{rank:02d}_sma{params.short_ma}_lma{params.long_ma}.png"
    fig.savefig(fpath, dpi=200, bbox_inches="tight")
    if SHOW_PLOTS:
        plt.show()
    plt.close(fig)


def optimize_horizon(df_all: pd.DataFrame, horizon_name: str, horizon_cfg: dict) -> None:
    horizon_start_time = time.perf_counter()

    horizon_dir = OUT_DIR / horizon_name
    plot_dir = FIGURES_ROOT / STRATEGY_NAME / horizon_name
    ensure_dir(horizon_dir)
    ensure_dir(plot_dir)

    df_h = get_horizon_df(df_all, TRAIN_END_DATE, horizon_cfg)
    if df_h.empty:
        print(f"[WARN] Horizon {horizon_name}: empty after date filtering.")
        return

    valid_pairs = get_valid_ma_pairs(df_h, MA_VALUES)
    if not valid_pairs:
        print(f"[WARN] Horizon {horizon_name}: no valid MA pairs for this horizon length.")
        return

    total_combos = len(valid_pairs)

    print("\n" + "=" * 80)
    print(f"HORIZON: {horizon_name}")
    print(f"TRAIN RANGE: {df_h[DATE_COL].iloc[0].date()} -> {df_h[DATE_COL].iloc[-1].date()}")
    print(f"ROWS: {len(df_h)}")
    print(f"VALID MA PAIRS: {len(valid_pairs)}")
    print(f"GRID SIZE FOR THIS HORIZON: {total_combos}")
    print("=" * 80)

    combo_start_time = time.perf_counter()
    all_params = [ParamSet(short_ma=int(s), long_ma=int(l)) for s, l in valid_pairs]

    if N_JOBS == 1:
        results = []
        for idx, params in enumerate(all_params, start=1):
            res = evaluate_one_param(df_h, params)
            if res is not None:
                results.append(res)
            if idx % 500 == 0 or idx == total_combos:
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
        "rank", "short_ma", "long_ma", "num_trades", "win_rate",
        "total_return", "buy_hold_return", "excess_vs_bh"
    ]
    print(top10[cols_to_show].to_string(index=False))

    print(f"\n[OK] Saved all ranked results: {ranked_path.resolve()}")
    print(f"[OK] Saved top 10 results:     {top10_path.resolve()}")

    for _, row in top10.iterrows():
        params = ParamSet(
            short_ma=int(row["short_ma"]),
            long_ma=int(row["long_ma"]),
        )
        plot_top_result(df_h, params, horizon_name, int(row["rank"]), plot_dir)

    print(f"[OK] Saved top 10 plots in:    {plot_dir.resolve()}")

    horizon_elapsed = time.perf_counter() - horizon_start_time
    print(f"[TIME] Horizon {horizon_name} elapsed: {horizon_elapsed:.2f} sec ({horizon_elapsed/60:.2f} min)")


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
    print("21_ma_crossover_multiwindow_optimization.py START")
    print("=" * 80)
    print(f"DATA_CSV:       {DATA_CSV}")
    print(f"TRAIN_END_DATE: {TRAIN_END_DATE}")
    print(f"TOP_N:          {TOP_N}")
    print(f"OUT_DIR:        {OUT_DIR}")
    print(f"FIGURES_ROOT:   {FIGURES_ROOT}")
    print(f"STRATEGY_NAME:  {STRATEGY_NAME}")
    print(f"MA RANGE:       {MA_VALUES[0]} to {MA_VALUES[-1]} step 5")
    print("-" * 80)
    print("Note: Each horizon automatically filters MA pairs to values that make sense inside that horizon.")

    for horizon_name, horizon_cfg in HORIZONS.items():
        optimize_horizon(df, horizon_name, horizon_cfg)

    total_elapsed = time.perf_counter() - total_start_time

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)
    print(f"[TIME] Total script elapsed: {total_elapsed:.2f} sec ({total_elapsed/60:.2f} min)")


if __name__ == "__main__":
    main()
