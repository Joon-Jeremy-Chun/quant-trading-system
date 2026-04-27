#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

# Load env vars
set -a
source "${ENV_FILE}"
set +a

# Run pipeline (signal is built on Windows and synced via GitHub; Pi just pulls and uses it)
"${VENV_PYTHON}" "${REPO_ROOT}/jobs/gld_daily_pipeline.py"

# Push updated tranche book data to GitHub (signal JSON comes from Windows, not Pi)
cd "${REPO_ROOT}"
git add outputs/live/history/gld_signal_log.csv \
        data/gld_us_d.csv

if git diff --cached --quiet; then
    echo "[skip] Nothing new to push"
else
    git commit -m "Auto: daily order log $(date +%Y-%m-%d)"
    git push
    echo "[OK] Pushed to GitHub"
fi
