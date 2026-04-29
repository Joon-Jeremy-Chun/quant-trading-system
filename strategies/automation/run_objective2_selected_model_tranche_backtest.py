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
from objective2_signal_matrix_builder import safe_quantile_scale
from strategy_matrix_builder import DATE_COL, load_price_only_data


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_selected_model_tranche_backtest"
DEFAULT_FORWARD_SUMMARY = (
    REPO_ROOT
    / "outputs"
    / "objective2_expanded_strategy_forward_validation"
    / "expanded_strategy_forward_validation_summary_forward_2024_to_2025.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a rolling-tranche backtest using a selected Objective 2 linear model."
    )
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Dataset CSV path.")
    parser.add_argument("--anchor-date", type=str, default="2024-12-31", help="Anchor date for optimization snapshot.")
    parser.add_argument("--selection-start-date", type=str, default="2024-01-01", help="Selection feature start date (YYYY-MM-DD).")
    parser.add_argument("--selection-end-date", type=str, default="2024-12-31", help="Selection feature end date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-start-date", type=str, default="2025-01-01", help="Evaluation start date (YYYY-MM-DD).")
    parser.add_argument("--evaluation-end-date", type=str, default="2025-12-31", help="Evaluation end date (YYYY-MM-DD).")
    parser.add_argument("--target-horizon-days", type=int, default=45, help="Selected future target horizon.")
    parser.add_argument("--hold-days", type=int, default=None, help="Holding period for tranche backtest. Defaults to target horizon.")
    parser.add_argument("--top-n-per-family", type=int, default=10, help="Number of top candidates per strategy family.")
    parser.add_argument("--forward-summary-json", type=str, default=str(DEFAULT_FORWARD_SUMMARY), help="Forward-validation summary JSON path.")
    parser.add_argument("--initial-capital", type=float, default=1.0, help="Initial capital.")
    parser.add_argument("--scale-quantile", type=float, default=0.95, help="Quantile used to scale selection predictions into weights.")
    parser.add_argument("--tag", type=str, default=None, help="Optional tag added to output filenames.")
    return parser.parse_args()


def maybe_tagged_path(base_dir: Path, stem: str, suffix: str, tag: str | None) -> Path:
    if tag:
        return base_dir / f"{stem}_{tag}{suffix}"
    return base_dir / f"{stem}{suffix}"


def compute_predictions(df: pd.DataFrame, intercept: float, coeff_pairs: list[list | tuple]) -> np.ndarray:
    pred = np.full(len(df), intercept, dtype=float)
    for score_column, coef in coeff_pairs:
        pred += float(coef) * df[score_column].to_numpy(dtype=float)
    return pred


def build_weight_series(predictions: np.ndarray, scale: float) -> np.ndarray:
    if not np.isfinite(scale) or scale <= 0:
        return (predictions > 0.0).astype(float)
    return np.clip(predictions / scale, 0.0, 1.0)


def simulate_long_only_tranches(
    df: pd.DataFrame,
    weight_col: str,
    price_col: str,
    hold_days: int,
    initial_capital: float,
) -> tuple[pd.DataFrame, list[dict]]:
    slot_cash = np.full(hold_days, initial_capital / hold_days, dtype=float)
    slot_shares = np.zeros(hold_days, dtype=float)
    tranche_history: list[dict] = []
    equity_rows: list[dict] = []

    for i, row in enumerate(df.to_dict(orient="records")):
        date = row[DATE_COL]
        price = float(row[price_col])
        weight = float(row[weight_col])
        signal = float(row["predicted_future_return"])
        slot = i % hold_days

        matured_value = float(slot_cash[slot] + slot_shares[slot] * price)
        tranche_history.append(
            {
                "date": date,
                "slot": slot,
                "signal": signal,
                "weight": weight,
                "recycled_capital": matured_value,
            }
        )

        allocation_value = matured_value * weight
        residual_cash = matured_value - allocation_value
        shares = allocation_value / price if price > 0 else 0.0

        slot_cash[slot] = residual_cash
        slot_shares[slot] = shares

        total_equity = float(slot_cash.sum() + (slot_shares * price).sum())
        gross_exposure = float((slot_shares * price).sum())
        equity_rows.append(
            {
                DATE_COL: date,
                "predicted_future_return": signal,
                "portfolio_weight": weight,
                "price": price,
                "gross_exposure": gross_exposure,
                "net_equity": total_equity,
            }
        )

    return pd.DataFrame(equity_rows), tranche_history


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    hold_days = int(args.hold_days) if args.hold_days is not None else int(args.target_horizon_days)
    if hold_days < 1:
        raise ValueError("hold_days must be at least 1.")

    summary_path = Path(args.forward_summary_json)
    if not summary_path.exists():
        raise FileNotFoundError(f"Forward summary JSON not found: {summary_path}")

    summary_obj = json.loads(summary_path.read_text(encoding="utf-8"))
    selected_row = next(
        (row for row in summary_obj["selected_models_by_horizon"] if int(row["target_horizon_days"]) == int(args.target_horizon_days)),
        None,
    )
    if selected_row is None:
        raise ValueError(f"Target horizon {args.target_horizon_days} not found in forward summary.")

    model_name = selected_row["model_name"]
    model_metadata = selected_row["best_model_metadata"]
    coeff_pairs = model_metadata.get("nonzero_coefficients") or model_metadata.get("nonzero_coefficients_scaled_space") or []
    intercept = float(model_metadata["intercept"])

    snapshot_root = (
        REPO_ROOT
        / "outputs"
        / "objective1_anchor_date_multi_horizon_evaluation"
        / f"anchor_{args.anchor_date}"
        / "optimization_outputs"
    )

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
        family_output_root=snapshot_root,
    )

    selection_predictions = compute_predictions(bundle.selection_df, intercept, coeff_pairs)
    evaluation_predictions = compute_predictions(bundle.evaluation_df, intercept, coeff_pairs)

    positive_selection_predictions = pd.Series(selection_predictions)[pd.Series(selection_predictions) > 0.0]
    scale = safe_quantile_scale(
        positive_selection_predictions if not positive_selection_predictions.empty else pd.Series(selection_predictions),
        q=args.scale_quantile,
        fallback=1.0,
    )

    eval_df = bundle.evaluation_df[[DATE_COL]].copy()
    eval_df["predicted_future_return"] = evaluation_predictions
    eval_df["portfolio_weight"] = build_weight_series(evaluation_predictions, scale)

    price_df = load_price_only_data(Path(args.data_csv)).rename(columns={"Price": "price"})
    eval_df = eval_df.merge(price_df[[DATE_COL, "price"]], on=DATE_COL, how="inner").sort_values(DATE_COL).reset_index(drop=True)

    equity_df, tranche_history = simulate_long_only_tranches(
        eval_df,
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
    avg_weight = float(equity_df["portfolio_weight"].mean())
    avg_exposure = float((equity_df["gross_exposure"] / equity_df["net_equity"]).mean())

    equity_csv = maybe_tagged_path(out_dir, "selected_model_tranche_backtest_equity_curve", ".csv", args.tag)
    tranches_csv = maybe_tagged_path(out_dir, "selected_model_tranche_backtest_tranches", ".csv", args.tag)
    summary_json = maybe_tagged_path(out_dir, "selected_model_tranche_backtest_summary", ".json", args.tag)

    equity_df.to_csv(equity_csv, index=False)
    pd.DataFrame(tranche_history).to_csv(tranches_csv, index=False)

    payload = {
        "anchor_date": args.anchor_date,
        "target_horizon_days": args.target_horizon_days,
        "hold_days": hold_days,
        "model_name": model_name,
        "selection_start_date": args.selection_start_date,
        "selection_end_date": args.selection_end_date,
        "evaluation_start_date": args.evaluation_start_date,
        "evaluation_end_date": args.evaluation_end_date,
        "initial_capital": initial_capital,
        "scale_quantile": args.scale_quantile,
        "prediction_scale": scale,
        "buy_hold_return": buy_hold_return,
        "strategy_return": strategy_return,
        "excess_vs_buy_hold": strategy_return - buy_hold_return,
        "final_equity": final_equity,
        "average_portfolio_weight": avg_weight,
        "average_gross_exposure_fraction": avg_exposure,
        "nonzero_count": selected_row.get("nonzero_count"),
        "selection_correlation": selected_row.get("selection_correlation"),
        "evaluation_correlation": selected_row.get("evaluation_correlation"),
        "evaluation_directional_accuracy": selected_row.get("evaluation_directional_accuracy"),
        "top_abs_coefficients": sorted(coeff_pairs, key=lambda x: abs(float(x[1])), reverse=True)[:20],
    }
    with open(summary_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)

    print("=" * 80)
    print("OBJECTIVE 2 SELECTED MODEL TRANCHE BACKTEST")
    print("=" * 80)
    print(f"TARGET_HORIZON_DAYS:     {args.target_horizon_days}")
    print(f"HOLD_DAYS:               {hold_days}")
    print(f"MODEL_NAME:              {model_name}")
    print(f"PREDICTION_SCALE:        {scale:.6f}")
    print(f"AVERAGE_WEIGHT:          {avg_weight:.4f}")
    print(f"AVERAGE_GROSS_EXPOSURE:  {avg_exposure:.4f}")
    print("-" * 80)
    print(f"BUY_HOLD_RETURN:         {buy_hold_return:.6f}")
    print(f"STRATEGY_RETURN:         {strategy_return:.6f}")
    print(f"EXCESS_VS_BUY_HOLD:      {strategy_return - buy_hold_return:.6f}")
    print(f"[OK] Saved equity CSV:   {equity_csv}")
    print(f"[OK] Saved tranches CSV: {tranches_csv}")
    print(f"[OK] Saved summary JSON: {summary_json}")


if __name__ == "__main__":
    main()
