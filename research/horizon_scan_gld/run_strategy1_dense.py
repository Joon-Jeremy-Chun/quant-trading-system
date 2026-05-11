"""
run_strategy1_dense.py

10개 앵커 × 5일 간격 dense windows로 Strategy 1 (Adaptive Band) 최적화 실행.
결과: outputs/strategy1_dense/anchor_<date>/<Xd>/

실험 폴더 독립 — 원본 파이프라인과 완전 분리.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

ANCHOR_DATES = [
    # "2021-05-28",  # 완료됨
    "2021-11-30",
    "2022-05-31",
    "2022-11-30",
    "2023-05-31",
    "2023-11-30",
    "2024-05-31",
    "2024-11-29",
    "2025-05-30",
    "2025-11-28",
]

N_JOBS = 19  # 20코어 - 1


def run_one_anchor(anchor_date: str) -> None:
    print(f"\n{'='*60}")
    print(f"  앵커: {anchor_date}")
    print(f"{'='*60}")
    t0 = time.perf_counter()

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "strategy1_dense_windows.py"),
        "--train-end-date", anchor_date,
        "--n-jobs", str(N_JOBS),
        "--top-n", "20",
    ]

    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"[ERROR] 앵커 {anchor_date} 실패 (returncode={result.returncode})")
    else:
        print(f"[OK] 앵커 {anchor_date} 완료 -- {elapsed/60:.1f}분")


def main() -> None:
    total_t0 = time.perf_counter()
    print("Strategy 1 Dense Window 최적화 시작")
    print(f"앵커 {len(ANCHOR_DATES)}개 × 5~520일(5일 간격) = 104 windows / 앵커")
    print(f"CPU: {N_JOBS} jobs (20코어 - 1)")

    for anchor_date in ANCHOR_DATES:
        run_one_anchor(anchor_date)

    total_elapsed = time.perf_counter() - total_t0
    print(f"\n전체 완료: {total_elapsed/60:.1f}분")


if __name__ == "__main__":
    main()
