"""
auto_pipeline.py
strategy1 dense 완료 감지 후 horizon scan 자동 실행
"""
from __future__ import annotations
import time, subprocess, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DENSE_ROOT = SCRIPT_DIR / "outputs" / "strategy1_dense"

ANCHOR_DATES = [
    "2021-05-28", "2021-11-30",
    "2022-05-31", "2022-11-30",
    "2023-05-31", "2023-11-30",
    "2024-05-31", "2024-11-29",
    "2025-05-30", "2025-11-28",
]
REQUIRED_WINDOWS = 101  # 20d~520d (5일 간격)
CHECK_INTERVAL   = 60   # 60초마다 체크


def count_done(anchor_date: str) -> int:
    d = DENSE_ROOT / f"anchor_{anchor_date}"
    if not d.exists():
        return 0
    return sum(1 for x in d.iterdir() if x.is_dir())


def all_done() -> bool:
    return all(count_done(a) >= REQUIRED_WINDOWS for a in ANCHOR_DATES)


def status_line() -> str:
    parts = []
    for a in ANCHOR_DATES:
        n = count_done(a)
        parts.append(f"{a[-5:]}:{n}")
    return "  ".join(parts)


def main() -> None:
    print("Auto pipeline 시작 -- strategy1 완료 대기 중...")
    while not all_done():
        print(f"[{time.strftime('%H:%M:%S')}] {status_line()}")
        time.sleep(CHECK_INTERVAL)

    print(f"\n[{time.strftime('%H:%M:%S')}] Strategy1 전체 완료! Horizon scan 시작...")

    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "run_horizon_scan.py")],
        cwd=str(SCRIPT_DIR.parents[1]),
    )
    if result.returncode == 0:
        print("Horizon scan 완료!")
    else:
        print(f"Horizon scan 오류 (returncode={result.returncode})")


if __name__ == "__main__":
    main()
