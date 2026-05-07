#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/home/pi/quant-trading-system}"
VENV_DIR="${REPO_ROOT}/.venv"
REQ_FILE="${REPO_ROOT}/deploy/raspberry_pi/requirements-live.txt"

echo "==> Pulling latest code"
git -C "${REPO_ROOT}" pull --ff-only

echo "==> Updating Python dependencies"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${REQ_FILE}"

echo "==> Refreshing systemd unit files"
sudo cp "${REPO_ROOT}/deploy/raspberry_pi/quant-pipeline.service.example" /etc/systemd/system/quant-pipeline.service
sudo cp "${REPO_ROOT}/deploy/raspberry_pi/quant-pipeline.timer.example" /etc/systemd/system/quant-pipeline.timer
sudo cp "${REPO_ROOT}/deploy/raspberry_pi/quant-order-execution.service.example" /etc/systemd/system/quant-order-execution.service
sudo cp "${REPO_ROOT}/deploy/raspberry_pi/quant-order-execution.timer.example" /etc/systemd/system/quant-order-execution.timer
sudo systemctl daemon-reload
sudo systemctl restart quant-pipeline.timer
sudo systemctl restart quant-order-execution.timer

echo "==> Running pipeline check with existing latest signal"
"${VENV_DIR}/bin/python" "${REPO_ROOT}/jobs/live_daily_pipeline.py" --skip-orders

echo "==> Update complete"
