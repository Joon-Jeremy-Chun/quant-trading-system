"""
monthly_anchor_refresh.py

Windows에서 새 앵커 계산 완료 후 실행하는 월별 갱신 스크립트.
1. models/pi_reference/<symbol>/ 를 최신 앵커로 갱신 (refresh_pi_reference.py 호출)
2. rsync로 Pi에 전송

Usage (Windows PowerShell):
    python scripts/monthly_anchor_refresh.py --dry-run
    python scripts/monthly_anchor_refresh.py

새 자산 추가 시:
    python scripts/monthly_anchor_refresh.py --symbols GLD,BRK-B,ITA,VRT
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PI_HOST   = "joonc@joon-pi"
PI_REPO   = "/home/joonc/my_github/quant-trading-system"

# All live assets now compute signal on Pi using models/pi_reference/<ASSET>/.
# ITA / VRT: pending_review, still Windows-push until promoted to live.
PI_COMPUTE_ASSETS = ["GLD", "BRK-B", "QQQ", "RKLB"]


def run(cmd: list[str], dry_run: bool) -> int:
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        print("    [DRY RUN skipped]")
        return 0
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def main() -> None:
    p = argparse.ArgumentParser(description="Monthly Pi reference anchor refresh.")
    p.add_argument("--symbols", default=",".join(PI_COMPUTE_ASSETS),
                   help=f"Comma-separated symbols to refresh (default: {','.join(PI_COMPUTE_ASSETS)})")
    p.add_argument("--keep", type=int, default=2,
                   help="Number of recent anchors to keep in pi_reference (default: 2)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    symbols   = [s.strip().upper() for s in args.symbols.split(",")]
    dry_run   = args.dry_run
    py        = sys.executable

    print("=" * 60)
    print(f"  Monthly Anchor Refresh  {'[DRY RUN]' if dry_run else ''}")
    print(f"  Symbols: {symbols}  |  Keep: {args.keep}")
    print("=" * 60)

    # ── Step 1: refresh pi_reference locally ─────────────────────────────────
    print("\n[1] Refreshing models/pi_reference/ on Windows...")
    for sym in symbols:
        print(f"\n  {sym}:")
        rc = run([py, str(REPO_ROOT / "scripts" / "refresh_pi_reference.py"),
                  "--symbol", sym, "--keep", str(args.keep)]
                 + (["--dry-run"] if dry_run else []), dry_run=False)
        if rc != 0:
            print(f"  [WARN] refresh failed for {sym} (rc={rc})")

    # ── Step 2: rsync to Pi ───────────────────────────────────────────────────
    print("\n[2] rsyncing models/pi_reference/ to Pi...")
    for sym in symbols:
        src = str(REPO_ROOT / "models" / "pi_reference" / sym) + "/"
        dst = f"{PI_HOST}:{PI_REPO}/models/pi_reference/{sym}/"
        cmd = ["rsync", "-av", "--delete", src, dst]
        rc  = run(cmd, dry_run)
        if rc != 0:
            print(f"  [WARN] rsync failed for {sym} (rc={rc})")

    # ── Step 3: git pull on Pi ────────────────────────────────────────────────
    print("\n[3] git pull on Pi (latest manifest + signals)...")
    rc = run(["ssh", PI_HOST, f"cd {PI_REPO} && git pull"], dry_run)
    if rc != 0:
        print("  [WARN] git pull failed")

    print("\n[OK] Monthly refresh complete.")
    print("     Next: run 'python scripts/simulate_tranche_bootstrap.py --dry-run' to update bootstrap if needed.")


if __name__ == "__main__":
    main()
