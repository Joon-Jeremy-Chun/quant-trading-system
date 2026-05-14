"""
sync_registry_to_execution.py

Pi 9시 git pull 후 실행.
models/registry/ 에서 새 앵커를 감지해 models/pi_reference/ (시행 폴더)에 복사.

- registry: 최신 앵커 1개만 (Windows가 매달 교체)
- pi_reference(execution): 모든 앵커 누적 (디버깅/롤백용)

Pi 동작:
  1. registry/<ASSET>/meta.json 읽기 -> active_anchor_date 확인
  2. pi_reference/<ASSET>/에 해당 앵커가 있으면 -> 스킵
  3. 없으면 -> registry에서 복사 -> pi_reference에 추가

Usage:
    python scripts/sync_registry_to_execution.py
    python scripts/sync_registry_to_execution.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT  = REPO_ROOT / "models" / "registry"
EXECUTION_ROOT = REPO_ROOT / "models" / "pi_reference"


def load_universe() -> dict:
    path = REGISTRY_ROOT / "universe.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def sync_asset(symbol: str, dry_run: bool) -> bool:
    meta_path = REGISTRY_ROOT / symbol / "meta.json"
    if not meta_path.exists():
        print(f"  [{symbol}] SKIP - no meta.json in registry")
        return False

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    anchor_date = meta.get("active_anchor_date")
    if not anchor_date:
        print(f"  [{symbol}] SKIP - meta.json missing active_anchor_date")
        return False

    src = REGISTRY_ROOT / symbol / f"anchor_{anchor_date}"
    dst = EXECUTION_ROOT / symbol / f"anchor_{anchor_date}"

    if dst.exists():
        print(f"  [{symbol}] OK - anchor_{anchor_date} already in execution folder")
        return False

    if not src.exists():
        print(f"  [{symbol}] WARN - anchor_{anchor_date} in meta but missing from registry")
        return False

    print(f"  [{symbol}] NEW anchor found: {anchor_date} - copying to execution folder")
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
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
