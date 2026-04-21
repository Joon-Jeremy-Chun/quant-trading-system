from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from objective2_signal_matrix_builder import clip_series, safe_divide, safe_quantile_scale
from run_objective2_monthly_update_tranche_backtest import (
    build_score_only_df_for_basis,
    build_update_starts,
    load_available_anchor_dates,
    previous_anchor_candidates_for_month,
)
from run_objective2_selected_model_tranche_backtest import (
    build_weight_series,
    maybe_tagged_path,
    simulate_long_only_tranches,
)
from strategy_matrix_builder import DATE_COL, load_price_only_data


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_ANCHOR_ROOT = REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective1_combination_tranche_backtest"

STRATEGY_KEYS = [
    "adaptive_band",
    "ma_crossover",
    "adaptive_volatility_band",
    "fear_greed_candle_volume",
]

EVAL_HORIZON_FOR_HOLD = {
    45: "3m",
    130: "6m",
}


@dataclass
class SimpleBasis:
    strategy_key: str
    params: dict
    score_column: str
    scale_value: float | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baseline B: Objective 1 combination tranche backtest. "
                    "Uses rank1 params + pre-optimized long-only weights per anchor date."
    )
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV))
    parser.add_argument("--anchor-output-root", type=str, default=str(DEFAULT_ANCHOR_ROOT))
    parser.add_argument("--evaluation-start-date", type=str, default="2024-01-01")
    parser.add_argument("--evaluation-end-date", type=str, default="2024-12-31")
    parser.add_argument("--hold-days", type=int, default=130)
    parser.add_argument("--update-interval-months", type=int, default=1)
    parser.add_argument("--scale-quantile", type=float, default=0.95)
    parser.add_argument("--initial-capital", type=float, default=1.0)
    parser.add_argument("--tag", type=str, default=None)
    return parser.parse_args()


def load_anchor_snapshot(anchor_dir: Path, hold_days: int) -> dict:
    """Load the weight summary JSON for the given anchor and hold horizon."""
    horizon = EVAL_HORIZON_FOR_HOLD.get(hold_days, "6m")
    candidates = [
        anchor_dir / f"evaluation_{horizon}" / "objective1_weight_search" / "optimized_weights_summary.json",
        anchor_dir / "evaluation_6m" / "objective1_weight_search" / "optimized_weights_summary.json",
        anchor_dir / "evaluation_3m" / "objective1_weight_search" / "optimized_weights_summary.json",
    ]
    for path in candidates:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"No optimized_weights_summary.json found under {anchor_dir}")


def build_bases_from_snapshot(snapshot: dict) -> list[SimpleBasis]:
    """Build SimpleBasis objects from anchor snapshot selected_strategies."""
    bases = []
    for entry in snapshot["selected_strategies"]:
        key = entry["strategy_key"]
        score_col = f"{key}_rank01_score"
        bases.append(SimpleBasis(
            strategy_key=key,
            params=entry["params"],
            score_column=score_col,
            scale_value=None,
        ))
    return bases


def get_long_only_weights(snapshot: dict) -> np.ndarray:
    """Extract long-only numerical_best weights from snapshot."""
    opt = snapshot.get("long_only_optimization", {})
    weights = opt.get("numerical_best", {}).get("weights", None)
    if weights is None:
        # fallback: equal weight
        weights = [0.25, 0.25, 0.25, 0.25]
    return np.array(weights, dtype=float)


def compute_combined_score(
    *,
    data_csv: Path,
    bases: list[SimpleBasis],
    weights: np.ndarray,
    month_start: str,
    month_end: str,
) -> pd.DataFrame:
    """Compute weighted-average score for each day in [month_start, month_end]."""
    score_dfs = []
    for basis in bases:
        df = build_score_only_df_for_basis(
            data_csv=data_csv,
            basis=basis,
            start_date=month_start,
            end_date=month_end,
        )
        score_dfs.append(df)

    # merge all on Date
    merged = score_dfs[0]
    for df in score_dfs[1:]:
        merged = merged.merge(df, on=DATE_COL, how="inner")

    score_cols = [b.score_column for b in bases]
    score_matrix = merged[score_cols].to_numpy(dtype=float)
    combined = score_matrix @ weights  # weighted sum, shape (n_days,)

    merged["combined_score"] = combined
    return merged[[DATE_COL, "combined_score"] + score_cols].sort_values(DATE_COL).reset_index(drop=True)


def fit_month_combination(
    *,
    data_csv: Path,
    anchor_dir: Path,
    hold_days: int,
    month_start: pd.Timestamp,
    month_end: pd.Timestamp,
    scale_quantile: float,
    anchor_date: pd.Timestamp,
) -> tuple[pd.DataFrame, dict]:
    snapshot = load_anchor_snapshot(anchor_dir, hold_days)
    bases = build_bases_from_snapshot(snapshot)
    weights = get_long_only_weights(snapshot)

    combined_df = compute_combined_score(
        data_csv=data_csv,
        bases=bases,
        weights=weights,
        month_start=month_start.strftime("%Y-%m-%d"),
        month_end=month_end.strftime("%Y-%m-%d"),
    )

    scores = combined_df["combined_score"].to_numpy(dtype=float)
    positive_scores = scores[scores > 0.0]
    scale = safe_quantile_scale(
        pd.Series(positive_scores) if len(positive_scores) > 0 else pd.Series(scores),
        q=scale_quantile,
        fallback=1.0,
    )

    month_df = combined_df.copy()
    month_df["predicted_future_return"] = scores
    month_df["portfolio_weight"] = build_weight_series(scores, scale)
    month_df["active_anchor_date"] = anchor_date.strftime("%Y-%m-%d")
    month_df["active_model_name"] = "obj1_long_only_combination"
    month_df["active_hold_days"] = hold_days
    month_df["prediction_scale"] = scale

    month_metadata = {
        "month_start": month_start.strftime("%Y-%m-%d"),
        "month_end": month_end.strftime("%Y-%m-%d"),
        "active_anchor_date": anchor_date.strftime("%Y-%m-%d"),
        "weights": weights.tolist(),
        "strategy_keys": [b.strategy_key for b in bases],
        "prediction_scale": scale,
    }
    return month_df, month_metadata


def main() -> None:
    args = parse_args()
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    evaluation_start = pd.Timestamp(args.evaluation_start_date)
    evaluation_end = pd.Timestamp(args.evaluation_end_date)
    anchor_output_root = Path(args.anchor_output_root)
    data_csv = Path(args.data_csv)

    available_anchor_dates = load_available_anchor_dates(anchor_output_root)
    update_starts = build_update_starts(evaluation_start, evaluation_end, args.update_interval_months)

    month_frames: list[pd.DataFrame] = []
    month_logs: list[dict] = []

    for update_start in update_starts:
        update_end = min(
            update_start + pd.offsets.MonthBegin(args.update_interval_months) - pd.offsets.Day(1),
            evaluation_end,
        )
        month_df = None
        month_metadata = None
        last_error: Exception | None = None

        for anchor_date in previous_anchor_candidates_for_month(update_start, available_anchor_dates):
            anchor_dir = anchor_output_root / f"anchor_{anchor_date.strftime('%Y-%m-%d')}"
            print(
                f"[PERIODIC UPDATE] period_start={update_start.strftime('%Y-%m-%d')} "
                f"| period_end={update_end.strftime('%Y-%m-%d')} "
                f"| trying anchor={anchor_date.strftime('%Y-%m-%d')}"
            )
            try:
                month_df, month_metadata = fit_month_combination(
                    data_csv=data_csv,
                    anchor_dir=anchor_dir,
                    hold_days=args.hold_days,
                    month_start=update_start,
                    month_end=update_end,
                    scale_quantile=args.scale_quantile,
                    anchor_date=anchor_date,
                )
                break
            except Exception as exc:
                last_error = exc
                continue

        if month_df is None or month_metadata is None:
            raise RuntimeError(
                f"Failed to fit combination model for {update_start.strftime('%Y-%m-%d')}."
            ) from last_error

        month_frames.append(month_df)
        month_logs.append(month_metadata)

    if not month_frames:
        raise ValueError("No monthly frames were generated.")

    signal_df = pd.concat(month_frames, ignore_index=True).sort_values(DATE_COL).reset_index(drop=True)

    price_df = load_price_only_data(data_csv).rename(columns={"Price": "price"})
    signal_df = (
        signal_df.merge(price_df[[DATE_COL, "price"]], on=DATE_COL, how="inner")
        .sort_values(DATE_COL)
        .reset_index(drop=True)
    )

    equity_df, tranche_history = simulate_long_only_tranches(
        signal_df,
        weight_col="portfolio_weight",
        price_col="price",
        hold_days=args.hold_days,
        initial_capital=args.initial_capital,
    )

    first_price = float(equity_df["price"].iloc[0])
    last_price = float(equity_df["price"].iloc[-1])
    buy_hold_return = (last_price / first_price) - 1.0
    final_equity = float(equity_df["net_equity"].iloc[-1])
    strategy_return = final_equity / args.initial_capital - 1.0
    avg_weight = float(signal_df["portfolio_weight"].mean())
    avg_exposure = float((equity_df["gross_exposure"] / equity_df["net_equity"]).mean())

    daily_signal_csv = maybe_tagged_path(out_dir, "obj1_combination_tranche_daily_signals", ".csv", args.tag)
    model_log_csv = maybe_tagged_path(out_dir, "obj1_combination_tranche_model_log", ".csv", args.tag)
    equity_csv = maybe_tagged_path(out_dir, "obj1_combination_tranche_equity_curve", ".csv", args.tag)
    tranche_csv = maybe_tagged_path(out_dir, "obj1_combination_tranche_tranches", ".csv", args.tag)
    summary_json = maybe_tagged_path(out_dir, "obj1_combination_tranche_summary", ".json", args.tag)

    signal_df.to_csv(daily_signal_csv, index=False)
    pd.DataFrame(month_logs).to_csv(model_log_csv, index=False)
    equity_df.to_csv(equity_csv, index=False)
    pd.DataFrame(tranche_history).to_csv(tranche_csv, index=False)

    payload = {
        "approach": "objective1_long_only_combination",
        "evaluation_start_date": args.evaluation_start_date,
        "evaluation_end_date": args.evaluation_end_date,
        "hold_days": args.hold_days,
        "update_interval_months": args.update_interval_months,
        "initial_capital": args.initial_capital,
        "buy_hold_return": buy_hold_return,
        "strategy_return": strategy_return,
        "excess_vs_buy_hold": strategy_return - buy_hold_return,
        "final_equity": final_equity,
        "average_portfolio_weight": avg_weight,
        "average_gross_exposure_fraction": avg_exposure,
        "months_modeled": len(month_logs),
        "monthly_models": month_logs,
    }
    with open(summary_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)

    print("=" * 80)
    print("OBJECTIVE 1 COMBINATION TRANCHE BACKTEST (Baseline B)")
    print("=" * 80)
    print(f"EVALUATION_START_DATE:    {args.evaluation_start_date}")
    print(f"EVALUATION_END_DATE:      {args.evaluation_end_date}")
    print(f"HOLD_DAYS:                {args.hold_days}")
    print(f"UPDATE_INTERVAL_MONTHS:   {args.update_interval_months}")
    print(f"MONTHS_MODELED:           {len(month_logs)}")
    print(f"AVERAGE_WEIGHT:           {avg_weight:.4f}")
    print(f"AVERAGE_GROSS_EXPOSURE:   {avg_exposure:.4f}")
    print("-" * 80)
    print(f"BUY_HOLD_RETURN:          {buy_hold_return:.6f}")
    print(f"STRATEGY_RETURN:          {strategy_return:.6f}")
    print(f"EXCESS_VS_BUY_HOLD:       {strategy_return - buy_hold_return:.6f}")
    print(f"[OK] Saved daily signals: {daily_signal_csv}")
    print(f"[OK] Saved model log:     {model_log_csv}")
    print(f"[OK] Saved equity CSV:    {equity_csv}")
    print(f"[OK] Saved tranche CSV:   {tranche_csv}")
    print(f"[OK] Saved summary JSON:  {summary_json}")


if __name__ == "__main__":
    main()
