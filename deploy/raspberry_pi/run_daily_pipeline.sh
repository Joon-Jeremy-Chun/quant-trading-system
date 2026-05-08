#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

# Load env vars
set -a
source "${ENV_FILE}"
set +a

# Phase 1 (runs at 12:45 PM PT): rebuild signals for Pi-capable assets only, no orders.
# git pull is handled inside live_daily_pipeline.py as the first step.
# GLD/BRK-B: Pi has optimization_outputs in models/pi_reference/ → build locally.
# QQQ/RKLB: build_signal_on_pi=false → signals come from Windows via git push.
# Phase 2 (runs at 1:00 PM PT via run_order_execution.sh): pull + validate all 4 + orders + email.
"${VENV_PYTHON}" "${REPO_ROOT}/jobs/live_daily_pipeline.py" \
  --build-signal \
  --skip-orders \
  --symbols GLD,BRK-B \
  --top-n-per-family 20 \
  --max-staleness-days 1

# Push only small live execution records to GitHub.
stage_if_exists() {
    for path in "$@"; do
        if [[ -e "${path}" ]]; then
            git add "${path}"
        fi
    done
}

stage_if_exists \
    outputs/live/history/gld_signal_log.csv \
    outputs/live/history/brkb_signal_log.csv \
    outputs/live/history/qqq_signal_log.csv \
    outputs/live/history/rklb_signal_log.csv \
    outputs/live/latest_gld_signal.json \
    outputs/live/latest_brkb_signal.json \
    outputs/live/latest_qqq_signal.json \
    outputs/live/latest_rklb_signal.json

for path in outputs/live/tranche_book_*.json outputs/live/*_tranche_order_*.json; do
    if [[ -e "${path}" ]]; then
        git add "${path}"
    fi
done

if git diff --cached --quiet; then
    echo "[skip] Nothing new to push"
else
    git commit -m "Auto: daily order log $(date +%Y-%m-%d)"
    git push
    echo "[OK] Pushed to GitHub"
fi
