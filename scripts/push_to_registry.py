"""
push_to_registry.py

Windows 월말 작업: 새 앵커 계산 완료 후 실행.
optimization_outputs에서 top-N 행만 추출해 models/registry/<ASSET>/ 에 저장.
  - 파일 크기: 43MB → ~40KB (1000x 축소)
  - git으로 Pi에 전달 가능

Usage:
    python scripts/push_to_registry.py                         # 활성 자산 전부
    python scripts/push_to_registry.py --symbols QQQ,RKLB      # 특정 자산만
    python scripts/push_to_registry.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT = REPO_ROOT / "models" / "registry"

# 자산별 full 앵커 소스 (Windows 분석 결과)
SYMBOL_SOURCE_ROOT = {
    "GLD":   REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation",
    "BRK-B": REPO_ROOT / "outputs" / "brkb" / "anchor_snapshots",
    "QQQ":   REPO_ROOT / "outputs" / "qqq" / "anchor_snapshots",
    "RKLB":  REPO_ROOT / "outputs" / "rklb" / "anchor_snapshots",
    "ITA":   REPO_ROOT / "outputs" / "ita" / "anchor_snapshots",
    "VRT":   REPO_ROOT / "outputs" / "vrt" / "anchor_snapshots",
}

# 파이프라인이 읽는 파일: 전략별 대표 horizon의 all_ranked_results.csv
FAMILY_HORIZON = {
    "11_adaptive_band_strategy_optimization":      "1y",
    "21_ma_crossover_optimization":                "6m",
    "31_adaptive_volatility_band_optimization":    "3m",
    "41_fear_greed_candle_volume_optimization":    "1m",
}


def find_latest_anchor(source_root: Path) -> str | None:
    anchors = []
    for d in source_root.glob("anchor_????-??-??"):
        if d.is_dir() and (d / "optimization_outputs").exists():
            anchors.append(d.name.replace("anchor_", ""))
    return sorted(anchors)[-1] if anchors else None


def write_lightweight_anchor(
    src_anchor_dir: Path,
    dst_anchor_dir: Path,
    top_n: int,
    dry_run: bool,
) -> None:
    for family_dir, horizon in FAMILY_HORIZON.items():
        src_csv = src_anchor_dir / "optimization_outputs" / family_dir / horizon / f"{horizon}_all_ranked_results.csv"
        dst_csv = dst_anchor_dir / "optimization_outputs" / family_dir / horizon / f"{horizon}_all_ranked_results.csv"

        if not src_csv.exists():
            print(f"    [SKIP] not found: {src_csv.relative_to(REPO_ROOT)}")
            continue

        df = pd.read_csv(src_csv)
        top_df = df.head(top_n)
        src_kb = src_csv.stat().st_size / 1024
        dst_kb = len(top_df.to_csv(index=False).encode()) / 1024

        print(f"    {family_dir[:2]}_{horizon}: {src_kb:.0f}KB → {dst_kb:.1f}KB ({len(top_df)} rows)")

        if not dry_run:
            dst_csv.parent.mkdir(parents=True, exist_ok=True)
            top_df.to_csv(dst_csv, index=False)


def update_universe_json(symbol: str, anchor_date: str, dry_run: bool) -> None:
    universe_path = REGISTRY_ROOT / "universe.json"
    if universe_path.exists():
        universe = json.loads(universe_path.read_text(encoding="utf-8"))
    else:
        universe = {"assets": {}, "history": []}

    universe["generated_at"] = date.today().isoformat()
    if symbol not in universe["assets"]:
        universe["assets"][symbol] = {"status": "active", "entered": date.today().isoformat()}
        universe["history"].append({"date": date.today().isoformat(), "action": "enter", "symbol": symbol})

    universe["assets"][symbol]["latest_anchor"] = anchor_date

    if not dry_run:
        REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
        universe_path.write_text(json.dumps(universe, indent=2), encoding="utf-8")
        print(f"  [OK] universe.json updated: {symbol} active_anchor={anchor_date}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default=",".join(SYMBOL_SOURCE_ROOT.keys()))
    p.add_argument("--top-n", type=int, default=20, help="Top-N rows per family CSV (default: 20)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Push to registry  symbols={symbols}  top_n={args.top_n}")
    print("=" * 60)

    for symbol in symbols:
        source_root = SYMBOL_SOURCE_ROOT.get(symbol)
        if not source_root or not source_root.exists():
            print(f"\n[{symbol}] SKIP — source root not found: {source_root}")
            continue

        anchor_date = find_latest_anchor(source_root)
        if not anchor_date:
            print(f"\n[{symbol}] SKIP — no valid anchor found")
            continue

        src_anchor = source_root / f"anchor_{anchor_date}"
        dst_anchor = REGISTRY_ROOT / symbol / f"anchor_{anchor_date}"

        print(f"\n[{symbol}] anchor={anchor_date}")
        print(f"  src: {src_anchor.relative_to(REPO_ROOT)}")
        print(f"  dst: {dst_anchor.relative_to(REPO_ROOT)}")

        # 이미 동일한 앵커가 있으면 스킵
        if dst_anchor.exists() and not args.dry_run:
            print(f"  [SKIP] already in registry: anchor_{anchor_date}")
        else:
            write_lightweight_anchor(src_anchor, dst_anchor, args.top_n, args.dry_run)

        # 이전 달 앵커 제거 (registry는 최신 1개만 유지)
        if not args.dry_run:
            for old in (REGISTRY_ROOT / symbol).glob("anchor_????-??-??"):
                if old.name != f"anchor_{anchor_date}":
                    print(f"  [REMOVE] old anchor: {old.name}")
                    shutil.rmtree(old)

        # meta.json 갱신
        if not args.dry_run:
            meta = {"symbol": symbol, "active_anchor_date": anchor_date}
            (REGISTRY_ROOT / symbol / "meta.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )

        update_universe_json(symbol, anchor_date, args.dry_run)

    print("\n[OK] Registry push complete.")
    print("     Next: git add models/registry/ && git commit && git push")


if __name__ == "__main__":
    main()
