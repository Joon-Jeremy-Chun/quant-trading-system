from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from objective2_signal_matrix_builder import (
    build_evaluation_signal_matrix,
    build_selection_signal_matrix,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "objective2_prediction_matrix"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Objective 2 signal-based predictor matrices for selection and evaluation periods."
    )
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


def to_builtin(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: to_builtin(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [to_builtin(item) for item in value]
    return value


def main() -> None:
    args = parse_args()
    data_csv = Path(args.data_csv)
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    selection_df, contexts, selections = build_selection_signal_matrix(
        repo_root=REPO_ROOT,
        data_csv=data_csv,
        selection_start_date=args.selection_start_date,
        selection_end_date=args.selection_end_date,
        target_horizon_days=args.target_horizon_days,
    )
    evaluation_df = build_evaluation_signal_matrix(
        data_csv=data_csv,
        selections=selections,
        contexts=contexts,
        evaluation_start_date=args.evaluation_start_date,
        evaluation_end_date=args.evaluation_end_date,
        target_horizon_days=args.target_horizon_days,
    )

    selection_csv = maybe_tagged_path(out_dir, "selection_signal_matrix", ".csv", args.tag)
    evaluation_csv = maybe_tagged_path(out_dir, "evaluation_signal_matrix", ".csv", args.tag)
    metadata_json = maybe_tagged_path(out_dir, "signal_matrix_metadata", ".json", args.tag)

    selection_df.to_csv(selection_csv, index=False)
    evaluation_df.to_csv(evaluation_csv, index=False)

    metadata = {
        "data_csv": str(data_csv),
        "selection_start_date": args.selection_start_date,
        "selection_end_date": args.selection_end_date,
        "evaluation_start_date": args.evaluation_start_date,
        "evaluation_end_date": args.evaluation_end_date,
        "target_horizon_days": args.target_horizon_days,
        "score_columns": [context.score_column for context in contexts],
        "selected_strategies": [
            {
                "strategy_key": selection.strategy_key,
                "source_kind": selection.source_kind,
                "source_horizon": selection.horizon_name,
                "source_csv": str(selection.source_csv),
                "params": to_builtin(selection.params),
            }
            for selection in selections
        ],
        "score_contexts": [
            {
                "strategy_key": context.strategy_key,
                "score_column": context.score_column,
                "scale_value": context.scale_value,
            }
            for context in contexts
        ],
        "selection_rows": len(selection_df),
        "evaluation_rows": len(evaluation_df),
    }

    with open(metadata_json, "w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2)

    print("=" * 80)
    print("OBJECTIVE 2 PREDICTION MATRIX BUILDER")
    print("=" * 80)
    print(f"DATA_CSV:               {data_csv}")
    print(f"SELECTION_START_DATE:   {args.selection_start_date}")
    print(f"SELECTION_END_DATE:     {args.selection_end_date}")
    print(f"EVALUATION_START_DATE:  {args.evaluation_start_date}")
    print(f"EVALUATION_END_DATE:    {args.evaluation_end_date}")
    print(f"TARGET_HORIZON_DAYS:    {args.target_horizon_days}")
    print(f"SELECTION_MATRIX_SHAPE: {selection_df.shape}")
    print(f"EVALUATION_MATRIX_SHAPE:{evaluation_df.shape}")
    print(f"[OK] Saved selection matrix: {selection_csv}")
    print(f"[OK] Saved evaluation matrix:{evaluation_csv}")
    print(f"[OK] Saved metadata:         {metadata_json}")


if __name__ == "__main__":
    main()
