"""top10 완료 후 top20 자동 실행"""
import subprocess, sys, time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "run_horizon_scan.py"
WD     = Path(__file__).resolve().parents[2]

for top_n in [10, 20]:
    print(f"\n{'='*50}")
    print(f"Starting top-n={top_n}  [{time.strftime('%H:%M:%S')}]")
    print(f"{'='*50}")
    result = subprocess.run(
        [sys.executable, "-u", str(SCRIPT), f"--top-n", str(top_n)],
        cwd=str(WD),
    )
    if result.returncode != 0:
        print(f"[ERROR] top-n={top_n} failed")
        break
    print(f"[DONE] top-n={top_n}  [{time.strftime('%H:%M:%S')}]")

print("\nAll done.")
