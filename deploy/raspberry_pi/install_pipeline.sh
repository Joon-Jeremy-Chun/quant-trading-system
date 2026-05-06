#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/home/pi/quant-trading-system}"
ENV_FILE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env"
ENV_EXAMPLE="${REPO_ROOT}/deploy/raspberry_pi/quant-trading.env.example"
VENV_DIR="${REPO_ROOT}/.venv"
REQ_FILE="${REPO_ROOT}/deploy/raspberry_pi/requirements-live.txt"

echo "==> Installing OS packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip

echo "==> Creating virtual environment"
python3 -m venv "${VENV_DIR}"

echo "==> Installing Python dependencies"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${REQ_FILE}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "==> Creating local env file from example"
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  echo "Fill in ${ENV_FILE} before enabling live orders or email alerts."
fi

echo "==> Installing systemd service and timer"
sudo cp "${REPO_ROOT}/deploy/raspberry_pi/gld-daily-pipeline.service.example" /etc/systemd/system/gld-daily-pipeline.service
sudo cp "${REPO_ROOT}/deploy/raspberry_pi/gld-daily-pipeline.timer.example" /etc/systemd/system/gld-daily-pipeline.timer
sudo systemctl daemon-reload
sudo systemctl enable gld-daily-pipeline.timer

echo "==> Installation complete"
echo "Next recommended steps:"
echo "  1. Edit ${ENV_FILE}"
echo "  2. Test: ${VENV_DIR}/bin/python ${REPO_ROOT}/jobs/daily_pipeline.py"
echo "  3. Start timer: sudo systemctl start gld-daily-pipeline.timer"
