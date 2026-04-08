from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_matrix_builder import (
    DATE_COL,
    StrategySelection,
    add_position_from_binary_signals,
    get_test_df,
    load_best_optimization_selection,
    load_ohlc_data,
    load_price_only_data,
    normalize_series,
)


SCORE_COLUMNS = {
    "adaptive_band": "adaptive_band_score",
    "ma_crossover": "ma_crossover_score",
    "adaptive_volatility_band": "adaptive_volatility_band_score",
    "fear_greed_candle_volume": "fear_greed_candle_volume_score",
}


@dataclass(frozen=True)
class StrategyScoreContext:
    strategy_key: str
    score_column: str
    params: dict[str, float | int]
    source_kind: str
    source_csv: str
    source_horizon: str
    scale_value: float | None = None


def clip_series(x: pd.Series, lower: float = -1.0, upper: float = 1.0) -> pd.Series:
    return x.clip(lower=lower, upper=upper)


def safe_divide(numerator: pd.Series, denominator: pd.Series | float) -> pd.Series:
    den = denominator if isinstance(denominator, pd.Series) else float(denominator)
    out = numerator / den
    return out.replace([np.inf, -np.inf], np.nan)


def safe_quantile_scale(x: pd.Series, q: float = 0.95, fallback: float = 1.0) -> float:
    valid = x.dropna().abs()
    if valid.empty:
        return fallback
    scale = float(valid.quantile(q))
    if not np.isfinite(scale) or scale <= 0:
        return fallback
    return scale


def add_targets(df: pd.DataFrame, price_col: str) -> pd.DataFrame:
    out = df.copy()
    out["asset_return"] = out[price_col].pct_change().fillna(0.0)
    out["target_next_return"] = out["asset_return"].shift(-1)
    out["target_next_direction"] = (out["target_next_return"] > 0).astype(float)
    return out


def adaptive_band_score_df(
    csv_path: Path,
    selection: StrategySelection,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, StrategyScoreContext]:
    df = load_price_only_data(csv_path)
    df = get_test_df(df, start_date, end_date)

    ma_window = int(selection.params["ma_window"])
    upper_k = float(selection.params["upper_k"])
    lower_k = float(selection.params["lower_k"])

    out = df.copy()
    out["Price_Norm"] = normalize_series(out["Price"], "zscore")
    out["MA"] = out["Price_Norm"].rolling(window=ma_window, min_periods=ma_window).mean()
    out["Sigma"] = out["Price_Norm"].rolling(window=ma_window, min_periods=ma_window).std(ddof=0)
    out["Upper"] = out["MA"] + upper_k * out["Sigma"]
    out["Lower"] = out["MA"] - lower_k * out["Sigma"]
    out["BandMid"] = (out["Upper"] + out["Lower"]) / 2.0
    out["HalfBandWidth"] = (out["Upper"] - out["Lower"]) / 2.0
    out["raw_score"] = -safe_divide(out["Price_Norm"] - out["BandMid"], out["HalfBandWidth"])
    out[SCORE_COLUMNS["adaptive_band"]] = clip_series(out["raw_score"])
    out = add_targets(out, "Price")
    out = out.dropna(subset=[SCORE_COLUMNS["adaptive_band"], "target_next_return"]).reset_index(drop=True)

    context = StrategyScoreContext(
        strategy_key="adaptive_band",
        score_column=SCORE_COLUMNS["adaptive_band"],
        params=selection.params,
        source_kind=selection.source_kind,
        source_csv=str(selection.source_csv),
        source_horizon=selection.horizon_name,
        scale_value=None,
    )
    return out[[DATE_COL, SCORE_COLUMNS["adaptive_band"], "target_next_return", "target_next_direction"]], context


def ma_crossover_score_df(
    csv_path: Path,
    selection: StrategySelection,
    start_date: str,
    end_date: str,
    scale_value: float | None = None,
) -> tuple[pd.DataFrame, StrategyScoreContext]:
    df = load_price_only_data(csv_path)
    df = get_test_df(df, start_date, end_date)

    short_ma = int(selection.params["short_ma"])
    long_ma = int(selection.params["long_ma"])

    out = df.copy()
    out["ShortMA"] = out["Price"].rolling(window=short_ma, min_periods=short_ma).mean()
    out["LongMA"] = out["Price"].rolling(window=long_ma, min_periods=long_ma).mean()
    out["Spread"] = out["ShortMA"] - out["LongMA"]
    out = out.dropna(subset=["ShortMA", "LongMA", "Spread"]).reset_index(drop=True)

    scale = scale_value if scale_value is not None else safe_quantile_scale(out["Spread"])
    out["raw_score"] = safe_divide(out["Spread"], scale)
    out[SCORE_COLUMNS["ma_crossover"]] = clip_series(out["raw_score"])
    out = add_targets(out, "Price")
    out = out.dropna(subset=[SCORE_COLUMNS["ma_crossover"], "target_next_return"]).reset_index(drop=True)

    context = StrategyScoreContext(
        strategy_key="ma_crossover",
        score_column=SCORE_COLUMNS["ma_crossover"],
        params=selection.params,
        source_kind=selection.source_kind,
        source_csv=str(selection.source_csv),
        source_horizon=selection.horizon_name,
        scale_value=scale,
    )
    return out[[DATE_COL, SCORE_COLUMNS["ma_crossover"], "target_next_return", "target_next_direction"]], context


def adaptive_volatility_score_df(
    csv_path: Path,
    selection: StrategySelection,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, StrategyScoreContext]:
    df = load_ohlc_data(csv_path, include_volume=False)
    df = get_test_df(df, start_date, end_date)

    vol_window = int(selection.params["vol_window"])
    upper_k = float(selection.params["upper_k"])
    lower_k = float(selection.params["lower_k"])

    out = df.copy()
    out["VolProxy"] = (out["High"] - out["Low"]) / out["Close"]
    out["VolMean"] = out["VolProxy"].rolling(window=vol_window, min_periods=vol_window).mean()
    out["VolSigma"] = out["VolProxy"].rolling(window=vol_window, min_periods=vol_window).std(ddof=0)
    out["UpperBand"] = out["VolMean"] + upper_k * out["VolSigma"]
    out["LowerBand"] = out["VolMean"] - lower_k * out["VolSigma"]
    out["BandMid"] = (out["UpperBand"] + out["LowerBand"]) / 2.0
    out["HalfBandWidth"] = (out["UpperBand"] - out["LowerBand"]) / 2.0
    out["raw_score"] = -safe_divide(out["VolProxy"] - out["BandMid"], out["HalfBandWidth"])
    out[SCORE_COLUMNS["adaptive_volatility_band"]] = clip_series(out["raw_score"])
    out = add_targets(out, "Close")
    out = out.dropna(subset=[SCORE_COLUMNS["adaptive_volatility_band"], "target_next_return"]).reset_index(drop=True)

    context = StrategyScoreContext(
        strategy_key="adaptive_volatility_band",
        score_column=SCORE_COLUMNS["adaptive_volatility_band"],
        params=selection.params,
        source_kind=selection.source_kind,
        source_csv=str(selection.source_csv),
        source_horizon=selection.horizon_name,
        scale_value=None,
    )
    return out[[DATE_COL, SCORE_COLUMNS["adaptive_volatility_band"], "target_next_return", "target_next_direction"]], context


def fear_greed_score_df(
    csv_path: Path,
    selection: StrategySelection,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, StrategyScoreContext]:
    df = load_ohlc_data(csv_path, include_volume=True)
    df = get_test_df(df, start_date, end_date)

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
    next_close = out["Close"].shift(-1)
    out["BuySignal"] = ((out["BuyCandidate"] == 1) & (next_close > out["High"])).astype(int)
    out["SellSignal"] = ((out["SellCandidate"] == 1) & (next_close < out["Low"])).astype(int)
    out[SCORE_COLUMNS["fear_greed_candle_volume"]] = out["BuySignal"] - out["SellSignal"]
    out = add_targets(out, "Close")
    out = out.dropna(subset=["AvgBody", "AvgVolume", "RecentLow", "RecentHigh", "target_next_return"]).reset_index(drop=True)

    context = StrategyScoreContext(
        strategy_key="fear_greed_candle_volume",
        score_column=SCORE_COLUMNS["fear_greed_candle_volume"],
        params=selection.params,
        source_kind=selection.source_kind,
        source_csv=str(selection.source_csv),
        source_horizon=selection.horizon_name,
        scale_value=None,
    )
    return out[[DATE_COL, SCORE_COLUMNS["fear_greed_candle_volume"], "target_next_return", "target_next_direction"]], context


def load_representative_selections(repo_root: Path, strategy_keys: list[str] | None = None) -> list[StrategySelection]:
    keys = strategy_keys or [
        "adaptive_band",
        "ma_crossover",
        "adaptive_volatility_band",
        "fear_greed_candle_volume",
    ]
    return [load_best_optimization_selection(repo_root, key) for key in keys]


def build_selection_signal_matrix(
    repo_root: Path,
    data_csv: Path,
    selection_start_date: str,
    selection_end_date: str,
    strategy_keys: list[str] | None = None,
) -> tuple[pd.DataFrame, list[StrategyScoreContext], list[StrategySelection]]:
    selections = load_representative_selections(repo_root, strategy_keys)
    merged_df: pd.DataFrame | None = None
    contexts: list[StrategyScoreContext] = []

    for selection in selections:
        if selection.strategy_key == "adaptive_band":
            score_df, context = adaptive_band_score_df(data_csv, selection, selection_start_date, selection_end_date)
        elif selection.strategy_key == "ma_crossover":
            score_df, context = ma_crossover_score_df(data_csv, selection, selection_start_date, selection_end_date)
        elif selection.strategy_key == "adaptive_volatility_band":
            score_df, context = adaptive_volatility_score_df(data_csv, selection, selection_start_date, selection_end_date)
        elif selection.strategy_key == "fear_greed_candle_volume":
            score_df, context = fear_greed_score_df(data_csv, selection, selection_start_date, selection_end_date)
        else:
            raise ValueError(f"Unsupported strategy key: {selection.strategy_key}")

        score_only = score_df[[DATE_COL, context.score_column]]
        if merged_df is None:
            merged_df = score_df.copy()
        else:
            merged_df = merged_df.merge(score_only, on=DATE_COL, how="inner")
        contexts.append(context)

    if merged_df is None or merged_df.empty:
        raise ValueError("Selection signal matrix is empty after merging.")

    return merged_df.sort_values(DATE_COL).reset_index(drop=True), contexts, selections


def build_evaluation_signal_matrix(
    data_csv: Path,
    selections: list[StrategySelection],
    contexts: list[StrategyScoreContext],
    evaluation_start_date: str,
    evaluation_end_date: str,
) -> pd.DataFrame:
    merged_df: pd.DataFrame | None = None
    target_cols = [DATE_COL, "target_next_return", "target_next_direction"]

    context_by_key = {context.strategy_key: context for context in contexts}

    for selection in selections:
        context = context_by_key[selection.strategy_key]
        if selection.strategy_key == "adaptive_band":
            score_df, _ = adaptive_band_score_df(data_csv, selection, evaluation_start_date, evaluation_end_date)
        elif selection.strategy_key == "ma_crossover":
            score_df, _ = ma_crossover_score_df(
                data_csv,
                selection,
                evaluation_start_date,
                evaluation_end_date,
                scale_value=context.scale_value,
            )
        elif selection.strategy_key == "adaptive_volatility_band":
            score_df, _ = adaptive_volatility_score_df(data_csv, selection, evaluation_start_date, evaluation_end_date)
        elif selection.strategy_key == "fear_greed_candle_volume":
            score_df, _ = fear_greed_score_df(data_csv, selection, evaluation_start_date, evaluation_end_date)
        else:
            raise ValueError(f"Unsupported strategy key: {selection.strategy_key}")

        score_only = score_df[[DATE_COL, context.score_column]]
        if merged_df is None:
            merged_df = score_df.copy()
        else:
            merged_df = merged_df.merge(score_only, on=DATE_COL, how="inner")

    if merged_df is None or merged_df.empty:
        raise ValueError("Evaluation signal matrix is empty after merging.")

    score_cols = [context.score_column for context in contexts]
    keep_cols = target_cols + score_cols
    return merged_df[keep_cols].sort_values(DATE_COL).reset_index(drop=True)
