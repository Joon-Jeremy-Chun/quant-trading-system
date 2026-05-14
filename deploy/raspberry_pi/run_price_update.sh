#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

set -a
source "${ENV_FILE}"
set +a

# Runs at 09:05 AM PT (after git pull at 09:00).
# Step 1: sync registry -> execution folder (detects new monthly anchor from Windows)
echo "[registry-sync] Checking for new anchors..."
"${VENV_PYTHON}" "${REPO_ROOT}/scripts/sync_registry_to_execution.py" || echo "[warn] registry sync failed, continuing"

# Step 2: update price CSVs for all live assets
for SYMBOL in GLD BRK-B QQQ RKLB; do
    SLUG=$(echo "${SYMBOL}" | tr '[:upper:]' '[:lower:]' | tr -d '-')
    CSV="${REPO_ROOT}/data/${SLUG}_us_d.csv"
    echo "[price-update] ${SYMBOL} ..."
    "${VENV_PYTHON}" "${REPO_ROOT}/jobs/update_daily_price_data.py" \
        --symbol "${SYMBOL}" \
        --data-csv "${CSV}" \
        --max-staleness-days 1 || echo "[warn] ${SYMBOL} update failed, continuing"
done

echo "[price-update] Done — $(date)"
