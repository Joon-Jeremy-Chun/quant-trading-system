from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scipy.optimize import minimize
except ImportError:  # pragma: no cover
    minimize = None

from objective2_signal_matrix_builder import (
    TARGET_DIRECTION_COL,
    TARGET_RETURN_COL,
    StrategyScoreContext,
    build_evaluation_signal_matrix,
    build_selection_signal_matrix,
)
from strategy_matrix_builder import StrategySelection


@dataclass(frozen=True)
class Objective2DataBundle:
    selection_df: pd.DataFrame
    evaluation_df: pd.DataFrame
    feature_columns: list[str]
    contexts: list[StrategyScoreContext]
    selections: list[StrategySelection]
    target_horizon_days: int
    target_return_column: str
    target_direction_column: str


@dataclass(frozen=True)
class LinearRegressionFit:
    intercept: float
    coefficients: np.ndarray


@dataclass(frozen=True)
class LogisticRegressionFit:
    intercept: float
    coefficients: np.ndarray


def load_objective2_data(
    repo_root: Path,
    data_csv: Path,
    selection_start_date: str,
    selection_end_date: str,
    evaluation_start_date: str,
    evaluation_end_date: str,
    target_horizon_days: int = 1,
) -> Objective2DataBundle:
    selection_df, contexts, selections = build_selection_signal_matrix(
        repo_root=repo_root,
        data_csv=data_csv,
        selection_start_date=selection_start_date,
        selection_end_date=selection_end_date,
        target_horizon_days=target_horizon_days,
    )
    evaluation_df = build_evaluation_signal_matrix(
        data_csv=data_csv,
        selections=selections,
        contexts=contexts,
        evaluation_start_date=evaluation_start_date,
        evaluation_end_date=evaluation_end_date,
        target_horizon_days=target_horizon_days,
    )
    feature_columns = [col for col in selection_df.columns if col.endswith("_score")]
    return Objective2DataBundle(
        selection_df=selection_df,
        evaluation_df=evaluation_df,
        feature_columns=feature_columns,
        contexts=contexts,
        selections=selections,
        target_horizon_days=target_horizon_days,
        target_return_column=TARGET_RETURN_COL,
        target_direction_column=TARGET_DIRECTION_COL,
    )


def fit_linear_regression(X: np.ndarray, y: np.ndarray) -> LinearRegressionFit:
    X_aug = np.column_stack([np.ones(len(X)), X])
    beta, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    return LinearRegressionFit(intercept=float(beta[0]), coefficients=beta[1:].astype(float))


def predict_linear_regression(model: LinearRegressionFit, X: np.ndarray) -> np.ndarray:
    return model.intercept + X @ model.coefficients


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -50.0, 50.0)))


def fit_logistic_regression(X: np.ndarray, y: np.ndarray) -> LogisticRegressionFit:
    if minimize is None:
        raise ImportError("scipy is required for logistic regression but is not installed.")

    X_aug = np.column_stack([np.ones(len(X)), X])
    y = y.astype(float)

    def objective(beta: np.ndarray) -> float:
        logits = X_aug @ beta
        probs = sigmoid(logits)
        eps = 1e-12
        return float(-np.mean(y * np.log(probs + eps) + (1.0 - y) * np.log(1.0 - probs + eps)))

    def gradient(beta: np.ndarray) -> np.ndarray:
        probs = sigmoid(X_aug @ beta)
        return (X_aug.T @ (probs - y)) / len(X_aug)

    result = minimize(
        objective,
        x0=np.zeros(X_aug.shape[1], dtype=float),
        jac=gradient,
        method="BFGS",
    )
    if not result.success:
        raise RuntimeError(f"Logistic regression failed: {result.message}")

    beta = result.x
    return LogisticRegressionFit(intercept=float(beta[0]), coefficients=beta[1:].astype(float))


def predict_logistic_probability(model: LogisticRegressionFit, X: np.ndarray) -> np.ndarray:
    logits = model.intercept + X @ model.coefficients
    return sigmoid(logits)


def build_return_prediction_frame(
    df: pd.DataFrame,
    feature_columns: list[str],
    predictions: np.ndarray,
    target_return_column: str = TARGET_RETURN_COL,
    target_direction_column: str = TARGET_DIRECTION_COL,
) -> pd.DataFrame:
    out = df[["Date", target_return_column, target_direction_column, *feature_columns]].copy()
    out["predicted_next_return"] = predictions
    out["predicted_next_direction_from_return"] = (out["predicted_next_return"] > 0.0).astype(float)
    out["long_short_strategy_return"] = np.sign(out["predicted_next_return"]) * out[target_return_column]
    return out


def build_direction_prediction_frame(
    df: pd.DataFrame,
    feature_columns: list[str],
    probabilities: np.ndarray,
    target_return_column: str = TARGET_RETURN_COL,
    target_direction_column: str = TARGET_DIRECTION_COL,
) -> pd.DataFrame:
    out = df[["Date", target_return_column, target_direction_column, *feature_columns]].copy()
    out["predicted_up_probability"] = probabilities
    out["predicted_direction"] = (out["predicted_up_probability"] >= 0.5).astype(float)
    out["long_short_strategy_return"] = np.where(
        out["predicted_direction"] > 0.5,
        out[target_return_column],
        -out[target_return_column],
    )
    return out


def cumulative_return_from_series(x: pd.Series | np.ndarray) -> float:
    arr = np.asarray(x, dtype=float)
    return float(np.prod(1.0 + arr) - 1.0)


def summarize_return_predictions(
    pred_df: pd.DataFrame,
    target_return_column: str = TARGET_RETURN_COL,
    target_direction_column: str = TARGET_DIRECTION_COL,
) -> dict:
    actual = pred_df[target_return_column].to_numpy(dtype=float)
    predicted = pred_df["predicted_next_return"].to_numpy(dtype=float)
    mse = float(np.mean((predicted - actual) ** 2))
    mae = float(np.mean(np.abs(predicted - actual)))
    corr = float(np.corrcoef(predicted, actual)[0, 1]) if len(pred_df) > 1 else float("nan")
    directional_accuracy = float(
        np.mean((pred_df["predicted_next_direction_from_return"] == pred_df[target_direction_column]).astype(float))
    )
    strategy_return = cumulative_return_from_series(pred_df["long_short_strategy_return"])
    return {
        "rows": len(pred_df),
        "mse": mse,
        "mae": mae,
        "correlation": corr,
        "directional_accuracy": directional_accuracy,
        "long_short_strategy_return": strategy_return,
    }


def summarize_direction_predictions(
    pred_df: pd.DataFrame,
    target_direction_column: str = TARGET_DIRECTION_COL,
) -> dict:
    actual = pred_df[target_direction_column].to_numpy(dtype=float)
    predicted = pred_df["predicted_direction"].to_numpy(dtype=float)
    probs = pred_df["predicted_up_probability"].to_numpy(dtype=float)
    accuracy = float(np.mean((predicted == actual).astype(float)))
    eps = 1e-12
    log_loss = float(-np.mean(actual * np.log(probs + eps) + (1.0 - actual) * np.log(1.0 - probs + eps)))
    strategy_return = cumulative_return_from_series(pred_df["long_short_strategy_return"])
    return {
        "rows": len(pred_df),
        "accuracy": accuracy,
        "log_loss": log_loss,
        "long_short_strategy_return": strategy_return,
    }
