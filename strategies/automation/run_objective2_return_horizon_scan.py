from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LinearRegression

from objective2_modeling import (
    build_return_prediction_frame,
    load_objective2_data,
    summarize_return_predictions,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_return_horizon_scan"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan future target horizons for Objective 2 return prediction.")
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument("--selection-start-date", type=str, default="2024-01-01", help="Selection-period start date (YYYY-MM-DD).")
    parser.add_argument("--selection-end-date", type=str, default="2024-12-31", help="Selection-period end date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-start-date", type=str, default="2025-01-01", help="Evaluation-period start date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-end-date", type=str, default="2025-12-31", help="Evaluation-period end date (YYYY-MM-DD).")
    parser.add_argument("--min-horizon-days", type=int, default=1, help="Minimum future target horizon in trading days.")
    parser.add_argument("--max-horizon-days", type=int, default=65, help="Maximum future target horizon in trading days.")
    parser.add_argument("--tag", type=str, default=None, help="Optional tag added to output filenames.")
    return parser.parse_args()


def maybe_tagged_path(base_dir: Path, stem: str, suffix: str, tag: str | None) -> Path:
    if tag:
        return base_dir / f"{stem}_{tag}{suffix}"
    return base_dir / f"{stem}{suffix}"


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for horizon_days in range(args.min_horizon_days, args.max_horizon_days + 1):
        bundle = load_objective2_data(
            repo_root=REPO_ROOT,
            data_csv=Path(args.data_csv),
            selection_start_date=args.selection_start_date,
            selection_end_date=args.selection_end_date,
            evaluation_start_date=args.evaluation_start_date,
            evaluation_end_date=args.evaluation_end_date,
            target_horizon_days=horizon_days,
        )
        X_selection = bundle.selection_df[bundle.feature_columns].to_numpy(dtype=float)
        y_selection = bundle.selection_df[bundle.target_return_column].to_numpy(dtype=float)
        X_evaluation = bundle.evaluation_df[bundle.feature_columns].to_numpy(dtype=float)

        model = LinearRegression().fit(X_selection, y_selection)
        selection_predictions = model.predict(X_selection)
        evaluation_predictions = model.predict(X_evaluation)

        selection_pred_df = build_return_prediction_frame(
            bundle.selection_df,
            bundle.feature_columns,
            selection_predictions,
            target_return_column=bundle.target_return_column,
            target_direction_column=bundle.target_direction_column,
        )
        evaluation_pred_df = build_return_prediction_frame(
            bundle.evaluation_df,
            bundle.feature_columns,
            evaluation_predictions,
            target_return_column=bundle.target_return_column,
            target_direction_column=bundle.target_direction_column,
        )
        selection_summary = summarize_return_predictions(
            selection_pred_df,
            target_return_column=bundle.target_return_column,
            target_direction_column=bundle.target_direction_column,
        )
        evaluation_summary = summarize_return_predictions(
            evaluation_pred_df,
            target_return_column=bundle.target_return_column,
            target_direction_column=bundle.target_direction_column,
        )

        rows.append(
            {
                "target_horizon_days": horizon_days,
                "selection_rows": len(bundle.selection_df),
                "evaluation_rows": len(bundle.evaluation_df),
                "selection_correlation": selection_summary["correlation"],
                "selection_directional_accuracy": selection_summary["directional_accuracy"],
                "selection_long_short_strategy_return": selection_summary["long_short_strategy_return"],
                "evaluation_correlation": evaluation_summary["correlation"],
                "evaluation_directional_accuracy": evaluation_summary["directional_accuracy"],
                "evaluation_long_short_strategy_return": evaluation_summary["long_short_strategy_return"],
            }
        )

    summary_df = pd.DataFrame(rows).sort_values(
        by=["evaluation_correlation", "evaluation_long_short_strategy_return"],
        ascending=[False, False],
    )

    summary_csv = maybe_tagged_path(out_dir, "return_horizon_scan_summary", ".csv", args.tag)
    summary_df.to_csv(summary_csv, index=False)

    print("=" * 80)
    print("OBJECTIVE 2 RETURN HORIZON SCAN")
    print("=" * 80)
    print(summary_df.head(15).to_string(index=False))
    print(f"[OK] Saved horizon scan summary: {summary_csv}")


if __name__ == "__main__":
    main()
