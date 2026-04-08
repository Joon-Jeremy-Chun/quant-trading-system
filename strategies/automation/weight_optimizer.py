from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable

import numpy as np

try:
    from scipy.optimize import minimize
except ImportError:  # pragma: no cover
    minimize = None


@dataclass(frozen=True)
class WeightSearchResult:
    weights: np.ndarray
    objective_value: float


def evaluate_log_cum_return(A: np.ndarray, x: np.ndarray) -> float:
    daily_returns = A @ x
    if np.any(1.0 + daily_returns <= 0.0):
        return -np.inf
    return float(np.sum(np.log1p(daily_returns)))


def generate_feasible_weights(step: float, n_assets: int) -> Iterable[np.ndarray]:
    if n_assets < 2:
        raise ValueError("n_assets must be at least 2")

    grid = np.arange(-1.0, 1.0 + step / 2.0, step)
    for partial in product(grid, repeat=n_assets - 1):
        last_weight = 1.0 - float(np.sum(partial))
        if -1.0 <= last_weight <= 1.0:
            yield np.array([*partial, last_weight], dtype=float)


def coarse_grid_search(A: np.ndarray, step: float = 0.1, top_k: int = 10) -> list[WeightSearchResult]:
    results: list[WeightSearchResult] = []
    n_assets = A.shape[1]

    for weights in generate_feasible_weights(step=step, n_assets=n_assets):
        objective = evaluate_log_cum_return(A, weights)
        if np.isfinite(objective):
            results.append(WeightSearchResult(weights=weights, objective_value=objective))

    results.sort(key=lambda item: item.objective_value, reverse=True)
    return results[:top_k]


def local_grid_search(
    A: np.ndarray,
    center: np.ndarray,
    radius: float = 0.1,
    step: float = 0.02,
    top_k: int = 10,
) -> list[WeightSearchResult]:
    n_assets = A.shape[1]
    grids = []
    for value in center[:-1]:
        low = max(-1.0, value - radius)
        high = min(1.0, value + radius)
        grids.append(np.arange(low, high + step / 2.0, step))

    results: list[WeightSearchResult] = []
    for partial in product(*grids):
        last_weight = 1.0 - float(np.sum(partial))
        if not (-1.0 <= last_weight <= 1.0):
            continue
        weights = np.array([*partial, last_weight], dtype=float)
        objective = evaluate_log_cum_return(A, weights)
        if np.isfinite(objective):
            results.append(WeightSearchResult(weights=weights, objective_value=objective))

    results.sort(key=lambda item: item.objective_value, reverse=True)
    return results[:top_k]


def solve_numerical_optimization(A: np.ndarray, x0: np.ndarray) -> WeightSearchResult:
    if minimize is None:
        raise ImportError("scipy is required for numerical optimization but is not installed.")

    def objective(weights: np.ndarray) -> float:
        return -evaluate_log_cum_return(A, weights)

    constraints = [{"type": "eq", "fun": lambda weights: np.sum(weights) - 1.0}]
    bounds = [(-1.0, 1.0)] * A.shape[1]

    result = minimize(
        objective,
        x0=x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not result.success:
        raise RuntimeError(f"Numerical optimization failed: {result.message}")

    return WeightSearchResult(weights=result.x, objective_value=-float(result.fun))
