"""
tuning_job.py  —  Stage A: Model Selection Viewer

Stage A role: shows HOW the system picks the best model for a given asset.
Stage B (production): daily_pipeline.py runs this automatically at 12:45 PT.

What this does:
  1. Reads the anchor's strategy_top_candidates.csv (pre-computed optimization results)
  2. Ranks strategies by selection_cv_mse (cross-validated MSE — lower = better)
  3. Saves the best params to outputs/params/latest_params.json
  4. Prints a summary table so you can see what the model chose

Usage:
    python jobs/tuning_job.py                            # GLD, latest anchor
    python jobs/tuning_job.py --symbol BRKB --top-n 5
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR  = REPO_ROOT / "outputs" / "live"

ANCHOR_ROOTS = {
    "GLD":   REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation",
    "BRKB":  REPO_ROOT / "outputs" / "brkb" / "anchor_snapshots",
    "QQQ":   REPO_ROOT / "outputs" / "qqq"  / "anchor_snapshots",
    "RKLB":  REPO_ROOT / "outputs" / "rklb" / "anchor_snapshots",
}


def latest_anchor_dir(anchor_root: Path) -> Path | None:
    dirs = sorted(
        [d for d in anchor_root.iterdir() if d.is_dir() and d.name.startswith("anchor_")],
        reverse=True,
    )
    return dirs[0] if dirs else None


def load_top_candidates(anchor_dir: Path) -> pd.DataFrame | None:
    csv_path = anchor_dir / "strategy_top_candidates.csv"
    if not csv_path.exists():
        return None
    return pd.read_csv(csv_path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="GLD", choices=list(ANCHOR_ROOTS.keys()))
    p.add_argument("--top-n", type=int, default=3, help="Show top-N candidates")
    p.add_argument("--criterion", default="selection_cv_mse",
                   help="Column to rank by (lower = better)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    symbol = args.symbol.upper()

    anchor_root = ANCHOR_ROOTS.get(symbol)
    if anchor_root is None or not anchor_root.exists():
        print(f"[ERROR] No anchor root for {symbol}: {anchor_root}")
        return

    anchor_dir = latest_anchor_dir(anchor_root)
    if anchor_dir is None:
        print(f"[ERROR] No anchor found in {anchor_root}")
        return

    df = load_top_candidates(anchor_dir)
    if df is None:
        print(f"[ERROR] strategy_top_candidates.csv not found in {anchor_dir}")
        return

    print("=" * 64)
    print(f"  Tuning Job  —  {symbol}  |  anchor: {anchor_dir.name}")
    print("=" * 64)

    # Rank by criterion (lower MSE = better)
    if args.criterion in df.columns:
        df = df.sort_values(args.criterion).reset_index(drop=True)

    top = df.head(args.top_n)
    show_cols = [c for c in ["strategy_id", "family", args.criterion, "selection_correlation",
                              "top_n_rank"] if c in df.columns]
    print(f"\n  Top-{args.top_n} strategies by {args.criterion}:\n")
    print(top[show_cols].to_string(index=False))

    # Save best params
    best = df.iloc[0].to_dict()
    out_dir = REPO_ROOT / "outputs" / "params"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "anchor": anchor_dir.name,
        "criterion": args.criterion,
        "best_strategy": best,
        "params": {
            k: v for k, v in best.items()
            if k not in ("strategy_id", "family") and not k.startswith("selection_")
        },
    }
    out_path = out_dir / "latest_params.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"\n  [OK] Best strategy: {best.get('strategy_id', '?')}")
    print(f"  [OK] Saved to: {out_path.relative_to(REPO_ROOT)}")
    print()
    print("  Stage B connection:")
    print("  -> daily_pipeline.py runs this automatically via --build-signal")
    print("  -> check_and_refresh_signals.py refreshes when anchor is stale")


if __name__ == "__main__":
    main()
