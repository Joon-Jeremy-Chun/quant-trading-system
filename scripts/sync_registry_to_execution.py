"""
sync_registry_to_execution.py

Pi 9시 git pull 후 실행.
models/registry/ 에서 새 앵커를 감지해 models/pi_reference/ (시행 폴더)에 복사.

- registry: 최신 앵커 1개만 (Windows가 매달 교체)
- pi_reference(execution): 모든 앵커 누적 (forensic 추적/롤백용)

Pi 동작:
  1. registry/<ASSET>/meta.json 읽기 -> active_anchor_date 확인
  2. pi_reference/<ASSET>/에 해당 앵커가 있으면 -> anchor 복사 스킵
     (execution_meta.json 없으면 → 보강 기록)
  3. 없으면 -> registry에서 복사 -> execution_meta.json 기록

execution_meta.json: registry meta + synced_at 기록.
이 파일이 있어야 "이 앵커가 어떤 Windows commit/checksum에서 왔는지" 역추적 가능.

Usage:
    python scripts/sync_registry_to_execution.py
    python scripts/sync_registry_to_execution.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Pipeline reads these 4 family/horizon CSVs — same as push_to_registry.py
FAMILY_HORIZON = {
    "11_adaptive_band_strategy_optimization":   "1y",
    "21_ma_crossover_optimization":             "6m",
    "31_adaptive_volatility_band_optimization": "3m",
    "41_fear_greed_candle_volume_optimization": "1m",
}

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT  = REPO_ROOT / "models" / "registry"
EXECUTION_ROOT = REPO_ROOT / "models" / "pi_reference"


def load_universe() -> dict:
    path = REGISTRY_ROOT / "universe.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_checksum(anchor_dir: Path) -> str:
    """Canonical CSV checksum — same algorithm as push_to_registry.py.
    pandas round-trip with LF neutralizes Windows/Pi line-ending differences.
    """
    h = hashlib.sha256()
    for family_dir, horizon in sorted(FAMILY_HORIZON.items()):
        csv = anchor_dir / "optimization_outputs" / family_dir / horizon / f"{horizon}_all_ranked_results.csv"
        if csv.exists():
            canonical = pd.read_csv(csv).to_csv(index=False, lineterminator="\n")
            h.update(canonical.encode("utf-8"))
    return h.hexdigest()[:16]


def _write_execution_meta(dst: Path, registry_meta: dict, dry_run: bool) -> None:
    """Write execution_meta.json inside anchor folder for forensic tracing.

    Records both registry_checksum (from Windows push) and execution_checksum
    (from actual files in pi_reference). checksum_match=false signals that the
    execution model differs from the registry version (e.g. pre-registry scp artifacts).
    """
    registry_checksum = registry_meta.get("csv_checksum_sha256_16", "unknown")
    execution_checksum = _canonical_checksum(dst) if not dry_run else "dry_run"
    checksum_match = (registry_checksum == execution_checksum)

    execution_meta = {
        **registry_meta,
        "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "execution_checksum": execution_checksum,
        "checksum_match": checksum_match,
    }
    # Rename the registry checksum field for clarity
    execution_meta["registry_checksum"] = execution_meta.pop("csv_checksum_sha256_16", registry_checksum)

    meta_path = dst / "execution_meta.json"
    if not dry_run:
        meta_path.write_text(json.dumps(execution_meta, indent=2), encoding="utf-8")
    status = "OK" if checksum_match else "MISMATCH (pre-registry artifact or different computation)"
    print(f"  [meta] commit={registry_meta.get('source_windows_commit','?')}  checksum_match={checksum_match} [{status}]")


def sync_asset(symbol: str, dry_run: bool) -> bool:
    meta_path = REGISTRY_ROOT / symbol / "meta.json"
    if not meta_path.exists():
        print(f"  [{symbol}] SKIP - no meta.json in registry")
        return False

    registry_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    anchor_date = registry_meta.get("active_anchor_date")
    if not anchor_date:
        print(f"  [{symbol}] SKIP - meta.json missing active_anchor_date")
        return False

    src = REGISTRY_ROOT / symbol / f"anchor_{anchor_date}"
    dst = EXECUTION_ROOT / symbol / f"anchor_{anchor_date}"

    if dst.exists():
        # Anchor already present — check if execution_meta.json is there.
        # If missing (e.g. pre-forensic sync), backfill it now.
        exec_meta_path = dst / "execution_meta.json"
        if not exec_meta_path.exists():
            print(f"  [{symbol}] anchor_{anchor_date} exists but missing execution_meta.json — backfilling")
            _write_execution_meta(dst, registry_meta, dry_run)
            return True
        print(f"  [{symbol}] OK - anchor_{anchor_date} already in execution folder (with meta)")
        return False

    if not src.exists():
        print(f"  [{symbol}] WARN - anchor_{anchor_date} in meta but missing from registry")
        return False

    print(f"  [{symbol}] NEW anchor found: {anchor_date} - copying to execution folder")
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        _write_execution_meta(dst, registry_meta, dry_run)
        print(f"  [{symbol}] DONE - copied to {dst.relative_to(REPO_ROOT)}")

    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not REGISTRY_ROOT.exists():
        print("[sync] models/registry/ not found - nothing to do")
        return

    universe = load_universe()
    active_symbols = [
        sym for sym, info in universe.get("assets", {}).items()
        if info.get("status") == "active"
    ]

    if not active_symbols:
        # fallback: scan registry folder directly
        active_symbols = [d.name for d in REGISTRY_ROOT.iterdir() if d.is_dir()]

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Registry -> Execution sync")
    print(f"Active symbols: {active_symbols}")
    print("=" * 50)

    updated = []
    for symbol in active_symbols:
        if sync_asset(symbol, args.dry_run):
            updated.append(symbol)

    if updated:
        print(f"\n[sync] Updated: {updated}")
    else:
        print("\n[sync] All execution anchors up-to-date - nothing copied")


if __name__ == "__main__":
    main()
