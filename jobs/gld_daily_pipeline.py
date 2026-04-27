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
        description="Run the daily GLD live pipeline using an existing signal by default."
    )
    parser.add_argument("--symbol", type=str, default="GLD", help="Trading symbol label.")
    parser.add_argument(
        "--build-signal",
        action="store_true",
        help=(
            "Also refresh data and rebuild the Objective 2 live signal locally. "
            "Leave this off on Raspberry Pi when signals are produced elsewhere."
        ),
    )
    parser.add_argument("--target-horizon-days", type=int, default=130, help="Objective 2 target horizon.")
    parser.add_argument(
        "--update-interval-months",
        type=int,
        default=1,
        help="How frequently the active model is refreshed when --build-signal is used.",
    )
    parser.add_argument(
        "--selection-criterion",
        type=str,
        default="selection_cv_mse",
        choices=[
            "selection_correlation",
            "selection_directional_accuracy",
            "selection_long_short_strategy_return",
            "selection_mse",
            "selection_cv_mse",
        ],
        help="Criterion for selecting the active model when --build-signal is used.",
    )
    parser.add_argument(
        "--max-staleness-days",
        type=int,
        default=5,
        help="Refresh local daily data if the dataset is older than this many calendar days when --build-signal is used.",
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


def pull_latest_signal(root: Path) -> dict:
    result = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )
    pulled = result.returncode == 0
    return {
        "name": "git_pull_latest_signal",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "pulled": pulled,
    }


def validate_existing_signal(root: Path, symbol: str) -> dict:
    signal_path = root / "outputs" / "live" / "latest_gld_signal.json"
    if not signal_path.exists():
        raise FileNotFoundError(
            f"Missing live signal file: {signal_path}. "
            "Generate it on the modeling machine and sync/pull it before running the Raspberry Pi pipeline."
        )

    with open(signal_path, "r", encoding="utf-8") as f:
        signal_payload = json.load(f)

    signal_symbol = str(signal_payload.get("symbol", "")).upper()
    if signal_symbol and signal_symbol != symbol.upper():
        raise ValueError(f"Signal symbol mismatch: expected {symbol}, found {signal_symbol}")

    return {
        "name": "validate_existing_live_signal",
        "signal_path": str(signal_path),
        "symbol": signal_payload.get("symbol"),
        "asof_date": signal_payload.get("asof_date"),
        "signal": signal_payload.get("signal"),
        "target_weight": signal_payload.get("target_weight"),
        "active_anchor_date": signal_payload.get("active_anchor_date"),
        "active_model_name": signal_payload.get("active_model_name"),
        "selection_criterion": signal_payload.get("selection_criterion"),
        "dataset_staleness_days": signal_payload.get("dataset_staleness_days"),
        "model_age_days": signal_payload.get("model_age_days"),
    }


def main() -> None:
    args = parse_args()
    py = sys.executable
    outputs_dir = REPO_ROOT / "outputs" / "live"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    pipeline_steps: list[dict] = []

    pull_result = pull_latest_signal(REPO_ROOT)
    pipeline_steps.append(pull_result)
    if not pull_result["pulled"]:
        print(f"[WARN] git pull failed (returncode={pull_result['returncode']}): {pull_result['stderr']}")

    if args.build_signal:
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
    else:
        pipeline_steps.append(validate_existing_signal(REPO_ROOT, args.symbol))

    pipeline_steps.append(
        run_step(
            "submit_or_log_order",
            [py, str(REPO_ROOT / "jobs" / "gld_tranche_order_job.py")],
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
        "build_signal": args.build_signal,
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
    print(f"BUILD_SIGNAL:             {args.build_signal}")
    print(f"[OK] Saved pipeline log:  {out_path}")


if __name__ == "__main__":
    main()
