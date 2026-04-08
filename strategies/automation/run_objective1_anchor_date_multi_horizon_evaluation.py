from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

from cli_utils import horizon_token_to_offset, parse_horizon_tokens


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
STRATEGIES_DIR = REPO_ROOT / "strategies"

STRATEGY_RUN_CONFIGS = [
    {
        "strategy_key": "adaptive_band",
        "script_name": "11_adaptive_band_strategy_multiwindow_optimization.py",
        "output_dir": REPO_ROOT / "outputs" / "11_adaptive_band_strategy_optimization",
    },
    {
        "strategy_key": "ma_crossover",
        "script_name": "21_ma_crossover_multiwindow_optimization.py",
        "output_dir": REPO_ROOT / "outputs" / "21_ma_crossover_optimization",
    },
    {
        "strategy_key": "adaptive_volatility_band",
        "script_name": "31_adaptive_volatility_band_multiwindow_optimization.py",
        "output_dir": REPO_ROOT / "outputs" / "31_adaptive_volatility_band_optimization",
    },
    {
        "strategy_key": "fear_greed_candle_volume",
        "script_name": "41_fear_greed_candle_volume_multiwindow_optimization.py",
        "output_dir": REPO_ROOT / "outputs" / "41_fear_greed_candle_volume_optimization",
    },
]

OBJECTIVE1_WORKER = "run_objective1_weight_search.py"
WORKER_OUTPUT_DIR = REPO_ROOT / "outputs" / "objective1_weight_search"
WORKER_SUMMARY_PATH = WORKER_OUTPUT_DIR / "optimized_weights_summary.json"
MASTER_OUTPUT_DIR = REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Anchor-date Objective 1 runner: refit strategy parameters, learn selection weights, and evaluate across multiple future horizons."
    )
    parser.add_argument("--anchor-date", type=str, default=None, help="Single anchor date (YYYY-MM-DD).")
    parser.add_argument(
        "--anchor-dates",
        type=str,
        default=None,
        help="Comma-separated anchor dates (YYYY-MM-DD,YYYY-MM-DD,...)",
    )
    parser.add_argument("--data-csv", type=str, default=str(REPO_ROOT / "data" / "gld_us_d.csv"), help="Dataset CSV path.")
    parser.add_argument("--strategy-horizons", type=str, default="1m,3m,6m,1y,3y,5y,10y", help="Horizons passed into the 4 optimization scripts.")
    parser.add_argument("--evaluation-horizons", type=str, default="1m,3m,6m,9m,12m", help="Future evaluation horizons to test after the anchor date.")
    parser.add_argument("--selection-window-years", type=int, default=1, help="How many years before the anchor date to use for selection.")
    parser.add_argument("--top-n", type=int, default=10, help="Top-N value passed into optimization scripts.")
    parser.add_argument(
        "--top-n-by-strategy",
        type=str,
        default=None,
        help=(
            "Optional per-strategy Top-N overrides, e.g. "
            "\"adaptive_band=15,ma_crossover=8,adaptive_volatility_band=12,fear_greed_candle_volume=10\"."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    return parser.parse_args()


def resolve_anchor_dates(args: argparse.Namespace) -> list[str]:
    if args.anchor_dates:
        dates = [token.strip() for token in args.anchor_dates.split(",") if token.strip()]
    elif args.anchor_date:
        dates = [args.anchor_date]
    else:
        raise ValueError("You must provide either --anchor-date or --anchor-dates.")

    return dates


def compute_selection_window(anchor_date: str, years: int) -> tuple[str, str]:
    anchor = pd.Timestamp(anchor_date)
    selection_end = anchor
    selection_start = (anchor + pd.Timedelta(days=1)) - pd.DateOffset(years=years)
    return selection_start.strftime("%Y-%m-%d"), selection_end.strftime("%Y-%m-%d")


def compute_evaluation_window(anchor_date: str, horizon_token: str) -> tuple[str, str]:
    anchor = pd.Timestamp(anchor_date)
    evaluation_start = anchor + pd.Timedelta(days=1)
    evaluation_end = evaluation_start + pd.DateOffset(**horizon_token_to_offset(horizon_token)) - pd.Timedelta(days=1)
    return evaluation_start.strftime("%Y-%m-%d"), evaluation_end.strftime("%Y-%m-%d")


def run_command(cmd: list[str], cwd: Path, dry_run: bool) -> None:
    pretty = " ".join(cmd)
    print(f"[RUN] {pretty}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=cwd, check=True)


def load_worker_summary() -> dict:
    if not WORKER_SUMMARY_PATH.exists():
        raise FileNotFoundError(f"Expected worker summary was not found: {WORKER_SUMMARY_PATH}")

    with open(WORKER_SUMMARY_PATH, "r", encoding="utf-8") as fp:
        return json.load(fp)


def parse_top_n_by_strategy(raw_value: str | None, default_top_n: int) -> dict[str, int]:
    top_n_map = {config["strategy_key"]: default_top_n for config in STRATEGY_RUN_CONFIGS}
    if not raw_value:
        return top_n_map

    for token in raw_value.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise ValueError(f"Invalid top-n override token: {token}")
        strategy_key, top_n_text = token.split("=", 1)
        strategy_key = strategy_key.strip()
        top_n_text = top_n_text.strip()
        if strategy_key not in top_n_map:
            valid_keys = ", ".join(top_n_map.keys())
            raise ValueError(f"Unknown strategy key '{strategy_key}'. Valid keys: {valid_keys}")
        top_n_map[strategy_key] = int(top_n_text)

    return top_n_map


def safe_copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def collect_strategy_top_candidates(
    optimization_snapshot_dir: Path,
    anchor_dir: Path,
    top_n_map: dict[str, int],
) -> list[dict]:
    all_rows: list[dict] = []

    for config in STRATEGY_RUN_CONFIGS:
        strategy_key = config["strategy_key"]
        strategy_snapshot_dir = optimization_snapshot_dir / config["output_dir"].name
        if not strategy_snapshot_dir.exists():
            continue

        for horizon_dir in sorted(path for path in strategy_snapshot_dir.iterdir() if path.is_dir()):
            csv_path = horizon_dir / f"{horizon_dir.name}_top10_results.csv"
            if not csv_path.exists():
                continue

            df = pd.read_csv(csv_path)
            if df.empty:
                continue

            trimmed = df.head(top_n_map[strategy_key]).copy()
            trimmed.insert(0, "strategy_key", strategy_key)
            trimmed.insert(1, "horizon_name", horizon_dir.name)
            trimmed.insert(2, "requested_top_n", top_n_map[strategy_key])
            trimmed.insert(3, "source_csv", str(csv_path))
            all_rows.extend(trimmed.to_dict(orient="records"))

    if all_rows:
        pd.DataFrame(all_rows).to_csv(anchor_dir / "strategy_top_candidates.csv", index=False)

    return all_rows


def flatten_summary(anchor_date: str, evaluation_horizon: str, summary: dict) -> dict:
    row = {
        "anchor_date": anchor_date,
        "evaluation_horizon": evaluation_horizon,
        "selection_start_date": summary["selection_start_date"],
        "selection_end_date": summary["selection_end_date"],
        "evaluation_start_date": summary["evaluation_start_date"],
        "evaluation_end_date": summary["evaluation_end_date"],
        "selection_buy_and_hold_return": summary["selection_summary"]["buy_and_hold_return"],
        "selection_optimized_combined_return": summary["selection_summary"]["optimized_combined_return"],
        "evaluation_buy_and_hold_return": summary["evaluation_summary"]["buy_and_hold_return"],
        "evaluation_combined_return": summary["evaluation_summary"]["optimized_combined_return"],
    }

    for idx, weight in enumerate(summary["numerical_best"]["weights"], start=1):
        row[f"w{idx}"] = weight

    for strategy_name, ret in summary["selection_summary"]["standalone_returns"].items():
        row[f"selection_{strategy_name}_return"] = ret
    for strategy_name, ret in summary["evaluation_summary"]["standalone_returns"].items():
        row[f"evaluation_{strategy_name}_return"] = ret

    for selected in summary["selected_strategies"]:
        key = selected["strategy_key"]
        row[f"{key}_source_kind"] = selected["source_kind"]
        row[f"{key}_source_horizon"] = selected["horizon_name"]
        row[f"{key}_source_total_return"] = selected["source_total_return"]
        row[f"{key}_params"] = json.dumps(selected["params"], ensure_ascii=True, sort_keys=True)

    return row


def main() -> None:
    args = parse_args()
    anchor_dates = resolve_anchor_dates(args)
    evaluation_horizons = parse_horizon_tokens(args.evaluation_horizons)
    top_n_by_strategy = parse_top_n_by_strategy(args.top_n_by_strategy, args.top_n)

    MASTER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    master_rows: list[dict] = []

    total_runs = len(anchor_dates) * len(evaluation_horizons)
    run_index = 0

    print("=" * 80)
    print("OBJECTIVE 1 ANCHOR-DATE MULTI-HORIZON EVALUATION START")
    print("=" * 80)
    print(f"ANCHOR_DATES:          {anchor_dates}")
    print(f"DATA_CSV:              {args.data_csv}")
    print(f"STRATEGY_HORIZONS:     {args.strategy_horizons}")
    print(f"SELECTION_WINDOW_YEARS:{args.selection_window_years}")
    print(f"EVALUATION_HORIZONS:   {evaluation_horizons}")
    print(f"TOP_N:                 {args.top_n}")
    print(f"TOP_N_BY_STRATEGY:     {top_n_by_strategy}")
    print(f"DRY_RUN:               {args.dry_run}")
    print("=" * 80)

    for anchor_date in anchor_dates:
        selection_start_date, selection_end_date = compute_selection_window(anchor_date, args.selection_window_years)
        anchor_dir = MASTER_OUTPUT_DIR / f"anchor_{anchor_date}"
        anchor_dir.mkdir(parents=True, exist_ok=True)
        print("\n" + "=" * 80)
        print(f"ANCHOR DATE: {anchor_date}")
        print(f"SELECTION WINDOW: {selection_start_date} -> {selection_end_date}")
        print("=" * 80)

        for config in STRATEGY_RUN_CONFIGS:
            strategy_key = config["strategy_key"]
            cmd = [
                sys.executable,
                config["script_name"],
                "--data-csv",
                args.data_csv,
                "--train-end-date",
                anchor_date,
                "--horizons",
                args.strategy_horizons,
                "--top-n",
                str(top_n_by_strategy[strategy_key]),
            ]
            run_command(cmd, cwd=STRATEGIES_DIR, dry_run=args.dry_run)

        if not args.dry_run:
            optimization_snapshot_dir = anchor_dir / "optimization_outputs"
            optimization_snapshot_dir.mkdir(parents=True, exist_ok=True)
            for config in STRATEGY_RUN_CONFIGS:
                src_dir = config["output_dir"]
                safe_copy_tree(src_dir, optimization_snapshot_dir / src_dir.name)
            collect_strategy_top_candidates(optimization_snapshot_dir, anchor_dir, top_n_by_strategy)

        for horizon_token in evaluation_horizons:
            run_index += 1
            evaluation_start_date, evaluation_end_date = compute_evaluation_window(anchor_date, horizon_token)
            print(
                f"\n[{run_index}/{total_runs}] anchor={anchor_date} | "
                f"evaluation_horizon={horizon_token} | "
                f"evaluation_window={evaluation_start_date} -> {evaluation_end_date}"
            )

            worker_cmd = [
                sys.executable,
                OBJECTIVE1_WORKER,
                "--data-csv",
                args.data_csv,
                "--selection-start-date",
                selection_start_date,
                "--selection-end-date",
                selection_end_date,
                "--evaluation-start-date",
                evaluation_start_date,
                "--evaluation-end-date",
                evaluation_end_date,
            ]
            run_command(worker_cmd, cwd=SCRIPT_DIR, dry_run=args.dry_run)

            if args.dry_run:
                continue

            summary = load_worker_summary()
            row = flatten_summary(anchor_date, horizon_token, summary)
            for strategy_key, top_n in top_n_by_strategy.items():
                row[f"{strategy_key}_requested_top_n"] = top_n
            master_rows.append(row)

            per_run_json = MASTER_OUTPUT_DIR / f"anchor_{anchor_date}_eval_{horizon_token}.json"
            shutil.copyfile(WORKER_SUMMARY_PATH, per_run_json)
            per_run_dir = anchor_dir / f"evaluation_{horizon_token}"
            per_run_dir.mkdir(parents=True, exist_ok=True)
            safe_copy_tree(WORKER_OUTPUT_DIR, per_run_dir / WORKER_OUTPUT_DIR.name)

    if args.dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN COMPLETE")
        print("=" * 80)
        return

    if not master_rows:
        raise RuntimeError("No master rows were collected.")

    master_df = pd.DataFrame(master_rows)
    master_csv = MASTER_OUTPUT_DIR / "master_summary.csv"
    master_json = MASTER_OUTPUT_DIR / "master_summary.json"
    master_df.to_csv(master_csv, index=False)

    with open(master_json, "w", encoding="utf-8") as fp:
        json.dump(master_rows, fp, indent=2)

    print("\n" + "=" * 80)
    print("MASTER SUMMARY SAVED")
    print("=" * 80)
    print(f"[OK] Saved master CSV:  {master_csv}")
    print(f"[OK] Saved master JSON: {master_json}")


if __name__ == "__main__":
    main()
