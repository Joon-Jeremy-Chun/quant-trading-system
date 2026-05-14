"""
check_and_refresh_signals.py

Windows automation: checks if each asset's live signal uses the latest valid anchor
(anchor_date <= today - MIN_ANCHOR_AGE_DAYS). If stale, rebuilds the signal and
pushes to GitHub so Pi can pull the fresh model.

Run manually or on a schedule (e.g., daily at 9 AM or 3 days before month-end).

Usage:
    python scripts/check_and_refresh_signals.py              # check + rebuild stale
    python scripts/check_and_refresh_signals.py --dry-run    # check only, no rebuild
    python scripts/check_and_refresh_signals.py --force      # rebuild all regardless
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = REPO_ROOT / "outputs" / "live"
MIN_ANCHOR_AGE_DAYS = 7

ASSET_CONFIGS = {
    "GLD": {
        "slug": "gld",
        "data_csv": REPO_ROOT / "data" / "gld_us_d.csv",
        "anchor_output_root": REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation",
        "build_signal_on_pi": True,
    },
    "BRK-B": {
        "slug": "brkb",
        "data_csv": REPO_ROOT / "data" / "brkb_us_d.csv",
        "anchor_output_root": REPO_ROOT / "outputs" / "brkb" / "anchor_snapshots",
        "build_signal_on_pi": True,
    },
    "QQQ": {
        "slug": "qqq",
        "data_csv": REPO_ROOT / "data" / "qqq_us_d.csv",
        "anchor_output_root": REPO_ROOT / "models" / "pi_reference" / "QQQ",
        "build_signal_on_pi": True,
    },
    "RKLB": {
        "slug": "rklb",
        "data_csv": REPO_ROOT / "data" / "rklb_us_d.csv",
        "anchor_output_root": REPO_ROOT / "models" / "pi_reference" / "RKLB",
        "build_signal_on_pi": True,
    },
    # --- forward test candidates (pending_review) ---
    "ITA": {
        "slug": "ita",
        "data_csv": REPO_ROOT / "data" / "ita_us_d.csv",
        "anchor_output_root": REPO_ROOT / "outputs" / "ita" / "anchor_snapshots",
        "build_signal_on_pi": False,
    },
    "VRT": {
        "slug": "vrt",
        "data_csv": REPO_ROOT / "data" / "vrt_us_d.csv",
        "anchor_output_root": REPO_ROOT / "outputs" / "vrt" / "anchor_snapshots",
        "build_signal_on_pi": False,
    },
}


def find_latest_valid_anchor(anchor_root: Path, cutoff: date) -> str | None:
    if not anchor_root.exists():
        return None
    candidates = sorted(
        [d.name.replace("anchor_", "") for d in anchor_root.iterdir()
         if d.is_dir() and d.name.startswith("anchor_")
         and (anchor_root / d.name / "optimization_outputs").exists()],
        reverse=True,
    )
    valid = [a for a in candidates if a <= str(cutoff)]
    return valid[0] if valid else None


def read_signal_anchor(slug: str) -> tuple[str | None, str | None]:
    path = LIVE_DIR / f"latest_{slug}_signal.json"
    if not path.exists():
        return None, None
    with open(path) as f:
        sig = json.load(f)
    return sig.get("active_anchor_date"), sig.get("asof_date")


def update_data(symbol: str, cfg: dict) -> bool:
    """Fill missing price data before rebuilding signal."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "jobs" / "update_daily_price_data.py"),
         "--symbol", symbol, "--data-csv", str(cfg["data_csv"]), "--max-staleness-days", "1"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  [{symbol}] data update warning: {result.stderr[-200:]}")
    return True


def rebuild_signal(symbol: str, cfg: dict) -> bool:
    print(f"  [{symbol}] Updating price data...")
    update_data(symbol, cfg)

    print(f"  [{symbol}] Rebuilding signal...")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "strategies" / "automation" / "run_objective2_latest_live_signal.py"),
        "--symbol", symbol,
        "--data-csv", str(cfg["data_csv"]),
        "--anchor-output-root", str(cfg["anchor_output_root"]),
        "--target-horizon-days", "130",
        "--top-n-per-family", "20",
        "--selection-criterion", "selection_cv_mse",
        "--update-interval-months", "1",
    ]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [{symbol}] ERROR: {result.stderr[-500:]}")
        return False
    anchor, asof = read_signal_anchor(cfg["slug"])
    print(f"  [{symbol}] Done  anchor={anchor}, asof={asof}")
    return True


def git_push(symbols: list[str]) -> None:
    files = []
    for sym in symbols:
        slug = ASSET_CONFIGS[sym]["slug"]
        for fname in [f"latest_{slug}_signal.json", f"history/{slug}_signal_log.csv"]:
            p = LIVE_DIR / fname
            if p.exists():
                files.append(str(p.relative_to(REPO_ROOT)))

    if not files:
        print("[git] No files to push.")
        return

    subprocess.run(["git", "add"] + files, cwd=str(REPO_ROOT), check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(REPO_ROOT))
    if diff.returncode == 0:
        print("[git] Nothing changed — skip push.")
        return

    msg = f"Auto: refresh signals {date.today()} — {','.join(symbols)}"
    subprocess.run(["git", "commit", "-m", msg], cwd=str(REPO_ROOT), check=True)
    subprocess.run(["git", "push"], cwd=str(REPO_ROOT), check=True)
    print(f"[git] Pushed: {', '.join(symbols)}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Check only, no rebuild")
    p.add_argument("--force", action="store_true", help="Rebuild all assets regardless")
    p.add_argument("--symbols", default=None, help="Comma-separated subset, e.g. GLD,QQQ")
    args = p.parse_args()

    today = date.today()
    cutoff = today - timedelta(days=MIN_ANCHOR_AGE_DAYS)
    print(f"Signal freshness check  today={today}, 7-day cutoff={cutoff}")
    print("=" * 60)

    target = list(ASSET_CONFIGS.keys())
    if args.symbols:
        target = [s.strip().upper() for s in args.symbols.split(",")]

    stale: list[str] = []
    for sym in target:
        cfg = ASSET_CONFIGS[sym]
        cur_anchor, asof = read_signal_anchor(cfg["slug"])
        best = find_latest_valid_anchor(cfg["anchor_output_root"], cutoff)
        status = "OK" if cur_anchor == best else "STALE"
        print(f"  {sym:<8} current={cur_anchor or 'NONE':<12} best={best or 'NONE':<12} [{status}]")
        if status == "STALE" or args.force:
            stale.append(sym)

    print()
    if not stale:
        print("All signals up-to-date. Nothing to do.")
        return

    if args.dry_run:
        print(f"[DRY RUN] Would rebuild: {stale}")
        return

    print(f"Rebuilding: {stale}")
    rebuilt = []
    for sym in stale:
        if rebuild_signal(sym, ASSET_CONFIGS[sym]):
            rebuilt.append(sym)

    if rebuilt:
        print()
        git_push(rebuilt)
    else:
        print("No signals were rebuilt successfully.")


if __name__ == "__main__":
    main()
