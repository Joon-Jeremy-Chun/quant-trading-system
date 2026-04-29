from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_MANIFEST = REPO_ROOT / "models" / "live" / "latest_model_manifest.json"
ASSET_CONFIGS = {
    "GLD": {
        "slug": "gld",
        "data_csv": REPO_ROOT / "data" / "gld_us_d.csv",
        "anchor_output_root": REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation",
    },
    "BRK-B": {
        "slug": "brkb",
        "data_csv": REPO_ROOT / "data" / "brkb_us_d.csv",
        "anchor_output_root": REPO_ROOT / "outputs" / "brkb" / "anchor_snapshots",
    },
}


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return int(default)
    return int(raw)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the daily GLD live pipeline using an existing signal by default."
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Optional single-symbol override kept for backward compatibility.",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=os.getenv("LIVE_SYMBOLS", "GLD,BRK-B"),
        help="Comma-separated symbols to process. Defaults to GLD,BRK-B.",
    )
    parser.add_argument(
        "--build-signal",
        action="store_true",
        help=(
            "Also refresh data and rebuild the Objective 2 live signal locally. "
            "Use this on Raspberry Pi when model artifacts are synced through GitHub."
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
    parser.add_argument(
        "--allow-pull-failure",
        action="store_true",
        help="Continue with local files if git pull fails. Default is to stop before trading.",
    )
    parser.add_argument(
        "--model-manifest",
        type=str,
        default=os.getenv("LIVE_MODEL_MANIFEST", str(DEFAULT_MODEL_MANIFEST)),
        help=(
            "Path to the latest live model manifest. If present, it overrides per-symbol data/model paths "
            "and parameters before building signals."
        ),
    )
    parser.add_argument(
        "--require-model-manifest",
        action="store_true",
        default=env_bool("REQUIRE_LIVE_MODEL_MANIFEST", False),
        help="Fail before trading when --build-signal is used and the live model manifest is missing.",
    )
    return parser.parse_args()


def selected_symbols(args: argparse.Namespace) -> list[str]:
    raw = args.symbol if args.symbol else args.symbols
    symbols = [part.strip().upper() for part in raw.split(",") if part.strip()]
    if not symbols:
        raise ValueError("No symbols selected.")
    unsupported = [symbol for symbol in symbols if symbol not in ASSET_CONFIGS]
    if unsupported:
        raise ValueError(f"Unsupported live symbols: {unsupported}. Supported: {sorted(ASSET_CONFIGS)}")
    return symbols


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


def repo_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def load_model_manifest(path: Path, required: bool) -> dict:
    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"Missing live model manifest: {path}. "
                "Push the latest workstation-generated model artifact before running the Pi pipeline."
            )
        return {
            "name": "live_model_manifest",
            "path": str(path),
            "loaded": False,
            "reason": "missing",
            "symbols": {},
        }

    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    if not isinstance(manifest.get("symbols"), dict):
        raise ValueError(f"Invalid live model manifest, missing object field 'symbols': {path}")
    return {
        "name": "live_model_manifest",
        "path": str(path),
        "loaded": True,
        "schema_version": manifest.get("schema_version"),
        "generated_at_utc": manifest.get("generated_at_utc"),
        "model_set_id": manifest.get("model_set_id"),
        "symbols": manifest.get("symbols", {}),
    }


def resolve_asset_config(symbol: str, manifest_step: dict) -> dict:
    asset = ASSET_CONFIGS[symbol].copy()
    symbol_manifest = manifest_step.get("symbols", {}).get(symbol, {})
    if not symbol_manifest:
        return asset

    data_csv = repo_path(symbol_manifest.get("data_csv"))
    anchor_output_root = repo_path(symbol_manifest.get("anchor_output_root"))
    if data_csv is not None:
        asset["data_csv"] = data_csv
    if anchor_output_root is not None:
        asset["anchor_output_root"] = anchor_output_root
    for key in ("target_horizon_days", "update_interval_months", "selection_criterion", "top_n_per_family"):
        if key in symbol_manifest and symbol_manifest[key] is not None:
            asset[key] = symbol_manifest[key]
    asset["model_manifest"] = symbol_manifest
    return asset


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


def load_signal(root: Path, symbol: str) -> dict | None:
    slug = ASSET_CONFIGS[symbol]["slug"]
    path = root / "outputs" / "live" / f"latest_{slug}_signal.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_existing_signal(root: Path, symbol: str) -> dict:
    slug = ASSET_CONFIGS[symbol]["slug"]
    signal_path = root / "outputs" / "live" / f"latest_{slug}_signal.json"
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

    today = date.today()
    signal_date = date.fromisoformat(signal_payload["asof_date"])
    signal_age_days = (today - signal_date).days
    max_signal_age_days = env_int("MAX_SIGNAL_AGE_DAYS", 5)
    max_dataset_staleness_days = env_int("MAX_DATASET_STALENESS_DAYS", 5)
    max_model_age_days = env_int("MAX_MODEL_AGE_DAYS", 540)
    dataset_staleness_days = int(signal_payload.get("dataset_staleness_days", 0) or 0)
    model_age_days = int(signal_payload.get("model_age_days", 0) or 0)
    block_on_stale_model = env_bool("BLOCK_ON_STALE_MODEL", False)

    if signal_age_days < 0:
        raise ValueError(f"{symbol} signal date is in the future: {signal_payload['asof_date']}")
    if signal_age_days > max_signal_age_days:
        raise ValueError(f"{symbol} signal is too old: {signal_age_days}d > {max_signal_age_days}d")
    if dataset_staleness_days > max_dataset_staleness_days:
        raise ValueError(
            f"{symbol} dataset is too stale: {dataset_staleness_days}d > {max_dataset_staleness_days}d"
        )
    if block_on_stale_model and model_age_days > max_model_age_days:
        raise ValueError(f"{symbol} model is too old: {model_age_days}d > {max_model_age_days}d")

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
        "signal_age_days": signal_age_days,
    }


def legacy_main() -> None:
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

    # ── Multi-asset weight normalization ─────────────────────────────────────
    gld_signal = load_signal(REPO_ROOT, "GLD")
    brkb_signal = load_signal(REPO_ROOT, "BRK-B")
    gld_w_raw = float(gld_signal.get("target_weight", 0.0)) if gld_signal else 0.0
    brkb_w_raw = float(brkb_signal.get("target_weight", 0.0)) if brkb_signal else 0.0
    total_w = gld_w_raw + brkb_w_raw
    if total_w > 1.0:
        gld_w = gld_w_raw / total_w
        brkb_w = brkb_w_raw / total_w
        norm_applied = True
    else:
        gld_w = gld_w_raw
        brkb_w = brkb_w_raw
        norm_applied = False
    pipeline_steps.append({
        "name": "multi_asset_normalization",
        "gld_raw": gld_w_raw, "brkb_raw": brkb_w_raw,
        "gld_final": gld_w, "brkb_final": brkb_w,
        "total_raw": total_w, "normalized": norm_applied,
    })

    # ── GLD order ─────────────────────────────────────────────────────────────
    pipeline_steps.append(
        run_step(
            "submit_gld_order",
            [py, str(REPO_ROOT / "jobs" / "gld_tranche_order_job.py"),
             "--symbol", "GLD", "--weight-override", str(round(gld_w, 6))],
            REPO_ROOT,
        )
    )

    # ── BRK-B order ───────────────────────────────────────────────────────────
    if brkb_signal:
        pipeline_steps.append(
            run_step(
                "submit_brkb_order",
                [py, str(REPO_ROOT / "jobs" / "gld_tranche_order_job.py"),
                 "--symbol", "BRK-B", "--weight-override", str(round(brkb_w, 6))],
                REPO_ROOT,
            )
        )

    # ── Combined email ────────────────────────────────────────────────────────
    pipeline_steps.append(
        run_step(
            "send_email_alert",
            [py, str(REPO_ROOT / "jobs" / "send_gld_email_alert.py")],
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


def main() -> None:
    args = parse_args()
    py = sys.executable
    symbols = selected_symbols(args)
    outputs_dir = REPO_ROOT / "outputs" / "live"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    pipeline_steps: list[dict] = []

    pull_result = pull_latest_signal(REPO_ROOT)
    pipeline_steps.append(pull_result)
    if not pull_result["pulled"]:
        message = f"git pull failed (returncode={pull_result['returncode']}): {pull_result['stderr']}"
        if not args.allow_pull_failure:
            raise RuntimeError(message)
        print(f"[WARN] {message}")

    manifest_path = repo_path(args.model_manifest) or DEFAULT_MODEL_MANIFEST
    manifest_step = load_model_manifest(manifest_path, args.require_model_manifest and args.build_signal)
    pipeline_steps.append(manifest_step)

    for symbol in symbols:
        asset = resolve_asset_config(symbol, manifest_step)
        if args.build_signal:
            target_horizon_days = int(asset.get("target_horizon_days", args.target_horizon_days))
            update_interval_months = int(asset.get("update_interval_months", args.update_interval_months))
            selection_criterion = str(asset.get("selection_criterion", args.selection_criterion))
            top_n_per_family = int(asset.get("top_n_per_family", args.top_n_per_family))
            pipeline_steps.append(
                run_step(
                    f"update_daily_data_{asset['slug']}",
                    [
                        py,
                        str(REPO_ROOT / "jobs" / "update_gld_daily_data.py"),
                        "--max-staleness-days",
                        str(args.max_staleness_days),
                        "--symbol",
                        symbol,
                        "--data-csv",
                        str(asset["data_csv"]),
                    ],
                    REPO_ROOT,
                )
            )

            signal_cmd = [
                py,
                str(REPO_ROOT / "strategies" / "automation" / "run_objective2_latest_live_signal.py"),
                "--target-horizon-days",
                str(target_horizon_days),
                "--update-interval-months",
                str(update_interval_months),
                "--selection-criterion",
                selection_criterion,
                "--top-n-per-family",
                str(top_n_per_family),
                "--symbol",
                symbol,
                "--data-csv",
                str(asset["data_csv"]),
                "--anchor-output-root",
                str(asset["anchor_output_root"]),
            ]
            if args.tag:
                signal_cmd.extend(["--tag", args.tag])
            pipeline_steps.append(run_step(f"build_latest_live_signal_{asset['slug']}", signal_cmd, REPO_ROOT))
        else:
            pipeline_steps.append(validate_existing_signal(REPO_ROOT, symbol))

    signals = {symbol: load_signal(REPO_ROOT, symbol) for symbol in symbols}
    raw_weights = {
        symbol: max(float(signal.get("target_weight", 0.0) or 0.0), 0.0) if signal else 0.0
        for symbol, signal in signals.items()
    }
    total_w = sum(raw_weights.values())
    if total_w > 1.0:
        final_weights = {symbol: weight / total_w for symbol, weight in raw_weights.items()}
        norm_applied = True
    else:
        final_weights = raw_weights.copy()
        norm_applied = False
    pipeline_steps.append(
        {
            "name": "multi_asset_normalization",
            "raw_weights": raw_weights,
            "final_weights": final_weights,
            "total_raw": total_w,
            "normalized": norm_applied,
        }
    )

    for symbol in symbols:
        signal = signals.get(symbol)
        if not signal:
            pipeline_steps.append({"name": f"skip_order_{symbol}", "reason": "missing_signal"})
            continue
        pipeline_steps.append(
            run_step(
                f"submit_order_{ASSET_CONFIGS[symbol]['slug']}",
                [
                    py,
                    str(REPO_ROOT / "jobs" / "gld_tranche_order_job.py"),
                    "--symbol",
                    symbol,
                    "--weight-override",
                    str(round(final_weights[symbol], 6)),
                ],
                REPO_ROOT,
            )
        )

    pipeline_steps.append(
        run_step(
            "send_email_alert",
            [py, str(REPO_ROOT / "jobs" / "send_gld_email_alert.py")],
            REPO_ROOT,
        )
    )

    summary = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "target_horizon_days": args.target_horizon_days,
        "update_interval_months": args.update_interval_months,
        "selection_criterion": args.selection_criterion,
        "build_signal": args.build_signal,
        "model_manifest": manifest_step,
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
    print(f"SYMBOLS:                  {','.join(symbols)}")
    print(f"TARGET_HORIZON_DAYS:      {args.target_horizon_days}")
    print(f"UPDATE_INTERVAL_MONTHS:   {args.update_interval_months}")
    print(f"SELECTION_CRITERION:      {args.selection_criterion}")
    print(f"BUILD_SIGNAL:             {args.build_signal}")
    print(f"[OK] Saved pipeline log:  {out_path}")


if __name__ == "__main__":
    main()
