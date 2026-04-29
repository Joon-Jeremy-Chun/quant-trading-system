from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNetCV, LassoCV, LinearRegression, RidgeCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from objective2_expanded_strategy_space import (
    DEFAULT_FAMILY_HORIZONS,
    DEFAULT_TOP_N_PER_FAMILY,
    ExpandedStrategySpaceBundle,
    build_expanded_strategy_space,
)
from objective2_modeling import (
    build_return_prediction_frame,
    summarize_return_predictions,
)
from objective2_signal_matrix_builder import TARGET_DIRECTION_COL, TARGET_RETURN_COL


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_expanded_strategy_model_selection"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Model selection on an expanded Objective 2 strategy space using top candidates from each strategy family."
    )
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument("--selection-start-date", type=str, default="2024-01-01", help="Selection-period start date (YYYY-MM-DD).")
    parser.add_argument("--selection-end-date", type=str, default="2024-12-31", help="Selection-period end date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-start-date", type=str, default="2025-01-01", help="Evaluation-period start date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-end-date", type=str, default="2025-12-31", help="Evaluation-period end date (YYYY-MM-DD).")
    parser.add_argument("--target-horizon-days", type=int, default=1, help="Future target horizon in trading days.")
    parser.add_argument("--top-n-per-family", type=int, default=10, help="Number of top candidates to use from each strategy family.")
    parser.add_argument("--tag", type=str, default=None, help="Optional tag added to output filenames.")
    return parser.parse_args()


def maybe_tagged_path(base_dir: Path, stem: str, suffix: str, tag: str | None) -> Path:
    if tag:
        return base_dir / f"{stem}_{tag}{suffix}"
    return base_dir / f"{stem}{suffix}"


def to_builtin(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: to_builtin(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [to_builtin(item) for item in value]
    return value


def build_model_specs(n_selection_rows: int) -> list[tuple[str, object]]:
    n_splits = max(3, min(5, max(3, n_selection_rows // 40)))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    alphas = np.logspace(-4, 1, 30)

    return [
        ("ols", LinearRegression()),
        ("ridge", Pipeline([
            ("scaler", StandardScaler()),
            ("model", RidgeCV(alphas=alphas, cv=tscv)),
        ])),
        ("lasso", Pipeline([
            ("scaler", StandardScaler()),
            ("model", LassoCV(alphas=alphas, cv=tscv, max_iter=20000)),
        ])),
        ("elastic_net", Pipeline([
            ("scaler", StandardScaler()),
            ("model", ElasticNetCV(alphas=alphas, l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9], cv=tscv, max_iter=20000)),
        ])),
    ]


def extract_model_metadata(fitted_model: object, feature_columns: list[str]) -> dict:
    if isinstance(fitted_model, LinearRegression):
        coefs = fitted_model.coef_
        nonzero = [(col, float(val)) for col, val in zip(feature_columns, coefs) if abs(float(val)) > 1e-12]
        return {
            "intercept": float(fitted_model.intercept_),
            "nonzero_coefficients": nonzero,
            "nonzero_count": len(nonzero),
        }

    if isinstance(fitted_model, Pipeline):
        model = fitted_model.named_steps["model"]
        coefs = model.coef_
        nonzero = [(col, float(val)) for col, val in zip(feature_columns, coefs) if abs(float(val)) > 1e-12]
        payload = {
            "intercept": float(model.intercept_),
            "nonzero_coefficients_scaled_space": nonzero,
            "nonzero_count": len(nonzero),
        }
        if hasattr(model, "alpha_"):
            payload["alpha"] = float(model.alpha_)
        if hasattr(model, "l1_ratio_"):
            payload["l1_ratio"] = float(model.l1_ratio_)
        return payload

    return {}


def build_wide_prediction_frame(
    base_df: pd.DataFrame,
    feature_columns: list[str],
    per_model_predictions: dict[str, np.ndarray],
) -> pd.DataFrame:
    out = base_df[["Date", TARGET_RETURN_COL, TARGET_DIRECTION_COL, *feature_columns]].copy()
    for model_name, predictions in per_model_predictions.items():
        out[f"predicted_future_return__{model_name}"] = predictions
        out[f"predicted_future_direction__{model_name}"] = (predictions > 0.0).astype(float)
        out[f"long_short_strategy_return__{model_name}"] = np.sign(predictions) * out[TARGET_RETURN_COL]
    return out


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    top_n_map = {key: args.top_n_per_family for key in DEFAULT_TOP_N_PER_FAMILY}
    bundle = build_expanded_strategy_space(
        repo_root=REPO_ROOT,
        data_csv=Path(args.data_csv),
        selection_start_date=args.selection_start_date,
        selection_end_date=args.selection_end_date,
        evaluation_start_date=args.evaluation_start_date,
        evaluation_end_date=args.evaluation_end_date,
        target_horizon_days=args.target_horizon_days,
        family_horizons=DEFAULT_FAMILY_HORIZONS,
        top_n_per_family=top_n_map,
    )

    X_selection = bundle.selection_df[bundle.feature_columns].to_numpy(dtype=float)
    y_selection = bundle.selection_df[TARGET_RETURN_COL].to_numpy(dtype=float)
    X_evaluation = bundle.evaluation_df[bundle.feature_columns].to_numpy(dtype=float)

    summary_rows: list[dict] = []
    selection_predictions_by_model: dict[str, np.ndarray] = {}
    evaluation_predictions_by_model: dict[str, np.ndarray] = {}
    model_metadata: dict[str, dict] = {}

    for model_name, model in build_model_specs(len(bundle.selection_df)):
        fitted = model.fit(X_selection, y_selection)
        selection_predictions = fitted.predict(X_selection)
        evaluation_predictions = fitted.predict(X_evaluation)

        selection_pred_df = build_return_prediction_frame(
            bundle.selection_df,
            bundle.feature_columns,
            selection_predictions,
            target_return_column=TARGET_RETURN_COL,
            target_direction_column=TARGET_DIRECTION_COL,
        )
        evaluation_pred_df = build_return_prediction_frame(
            bundle.evaluation_df,
            bundle.feature_columns,
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

        selection_predictions_by_model[model_name] = selection_predictions
        evaluation_predictions_by_model[model_name] = evaluation_predictions
        model_metadata[model_name] = extract_model_metadata(fitted, bundle.feature_columns)

        summary_rows.append(
            {
                "model_name": model_name,
                "selection_mse": selection_summary["mse"],
                "selection_mae": selection_summary["mae"],
                "selection_correlation": selection_summary["correlation"],
                "selection_directional_accuracy": selection_summary["directional_accuracy"],
                "evaluation_mse": evaluation_summary["mse"],
                "evaluation_mae": evaluation_summary["mae"],
                "evaluation_correlation": evaluation_summary["correlation"],
                "evaluation_directional_accuracy": evaluation_summary["directional_accuracy"],
                "nonzero_count": model_metadata[model_name].get("nonzero_count"),
                "alpha": model_metadata[model_name].get("alpha"),
                "l1_ratio": model_metadata[model_name].get("l1_ratio"),
            }
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(
        by=["evaluation_correlation", "selection_correlation"],
        ascending=[False, False],
    )

    summary_csv = maybe_tagged_path(out_dir, "expanded_strategy_model_selection_summary", ".csv", args.tag)
    summary_json = maybe_tagged_path(out_dir, "expanded_strategy_model_selection_summary", ".json", args.tag)
    selection_csv = maybe_tagged_path(out_dir, "expanded_strategy_selection_predictions", ".csv", args.tag)
    evaluation_csv = maybe_tagged_path(out_dir, "expanded_strategy_evaluation_predictions", ".csv", args.tag)

    summary_df.to_csv(summary_csv, index=False)
    build_wide_prediction_frame(bundle.selection_df, bundle.feature_columns, selection_predictions_by_model).to_csv(selection_csv, index=False)
    build_wide_prediction_frame(bundle.evaluation_df, bundle.feature_columns, evaluation_predictions_by_model).to_csv(evaluation_csv, index=False)

    payload = {
        "data_csv": str(Path(args.data_csv)),
        "selection_start_date": args.selection_start_date,
        "selection_end_date": args.selection_end_date,
        "evaluation_start_date": args.evaluation_start_date,
        "evaluation_end_date": args.evaluation_end_date,
        "target_horizon_days": args.target_horizon_days,
        "feature_count": len(bundle.feature_columns),
        "feature_columns": bundle.feature_columns,
        "bases": [
            {
                "strategy_key": basis.strategy_key,
                "horizon_name": basis.horizon_name,
                "rank": basis.rank,
                "score_column": basis.score_column,
                "params": basis.params,
                "total_return": basis.total_return,
                "source_kind": basis.source_kind,
            }
            for basis in bundle.bases
        ],
        "model_details": to_builtin(model_metadata),
        "summary_rows": to_builtin(summary_rows),
    }
    with open(summary_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)

    print("=" * 80)
    print("OBJECTIVE 2 EXPANDED STRATEGY MODEL SELECTION")
    print("=" * 80)
    print(f"TARGET_HORIZON_DAYS: {args.target_horizon_days}")
    print(f"FEATURE_COUNT:       {len(bundle.feature_columns)}")
    print(summary_df.to_string(index=False))
    print(f"[OK] Saved summary CSV:         {summary_csv}")
    print(f"[OK] Saved summary JSON:        {summary_json}")
    print(f"[OK] Saved selection preds CSV: {selection_csv}")
    print(f"[OK] Saved evaluation preds CSV:{evaluation_csv}")


if __name__ == "__main__":
    main()
