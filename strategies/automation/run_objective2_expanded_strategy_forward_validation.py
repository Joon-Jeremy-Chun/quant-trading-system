from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import ElasticNetCV, LassoCV, LinearRegression, RidgeCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from objective2_expanded_strategy_space import (
    DEFAULT_FAMILY_HORIZONS,
    DEFAULT_TOP_N_PER_FAMILY,
    build_expanded_strategy_space,
)
from objective2_modeling import build_return_prediction_frame, summarize_return_predictions
from objective2_signal_matrix_builder import TARGET_DIRECTION_COL, TARGET_RETURN_COL


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_expanded_strategy_forward_validation"
DEFAULT_ANCHOR_DATE = "2024-12-31"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select expanded-strategy models on one period and validate them on a future period."
    )
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument("--anchor-date", type=str, default=DEFAULT_ANCHOR_DATE, help="Anchor date used to locate optimization snapshots.")
    parser.add_argument("--selection-start-date", type=str, default="2024-01-01", help="Selection feature start date (YYYY-MM-DD).")
    parser.add_argument("--selection-end-date", type=str, default="2024-12-31", help="Selection feature end date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-start-date", type=str, default="2025-01-01", help="Evaluation feature start date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-end-date", type=str, default="2025-12-31", help="Evaluation feature end date (YYYY-MM-DD).")
    parser.add_argument("--min-horizon-days", type=int, default=1, help="Minimum future target horizon in trading days.")
    parser.add_argument("--max-horizon-days", type=int, default=130, help="Maximum future target horizon in trading days.")
    parser.add_argument("--top-n-per-family", type=int, default=10, help="Number of top candidates to use from each strategy family.")
    parser.add_argument(
        "--selection-criterion",
        type=str,
        default="selection_correlation",
        choices=[
            "selection_correlation",
            "selection_directional_accuracy",
            "selection_long_short_strategy_return",
            "selection_mse",
            "selection_aic",
            "selection_bic",
            "selection_cv_mse",
        ],
        help="Criterion used to select the best model inside each target horizon.",
    )
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
    specs: list[tuple[str, object]] = [("ols", LinearRegression())]
    if n_selection_rows < 4:
        return specs

    n_splits = min(5, max(2, min(n_selection_rows - 1, n_selection_rows // 40 if n_selection_rows // 40 >= 2 else 2)))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    alphas = np.logspace(-4, 1, 30)

    specs.extend([
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
    ])
    return specs


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


def compute_aic_bic(y_true: np.ndarray, y_pred: np.ndarray, parameter_count: int) -> tuple[float, float]:
    n = len(y_true)
    if n <= 0:
        return float("nan"), float("nan")
    rss = float(np.square(y_true - y_pred).sum())
    rss = max(rss, np.finfo(float).tiny)
    aic = n * np.log(rss / n) + 2.0 * parameter_count
    bic = n * np.log(rss / n) + np.log(n) * parameter_count
    return float(aic), float(bic)


def compute_time_series_cv_mse(model: object, X: np.ndarray, y: np.ndarray, n_splits: int) -> float:
    if len(y) < 4:
        return float("nan")
    splitter = TimeSeriesSplit(n_splits=n_splits)
    errors: list[float] = []
    for train_idx, valid_idx in splitter.split(X):
        fitted = clone(model)
        fitted.fit(X[train_idx], y[train_idx])
        pred = fitted.predict(X[valid_idx])
        mse = float(np.mean(np.square(y[valid_idx] - pred)))
        errors.append(mse)
    if not errors:
        return float("nan")
    return float(np.mean(errors))


def pick_selected_row(horizon_rows: list[dict], criterion: str) -> dict:
    if criterion == "selection_correlation":
        return max(
            horizon_rows,
            key=lambda row: (
                float(row["selection_correlation"]),
                float(row["selection_directional_accuracy"]),
                -float(row["selection_mse"]),
            ),
        )
    if criterion == "selection_directional_accuracy":
        return max(
            horizon_rows,
            key=lambda row: (
                float(row["selection_directional_accuracy"]),
                float(row["selection_correlation"]),
                -float(row["selection_mse"]),
            ),
        )
    if criterion == "selection_long_short_strategy_return":
        return max(
            horizon_rows,
            key=lambda row: (
                float(row["selection_long_short_strategy_return"]),
                float(row["selection_correlation"]),
            ),
        )
    if criterion == "selection_mse":
        return min(
            horizon_rows,
            key=lambda row: (
                float(row["selection_mse"]),
                -float(row["selection_correlation"]),
            ),
        )
    if criterion == "selection_aic":
        return min(
            horizon_rows,
            key=lambda row: (
                float(row["selection_aic"]),
                float(row["selection_mse"]),
            ),
        )
    if criterion == "selection_bic":
        return min(
            horizon_rows,
            key=lambda row: (
                float(row["selection_bic"]),
                float(row["selection_mse"]),
            ),
        )
    if criterion == "selection_cv_mse":
        return min(
            horizon_rows,
            key=lambda row: (
                float(row["selection_cv_mse"]),
                float(row["selection_mse"]),
            ),
        )
    raise ValueError(f"Unsupported selection criterion: {criterion}")


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_root = (
        REPO_ROOT
        / "outputs"
        / "objective1_anchor_date_multi_horizon_evaluation"
        / f"anchor_{args.anchor_date}"
        / "optimization_outputs"
    )
    if not snapshot_root.exists():
        raise FileNotFoundError(f"Anchor optimization snapshot not found: {snapshot_root}")

    top_n_map = {key: args.top_n_per_family for key in DEFAULT_TOP_N_PER_FAMILY}

    all_rows: list[dict] = []
    selected_rows: list[dict] = []
    selected_payloads: list[dict] = []

    for horizon_days in range(args.min_horizon_days, args.max_horizon_days + 1):
        print(f"[FORWARD] horizon={horizon_days}")
        bundle = build_expanded_strategy_space(
            repo_root=REPO_ROOT,
            data_csv=Path(args.data_csv),
            selection_start_date=args.selection_start_date,
            selection_end_date=args.selection_end_date,
            evaluation_start_date=args.evaluation_start_date,
            evaluation_end_date=args.evaluation_end_date,
            target_horizon_days=horizon_days,
            family_horizons=DEFAULT_FAMILY_HORIZONS,
            top_n_per_family=top_n_map,
            family_output_root=snapshot_root,
        )

        X_selection = bundle.selection_df[bundle.feature_columns].to_numpy(dtype=float)
        y_selection = bundle.selection_df[TARGET_RETURN_COL].to_numpy(dtype=float)
        X_evaluation = bundle.evaluation_df[bundle.feature_columns].to_numpy(dtype=float)
        cv_n_splits = max(3, min(5, max(3, len(bundle.selection_df) // 40)))

        horizon_rows: list[dict] = []
        horizon_model_metadata: dict[str, dict] = {}

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

            model_metadata = extract_model_metadata(fitted, bundle.feature_columns)
            horizon_model_metadata[model_name] = model_metadata
            parameter_count = int(model_metadata.get("nonzero_count", len(bundle.feature_columns))) + 1
            selection_aic, selection_bic = compute_aic_bic(y_selection, selection_predictions, parameter_count)
            selection_cv_mse = (
                compute_time_series_cv_mse(model, X_selection, y_selection, cv_n_splits)
                if args.selection_criterion == "selection_cv_mse"
                else float("nan")
            )

            row = {
                "target_horizon_days": horizon_days,
                "model_name": model_name,
                "feature_count": len(bundle.feature_columns),
                "selection_rows": len(bundle.selection_df),
                "evaluation_rows": len(bundle.evaluation_df),
                "selection_mse": selection_summary["mse"],
                "selection_mae": selection_summary["mae"],
                "selection_correlation": selection_summary["correlation"],
                "selection_directional_accuracy": selection_summary["directional_accuracy"],
                "selection_long_short_strategy_return": selection_summary["long_short_strategy_return"],
                "selection_aic": selection_aic,
                "selection_bic": selection_bic,
                "selection_cv_mse": selection_cv_mse,
                "evaluation_mse": evaluation_summary["mse"],
                "evaluation_mae": evaluation_summary["mae"],
                "evaluation_correlation": evaluation_summary["correlation"],
                "evaluation_directional_accuracy": evaluation_summary["directional_accuracy"],
                "evaluation_long_short_strategy_return": evaluation_summary["long_short_strategy_return"],
                "nonzero_count": model_metadata.get("nonzero_count"),
                "alpha": model_metadata.get("alpha"),
                "l1_ratio": model_metadata.get("l1_ratio"),
            }
            horizon_rows.append(row)
            all_rows.append(row)

        selected = pick_selected_row(horizon_rows, args.selection_criterion)
        selected_rows.append(selected)
        selected_payloads.append(
            {
                **selected,
                "best_model_metadata": horizon_model_metadata[selected["model_name"]],
                "basis_summary": [
                    {
                        "score_column": basis.score_column,
                        "strategy_key": basis.strategy_key,
                        "horizon_name": basis.horizon_name,
                        "rank": basis.rank,
                        "params": basis.params,
                    }
                    for basis in bundle.bases
                ],
            }
        )

    all_models_df = pd.DataFrame(all_rows).sort_values(
        by=[args.selection_criterion, "evaluation_correlation"],
        ascending=[args.selection_criterion in {"selection_mse", "selection_aic", "selection_bic", "selection_cv_mse"}, False],
    ).reset_index(drop=True)

    selected_df = pd.DataFrame(selected_rows).sort_values(
        by=[args.selection_criterion, "evaluation_correlation"],
        ascending=[args.selection_criterion in {"selection_mse", "selection_aic", "selection_bic", "selection_cv_mse"}, False],
    ).reset_index(drop=True)

    all_models_csv = maybe_tagged_path(out_dir, "expanded_strategy_forward_validation_all_models", ".csv", args.tag)
    selected_csv = maybe_tagged_path(out_dir, "expanded_strategy_forward_validation_selected_models", ".csv", args.tag)
    summary_json = maybe_tagged_path(out_dir, "expanded_strategy_forward_validation_summary", ".json", args.tag)

    all_models_df.to_csv(all_models_csv, index=False)
    selected_df.to_csv(selected_csv, index=False)

    payload = {
        "data_csv": str(Path(args.data_csv)),
        "anchor_date": args.anchor_date,
        "snapshot_root": str(snapshot_root),
        "selection_start_date": args.selection_start_date,
        "selection_end_date": args.selection_end_date,
        "evaluation_start_date": args.evaluation_start_date,
        "evaluation_end_date": args.evaluation_end_date,
        "min_horizon_days": args.min_horizon_days,
        "max_horizon_days": args.max_horizon_days,
        "top_n_per_family": args.top_n_per_family,
        "selection_rule": args.selection_criterion,
        "selected_models_by_horizon": to_builtin(selected_payloads),
        "top_rows_all_models": to_builtin(all_models_df.head(50).to_dict(orient="records")),
    }
    with open(summary_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)

    print("=" * 80)
    print("OBJECTIVE 2 EXPANDED STRATEGY FORWARD VALIDATION")
    print("=" * 80)
    print(f"ANCHOR_DATE:         {args.anchor_date}")
    print(f"SELECTION_RULE:      {args.selection_criterion}")
    print("[TOP 15 SELECTED HORIZONS BY SELECTION SCORE]")
    print(selected_df.head(15).to_string(index=False))
    print("-" * 80)
    print("[TOP 15 ALL MODEL/HORIZON ROWS BY SELECTION SCORE]")
    print(all_models_df.head(15).to_string(index=False))
    print(f"[OK] Saved all-models CSV:  {all_models_csv}")
    print(f"[OK] Saved selected CSV:    {selected_csv}")
    print(f"[OK] Saved summary JSON:    {summary_json}")


if __name__ == "__main__":
    main()
