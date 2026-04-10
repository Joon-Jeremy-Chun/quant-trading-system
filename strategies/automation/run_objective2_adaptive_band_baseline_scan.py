from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LinearRegression

from objective2_modeling import build_return_prediction_frame, summarize_return_predictions
from objective2_signal_matrix_builder import TARGET_DIRECTION_COL, TARGET_RETURN_COL, adaptive_band_score_df, add_targets
from strategy_matrix_builder import DATE_COL, get_test_df, load_best_optimization_selection, load_price_only_data


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_adaptive_band_baseline_comparison"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare adaptive-band score against a simple raw price z-score baseline across future horizons."
    )
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument("--selection-start-date", type=str, default="2024-01-01", help="Selection-period start date (YYYY-MM-DD).")
    parser.add_argument("--selection-end-date", type=str, default="2024-12-31", help="Selection-period end date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-start-date", type=str, default="2025-01-01", help="Evaluation-period start date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-end-date", type=str, default="2025-12-31", help="Evaluation-period end date (YYYY-MM-DD).")
    parser.add_argument("--min-horizon-days", type=int, default=1, help="Minimum future target horizon in trading days.")
    parser.add_argument("--max-horizon-days", type=int, default=130, help="Maximum future target horizon in trading days.")
    parser.add_argument("--tag", type=str, default=None, help="Optional tag added to output filenames.")
    return parser.parse_args()


def maybe_tagged_path(base_dir: Path, stem: str, suffix: str, tag: str | None) -> Path:
    if tag:
        return base_dir / f"{stem}_{tag}{suffix}"
    return base_dir / f"{stem}{suffix}"


def raw_price_zscore_df(
    csv_path: Path,
    ma_window: int,
    start_date: str,
    end_date: str,
    target_horizon_days: int,
) -> pd.DataFrame:
    df = load_price_only_data(csv_path)
    df = get_test_df(df, start_date, end_date)

    out = df.copy()
    out["RollingMean"] = out["Price"].rolling(window=ma_window, min_periods=ma_window).mean()
    out["RollingStd"] = out["Price"].rolling(window=ma_window, min_periods=ma_window).std(ddof=0)
    out["raw_price_zscore"] = (out["Price"] - out["RollingMean"]) / out["RollingStd"]
    out = add_targets(out, "Price", horizon_days=target_horizon_days)
    out = out.dropna(subset=["raw_price_zscore", TARGET_RETURN_COL]).reset_index(drop=True)
    return out[[DATE_COL, "raw_price_zscore", TARGET_RETURN_COL, TARGET_DIRECTION_COL]]


def evaluate_single_feature(
    df_selection: pd.DataFrame,
    df_evaluation: pd.DataFrame,
    feature_column: str,
) -> dict:
    X_selection = df_selection[[feature_column]].to_numpy(dtype=float)
    y_selection = df_selection[TARGET_RETURN_COL].to_numpy(dtype=float)
    X_evaluation = df_evaluation[[feature_column]].to_numpy(dtype=float)

    model = LinearRegression().fit(X_selection, y_selection)

    selection_predictions = model.predict(X_selection)
    evaluation_predictions = model.predict(X_evaluation)

    selection_pred_df = build_return_prediction_frame(
        df_selection,
        [feature_column],
        selection_predictions,
        target_return_column=TARGET_RETURN_COL,
        target_direction_column=TARGET_DIRECTION_COL,
    )
    evaluation_pred_df = build_return_prediction_frame(
        df_evaluation,
        [feature_column],
        evaluation_predictions,
        target_return_column=TARGET_RETURN_COL,
        target_direction_column=TARGET_DIRECTION_COL,
    )

    selection_summary = summarize_return_predictions(
        selection_pred_df,
        target_return_column=TARGET_RETURN_COL,
        target_direction_column=TARGET_DIRECTION_COL,
    )
    evaluation_summary = summarize_return_predictions(
        evaluation_pred_df,
        target_return_column=TARGET_RETURN_COL,
        target_direction_column=TARGET_DIRECTION_COL,
    )

    return {
        "coefficient": float(model.coef_[0]),
        "intercept": float(model.intercept_),
        "selection_rows": len(df_selection),
        "evaluation_rows": len(df_evaluation),
        "selection_correlation": selection_summary["correlation"],
        "selection_directional_accuracy": selection_summary["directional_accuracy"],
        "evaluation_correlation": evaluation_summary["correlation"],
        "evaluation_directional_accuracy": evaluation_summary["directional_accuracy"],
    }


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    selection = load_best_optimization_selection(REPO_ROOT, "adaptive_band")
    ma_window = int(selection.params["ma_window"])

    rows: list[dict] = []
    for horizon_days in range(args.min_horizon_days, args.max_horizon_days + 1):
        adaptive_selection_df, _ = adaptive_band_score_df(
            Path(args.data_csv),
            selection,
            args.selection_start_date,
            args.selection_end_date,
            target_horizon_days=horizon_days,
        )
        adaptive_evaluation_df, _ = adaptive_band_score_df(
            Path(args.data_csv),
            selection,
            args.evaluation_start_date,
            args.evaluation_end_date,
            target_horizon_days=horizon_days,
        )

        raw_selection_df = raw_price_zscore_df(
            Path(args.data_csv),
            ma_window=ma_window,
            start_date=args.selection_start_date,
            end_date=args.selection_end_date,
            target_horizon_days=horizon_days,
        )
        raw_evaluation_df = raw_price_zscore_df(
            Path(args.data_csv),
            ma_window=ma_window,
            start_date=args.evaluation_start_date,
            end_date=args.evaluation_end_date,
            target_horizon_days=horizon_days,
        )

        adaptive_result = evaluate_single_feature(
            adaptive_selection_df,
            adaptive_evaluation_df,
            "adaptive_band_score",
        )
        raw_result = evaluate_single_feature(
            raw_selection_df,
            raw_evaluation_df,
            "raw_price_zscore",
        )

        rows.append(
            {
                "target_horizon_days": horizon_days,
                "ma_window": ma_window,
                "adaptive_band_selection_corr": adaptive_result["selection_correlation"],
                "adaptive_band_evaluation_corr": adaptive_result["evaluation_correlation"],
                "adaptive_band_selection_diracc": adaptive_result["selection_directional_accuracy"],
                "adaptive_band_evaluation_diracc": adaptive_result["evaluation_directional_accuracy"],
                "adaptive_band_coef": adaptive_result["coefficient"],
                "raw_zscore_selection_corr": raw_result["selection_correlation"],
                "raw_zscore_evaluation_corr": raw_result["evaluation_correlation"],
                "raw_zscore_selection_diracc": raw_result["selection_directional_accuracy"],
                "raw_zscore_evaluation_diracc": raw_result["evaluation_directional_accuracy"],
                "raw_zscore_coef": raw_result["coefficient"],
                "evaluation_corr_gap_adaptive_minus_raw": adaptive_result["evaluation_correlation"] - raw_result["evaluation_correlation"],
            }
        )

    summary_df = pd.DataFrame(rows).sort_values(
        by=["evaluation_corr_gap_adaptive_minus_raw", "adaptive_band_evaluation_corr"],
        ascending=[False, False],
    )

    summary_csv = maybe_tagged_path(out_dir, "adaptive_band_vs_raw_zscore_scan", ".csv", args.tag)
    summary_df.to_csv(summary_csv, index=False)

    print("=" * 80)
    print("OBJECTIVE 2 ADAPTIVE BAND VS RAW Z-SCORE SCAN")
    print("=" * 80)
    print(f"ADAPTIVE_BAND_MA_WINDOW: {ma_window}")
    print(summary_df.head(20).to_string(index=False))
    print(f"[OK] Saved comparison summary: {summary_csv}")


if __name__ == "__main__":
    main()
