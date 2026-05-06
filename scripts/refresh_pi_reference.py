"""
refresh_pi_reference.py

Copies the latest N anchors from a full anchor history into
models/pi_reference/<symbol>/, keeping only those N anchors.
Run this on Windows after computing a new anchor, or on Pi after git pull.

Usage:
    python scripts/refresh_pi_reference.py --symbol GLD
    python scripts/refresh_pi_reference.py --symbol BRK-B
    python scripts/refresh_pi_reference.py --symbol GLD --keep 3
    python scripts/refresh_pi_reference.py --symbol GLD --dry-run
"""

import argparse
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SYMBOL_SOURCE_ROOT = {
    "GLD":   "outputs/objective1_anchor_date_multi_horizon_evaluation",
    "BRK-B": "outputs/brkb/anchor_snapshots",
    "QQQ":   "outputs/qqq/anchor_snapshots",
    "RKLB":  "outputs/rklb/anchor_snapshots",
}

PI_REF_ROOT = REPO_ROOT / "models" / "pi_reference"


def find_valid_anchors(source_root: Path) -> list[str]:
    """Return anchor date strings sorted descending, only those with optimization_outputs."""
    anchors = []
    for d in source_root.glob("anchor_????-??-??"):
        if d.is_dir() and (d / "optimization_outputs").exists():
            anchors.append(d.name.replace("anchor_", ""))
    return sorted(anchors, reverse=True)


def copy_anchor(src_anchor_dir: Path, dst_anchor_dir: Path, dry_run: bool) -> None:
    dst_opt = dst_anchor_dir / "optimization_outputs"
    if dst_anchor_dir.exists() and dst_opt.exists():
        print(f"  [SKIP] already complete: {dst_anchor_dir.name}")
        return
    if dst_anchor_dir.exists() and not dst_opt.exists():
        # Dir exists (from git) but optimization_outputs missing — copy just that subdirectory
        src_opt = src_anchor_dir / "optimization_outputs"
        print(f"  [FIX]  {dst_anchor_dir.name}: dir exists but missing optimization_outputs, copying...")
        if not dry_run:
            shutil.copytree(src_opt, dst_opt)
        return
    print(f"  [COPY] {src_anchor_dir.name} -> {dst_anchor_dir}")
    if not dry_run:
        shutil.copytree(src_anchor_dir, dst_anchor_dir)


def remove_stale_anchors(pi_ref_symbol: Path, keep_dates: set[str], dry_run: bool) -> None:
    for d in pi_ref_symbol.glob("anchor_????-??-??"):
        date_str = d.name.replace("anchor_", "")
        if date_str not in keep_dates:
            print(f"  [REMOVE] stale anchor: {d.name}")
            if not dry_run:
                shutil.rmtree(d)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh models/pi_reference/<symbol> with latest anchors.")
    parser.add_argument("--symbol", required=True, choices=list(SYMBOL_SOURCE_ROOT.keys()))
    parser.add_argument("--keep", type=int, default=2, help="Number of anchors to keep (default: 2)")
    parser.add_argument("--source-root", help="Override source anchor root path (default: from SYMBOL_SOURCE_ROOT)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_root = Path(args.source_root) if args.source_root else REPO_ROOT / SYMBOL_SOURCE_ROOT[args.symbol]
    pi_ref_symbol = PI_REF_ROOT / args.symbol

    if not source_root.exists():
        print(f"[ERROR] Source root not found: {source_root}")
        return

    valid_anchors = find_valid_anchors(source_root)
    if not valid_anchors:
        print(f"[ERROR] No valid anchors (with optimization_outputs) found in {source_root}")
        return

    keep_anchors = valid_anchors[: args.keep]
    print(f"\n[{args.symbol}] Source: {source_root}")
    print(f"[{args.symbol}] Available anchors: {len(valid_anchors)} | Keeping: {keep_anchors}")
    print(f"[{args.symbol}] Destination: {pi_ref_symbol}")

    if not args.dry_run:
        pi_ref_symbol.mkdir(parents=True, exist_ok=True)

    for date_str in keep_anchors:
        src = source_root / f"anchor_{date_str}"
        dst = pi_ref_symbol / f"anchor_{date_str}"
        copy_anchor(src, dst, args.dry_run)

    remove_stale_anchors(pi_ref_symbol, set(keep_anchors), args.dry_run)

    if args.dry_run:
        print("\n[DRY RUN] No changes made.")
        return

    # Write a small metadata file so Pi can detect the active anchor date without scanning
    active_anchor = keep_anchors[0]
    meta = {"symbol": args.symbol, "active_anchor_date": active_anchor, "keep": args.keep}
    meta_path = pi_ref_symbol / "pi_reference_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  [OK] Wrote {meta_path.name}: active_anchor={active_anchor}")
    print(f"\n[{args.symbol}] Done.")


if __name__ == "__main__":
    main()
