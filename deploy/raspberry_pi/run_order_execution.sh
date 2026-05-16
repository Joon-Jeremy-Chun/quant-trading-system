#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

# Load env vars
set -a
source "${ENV_FILE}"
set +a

# Read live symbols from active_universe.json (single source of truth).
LIVE_SYMBOLS=$("${VENV_PYTHON}" -c "
import json, pathlib, sys
try:
    u = json.loads(pathlib.Path('${REPO_ROOT}/models/live_assets/active_universe.json').read_text())
    print(','.join(u.get('assets', [])))
except Exception as e:
    print(f'[ERROR] Cannot read active_universe.json: {e}', file=sys.stderr)
    sys.exit(1)
")
echo "[1PM] Live symbols: ${LIVE_SYMBOLS}"

# Phase 2 (runs at 1:00 PM PT): fetch today's Alpaca close → rebuild signals → orders + email.
#
# Step 1: git pull (latest QQQ/RKLB signals from Windows push)
cd "${REPO_ROOT}" && git pull

# Step 2: fetch today's close from Alpaca and append to price CSVs.
# Alpaca gives today's confirmed close at 1 PM PT (4 PM ET market close).
# This avoids yfinance's EOD delay and ensures asof_date = today.
echo "[1PM] Fetching today's close from Alpaca..."
"${VENV_PYTHON}" "${REPO_ROOT}/scripts/fetch_alpaca_close.py" \
  --symbols "${LIVE_SYMBOLS}"

# Step 3: rebuild all signals with today's Alpaca close price.
# --force-rebuild-signal bypasses the "signal_already_fresh_for_today" skip
# so 12:45's signal is always overwritten with today's confirmed Alpaca close.
echo "[1PM] Rebuilding all signals with today's close..."
"${VENV_PYTHON}" "${REPO_ROOT}/jobs/live_daily_pipeline.py" \
  --build-signal --skip-orders \
  --symbols "${LIVE_SYMBOLS}" \
  --top-n-per-family 20 \
  --max-staleness-days 0 \
  --force-rebuild-signal

# Step 4: execute orders + send email (simultaneously in same run).
echo "[1PM] Executing orders and sending email..."
"${VENV_PYTHON}" "${REPO_ROOT}/jobs/live_daily_pipeline.py" \
  --symbols "${LIVE_SYMBOLS}"

# Push live execution records to GitHub.
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

# Safety: never auto-commit data CSVs (large files, conflict-prone)
git restore --staged data/ 2>/dev/null || true

if git diff --cached --quiet; then
    echo "[skip] Nothing new to push"
else
    git commit -m "Auto: daily order log $(date +%Y-%m-%d)"
    git push
    echo "[OK] Pushed to GitHub"
fi
