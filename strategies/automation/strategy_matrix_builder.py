from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


DATE_COL = "Date"


@dataclass(frozen=True)
class StrategySelection:
    strategy_key: str
    horizon_name: str
    params: dict[str, float | int]
    total_return: float
    buy_hold_return: float
    excess_vs_bh: float
    source_csv: Path
    source_kind: str


def load_price_only_data(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if DATE_COL not in df.columns:
        raise ValueError(f"Missing date column: {DATE_COL}")

    price_col_candidates = ["Adj Close", "Adj_Close", "Close", "Price"]
    price_col = None
    for candidate in price_col_candidates:
        if candidate in df.columns:
            price_col = candidate
            break

    if price_col is None:
        raise ValueError(f"Could not resolve price column from: {price_col_candidates}")

    df[DATE_COL] = pd.to_datetime(df[DATE_COL])
    df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
    df = df.dropna(subset=[DATE_COL, price_col]).sort_values(DATE_COL).reset_index(drop=True)
    return df[[DATE_COL, price_col]].rename(columns={price_col: "Price"})


def load_ohlc_data(csv_path: Path, include_volume: bool = False) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if DATE_COL not in df.columns:
        raise ValueError(f"Missing date column: {DATE_COL}")

    candidates = {
        "Open": ["Open", "open"],
        "High": ["High", "high"],
        "Low": ["Low", "low"],
        "Close": ["Adj Close", "Adj_Close", "Close", "close", "Price"],
    }
    if include_volume:
        candidates["Volume"] = ["Volume", "volume"]

    resolved: dict[str, str] = {}
    for target_name, options in candidates.items():
        for option in options:
            if option in df.columns:
                resolved[target_name] = option
                break
        if target_name not in resolved:
            raise ValueError(f"Could not resolve column for {target_name}. Tried {options}")

    df[DATE_COL] = pd.to_datetime(df[DATE_COL])
    for source_col in resolved.values():
        df[source_col] = pd.to_numeric(df[source_col], errors="coerce")

    keep_cols = [DATE_COL, *resolved.values()]
    df = df.dropna(subset=keep_cols).sort_values(DATE_COL).reset_index(drop=True)
    rename_map = {src: dst for dst, src in resolved.items()}
    return df[[DATE_COL, *resolved.values()]].rename(columns=rename_map)


def get_test_df(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    return df[(df[DATE_COL] >= s) & (df[DATE_COL] <= e)].copy().reset_index(drop=True)


def get_history_df(df: pd.DataFrame, end_date: str) -> pd.DataFrame:
    e = pd.to_datetime(end_date)
    return df[df[DATE_COL] <= e].copy().reset_index(drop=True)


def add_strategy_daily_returns(df: pd.DataFrame, price_col: str) -> pd.DataFrame:
    out = df.copy()
    out["AssetReturn"] = out[price_col].pct_change().fillna(0.0)
    out["StrategyDailyReturn"] = out["Position"].shift(1, fill_value=0) * out["AssetReturn"]
    return out


def normalize_series(x: pd.Series, mode: str) -> pd.Series:
    arr = x.astype(float).to_numpy()

    if mode == "zscore":
        mu = np.nanmean(arr)
        sd = np.nanstd(arr, ddof=0)
        if sd == 0:
            return pd.Series(np.nan, index=x.index)
        return (x - mu) / sd

    if mode == "minmax":
        xmin = np.nanmin(arr)
        xmax = np.nanmax(arr)
        if xmax == xmin:
            return pd.Series(np.nan, index=x.index)
        return (x - xmin) / (xmax - xmin)

    if mode == "none":
        return x.astype(float)

    raise ValueError(f"Unsupported normalize mode: {mode}")


def add_position_from_binary_signals(df: pd.DataFrame, buy_col: str, sell_col: str) -> pd.DataFrame:
    out = df.copy()
    pos = np.zeros(len(out), dtype=int)
    state = 0

    buy_values = out[buy_col].fillna(0).astype(int).to_numpy()
    sell_values = out[sell_col].fillna(0).astype(int).to_numpy()

    for i in range(len(out)):
        if state == 1 and sell_values[i] == 1:
            state = 0
        elif state == 0 and buy_values[i] == 1:
            state = 1
        pos[i] = state

    out["Position"] = pos
    return out


def adaptive_band_daily_returns(csv_path: Path, selection: StrategySelection, test_start: str, test_end: str) -> pd.DataFrame:
    df = load_price_only_data(csv_path)
    df = get_history_df(df, test_end)

    ma_window = int(selection.params["ma_window"])
    upper_k = float(selection.params["upper_k"])
    lower_k = float(selection.params["lower_k"])

    out = df.copy()
    out["Price_Norm"] = normalize_series(out["Price"], "zscore")
    out["MA"] = out["Price_Norm"].rolling(window=ma_window, min_periods=ma_window).mean()
    out["Sigma"] = out["Price_Norm"].rolling(window=ma_window, min_periods=ma_window).std(ddof=0)
    out["Upper"] = out["MA"] + upper_k * out["Sigma"]
    out["Lower"] = out["MA"] - lower_k * out["Sigma"]
    out["BuySignal"] = (out["Price_Norm"] < out["Lower"]).astype(int)
    out["SellSignal"] = (out["Price_Norm"] > out["Upper"]).astype(int)
    out = out.dropna(subset=["Price_Norm", "MA", "Sigma", "Upper", "Lower"]).reset_index(drop=True)
    out = add_position_from_binary_signals(out, "BuySignal", "SellSignal")
    out = add_strategy_daily_returns(out, "Price")
    out = get_test_df(out, test_start, test_end)
    return out[[DATE_COL, "StrategyDailyReturn"]]


def ma_crossover_daily_returns(csv_path: Path, selection: StrategySelection, test_start: str, test_end: str) -> pd.DataFrame:
    df = load_price_only_data(csv_path)
    df = get_history_df(df, test_end)

    short_ma = int(selection.params["short_ma"])
    long_ma = int(selection.params["long_ma"])

    out = df.copy()
    out["ShortMA"] = out["Price"].rolling(window=short_ma, min_periods=short_ma).mean()
    out["LongMA"] = out["Price"].rolling(window=long_ma, min_periods=long_ma).mean()
    out = out.dropna(subset=["ShortMA", "LongMA"]).reset_index(drop=True)
    prev_short = out["ShortMA"].shift(1)
    prev_long = out["LongMA"].shift(1)
    out["BuySignal"] = ((prev_short <= prev_long) & (out["ShortMA"] > out["LongMA"])).astype(int)
    out["SellSignal"] = ((prev_short >= prev_long) & (out["ShortMA"] < out["LongMA"])).astype(int)
    out = add_position_from_binary_signals(out, "BuySignal", "SellSignal")
    out = add_strategy_daily_returns(out, "Price")
    out = get_test_df(out, test_start, test_end)
    return out[[DATE_COL, "StrategyDailyReturn"]]


def adaptive_volatility_daily_returns(csv_path: Path, selection: StrategySelection, test_start: str, test_end: str) -> pd.DataFrame:
    df = load_ohlc_data(csv_path, include_volume=False)
    df = get_history_df(df, test_end)

    vol_window = int(selection.params["vol_window"])
    upper_k = float(selection.params["upper_k"])
    lower_k = float(selection.params["lower_k"])

    out = df.copy()
    out["VolProxy"] = (out["High"] - out["Low"]) / out["Close"]
    out["VolMean"] = out["VolProxy"].rolling(window=vol_window, min_periods=vol_window).mean()
    out["VolSigma"] = out["VolProxy"].rolling(window=vol_window, min_periods=vol_window).std(ddof=0)
    out["UpperBand"] = out["VolMean"] + upper_k * out["VolSigma"]
    out["LowerBand"] = out["VolMean"] - lower_k * out["VolSigma"]
    out["BuySignal"] = (out["VolProxy"] < out["LowerBand"]).astype(int)
    out["SellSignal"] = (out["VolProxy"] > out["UpperBand"]).astype(int)
    out = out.dropna(subset=["VolProxy", "VolMean", "VolSigma", "UpperBand", "LowerBand"]).reset_index(drop=True)
    out = add_position_from_binary_signals(out, "BuySignal", "SellSignal")
    out = add_strategy_daily_returns(out, "Close")
    out = get_test_df(out, test_start, test_end)
    return out[[DATE_COL, "StrategyDailyReturn"]]


def fear_greed_daily_returns(csv_path: Path, selection: StrategySelection, test_start: str, test_end: str) -> pd.DataFrame:
    df = load_ohlc_data(csv_path, include_volume=True)
    df = get_history_df(df, test_end)

    k_body = float(selection.params["k_body"])
    k_volume = float(selection.params["k_volume"])
    price_zone_window = int(selection.params["price_zone_window"])
    body_window = 10
    volume_window = 10

    out = df.copy()
    out["Body"] = (out["Close"] - out["Open"]).abs()
    out["AvgBody"] = out["Body"].rolling(window=body_window, min_periods=body_window).mean()
    out["AvgVolume"] = out["Volume"].rolling(window=volume_window, min_periods=volume_window).mean()
    out["RecentLow"] = out["Low"].rolling(window=price_zone_window, min_periods=price_zone_window).min()
    out["RecentHigh"] = out["High"].rolling(window=price_zone_window, min_periods=price_zone_window).max()
    out["Bullish"] = (out["Close"] > out["Open"]).astype(int)
    out["Bearish"] = (out["Close"] < out["Open"]).astype(int)
    out["LargeBody"] = (out["Body"] > k_body * out["AvgBody"]).astype(int)
    out["LargeVolume"] = (out["Volume"] > k_volume * out["AvgVolume"]).astype(int)
    out["InLowZone"] = (out["Low"] <= out["RecentLow"]).astype(int)
    out["InHighZone"] = (out["High"] >= out["RecentHigh"]).astype(int)
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
    out["BuySignal"] = out["BuyCandidate"]
    out["SellSignal"] = out["SellCandidate"]
    out = out.dropna(subset=["AvgBody", "AvgVolume", "RecentLow", "RecentHigh"]).reset_index(drop=True)
    out = add_position_from_binary_signals(out, "BuySignal", "SellSignal")
    out = add_strategy_daily_returns(out, "Close")
    out = get_test_df(out, test_start, test_end)
    return out[[DATE_COL, "StrategyDailyReturn"]]


RETURN_BUILDERS: dict[str, Callable[[Path, StrategySelection, str, str], pd.DataFrame]] = {
    "adaptive_band": adaptive_band_daily_returns,
    "ma_crossover": ma_crossover_daily_returns,
    "adaptive_volatility_band": adaptive_volatility_daily_returns,
    "fear_greed_candle_volume": fear_greed_daily_returns,
}

OPTIMIZATION_RESULT_DIRS = {
    "adaptive_band": Path("outputs/11_adaptive_band_strategy_optimization"),
    "ma_crossover": Path("outputs/21_ma_crossover_optimization"),
    "adaptive_volatility_band": Path("outputs/31_adaptive_volatility_band_optimization"),
    "fear_greed_candle_volume": Path("outputs/41_fear_greed_candle_volume_optimization"),
}

PARAM_COLUMNS = {
    "adaptive_band": ["ma_window", "upper_k", "lower_k"],
    "ma_crossover": ["short_ma", "long_ma"],
    "adaptive_volatility_band": ["vol_window", "upper_k", "lower_k"],
    "fear_greed_candle_volume": ["k_body", "k_volume", "price_zone_window"],
}

DEFAULT_REPRESENTATIVE_HORIZONS = {
    "adaptive_band": "1y",
    "ma_crossover": "6m",
    "adaptive_volatility_band": "3m",
    "fear_greed_candle_volume": "1m",
}


def load_best_optimization_selection(repo_root: Path, strategy_key: str) -> StrategySelection:
    horizon_name = DEFAULT_REPRESENTATIVE_HORIZONS[strategy_key]
    source_csv = repo_root / OPTIMIZATION_RESULT_DIRS[strategy_key] / horizon_name / f"{horizon_name}_all_ranked_results.csv"
    if not source_csv.exists():
        raise FileNotFoundError(f"Missing optimization results file for {strategy_key}: {source_csv}")

    df = pd.read_csv(source_csv)
    if df.empty:
        raise ValueError(f"Optimization results file for {strategy_key} is empty: {source_csv}")

    row = df.iloc[0]
    params = {col: row[col] for col in PARAM_COLUMNS[strategy_key]}

    return StrategySelection(
        strategy_key=strategy_key,
        horizon_name=horizon_name,
        params=params,
        total_return=float(row["total_return"]),
        buy_hold_return=float(row["buy_hold_return"]),
        excess_vs_bh=float(row["excess_vs_bh"]),
        source_csv=source_csv,
        source_kind="optimization_rank1",
    )


def build_strategy_return_matrix(
    repo_root: Path,
    data_csv: Path,
    test_start_date: str,
    test_end_date: str,
    strategy_keys: list[str] | None = None,
) -> tuple[pd.DataFrame, list[StrategySelection]]:
    keys = strategy_keys or list(RETURN_BUILDERS.keys())

    selections = [load_best_optimization_selection(repo_root, key) for key in keys]
    merged_df: pd.DataFrame | None = None

    for selection in selections:
        builder = RETURN_BUILDERS[selection.strategy_key]
        strategy_df = builder(data_csv, selection, test_start_date, test_end_date).rename(
            columns={"StrategyDailyReturn": selection.strategy_key}
        )
        if merged_df is None:
            merged_df = strategy_df
        else:
            merged_df = merged_df.merge(strategy_df, on=DATE_COL, how="inner")

    if merged_df is None or merged_df.empty:
        raise ValueError("Strategy return matrix is empty after merging.")

    return merged_df.sort_values(DATE_COL).reset_index(drop=True), selections


def build_strategy_return_matrix_from_selections(
    data_csv: Path,
    selections: list[StrategySelection],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    merged_df: pd.DataFrame | None = None

    for selection in selections:
        builder = RETURN_BUILDERS[selection.strategy_key]
        strategy_df = builder(data_csv, selection, start_date, end_date).rename(
            columns={"StrategyDailyReturn": selection.strategy_key}
        )
        if merged_df is None:
            merged_df = strategy_df
        else:
            merged_df = merged_df.merge(strategy_df, on=DATE_COL, how="inner")

    if merged_df is None or merged_df.empty:
        raise ValueError("Strategy return matrix is empty after merging.")

    return merged_df.sort_values(DATE_COL).reset_index(drop=True)
