from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from objective2_modeling import (
    build_return_prediction_frame,
    fit_linear_regression,
    load_objective2_data,
    predict_linear_regression,
    summarize_return_predictions,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_return_prediction"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Objective 2 next-return prediction using the signal matrix.")
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument("--selection-start-date", type=str, default="2024-01-01", help="Selection-period start date (YYYY-MM-DD).")
    parser.add_argument("--selection-end-date", type=str, default="2024-12-31", help="Selection-period end date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-start-date", type=str, default="2025-01-01", help="Evaluation-period start date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-end-date", type=str, default="2025-12-31", help="Evaluation-period end date (YYYY-MM-DD).")
    parser.add_argument("--target-horizon-days", type=int, default=1, help="Future target horizon in trading days.")
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

    bundle = load_objective2_data(
        repo_root=REPO_ROOT,
        data_csv=Path(args.data_csv),
        selection_start_date=args.selection_start_date,
        selection_end_date=args.selection_end_date,
        evaluation_start_date=args.evaluation_start_date,
        evaluation_end_date=args.evaluation_end_date,
        target_horizon_days=args.target_horizon_days,
    )

    X_selection = bundle.selection_df[bundle.feature_columns].to_numpy(dtype=float)
    y_selection = bundle.selection_df[bundle.target_return_column].to_numpy(dtype=float)
    X_evaluation = bundle.evaluation_df[bundle.feature_columns].to_numpy(dtype=float)

    model = fit_linear_regression(X_selection, y_selection)

    selection_predictions = predict_linear_regression(model, X_selection)
    evaluation_predictions = predict_linear_regression(model, X_evaluation)

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

    selection_csv = maybe_tagged_path(out_dir, "selection_return_predictions", ".csv", args.tag)
    evaluation_csv = maybe_tagged_path(out_dir, "evaluation_return_predictions", ".csv", args.tag)
    summary_json = maybe_tagged_path(out_dir, "return_prediction_summary", ".json", args.tag)

    selection_pred_df.to_csv(selection_csv, index=False)
    evaluation_pred_df.to_csv(evaluation_csv, index=False)

    summary = {
        "data_csv": str(Path(args.data_csv)),
        "selection_start_date": args.selection_start_date,
        "selection_end_date": args.selection_end_date,
        "evaluation_start_date": args.evaluation_start_date,
        "evaluation_end_date": args.evaluation_end_date,
        "target_horizon_days": args.target_horizon_days,
        "feature_columns": bundle.feature_columns,
        "model_type": "linear_regression",
        "intercept": model.intercept,
        "coefficients": {
            column: float(value) for column, value in zip(bundle.feature_columns, model.coefficients)
        },
        "selection_summary": selection_summary,
        "evaluation_summary": evaluation_summary,
    }

    with open(summary_json, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)

    print("=" * 80)
    print("OBJECTIVE 2 RETURN PREDICTION")
    print("=" * 80)
    print(f"FEATURE_COLUMNS:        {bundle.feature_columns}")
    print(f"SELECTION_ROWS:         {len(selection_pred_df)}")
    print(f"EVALUATION_ROWS:        {len(evaluation_pred_df)}")
    print(f"TARGET_HORIZON_DAYS:    {args.target_horizon_days}")
    print(f"INTERCEPT:              {model.intercept:.6f}")
    print(f"COEFFICIENTS:           {np.round(model.coefficients, 6)}")
    print("-" * 80)
    print(
        "SELECTION: "
        f"MSE={selection_summary['mse']:.6f}, "
        f"MAE={selection_summary['mae']:.6f}, "
        f"Corr={selection_summary['correlation']:.6f}, "
        f"DirAcc={selection_summary['directional_accuracy']:.4f}, "
        f"LSReturn={selection_summary['long_short_strategy_return']:.6f}"
    )
    print(
        "EVALUATION: "
        f"MSE={evaluation_summary['mse']:.6f}, "
        f"MAE={evaluation_summary['mae']:.6f}, "
        f"Corr={evaluation_summary['correlation']:.6f}, "
        f"DirAcc={evaluation_summary['directional_accuracy']:.4f}, "
        f"LSReturn={evaluation_summary['long_short_strategy_return']:.6f}"
    )
    print(f"[OK] Saved selection predictions: {selection_csv}")
    print(f"[OK] Saved evaluation predictions:{evaluation_csv}")
    print(f"[OK] Saved summary:              {summary_json}")


if __name__ == "__main__":
    main()
