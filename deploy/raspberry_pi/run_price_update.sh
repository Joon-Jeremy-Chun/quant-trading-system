#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

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
echo "[price-update] Live symbols: ${LIVE_SYMBOLS}"

# Runs at 09:05 AM PT (after git pull at 09:00).
# Step 1: sync registry -> execution folder (detects new monthly anchor from Windows)
echo "[registry-sync] Checking for new anchors..."
"${VENV_PYTHON}" "${REPO_ROOT}/scripts/sync_registry_to_execution.py" || echo "[warn] registry sync failed, continuing"

# Step 2: update price CSVs for all live assets
IFS=',' read -ra SYMBOLS <<< "${LIVE_SYMBOLS}"
for SYMBOL in "${SYMBOLS[@]}"; do
    SLUG=$(echo "${SYMBOL}" | tr '[:upper:]' '[:lower:]' | tr -d '-')
    CSV="${REPO_ROOT}/data/${SLUG}_us_d.csv"
    echo "[price-update] ${SYMBOL} ..."
    "${VENV_PYTHON}" "${REPO_ROOT}/jobs/update_daily_price_data.py" \
        --symbol "${SYMBOL}" \
        --data-csv "${CSV}" \
        --max-staleness-days 1 || echo "[warn] ${SYMBOL} update failed, continuing"
done

# Step 3: validate all price CSVs — fail hard if missing or stale (>5 days).
# 5-day threshold covers weekends (Mon = Fri+3d) with 2d buffer.
FAIL=0
for SYMBOL in "${SYMBOLS[@]}"; do
    SLUG=$(echo "${SYMBOL}" | tr '[:upper:]' '[:lower:]' | tr -d '-')
    CSV="${REPO_ROOT}/data/${SLUG}_us_d.csv"
    if [[ ! -f "${CSV}" ]]; then
        echo "[ERROR] ${SYMBOL} CSV missing: ${CSV}"
        FAIL=1
        continue
    fi
    LATEST=$(tail -1 "${CSV}" | cut -d',' -f1)
    DATE_STATUS=$("${VENV_PYTHON}" -c "
from datetime import date
try:
    latest = date.fromisoformat('${LATEST}')
    gap = (date.today() - latest).days
    print('OK' if gap <= 5 else f'STALE:{gap}d')
except Exception as e:
    print(f'ERR:{e}')
")
    if [[ "${DATE_STATUS}" == "OK" ]]; then
        echo "[OK] ${SYMBOL} CSV latest: ${LATEST}"
    else
        echo "[ERROR] ${SYMBOL} CSV date check failed: latest=${LATEST} status=${DATE_STATUS}"
        FAIL=1
    fi
done
if [[ "${FAIL}" -eq 1 ]]; then
    echo "[FATAL] Price CSV validation failed — aborting"
    exit 1
fi

# Step 4: commit new execution_meta.json files to GitHub.
# These are written once per anchor by sync_registry_to_execution.py.
# Committing them ensures forensic trace survives Pi SD card failure.
for meta in "${REPO_ROOT}"/models/pi_reference/*/anchor_*/execution_meta.json; do
    if [[ -f "${meta}" ]]; then
        git -C "${REPO_ROOT}" add "${meta}"
    fi
done
git -C "${REPO_ROOT}" restore --staged data/ 2>/dev/null || true
if git -C "${REPO_ROOT}" diff --cached --quiet; then
    echo "[forensic] No new execution_meta.json to commit"
else
    git -C "${REPO_ROOT}" commit -m "Auto: forensic meta — anchor synced $(date +%Y-%m-%d)"
    git -C "${REPO_ROOT}" push
    echo "[forensic] Committed and pushed execution_meta.json"
fi

echo "[price-update] Done — $(date)"
