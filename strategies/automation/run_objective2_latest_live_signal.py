from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from run_objective2_monthly_update_tranche_backtest import (
    DEFAULT_ANCHOR_OUTPUT_ROOT,
    DEFAULT_DATA_CSV,
    REPO_ROOT,
    fit_month_model,
    load_available_anchor_dates,
    previous_anchor_candidates_for_month,
)
from strategy_matrix_builder import DATE_COL, load_price_only_data


DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "live"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the latest Objective 2 live signal for GLD using the most recently updated model."
    )
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument(
        "--anchor-output-root",
        type=str,
        default=str(DEFAULT_ANCHOR_OUTPUT_ROOT),
        help="Root directory containing anchor_<date>/optimization_outputs folders.",
    )
    parser.add_argument(
        "--asof-date",
        type=str,
        default=None,
        help="Optional as-of date (YYYY-MM-DD). Defaults to the latest trading date in the CSV.",
    )
    parser.add_argument(
        "--target-horizon-days",
        type=int,
        default=130,
        help="Prediction target horizon used for the live model.",
    )
    parser.add_argument(
        "--top-n-per-family",
        type=int,
        default=10,
        help="Number of top candidates used from each strategy family.",
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
        help="Criterion used to pick the active model inside the fixed horizon.",
    )
    parser.add_argument(
        "--update-interval-months",
        type=int,
        default=1,
        help="Model refresh interval in calendar months. Defaults to monthly.",
    )
    parser.add_argument(
        "--scale-quantile",
        type=float,
        default=0.95,
        help="Quantile used to scale predictions into the target weight.",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="GLD",
        help="Symbol label stored in the output payload.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Optional tag added to history filename. Latest snapshot path stays fixed.",
    )
    return parser.parse_args()


def resolve_asof_trading_date(data_csv: Path, asof_date: str | None) -> tuple[pd.Timestamp, pd.DataFrame]:
    price_df = load_price_only_data(data_csv).sort_values(DATE_COL).reset_index(drop=True)
    if price_df.empty:
        raise ValueError(f"No rows found in {data_csv}")

    if asof_date is None:
        return pd.Timestamp(price_df[DATE_COL].iloc[-1]).normalize(), price_df

    requested = pd.Timestamp(asof_date).normalize()
    eligible = price_df[price_df[DATE_COL] <= requested].copy()
    if eligible.empty:
        raise ValueError(f"No trading date on or before {requested.date()} in {data_csv}")
    return pd.Timestamp(eligible[DATE_COL].iloc[-1]).normalize(), price_df


def compute_period_start(asof_date: pd.Timestamp, update_interval_months: int) -> pd.Timestamp:
    if update_interval_months < 1:
        raise ValueError("update_interval_months must be at least 1.")
    month_index = ((asof_date.month - 1) // update_interval_months) * update_interval_months + 1
    return pd.Timestamp(year=asof_date.year, month=month_index, day=1)


def latest_json_path(out_dir: Path) -> Path:
    return out_dir / "latest_gld_signal.json"


def history_csv_path(out_dir: Path, tag: str | None) -> Path:
    suffix = f"_{tag}" if tag else ""
    return out_dir / "history" / f"gld_signal_log{suffix}.csv"


def append_history_row(csv_path: Path, row: dict) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(row.keys())
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def classify_signal_strength(target_weight: float) -> str:
    if target_weight <= 0.0:
        return "flat"
    if target_weight < 0.25:
        return "weak"
    if target_weight < 0.6:
        return "moderate"
    return "strong"


def summarize_family_contributions(contribution_pairs: list[tuple[str, float]]) -> tuple[dict[str, float], str | None]:
    family_sums: dict[str, float] = defaultdict(float)
    for score_column, contribution in contribution_pairs:
        if score_column.startswith("adaptive_band"):
            family_sums["adaptive_band"] += abs(float(contribution))
        elif score_column.startswith("ma_crossover"):
            family_sums["ma_crossover"] += abs(float(contribution))
        elif score_column.startswith("adaptive_volatility_band"):
            family_sums["adaptive_volatility_band"] += abs(float(contribution))
        elif score_column.startswith("fear_greed_candle_volume"):
            family_sums["fear_greed_candle_volume"] += abs(float(contribution))
    dominant_family = None
    if family_sums:
        dominant_family = max(family_sums.items(), key=lambda x: x[1])[0]
    return dict(sorted(family_sums.items())), dominant_family


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    data_csv = Path(args.data_csv)
    anchor_output_root = Path(args.anchor_output_root)

    asof_date, price_df = resolve_asof_trading_date(data_csv, args.asof_date)
    period_start = compute_period_start(asof_date, args.update_interval_months)
    available_anchor_dates = load_available_anchor_dates(anchor_output_root)
    anchor_candidates = previous_anchor_candidates_for_month(period_start, available_anchor_dates)

    month_df = None
    month_metadata = None
    last_error: Exception | None = None
    for anchor_date in anchor_candidates:
        try:
            month_df, month_metadata = fit_month_model(
                repo_root=REPO_ROOT,
                data_csv=data_csv,
                anchor_output_root=anchor_output_root,
                anchor_date=anchor_date,
                month_start=asof_date,
                month_end=asof_date,
                target_horizon_days=args.target_horizon_days,
                top_n_per_family=args.top_n_per_family,
                selection_criterion=args.selection_criterion,
                scale_quantile=args.scale_quantile,
            )
            break
        except Exception as exc:  # pragma: no cover - fallback logic depends on available snapshots
            last_error = exc
            continue

    if month_df is None or month_metadata is None:
        raise RuntimeError(
            f"Failed to fit a live signal model for {asof_date.date()} using anchors before {period_start.date()}."
        ) from last_error

    row = month_df.iloc[-1]
    price_row = price_df[price_df[DATE_COL] == asof_date]
    close_price = float(price_row["Price"].iloc[-1]) if not price_row.empty else None
    predicted_return = float(row["predicted_future_return"])
    target_weight = float(row["portfolio_weight"])
    signal = "BUY" if target_weight > 0 else "HOLD"
    signal_strength = classify_signal_strength(target_weight)
    nonzero_coefficients = month_metadata.get("nonzero_coefficients", [])

    feature_snapshot = {}
    contribution_pairs: list[tuple[str, float]] = []
    for score_column, coef in nonzero_coefficients:
        score_value = float(row.get(score_column, 0.0))
        contribution = float(coef) * score_value
        feature_snapshot[score_column] = score_value
        contribution_pairs.append((score_column, contribution))

    top_positive_contributions = sorted(
        [item for item in contribution_pairs if item[1] > 0],
        key=lambda x: x[1],
        reverse=True,
    )[:5]
    top_negative_contributions = sorted(
        [item for item in contribution_pairs if item[1] < 0],
        key=lambda x: x[1],
    )[:5]
    family_abs_contributions, dominant_family = summarize_family_contributions(contribution_pairs)
    model_age_days = int((asof_date - pd.Timestamp(month_metadata["active_anchor_date"])).days)
    utc_today = pd.Timestamp(datetime.now(timezone.utc).date())
    dataset_staleness_days = int((utc_today - asof_date).days)

    payload = {
        "symbol": args.symbol,
        "asof_date": asof_date.strftime("%Y-%m-%d"),
        "close_price": close_price,
        "signal": signal,
        "signal_strength": signal_strength,
        "target_weight": target_weight,
        "predicted_future_return": predicted_return,
        "target_horizon_days": args.target_horizon_days,
        "update_interval_months": args.update_interval_months,
        "selection_criterion": args.selection_criterion,
        "active_anchor_date": month_metadata["active_anchor_date"],
        "active_model_name": month_metadata["active_model_name"],
        "nonzero_count": month_metadata["nonzero_count"],
        "prediction_scale": month_metadata["prediction_scale"],
        "selection_correlation": month_metadata["selection_correlation"],
        "selection_directional_accuracy": month_metadata["selection_directional_accuracy"],
        "selection_mse": month_metadata["selection_mse"],
        "selection_long_short_strategy_return": month_metadata["selection_long_short_strategy_return"],
        "model_age_days": model_age_days,
        "dataset_staleness_days": dataset_staleness_days,
        "dominant_family": dominant_family,
        "family_abs_contributions": family_abs_contributions,
        "top_positive_contributions": top_positive_contributions,
        "top_negative_contributions": top_negative_contributions,
        "feature_snapshot": feature_snapshot,
        "nonzero_coefficients": nonzero_coefficients,
        "top_abs_coefficients": month_metadata["top_abs_coefficients"],
        "notes": [
            "This payload is intended for deployment-side order generation.",
            "Signal is BUY for positive target weight and HOLD otherwise under the current long-only setup.",
            "Feature snapshot stores only the active nonzero coefficient features for the current day.",
        ],
    }

    latest_path = latest_json_path(out_dir)
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    history_row = {
        "symbol": payload["symbol"],
        "asof_date": payload["asof_date"],
        "close_price": payload["close_price"],
        "signal": payload["signal"],
        "signal_strength": payload["signal_strength"],
        "target_weight": payload["target_weight"],
        "predicted_future_return": payload["predicted_future_return"],
        "target_horizon_days": payload["target_horizon_days"],
        "update_interval_months": payload["update_interval_months"],
        "selection_criterion": payload["selection_criterion"],
        "active_anchor_date": payload["active_anchor_date"],
        "active_model_name": payload["active_model_name"],
        "nonzero_count": payload["nonzero_count"],
        "model_age_days": payload["model_age_days"],
        "dataset_staleness_days": payload["dataset_staleness_days"],
        "dominant_family": payload["dominant_family"],
        "selection_correlation": payload["selection_correlation"],
        "selection_directional_accuracy": payload["selection_directional_accuracy"],
        "selection_mse": payload["selection_mse"],
        "selection_long_short_strategy_return": payload["selection_long_short_strategy_return"],
    }
    append_history_row(history_csv_path(out_dir, args.tag), history_row)

    print("=" * 80)
    print("OBJECTIVE 2 LATEST LIVE SIGNAL")
    print("=" * 80)
    print(f"ASOF_DATE:                {payload['asof_date']}")
    print(f"SYMBOL:                   {payload['symbol']}")
    print(f"CLOSE_PRICE:              {payload['close_price']}")
    print(f"SIGNAL:                   {payload['signal']}")
    print(f"SIGNAL_STRENGTH:          {payload['signal_strength']}")
    print(f"TARGET_WEIGHT:            {payload['target_weight']:.6f}")
    print(f"PREDICTED_FUTURE_RETURN:  {payload['predicted_future_return']:.6f}")
    print(f"ACTIVE_ANCHOR_DATE:       {payload['active_anchor_date']}")
    print(f"ACTIVE_MODEL_NAME:        {payload['active_model_name']}")
    print(f"DOMINANT_FAMILY:          {payload['dominant_family']}")
    print(f"UPDATE_INTERVAL_MONTHS:   {payload['update_interval_months']}")
    print(f"TARGET_HORIZON_DAYS:      {payload['target_horizon_days']}")
    print(f"[OK] Saved latest signal: {latest_path}")
    print(f"[OK] Appended history:    {history_csv_path(out_dir, args.tag)}")


if __name__ == "__main__":
    main()
