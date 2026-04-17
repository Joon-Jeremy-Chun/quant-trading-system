from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the daily GLD live pipeline: data update -> signal build -> order job."
    )
    parser.add_argument("--symbol", type=str, default="GLD", help="Trading symbol label.")
    parser.add_argument("--target-horizon-days", type=int, default=130, help="Objective 2 target horizon.")
    parser.add_argument(
        "--update-interval-months",
        type=int,
        default=1,
        help="How frequently the active model is refreshed.",
    )
    parser.add_argument(
        "--selection-criterion",
        type=str,
        default="selection_correlation",
        choices=[
            "selection_correlation",
            "selection_directional_accuracy",
            "selection_long_short_strategy_return",
            "selection_mse",
        ],
        help="Criterion for selecting the active model.",
    )
    parser.add_argument(
        "--max-staleness-days",
        type=int,
        default=5,
        help="Refresh local daily data if the dataset is older than this many calendar days.",
    )
    parser.add_argument(
        "--top-n-per-family",
        type=int,
        default=10,
        help="Number of top candidates used from each strategy family.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Optional tag used for pipeline outputs and signal history.",
    )
    return parser.parse_args()


def run_step(name: str, cmd: list[str], cwd: Path) -> dict:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    payload = {
        "name": name,
        "command": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if result.returncode != 0:
        raise RuntimeError(
            f"Step '{name}' failed with exit code {result.returncode}.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return payload


def main() -> None:
    args = parse_args()
    py = sys.executable
    outputs_dir = REPO_ROOT / "outputs" / "live"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    pipeline_steps: list[dict] = []

    pipeline_steps.append(
        run_step(
            "update_gld_daily_data",
            [
                py,
                str(REPO_ROOT / "jobs" / "update_gld_daily_data.py"),
                "--max-staleness-days",
                str(args.max_staleness_days),
                "--symbol",
                args.symbol,
            ],
            REPO_ROOT,
        )
    )

    signal_cmd = [
        py,
        str(REPO_ROOT / "strategies" / "automation" / "run_objective2_latest_live_signal.py"),
        "--target-horizon-days",
        str(args.target_horizon_days),
        "--update-interval-months",
        str(args.update_interval_months),
        "--selection-criterion",
        args.selection_criterion,
        "--top-n-per-family",
        str(args.top_n_per_family),
        "--symbol",
        args.symbol,
    ]
    if args.tag:
        signal_cmd.extend(["--tag", args.tag])

    pipeline_steps.append(run_step("build_latest_live_signal", signal_cmd, REPO_ROOT))

    pipeline_steps.append(
        run_step(
            "submit_or_log_order",
            [py, str(REPO_ROOT / "jobs" / "gld_close_order_job.py")],
            REPO_ROOT,
        )
    )

    pipeline_steps.append(
        run_step(
            "send_email_alert",
            [py, str(REPO_ROOT / "jobs" / "send_gld_email_alert.py"), "--symbol", args.symbol],
            REPO_ROOT,
        )
    )

    summary = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "target_horizon_days": args.target_horizon_days,
        "update_interval_months": args.update_interval_months,
        "selection_criterion": args.selection_criterion,
        "max_staleness_days": args.max_staleness_days,
        "top_n_per_family": args.top_n_per_family,
        "steps": pipeline_steps,
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"_{args.tag}" if args.tag else ""
    out_path = outputs_dir / f"gld_daily_pipeline_{timestamp}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("=" * 80)
    print("GLD DAILY PIPELINE")
    print("=" * 80)
    print(f"SYMBOL:                   {args.symbol}")
    print(f"TARGET_HORIZON_DAYS:      {args.target_horizon_days}")
    print(f"UPDATE_INTERVAL_MONTHS:   {args.update_interval_months}")
    print(f"SELECTION_CRITERION:      {args.selection_criterion}")
    print(f"[OK] Saved pipeline log:  {out_path}")


if __name__ == "__main__":
    main()
