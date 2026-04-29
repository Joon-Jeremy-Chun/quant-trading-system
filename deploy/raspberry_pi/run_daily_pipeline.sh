#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

# Load env vars
set -a
source "${ENV_FILE}"
set +a

# Run pipeline. The Pi pulls the latest model manifest/artifacts, refreshes
# its own daily market data, rebuilds today's signals, then places/logs orders.
"${VENV_PYTHON}" "${REPO_ROOT}/jobs/gld_daily_pipeline.py" --build-signal --symbols GLD,BRK-B

# Push only small live execution records to GitHub. Research data, figures, and
# workstation analysis outputs stay local and are reproduced independently.
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
    outputs/live/latest_gld_signal.json \
    outputs/live/latest_brkb_signal.json

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
