"""
Generic multi-asset research pipeline runner.

Usage examples:
  # 1. Fetch data for a new asset
  python scripts/run_asset.py --asset brkb --step fetch

  # 2. Run anchor parameter optimization (heavy, run once per month)
  python scripts/run_asset.py --asset brkb --step optimize --anchor-dates 2024-12-31,2025-03-31

  # 3. Generate latest live signal
  python scripts/run_asset.py --asset brkb --step signal

  # 4. Run full backtest (Stage C)
  python scripts/run_asset.py --asset brkb --step backtest --tag 2024

  # Run all steps in sequence
  python scripts/run_asset.py --asset brkb --step all --anchor-dates 2024-12-31
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO_ROOT / "assets"
AUTOMATION_DIR = REPO_ROOT / "strategies" / "automation"
JOBS_DIR = REPO_ROOT / "jobs"
PY = sys.executable

STEPS = ["fetch", "optimize", "signal", "backtest", "all"]


def load_config(asset: str) -> dict:
    config_path = ASSETS_DIR / asset / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            f"Available assets: {[d.name for d in ASSETS_DIR.iterdir() if d.is_dir()]}"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_path(cfg_value: str) -> str:
    return str(REPO_ROOT / cfg_value)


def run(name: str, cmd: list[str]) -> None:
    print(f"\n{'='*70}")
    print(f"STEP: {name}")
    print(f"CMD:  {' '.join(cmd)}")
    print(f"{'='*70}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        print(f"\n[FAIL] Step '{name}' exited with code {result.returncode}")
        sys.exit(result.returncode)
    print(f"[OK] {name} completed.")


def step_fetch(asset: str, cfg: dict) -> None:
    data_csv = Path(resolve_path(cfg["data_csv"]))
    if not data_csv.exists():
        # First-time: full historical download
        run("init_data", [
            PY, str(REPO_ROOT / "scripts" / "init_asset_data.py"),
            "--asset", asset,
        ])
    else:
        # Incremental update
        run("update_data", [
            PY, str(JOBS_DIR / "update_gld_daily_data.py"),
            "--symbol", cfg["symbol"],
            "--data-csv", str(data_csv),
        ])


def step_optimize(cfg: dict, anchor_dates: str, reuse: bool) -> None:
    cmd = [
        PY, str(AUTOMATION_DIR / "run_objective1_anchor_date_multi_horizon_evaluation.py"),
        "--data-csv", resolve_path(cfg["data_csv"]),
        "--anchor-dates", anchor_dates,
        "--strategy-horizons", cfg.get("strategy_horizons", "1m,3m,6m,1y,3y,5y,10y"),
        "--evaluation-horizons", cfg.get("evaluation_horizons", "1m,3m,6m,9m,12m"),
        "--selection-window-years", str(cfg.get("selection_window_years", 1)),
        "--top-n", str(cfg.get("top_n_per_family", 10)),
    ]
    # redirect anchor output root via env override is not needed —
    # the script uses its own default but we patch via symlink or copy approach.
    # For now we pass a note: anchor output is per-script default.
    # TODO: add --anchor-output-root to run_objective1_anchor_date_multi_horizon_evaluation.py
    if reuse:
        cmd.append("--reuse-existing-optimization-snapshots")
    run("anchor_optimization", cmd)


def step_signal(cfg: dict) -> None:
    run("generate_signal", [
        PY, str(AUTOMATION_DIR / "run_objective2_latest_live_signal.py"),
        "--symbol", cfg["symbol"],
        "--data-csv", resolve_path(cfg["data_csv"]),
        "--anchor-output-root", resolve_path(cfg["anchor_output_root"]),
        "--target-horizon-days", str(cfg.get("target_horizon_days", 130)),
        "--update-interval-months", str(cfg.get("update_interval_months", 1)),
        "--selection-criterion", cfg.get("selection_criterion", "selection_cv_mse"),
        "--top-n-per-family", str(cfg.get("top_n_per_family", 10)),
    ])


def step_backtest(cfg: dict, tag: str | None) -> None:
    cmd = [
        PY, str(AUTOMATION_DIR / "run_objective2_monthly_update_tranche_backtest.py"),
        "--data-csv", resolve_path(cfg["data_csv"]),
        "--anchor-output-root", resolve_path(cfg["anchor_output_root"]),
        "--target-horizon-days", str(cfg.get("target_horizon_days", 130)),
        "--update-interval-months", str(cfg.get("update_interval_months", 1)),
    ]
    if tag:
        cmd.extend(["--tag", tag])
    run("backtest", cmd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generic multi-asset research pipeline runner.")
    parser.add_argument("--asset", required=True, help="Asset name (folder under assets/). e.g. gld, brkb, rklb")
    parser.add_argument("--step", required=True, choices=STEPS, help="Pipeline step to run.")
    parser.add_argument("--anchor-dates", type=str, default=None, help="Comma-separated anchor dates for optimize step.")
    parser.add_argument("--reuse", action="store_true", help="Reuse existing optimization snapshots.")
    parser.add_argument("--tag", type=str, default=None, help="Output tag for backtest step.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.asset)

    print(f"\n{'='*70}")
    print(f"ASSET PIPELINE RUNNER")
    print(f"{'='*70}")
    print(f"ASSET:  {args.asset}  ({cfg['symbol']})")
    print(f"STEP:   {args.step}")
    print(f"CONFIG: {ASSETS_DIR / args.asset / 'config.yaml'}")

    if args.step == "fetch" or args.step == "all":
        step_fetch(args.asset, cfg)

    if args.step == "optimize" or args.step == "all":
        if not args.anchor_dates:
            print("[ERROR] --anchor-dates required for optimize step.")
            sys.exit(1)
        step_optimize(cfg, args.anchor_dates, args.reuse)

    if args.step == "signal" or args.step == "all":
        step_signal(cfg)

    if args.step == "backtest" or args.step == "all":
        step_backtest(cfg, args.tag)

    print(f"\n[DONE] Pipeline complete: {args.asset} / {args.step}")


if __name__ == "__main__":
    main()
