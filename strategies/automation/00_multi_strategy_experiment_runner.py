from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
STRATEGIES_DIR = SCRIPT_DIR.parent

STRATEGY_REGISTRY = {
    "adaptive_band": {
        "optimization": "11_adaptive_band_strategy_multiwindow_optimization.py",
        "forward": "12_adaptive_band_strategy_forward_test.py",
    },
    "ma_crossover": {
        "optimization": "21_ma_crossover_multiwindow_optimization.py",
        "forward": "22_ma_crossover_forward_test.py",
    },
    "adaptive_volatility_band": {
        "optimization": "31_adaptive_volatility_band_multiwindow_optimization.py",
        "forward": "32_adaptive_volatility_band_forward_test.py",
    },
    "fear_greed_candle_volume": {
        "optimization": "41_fear_greed_candle_volume_multiwindow_optimization.py",
        "forward": "42_fear_greed_candle_volume_forward_test.py",
    },
}

DEFAULT_CONFIG = {
    "data_csv": "../data/gld_us_d.csv",
    "train_end_date": "2024-12-31",
    "test_start_date": "2025-01-01",
    "test_end_date": "2025-12-31",
    "horizons": "1m,6m,1y,3y,5y,10y",
    "top_n": 10,
    "strategies": "all",
    "skip_optimization": False,
    "skip_forward": False,
    "dry_run": False,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-strategy optimization and forward-test experiments.")
    parser.add_argument("--config", type=str, default=None, help="Path to a JSON experiment config file.")
    parser.add_argument("--data-csv", type=str, default=None, help="Dataset CSV path relative to the strategies folder or absolute path.")
    parser.add_argument("--train-end-date", type=str, default=None, help="Training end date (YYYY-MM-DD).")
    parser.add_argument("--test-start-date", type=str, default=None, help="Forward-test start date (YYYY-MM-DD).")
    parser.add_argument("--test-end-date", type=str, default=None, help="Forward-test end date (YYYY-MM-DD).")
    parser.add_argument("--horizons", type=str, default=None, help="Comma-separated horizons such as 1m,3m,6m,1y.")
    parser.add_argument("--top-n", type=int, default=None, help="Top-N parameter sets to keep or load.")
    parser.add_argument(
        "--strategies",
        type=str,
        default=None,
        help="Comma-separated strategy keys or 'all'. Choices: adaptive_band, ma_crossover, adaptive_volatility_band, fear_greed_candle_volume",
    )
    parser.add_argument("--skip-optimization", action="store_true", help="Skip optimization scripts.")
    parser.add_argument("--skip-forward", action="store_true", help="Skip forward-test scripts.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    return parser.parse_args()


def resolve_config_path(raw: str | None) -> Path | None:
    if not raw:
        return None

    path = Path(raw)
    if not path.is_absolute():
        path = (SCRIPT_DIR / path).resolve()
    return path


def normalize_horizons(value: str | list[str]) -> str:
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def normalize_strategies(value: str | list[str]) -> str:
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def load_json_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        config = json.load(fp)

    if not isinstance(config, dict):
        raise ValueError("JSON config root must be an object.")

    normalized = dict(config)
    if "horizons" in normalized:
        normalized["horizons"] = normalize_horizons(normalized["horizons"])
    if "strategies" in normalized:
        normalized["strategies"] = normalize_strategies(normalized["strategies"])
    return normalized


def build_effective_config(args: argparse.Namespace) -> dict:
    config = dict(DEFAULT_CONFIG)

    config_path = resolve_config_path(args.config)
    if config_path is not None:
        file_config = load_json_config(config_path)
        config.update(file_config)
        config["config_path"] = str(config_path)
    else:
        config["config_path"] = None

    cli_overrides = {
        "data_csv": args.data_csv,
        "train_end_date": args.train_end_date,
        "test_start_date": args.test_start_date,
        "test_end_date": args.test_end_date,
        "horizons": args.horizons,
        "top_n": args.top_n,
        "strategies": args.strategies,
    }
    for key, value in cli_overrides.items():
        if value is not None:
            config[key] = value

    if args.skip_optimization:
        config["skip_optimization"] = True
    if args.skip_forward:
        config["skip_forward"] = True
    if args.dry_run:
        config["dry_run"] = True

    return config


def resolve_strategy_keys(raw: str) -> list[str]:
    if raw.strip().lower() == "all":
        return list(STRATEGY_REGISTRY.keys())

    keys = [token.strip() for token in raw.split(",") if token.strip()]
    invalid = [key for key in keys if key not in STRATEGY_REGISTRY]
    if invalid:
        raise ValueError(f"Unknown strategy keys: {invalid}")
    return keys


def build_base_args(config: dict) -> list[str]:
    return [
        "--data-csv",
        config["data_csv"],
        "--train-end-date",
        config["train_end_date"],
        "--horizons",
        config["horizons"],
        "--top-n",
        str(config["top_n"]),
    ]


def build_forward_args(config: dict) -> list[str]:
    return build_base_args(config) + [
        "--test-start-date",
        config["test_start_date"],
        "--test-end-date",
        config["test_end_date"],
    ]


def run_script(script_name: str, script_args: list[str], dry_run: bool) -> None:
    cmd = [sys.executable, script_name, *script_args]
    pretty = " ".join(cmd)
    print(f"[RUN] {pretty}")

    if dry_run:
        return

    subprocess.run(cmd, cwd=STRATEGIES_DIR, check=True)


def main() -> None:
    args = parse_args()
    config = build_effective_config(args)
    strategy_keys = resolve_strategy_keys(config["strategies"])

    print("=" * 80)
    print("00_multi_strategy_experiment_runner.py START")
    print("=" * 80)
    print(f"CONFIG_PATH:      {config['config_path']}")
    print(f"STRATEGIES:       {strategy_keys}")
    print(f"DATA_CSV:         {config['data_csv']}")
    print(f"TRAIN_END_DATE:   {config['train_end_date']}")
    print(f"TEST_START_DATE:  {config['test_start_date']}")
    print(f"TEST_END_DATE:    {config['test_end_date']}")
    print(f"HORIZONS:         {config['horizons']}")
    print(f"TOP_N:            {config['top_n']}")
    print(f"SKIP_OPTIMIZATION:{config['skip_optimization']}")
    print(f"SKIP_FORWARD:     {config['skip_forward']}")
    print(f"DRY_RUN:          {config['dry_run']}")
    print("=" * 80)

    total_tasks = len(strategy_keys) * (int(not config["skip_optimization"]) + int(not config["skip_forward"]))
    task_index = 0

    for key in strategy_keys:
        meta = STRATEGY_REGISTRY[key]
        print(f"\n[STRATEGY] {key}")

        if not config["skip_optimization"]:
            task_index += 1
            print(f"[{task_index}/{total_tasks}] {key} optimization started")
            run_script(meta["optimization"], build_base_args(config), config["dry_run"])

        if not config["skip_forward"]:
            task_index += 1
            print(f"[{task_index}/{total_tasks}] {key} forward test started")
            run_script(meta["forward"], build_forward_args(config), config["dry_run"])

    print("\n" + "=" * 80)
    print("MASTER RUN COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
