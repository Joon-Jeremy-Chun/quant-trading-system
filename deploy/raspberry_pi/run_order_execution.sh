#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

# Load env vars
set -a
source "${ENV_FILE}"
set +a

# Phase 2 (runs at 1:00 PM PT): signal already fresh from 12:45 prep.
# Validates freshness, normalizes weights, places limit orders, sends email.
"${VENV_PYTHON}" "${REPO_ROOT}/jobs/live_daily_pipeline.py" \
  --symbols GLD,BRK-B,QQQ,RKLB

# Push live execution records to GitHub.
cd "${REPO_ROOT}"
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
    outputs/live/latest_rklb_signal.json \
    outputs/live/tranche_log.csv

for path in outputs/live/delta_tranche_*.json outputs/live/tranche_book_*.json outputs/live/*_tranche_order_*.json; do
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
