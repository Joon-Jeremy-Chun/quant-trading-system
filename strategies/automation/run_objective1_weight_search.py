from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from dataclasses import dataclass

from strategy_matrix_builder import DATE_COL, build_strategy_return_matrix, build_strategy_return_matrix_from_selections
from weight_optimizer import coarse_grid_search, local_grid_search, solve_numerical_optimization


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective1_weight_search"


@dataclass(frozen=True)
class OptimizationBundle:
    label: str
    lower_bound: float
    upper_bound: float
    coarse_results: list
    local_results: list
    coarse_best: object
    local_best: object
    numerical_best: object
    selection_combined_return: float
    evaluation_combined_return: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Objective 1 weight search over the strategy return matrix.")
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument("--selection-start-date", type=str, default="2025-01-01", help="Selection-period start date (YYYY-MM-DD).")
    parser.add_argument("--selection-end-date", type=str, default="2025-12-31", help="Selection-period end date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-start-date", type=str, default="2026-01-01", help="Evaluation-period start date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-end-date", type=str, default="2026-03-31", help="Evaluation-period end date (YYYY-MM-DD).")
    parser.add_argument("--test-start-date", type=str, default=None, help="Deprecated alias for --selection-start-date.")
    parser.add_argument("--test-end-date", type=str, default=None, help="Deprecated alias for --selection-end-date.")
    parser.add_argument("--coarse-step", type=float, default=0.1, help="Grid step for coarse search.")
    parser.add_argument("--local-radius", type=float, default=0.1, help="Search radius around coarse best.")
    parser.add_argument("--local-step", type=float, default=0.02, help="Grid step for local refinement.")
    parser.add_argument("--top-k", type=int, default=10, help="How many top candidates to keep.")
    return parser.parse_args()


def results_to_frame(results: list) -> pd.DataFrame:
    rows = []
    for rank, result in enumerate(results, start=1):
        row = {"rank": rank, "objective_value": result.objective_value}
        for idx, weight in enumerate(result.weights, start=1):
            row[f"w{idx}"] = weight
        rows.append(row)
    return pd.DataFrame(rows)


def to_builtin(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: to_builtin(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [to_builtin(item) for item in value]
    return value


def cumulative_return(daily_returns: np.ndarray) -> float:
    return float(np.prod(1.0 + daily_returns) - 1.0)


def compute_period_buy_hold_return(data_csv: Path, start_date: str, end_date: str) -> float:
    price_df = pd.read_csv(data_csv)
    price_df[DATE_COL] = pd.to_datetime(price_df[DATE_COL])
    price_col = next((col for col in ["Adj Close", "Adj_Close", "Close", "Price"] if col in price_df.columns), None)
    if price_col is None:
        raise ValueError("Could not resolve a price column for buy-and-hold comparison.")
    price_df[price_col] = pd.to_numeric(price_df[price_col], errors="coerce")
    price_df = price_df.dropna(subset=[DATE_COL, price_col]).sort_values(DATE_COL).reset_index(drop=True)
    price_df = price_df[(price_df[DATE_COL] >= pd.to_datetime(start_date)) & (price_df[DATE_COL] <= pd.to_datetime(end_date))].copy()
    return cumulative_return(price_df[price_col].pct_change().fillna(0.0).to_numpy(dtype=float))


def optimize_under_constraints(
    A: np.ndarray,
    evaluation_A: np.ndarray,
    label: str,
    lower_bound: float,
    upper_bound: float,
    coarse_step: float,
    local_radius: float,
    local_step: float,
    top_k: int,
) -> OptimizationBundle:
    coarse_results = coarse_grid_search(
        A,
        step=coarse_step,
        top_k=top_k,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )
    if not coarse_results:
        raise RuntimeError(f"Coarse grid search found no feasible solutions for mode '{label}'.")

    coarse_best = coarse_results[0]
    local_results = local_grid_search(
        A,
        center=coarse_best.weights,
        radius=local_radius,
        step=local_step,
        top_k=top_k,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )
    local_best = local_results[0] if local_results else coarse_best
    numerical_best = solve_numerical_optimization(
        A,
        x0=local_best.weights,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )

    return OptimizationBundle(
        label=label,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        coarse_results=coarse_results,
        local_results=local_results,
        coarse_best=coarse_best,
        local_best=local_best,
        numerical_best=numerical_best,
        selection_combined_return=cumulative_return(A @ numerical_best.weights),
        evaluation_combined_return=cumulative_return(evaluation_A @ numerical_best.weights),
    )


def main() -> None:
    args = parse_args()
    selection_start_date = args.selection_start_date or args.test_start_date
    selection_end_date = args.selection_end_date or args.test_end_date

    if args.test_start_date:
        selection_start_date = args.test_start_date
    if args.test_end_date:
        selection_end_date = args.test_end_date

    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    data_csv = Path(args.data_csv)
    matrix_df, selections = build_strategy_return_matrix(
        repo_root=REPO_ROOT,
        data_csv=data_csv,
        test_start_date=selection_start_date,
        test_end_date=selection_end_date,
    )

    strategy_columns = [col for col in matrix_df.columns if col != DATE_COL]
    A = matrix_df[strategy_columns].to_numpy(dtype=float)
    selection_standalone_returns = {
        column: cumulative_return(matrix_df[column].to_numpy(dtype=float))
        for column in strategy_columns
    }

    print("=" * 80)
    print("OBJECTIVE 1 WEIGHT SEARCH START")
    print("=" * 80)
    print(f"DATA_CSV:        {data_csv}")
    print(f"SELECTION_START_DATE: {selection_start_date}")
    print(f"SELECTION_END_DATE:   {selection_end_date}")
    print(f"EVALUATION_START_DATE:{args.evaluation_start_date}")
    print(f"EVALUATION_END_DATE:  {args.evaluation_end_date}")
    print(f"MATRIX_SHAPE:    {A.shape}")
    print(f"STRATEGIES:      {strategy_columns}")
    print("=" * 80)

    for selection in selections:
        print(
            f"[SELECTED] {selection.strategy_key} | horizon={selection.horizon_name} | "
            f"source={selection.source_kind} | params={to_builtin(selection.params)} | "
            f"source_total_return={selection.total_return:.6f}"
        )

    selection_buy_hold_return = compute_period_buy_hold_return(data_csv, selection_start_date, selection_end_date)

    evaluation_matrix_df = build_strategy_return_matrix_from_selections(
        data_csv=data_csv,
        selections=selections,
        start_date=args.evaluation_start_date,
        end_date=args.evaluation_end_date,
    )
    evaluation_A = evaluation_matrix_df[strategy_columns].to_numpy(dtype=float)
    evaluation_standalone_returns = {
        column: cumulative_return(evaluation_matrix_df[column].to_numpy(dtype=float))
        for column in strategy_columns
    }
    evaluation_buy_hold_return = compute_period_buy_hold_return(data_csv, args.evaluation_start_date, args.evaluation_end_date)

    signed_bundle = optimize_under_constraints(
        A=A,
        evaluation_A=evaluation_A,
        label="signed",
        lower_bound=-1.0,
        upper_bound=1.0,
        coarse_step=args.coarse_step,
        local_radius=args.local_radius,
        local_step=args.local_step,
        top_k=args.top_k,
    )
    long_only_bundle = optimize_under_constraints(
        A=A,
        evaluation_A=evaluation_A,
        label="long_only",
        lower_bound=0.0,
        upper_bound=1.0,
        coarse_step=args.coarse_step,
        local_radius=args.local_radius,
        local_step=args.local_step,
        top_k=args.top_k,
    )

    matrix_path = out_dir / "combined_strategy_return_matrix.csv"
    evaluation_matrix_path = out_dir / "evaluation_strategy_return_matrix.csv"
    coarse_path = out_dir / "coarse_grid_top_candidates.csv"
    local_path = out_dir / "local_grid_top_candidates.csv"
    long_only_coarse_path = out_dir / "long_only_coarse_grid_top_candidates.csv"
    long_only_local_path = out_dir / "long_only_local_grid_top_candidates.csv"
    summary_path = out_dir / "optimized_weights_summary.json"

    matrix_df.to_csv(matrix_path, index=False)
    evaluation_matrix_df.to_csv(evaluation_matrix_path, index=False)
    results_to_frame(signed_bundle.coarse_results).to_csv(coarse_path, index=False)
    results_to_frame(signed_bundle.local_results or [signed_bundle.local_best]).to_csv(local_path, index=False)
    results_to_frame(long_only_bundle.coarse_results).to_csv(long_only_coarse_path, index=False)
    results_to_frame(long_only_bundle.local_results or [long_only_bundle.local_best]).to_csv(long_only_local_path, index=False)

    summary = {
        "data_csv": str(data_csv),
        "selection_start_date": selection_start_date,
        "selection_end_date": selection_end_date,
        "evaluation_start_date": args.evaluation_start_date,
        "evaluation_end_date": args.evaluation_end_date,
        "strategy_columns": strategy_columns,
        "selected_strategies": [
            {
                "strategy_key": selection.strategy_key,
                "horizon_name": selection.horizon_name,
                "source_kind": selection.source_kind,
                "params": to_builtin(selection.params),
                "source_total_return": selection.total_return,
                "source_buy_hold_return": selection.buy_hold_return,
                "source_excess_vs_bh": selection.excess_vs_bh,
                "source_csv": str(selection.source_csv),
            }
            for selection in selections
        ],
        "selection_summary": {
            "buy_and_hold_return": selection_buy_hold_return,
            "standalone_returns": selection_standalone_returns,
            "optimized_combined_return": signed_bundle.selection_combined_return,
            "long_only_combined_return": long_only_bundle.selection_combined_return,
        },
        "evaluation_summary": {
            "buy_and_hold_return": evaluation_buy_hold_return,
            "standalone_returns": evaluation_standalone_returns,
            "optimized_combined_return": signed_bundle.evaluation_combined_return,
            "long_only_combined_return": long_only_bundle.evaluation_combined_return,
        },
        "signed_optimization": {
            "bounds": [signed_bundle.lower_bound, signed_bundle.upper_bound],
            "coarse_best": {
                "weights": signed_bundle.coarse_best.weights.tolist(),
                "objective_value": signed_bundle.coarse_best.objective_value,
            },
            "local_best": {
                "weights": signed_bundle.local_best.weights.tolist(),
                "objective_value": signed_bundle.local_best.objective_value,
            },
            "numerical_best": {
                "weights": signed_bundle.numerical_best.weights.tolist(),
                "objective_value": signed_bundle.numerical_best.objective_value,
            },
        },
        "long_only_optimization": {
            "bounds": [long_only_bundle.lower_bound, long_only_bundle.upper_bound],
            "coarse_best": {
                "weights": long_only_bundle.coarse_best.weights.tolist(),
                "objective_value": long_only_bundle.coarse_best.objective_value,
            },
            "local_best": {
                "weights": long_only_bundle.local_best.weights.tolist(),
                "objective_value": long_only_bundle.local_best.objective_value,
            },
            "numerical_best": {
                "weights": long_only_bundle.numerical_best.weights.tolist(),
                "objective_value": long_only_bundle.numerical_best.objective_value,
            },
        },
    }

    with open(summary_path, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)

    print("\n" + "=" * 80)
    print("SELECTION SUMMARY")
    print("=" * 80)
    print(f"Buy & Hold return:      {selection_buy_hold_return:.6f}")
    for column in strategy_columns:
        print(f"{column} standalone:  {selection_standalone_returns[column]:.6f}")
    print(f"Optimized combined return: {signed_bundle.selection_combined_return:.6f}")
    print(f"Long-only combined return: {long_only_bundle.selection_combined_return:.6f}")
    print("-" * 80)
    print(f"Coarse best weights:    {np.round(signed_bundle.coarse_best.weights, 4)}")
    print(f"Coarse best objective:  {signed_bundle.coarse_best.objective_value:.6f}")
    print(f"Local best weights:     {np.round(signed_bundle.local_best.weights, 4)}")
    print(f"Local best objective:   {signed_bundle.local_best.objective_value:.6f}")
    print(f"Numerical best weights: {np.round(signed_bundle.numerical_best.weights, 4)}")
    print(f"Numerical best objective:{signed_bundle.numerical_best.objective_value:.6f}")
    print("-" * 80)
    print("LONG-ONLY COVERAGE")
    print("-" * 80)
    print(f"Coarse best weights:    {np.round(long_only_bundle.coarse_best.weights, 4)}")
    print(f"Coarse best objective:  {long_only_bundle.coarse_best.objective_value:.6f}")
    print(f"Local best weights:     {np.round(long_only_bundle.local_best.weights, 4)}")
    print(f"Local best objective:   {long_only_bundle.local_best.objective_value:.6f}")
    print(f"Numerical best weights: {np.round(long_only_bundle.numerical_best.weights, 4)}")
    print(f"Numerical best objective:{long_only_bundle.numerical_best.objective_value:.6f}")
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Buy & Hold return:      {evaluation_buy_hold_return:.6f}")
    for column in strategy_columns:
        print(f"{column} standalone:  {evaluation_standalone_returns[column]:.6f}")
    print(f"Selection-weight combined return: {signed_bundle.evaluation_combined_return:.6f}")
    print(f"Long-only combined return:        {long_only_bundle.evaluation_combined_return:.6f}")
    print(f"[OK] Saved matrix:      {matrix_path}")
    print(f"[OK] Saved eval matrix: {evaluation_matrix_path}")
    print(f"[OK] Saved coarse top:  {coarse_path}")
    print(f"[OK] Saved local top:   {local_path}")
    print(f"[OK] Saved long-only coarse top:  {long_only_coarse_path}")
    print(f"[OK] Saved long-only local top:   {long_only_local_path}")
    print(f"[OK] Saved summary:     {summary_path}")


if __name__ == "__main__":
    main()
