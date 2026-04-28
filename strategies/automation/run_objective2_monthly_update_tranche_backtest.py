from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from objective2_expanded_strategy_space import (
    DEFAULT_FAMILY_HORIZONS,
    DEFAULT_TOP_N_PER_FAMILY,
    build_expanded_strategy_space,
)
from objective2_modeling import build_return_prediction_frame, summarize_return_predictions
from objective2_signal_matrix_builder import (
    TARGET_DIRECTION_COL,
    TARGET_RETURN_COL,
    SCORE_COLUMNS,
    clip_series,
    safe_divide,
    safe_quantile_scale,
)
from run_objective2_expanded_strategy_forward_validation import (
    build_model_specs,
    compute_time_series_cv_mse,
    extract_model_metadata,
    pick_selected_row,
)
from run_objective2_selected_model_tranche_backtest import (
    build_weight_series,
    compute_predictions,
    maybe_tagged_path,
    simulate_long_only_tranches,
)
from strategy_matrix_builder import DATE_COL, load_price_only_data
from strategy_matrix_builder import get_history_df, get_test_df, load_ohlc_data, normalize_series


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_monthly_update_tranche_backtest"
DEFAULT_ANCHOR_OUTPUT_ROOT = REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a monthly model-update rolling-tranche backtest with fixed holding horizon."
    )
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument(
        "--anchor-output-root",
        type=str,
        default=str(DEFAULT_ANCHOR_OUTPUT_ROOT),
        help="Root directory containing anchor_<date>/optimization_outputs folders.",
    )
    parser.add_argument(
        "--evaluation-start-date",
        type=str,
        default="2024-01-01",
        help="Evaluation start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--evaluation-end-date",
        type=str,
        default="2024-12-31",
        help="Evaluation end date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--target-horizon-days",
        type=int,
        default=130,
        help="Fixed future target horizon used for model fitting.",
    )
    parser.add_argument(
        "--hold-days",
        type=int,
        default=None,
        help="Fixed tranche holding period. Defaults to target horizon.",
    )
    parser.add_argument(
        "--top-n-per-family",
        type=int,
        default=10,
        help="Number of top candidates to use from each strategy family.",
    )
    parser.add_argument(
        "--selection-criterion",
        type=str,
        default="selection_cv_mse",
        choices=[
            "selection_correlation",
            "selection_directional_accuracy",
            "selection_long_short_strategy_return",
            "selection_mse",
            "selection_cv_mse",
        ],
        help="Criterion used to select the monthly best model inside the fixed horizon.",
    )
    parser.add_argument(
        "--update-interval-months",
        type=int,
        default=1,
        help="How often to refresh the predictive model in months. Use 1 for monthly, 6 for semiannual.",
    )
    parser.add_argument(
        "--scale-quantile",
        type=float,
        default=0.95,
        help="Quantile used to scale monthly selection predictions into portfolio weights.",
    )
    parser.add_argument("--initial-capital", type=float, default=1.0, help="Initial capital.")
    parser.add_argument(
        "--max-exposure-cap",
        type=float,
        default=None,
        help="If set, clip portfolio_weight to this upper bound before simulation (e.g. 0.6 for 60%% cap).",
    )
    parser.add_argument("--tag", type=str, default=None, help="Optional tag added to output filenames.")
    parser.add_argument(
        "--strict-label-cutoff",
        action="store_true",
        default=False,
        help="Drop the last target_horizon_days training rows so no label extends past the anchor date (leakage fix).",
    )
    parser.add_argument(
        "--selection-window-years",
        type=int,
        default=1,
        help="Selection window length in years (default 1). Use 2 to compensate for reduced training rows with --strict-label-cutoff.",
    )
    return parser.parse_args()


def load_available_anchor_dates(anchor_output_root: Path) -> list[pd.Timestamp]:
    anchor_dates: list[pd.Timestamp] = []
    for entry in anchor_output_root.glob("anchor_*"):
        if not entry.is_dir():
            continue
        raw = entry.name.replace("anchor_", "", 1)
        try:
            dt = pd.Timestamp(raw)
        except ValueError:
            continue
        if (entry / "optimization_outputs").exists():
            anchor_dates.append(dt.normalize())
    anchor_dates = sorted(set(anchor_dates))
    if not anchor_dates:
        raise FileNotFoundError(f"No anchor_<date>/optimization_outputs folders found under {anchor_output_root}")
    return anchor_dates


def build_update_starts(
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
    update_interval_months: int,
) -> list[pd.Timestamp]:
    if update_interval_months < 1:
        raise ValueError("update_interval_months must be at least 1.")
    month_starts: list[pd.Timestamp] = []
    current = evaluation_start.replace(day=1)
    while current <= evaluation_end:
        month_starts.append(current)
        current = current + pd.offsets.MonthBegin(update_interval_months)
    return month_starts


def previous_anchor_candidates_for_month(
    month_start: pd.Timestamp,
    available_anchor_dates: list[pd.Timestamp],
) -> list[pd.Timestamp]:
    business_day_candidates = [dt for dt in available_anchor_dates if dt < month_start and dt.dayofweek < 5]
    other_candidates = [dt for dt in available_anchor_dates if dt < month_start and dt.dayofweek >= 5]
    candidates = sorted(business_day_candidates, reverse=True) + sorted(other_candidates, reverse=True)
    if not candidates:
        raise ValueError(f"No prior anchor snapshot found before month start {month_start.date()}.")
    return candidates


def selection_start_for_anchor(anchor_date: pd.Timestamp, years: int = 1) -> str:
    start = anchor_date - pd.DateOffset(years=years) + pd.DateOffset(days=1)
    return start.strftime("%Y-%m-%d")


def fit_month_model(
    *,
    repo_root: Path,
    data_csv: Path,
    anchor_output_root: Path,
    anchor_date: pd.Timestamp,
    month_start: pd.Timestamp,
    month_end: pd.Timestamp,
    target_horizon_days: int,
    top_n_per_family: int,
    selection_criterion: str,
    scale_quantile: float,
    strict_label_cutoff: bool = False,
    selection_window_years: int = 1,
) -> tuple[pd.DataFrame, dict]:
    snapshot_root = anchor_output_root / f"anchor_{anchor_date.strftime('%Y-%m-%d')}" / "optimization_outputs"
    if not snapshot_root.exists():
        raise FileNotFoundError(f"Optimization snapshot not found: {snapshot_root}")

    top_n_map = {key: top_n_per_family for key in DEFAULT_TOP_N_PER_FAMILY}
    sel_start = selection_start_for_anchor(anchor_date, years=selection_window_years)
    bundle = build_expanded_strategy_space(
        repo_root=repo_root,
        data_csv=data_csv,
        selection_start_date=sel_start,
        selection_end_date=anchor_date.strftime("%Y-%m-%d"),
        evaluation_start_date=sel_start,
        evaluation_end_date=anchor_date.strftime("%Y-%m-%d"),
        target_horizon_days=target_horizon_days,
        family_horizons=DEFAULT_FAMILY_HORIZONS,
        top_n_per_family=top_n_map,
        family_output_root=snapshot_root,
    )

    # Strict label cutoff: drop the last target_horizon_days rows whose labels
    # extend past anchor_date (look-ahead leakage fix).
    train_df = bundle.selection_df
    if strict_label_cutoff and target_horizon_days > 0:
        n_drop = min(target_horizon_days, len(train_df) - 1)
        train_df = train_df.iloc[:-n_drop].copy()

    X_selection = train_df[bundle.feature_columns].to_numpy(dtype=float)
    y_selection = train_df[TARGET_RETURN_COL].to_numpy(dtype=float)
    evaluation_feature_df = build_month_feature_matrix(
        data_csv=data_csv,
        bases=bundle.bases,
        month_start=month_start.strftime("%Y-%m-%d"),
        month_end=month_end.strftime("%Y-%m-%d"),
        norm_end_date=anchor_date.strftime("%Y-%m-%d"),
    )
    X_evaluation = evaluation_feature_df[bundle.feature_columns].to_numpy(dtype=float)

    cv_n_splits = max(3, min(5, max(3, len(train_df) // 40)))

    candidate_rows: list[dict] = []
    model_metadata_map: dict[str, dict] = {}
    fitted_models: dict[str, object] = {}

    for model_name, model in build_model_specs(len(bundle.selection_df)):
        fitted = model.fit(X_selection, y_selection)
        fitted_models[model_name] = fitted

        selection_predictions = fitted.predict(X_selection)
        selection_pred_df = build_return_prediction_frame(
            bundle.selection_df,
            bundle.feature_columns,
            selection_predictions,
            target_return_column=TARGET_RETURN_COL,
            target_direction_column=TARGET_DIRECTION_COL,
        )
        selection_summary = summarize_return_predictions(
            selection_pred_df,
            target_return_column=TARGET_RETURN_COL,
            target_direction_column=TARGET_DIRECTION_COL,
        )
        metadata = extract_model_metadata(fitted, bundle.feature_columns)
        model_metadata_map[model_name] = metadata
        selection_cv_mse = compute_time_series_cv_mse(model, X_selection, y_selection, cv_n_splits)

        candidate_rows.append(
            {
                "target_horizon_days": target_horizon_days,
                "model_name": model_name,
                "selection_rows": len(train_df),
                "evaluation_rows": len(bundle.evaluation_df),
                "selection_mse": selection_summary["mse"],
                "selection_mae": selection_summary["mae"],
                "selection_correlation": selection_summary["correlation"],
                "selection_directional_accuracy": selection_summary["directional_accuracy"],
                "selection_long_short_strategy_return": selection_summary["long_short_strategy_return"],
                "selection_cv_mse": selection_cv_mse,
                "nonzero_count": metadata.get("nonzero_count"),
            }
        )

    selected_row = pick_selected_row(candidate_rows, selection_criterion)
    selected_model_name = selected_row["model_name"]
    selected_metadata = model_metadata_map[selected_model_name]
    selected_model = fitted_models[selected_model_name]

    evaluation_predictions = selected_model.predict(X_evaluation)
    positive_selection_predictions = pd.Series(
        fitted_models[selected_model_name].predict(X_selection)
    )
    positive_selection_predictions = positive_selection_predictions[positive_selection_predictions > 0.0]
    scale = safe_quantile_scale(
        positive_selection_predictions
        if not positive_selection_predictions.empty
        else pd.Series(fitted_models[selected_model_name].predict(X_selection)),
        q=scale_quantile,
        fallback=1.0,
    )

    month_df = evaluation_feature_df[[DATE_COL, *bundle.feature_columns]].copy()
    month_df["predicted_future_return"] = evaluation_predictions
    month_df["portfolio_weight"] = build_weight_series(evaluation_predictions, scale)
    month_df["active_anchor_date"] = anchor_date.strftime("%Y-%m-%d")
    month_df["active_model_name"] = selected_model_name
    month_df["active_target_horizon_days"] = target_horizon_days
    month_df["prediction_scale"] = scale

    month_metadata = {
        "month_start": month_start.strftime("%Y-%m-%d"),
        "month_end": month_end.strftime("%Y-%m-%d"),
        "active_anchor_date": anchor_date.strftime("%Y-%m-%d"),
        "active_model_name": selected_model_name,
        "target_horizon_days": target_horizon_days,
        "selection_criterion": selection_criterion,
        "selection_correlation": selected_row["selection_correlation"],
        "selection_directional_accuracy": selected_row["selection_directional_accuracy"],
        "selection_mse": selected_row["selection_mse"],
        "selection_cv_mse": selected_row.get("selection_cv_mse"),
        "selection_long_short_strategy_return": selected_row["selection_long_short_strategy_return"],
        "selection_rows": selected_row["selection_rows"],
        "evaluation_rows": selected_row["evaluation_rows"],
        "nonzero_count": selected_metadata.get("nonzero_count"),
        "prediction_scale": scale,
        "nonzero_coefficients": selected_metadata.get("nonzero_coefficients")
        or selected_metadata.get("nonzero_coefficients_scaled_space")
        or [],
        "top_abs_coefficients": sorted(
            selected_metadata.get("nonzero_coefficients")
            or selected_metadata.get("nonzero_coefficients_scaled_space")
            or [],
            key=lambda x: abs(float(x[1])),
            reverse=True,
        )[:10],
    }
    return month_df, month_metadata


def build_score_only_df_for_basis(
    *,
    data_csv: Path,
    basis,
    start_date: str,
    end_date: str,
    norm_end_date: str | None = None,
) -> pd.DataFrame:
    # norm_end_date: the anchor date used for normalization stats (defaults to end_date).
    # Passing the anchor date here ensures features in the evaluation period are
    # normalized with the same mu/sd as during training (no post-anchor data leaks
    # into the z-score computation).
    _norm_end = norm_end_date if norm_end_date is not None else end_date

    if basis.strategy_key == "adaptive_band":
        df = load_price_only_data(data_csv)
        # Compute normalization stats from history up to ANCHOR (not month_end)
        norm_prices = get_history_df(df, _norm_end)["Price"].astype(float)
        norm_mu = float(norm_prices.mean())
        norm_sd = float(norm_prices.std(ddof=0))
        if norm_sd == 0:
            norm_sd = 1.0
        df = get_history_df(df, end_date)
        out = df.copy()
        ma_window = int(basis.params["ma_window"])
        upper_k = float(basis.params["upper_k"])
        lower_k = float(basis.params["lower_k"])
        out["Price_Norm"] = (out["Price"].astype(float) - norm_mu) / norm_sd
        out["MA"] = out["Price_Norm"].rolling(window=ma_window, min_periods=ma_window).mean()
        out["Sigma"] = out["Price_Norm"].rolling(window=ma_window, min_periods=ma_window).std(ddof=0)
        out["Upper"] = out["MA"] + upper_k * out["Sigma"]
        out["Lower"] = out["MA"] - lower_k * out["Sigma"]
        out["BandMid"] = (out["Upper"] + out["Lower"]) / 2.0
        out["HalfBandWidth"] = (out["Upper"] - out["Lower"]) / 2.0
        out["raw_score"] = -safe_divide(out["Price_Norm"] - out["BandMid"], out["HalfBandWidth"])
        out[basis.score_column] = clip_series(out["raw_score"])
        out = out.dropna(subset=[basis.score_column]).reset_index(drop=True)
        out = get_test_df(out, start_date, end_date)
        return out[[DATE_COL, basis.score_column]]

    if basis.strategy_key == "ma_crossover":
        df = load_price_only_data(data_csv)
        df = get_history_df(df, end_date)
        out = df.copy()
        short_ma = int(basis.params["short_ma"])
        long_ma = int(basis.params["long_ma"])
        out["ShortMA"] = out["Price"].rolling(window=short_ma, min_periods=short_ma).mean()
        out["LongMA"] = out["Price"].rolling(window=long_ma, min_periods=long_ma).mean()
        out["Spread"] = out["ShortMA"] - out["LongMA"]
        out = out.dropna(subset=["ShortMA", "LongMA", "Spread"]).reset_index(drop=True)
        scale = basis.scale_value if basis.scale_value is not None else safe_quantile_scale(out["Spread"])
        out["raw_score"] = safe_divide(out["Spread"], scale)
        out[basis.score_column] = clip_series(out["raw_score"])
        out = out.dropna(subset=[basis.score_column]).reset_index(drop=True)
        out = get_test_df(out, start_date, end_date)
        return out[[DATE_COL, basis.score_column]]

    if basis.strategy_key == "adaptive_volatility_band":
        df = load_ohlc_data(data_csv, include_volume=False)
        # VolProxy rolling stats: also use anchor-date history for consistency
        norm_df = get_history_df(df, _norm_end).copy()
        norm_df["VolProxy"] = (norm_df["High"] - norm_df["Low"]) / norm_df["Close"]
        vol_window = int(basis.params["vol_window"])
        _vol_mean_ref = norm_df["VolProxy"].rolling(window=vol_window, min_periods=vol_window).mean().iloc[-1]
        _vol_sigma_ref = norm_df["VolProxy"].rolling(window=vol_window, min_periods=vol_window).std(ddof=0).iloc[-1]
        df = get_history_df(df, end_date)
        out = df.copy()
        upper_k = float(basis.params["upper_k"])
        lower_k = float(basis.params["lower_k"])
        out["VolProxy"] = (out["High"] - out["Low"]) / out["Close"]
        out["VolMean"] = out["VolProxy"].rolling(window=vol_window, min_periods=vol_window).mean()
        out["VolSigma"] = out["VolProxy"].rolling(window=vol_window, min_periods=vol_window).std(ddof=0)
        out["UpperBand"] = out["VolMean"] + upper_k * out["VolSigma"]
        out["LowerBand"] = out["VolMean"] - lower_k * out["VolSigma"]
        out["BandMid"] = (out["UpperBand"] + out["LowerBand"]) / 2.0
        out["HalfBandWidth"] = (out["UpperBand"] - out["LowerBand"]) / 2.0
        out["raw_score"] = -safe_divide(out["VolProxy"] - out["BandMid"], out["HalfBandWidth"])
        out[basis.score_column] = clip_series(out["raw_score"])
        out = out.dropna(subset=[basis.score_column]).reset_index(drop=True)
        out = get_test_df(out, start_date, end_date)
        return out[[DATE_COL, basis.score_column]]

    if basis.strategy_key == "fear_greed_candle_volume":
        df = load_ohlc_data(data_csv, include_volume=True)
        df = get_history_df(df, end_date)
        out = df.copy()
        k_body = float(basis.params["k_body"])
        k_volume = float(basis.params["k_volume"])
        price_zone_window = int(basis.params["price_zone_window"])
        body_window = 10
        volume_window = 10
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
            (out["Bullish"] == 1)
            & (out["LargeBody"] == 1)
            & (out["LargeVolume"] == 1)
            & (out["InLowZone"] == 1)
        ).astype(int)
        out["SellCandidate"] = (
            (out["Bearish"] == 1)
            & (out["LargeBody"] == 1)
            & (out["LargeVolume"] == 1)
            & (out["InHighZone"] == 1)
        ).astype(int)
        out["BuySignal"] = out["BuyCandidate"]
        out["SellSignal"] = out["SellCandidate"]
        out[basis.score_column] = out["BuySignal"] - out["SellSignal"]
        out = out.dropna(subset=["AvgBody", "AvgVolume", "RecentLow", "RecentHigh"]).reset_index(drop=True)
        out = get_test_df(out, start_date, end_date)
        return out[[DATE_COL, basis.score_column]]

    raise ValueError(f"Unsupported strategy key: {basis.strategy_key}")


def build_month_feature_matrix(
    *,
    data_csv: Path,
    bases: list,
    month_start: str,
    month_end: str,
    norm_end_date: str | None = None,
) -> pd.DataFrame:
    merged = None
    for basis in bases:
        score_df = build_score_only_df_for_basis(
            data_csv=data_csv,
            basis=basis,
            start_date=month_start,
            end_date=month_end,
            norm_end_date=norm_end_date,
        )
        if merged is None:
            merged = score_df
        else:
            merged = merged.merge(score_df, on=DATE_COL, how="inner")
    if merged is None or merged.empty:
        raise ValueError("Monthly feature matrix is empty after merging score-only bases.")
    return merged.sort_values(DATE_COL).reset_index(drop=True)


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    hold_days = int(args.hold_days) if args.hold_days is not None else int(args.target_horizon_days)
    if hold_days < 1:
        raise ValueError("hold_days must be at least 1.")

    evaluation_start = pd.Timestamp(args.evaluation_start_date)
    evaluation_end = pd.Timestamp(args.evaluation_end_date)
    if evaluation_end < evaluation_start:
        raise ValueError("evaluation_end_date must be on or after evaluation_start_date.")

    anchor_output_root = Path(args.anchor_output_root)
    available_anchor_dates = load_available_anchor_dates(anchor_output_root)
    update_starts = build_update_starts(
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        update_interval_months=args.update_interval_months,
    )

    month_frames: list[pd.DataFrame] = []
    month_logs: list[dict] = []

    for update_start in update_starts:
        update_end = min(update_start + pd.offsets.MonthBegin(args.update_interval_months) - pd.offsets.Day(1), evaluation_end)
        month_df = None
        month_metadata = None
        last_error: Exception | None = None
        for anchor_date in previous_anchor_candidates_for_month(update_start, available_anchor_dates):
            print(
                f"[PERIODIC UPDATE] period_start={update_start.strftime('%Y-%m-%d')} "
                f"| period_end={update_end.strftime('%Y-%m-%d')} "
                f"| trying anchor={anchor_date.strftime('%Y-%m-%d')}"
            )
            try:
                month_df, month_metadata = fit_month_model(
                    repo_root=REPO_ROOT,
                    data_csv=Path(args.data_csv),
                    anchor_output_root=anchor_output_root,
                    anchor_date=anchor_date,
                    month_start=update_start,
                    month_end=update_end,
                    target_horizon_days=args.target_horizon_days,
                    top_n_per_family=args.top_n_per_family,
                    selection_criterion=args.selection_criterion,
                    scale_quantile=args.scale_quantile,
                    strict_label_cutoff=args.strict_label_cutoff,
                    selection_window_years=args.selection_window_years,
                )
                break
            except Exception as exc:  # pragma: no cover - fallback path for sparse monthly snapshots
                last_error = exc
                continue
        if month_df is None or month_metadata is None:
            raise RuntimeError(
                f"Failed to fit any periodic-update model for {update_start.strftime('%Y-%m-%d')} using prior anchors."
            ) from last_error
        month_frames.append(month_df)
        month_logs.append(month_metadata)

    if not month_frames:
        raise ValueError("No monthly frames were generated.")

    signal_df = pd.concat(month_frames, ignore_index=True).sort_values(DATE_COL).reset_index(drop=True)

    if args.max_exposure_cap is not None:
        signal_df["portfolio_weight"] = signal_df["portfolio_weight"].clip(upper=args.max_exposure_cap)

    price_df = load_price_only_data(Path(args.data_csv)).rename(columns={"Price": "price"})
    signal_df = (
        signal_df.merge(price_df[[DATE_COL, "price"]], on=DATE_COL, how="inner")
        .sort_values(DATE_COL)
        .reset_index(drop=True)
    )

    equity_df, tranche_history = simulate_long_only_tranches(
        signal_df,
        weight_col="portfolio_weight",
        price_col="price",
        hold_days=hold_days,
        initial_capital=args.initial_capital,
    )

    first_price = float(equity_df["price"].iloc[0])
    last_price = float(equity_df["price"].iloc[-1])
    buy_hold_return = (last_price / first_price) - 1.0

    initial_capital = float(args.initial_capital)
    final_equity = float(equity_df["net_equity"].iloc[-1])
    strategy_return = final_equity / initial_capital - 1.0
    avg_weight = float(signal_df["portfolio_weight"].mean())
    avg_exposure = float((equity_df["gross_exposure"] / equity_df["net_equity"]).mean())

    daily_signal_csv = maybe_tagged_path(out_dir, "monthly_update_tranche_backtest_daily_signals", ".csv", args.tag)
    model_log_csv = maybe_tagged_path(out_dir, "monthly_update_tranche_backtest_model_log", ".csv", args.tag)
    equity_csv = maybe_tagged_path(out_dir, "monthly_update_tranche_backtest_equity_curve", ".csv", args.tag)
    tranche_csv = maybe_tagged_path(out_dir, "monthly_update_tranche_backtest_tranches", ".csv", args.tag)
    summary_json = maybe_tagged_path(out_dir, "monthly_update_tranche_backtest_summary", ".json", args.tag)

    signal_df.to_csv(daily_signal_csv, index=False)
    pd.DataFrame(month_logs).to_csv(model_log_csv, index=False)
    equity_df.to_csv(equity_csv, index=False)
    pd.DataFrame(tranche_history).to_csv(tranche_csv, index=False)

    payload = {
        "evaluation_start_date": args.evaluation_start_date,
        "evaluation_end_date": args.evaluation_end_date,
        "target_horizon_days": args.target_horizon_days,
        "hold_days": hold_days,
        "selection_criterion": args.selection_criterion,
        "update_interval_months": args.update_interval_months,
        "initial_capital": initial_capital,
        "scale_quantile": args.scale_quantile,
        "max_exposure_cap": args.max_exposure_cap,
        "buy_hold_return": buy_hold_return,
        "strategy_return": strategy_return,
        "excess_vs_buy_hold": strategy_return - buy_hold_return,
        "final_equity": final_equity,
        "average_portfolio_weight": avg_weight,
        "average_gross_exposure_fraction": avg_exposure,
        "months_modeled": len(month_logs),
        "monthly_models": month_logs,
    }
    with open(summary_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)

    print("=" * 80)
    print("OBJECTIVE 2 MONTHLY UPDATE TRANCHE BACKTEST")
    print("=" * 80)
    print(f"EVALUATION_START_DATE:    {args.evaluation_start_date}")
    print(f"EVALUATION_END_DATE:      {args.evaluation_end_date}")
    print(f"TARGET_HORIZON_DAYS:      {args.target_horizon_days}")
    print(f"HOLD_DAYS:                {hold_days}")
    print(f"SELECTION_CRITERION:      {args.selection_criterion}")
    print(f"UPDATE_INTERVAL_MONTHS:   {args.update_interval_months}")
    print(f"MONTHS_MODELED:           {len(month_logs)}")
    print(f"MAX_EXPOSURE_CAP:         {args.max_exposure_cap if args.max_exposure_cap is not None else 'none'}")
    print(f"AVERAGE_WEIGHT:           {avg_weight:.4f}")
    print(f"AVERAGE_GROSS_EXPOSURE:   {avg_exposure:.4f}")
    print("-" * 80)
    print(f"BUY_HOLD_RETURN:          {buy_hold_return:.6f}")
    print(f"STRATEGY_RETURN:          {strategy_return:.6f}")
    print(f"EXCESS_VS_BUY_HOLD:       {strategy_return - buy_hold_return:.6f}")
    print(f"[OK] Saved daily signals: {daily_signal_csv}")
    print(f"[OK] Saved model log:     {model_log_csv}")
    print(f"[OK] Saved equity CSV:    {equity_csv}")
    print(f"[OK] Saved tranche CSV:   {tranche_csv}")
    print(f"[OK] Saved summary JSON:  {summary_json}")


if __name__ == "__main__":
    main()
