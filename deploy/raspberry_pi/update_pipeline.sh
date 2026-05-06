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
sudo cp "${REPO_ROOT}/deploy/raspberry_pi/gld-daily-pipeline.service.example" /etc/systemd/system/gld-daily-pipeline.service
sudo cp "${REPO_ROOT}/deploy/raspberry_pi/gld-daily-pipeline.timer.example" /etc/systemd/system/gld-daily-pipeline.timer
sudo systemctl daemon-reload
sudo systemctl restart gld-daily-pipeline.timer

echo "==> Running pipeline check with existing latest signal"
"${VENV_DIR}/bin/python" "${REPO_ROOT}/jobs/daily_pipeline.py"

echo "==> Update complete"
