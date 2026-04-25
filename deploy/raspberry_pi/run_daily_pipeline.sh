#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

# Load env vars
set -a
source "${ENV_FILE}"
set +a

# Run pipeline
"${VENV_PYTHON}" "${REPO_ROOT}/jobs/gld_daily_pipeline.py" --build-signal

# Push updated data and signal to GitHub
cd "${REPO_ROOT}"
git add data/gld_us_d.csv \
        outputs/live/latest_gld_signal.json \
        outputs/live/history/gld_signal_log.csv

if git diff --cached --quiet; then
    echo "[skip] Nothing new to push"
else
    git commit -m "Auto: daily GLD data + signal $(date +%Y-%m-%d)"
    git push
    echo "[OK] Pushed to GitHub"
fi
