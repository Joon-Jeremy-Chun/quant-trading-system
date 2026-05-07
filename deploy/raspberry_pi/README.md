# Raspberry Pi Deployment

This folder contains the `systemd` setup for running the live quant pipeline on a Raspberry Pi.

## Files

- `quant-trading.env.example`
  - template for local environment variables
- `requirements-live.txt`
  - minimal Python packages needed for the live pipeline
- `install_pipeline.sh`
  - first-time Raspberry Pi setup helper
- `update_pipeline.sh`
  - pull latest code and refresh the pipeline install
- `quant-order-execution.service.example`
  - one-shot service for a portfolio order execution and daily report
- `quant-order-execution.timer.example`
  - timer template for running the portfolio order job near `1:00 p.m. PT`
- `quant-pipeline.service.example`
  - one-shot service for the signal preparation pipeline
- `quant-pipeline.timer.example`
  - timer template for running the signal preparation pipeline at `12:45 p.m. PT`

## Recommended Layout on Raspberry Pi

Clone this repository to:

```text
/home/pi/quant-trading-system
```

Then create a real environment file:

```bash
cp /home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env.example \
   /home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env
```

Edit the copied file and fill in your Alpaca paper-trading credentials.

## Recommended First-Time Setup

The easiest path on Raspberry Pi is now:

```bash
cd /home/pi/quant-trading-system
bash deploy/raspberry_pi/install_pipeline.sh
```

This script:

- installs `python3-venv` and `python3-pip`,
- creates `/home/pi/quant-trading-system/.venv`,
- installs the live pipeline dependencies,
- creates `quant-trading.env` if it does not exist,
- installs the `systemd` unit files,
- enables the signal-prep and order-execution timers.

After that, edit:

```bash
/home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env
```

and fill in:

- Alpaca paper keys
- email alert settings, if desired

## Order Execution Service

Use this one-shot service and timer for weekday portfolio order execution and the daily email report.

Copy the templates:

```bash
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/quant-order-execution.service.example \
        /etc/systemd/system/quant-order-execution.service
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/quant-order-execution.timer.example \
        /etc/systemd/system/quant-order-execution.timer
```

Reload `systemd`, enable the timer, and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable quant-order-execution.timer
sudo systemctl start quant-order-execution.timer
```

Check timer status:

```bash
sudo systemctl status quant-order-execution.timer
systemctl list-timers --all | grep quant-order-execution
```

This timer is set for `13:00:05` Pacific Time on weekdays. That is intentionally just after the close rather than exactly `13:00:00`.

## Signal Preparation Pipeline

Use this one-shot service and timer to rebuild Pi-capable signals before order execution. It runs at `12:45 p.m. PT` and skips orders.

Copy the templates:

```bash
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/quant-pipeline.service.example \
        /etc/systemd/system/quant-pipeline.service
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/quant-pipeline.timer.example \
        /etc/systemd/system/quant-pipeline.timer
```

Reload and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable quant-pipeline.timer
sudo systemctl start quant-pipeline.timer
```

Manual test:

```bash
sudo systemctl start quant-pipeline.service
sudo systemctl status quant-pipeline.service
```

The pipeline entrypoint currently points to:

```text
/home/pi/quant-trading-system/deploy/raspberry_pi/run_daily_pipeline.sh
```

The Raspberry Pi signal-prep path pulls the latest repository state, refreshes missing daily data, and rebuilds GLD/BRK-B live signals from `models/pi_reference/`. Order execution is handled later by `run_order_execution.sh`. `git pull` failure and stale signal/data checks stop the trading path by default.

## GitHub Model Artifact Handoff

The normal production handoff is:

1. On the modeling machine, run research, update local datasets, evaluate
   candidates, and publish only the latest live model artifact bundle.

2. Commit and push only small handoff files:

```bash
git add models/live/latest_model_manifest.json models/live/
git commit -m "Update live model artifacts"
git push
```

3. On the Raspberry Pi, pull the latest repository state, refresh daily data
   independently, build today's signals, and run the operating pipeline:

```bash
cd /home/pi/quant-trading-system
git pull --ff-only
/home/pi/quant-trading-system/.venv/bin/python jobs/live_daily_pipeline.py --build-signal --skip-orders --symbols GLD,BRK-B
```

The generated `latest_gld_signal.json` and `latest_brkb_signal.json` are still written under `outputs/live/` for audit and email reporting. Full research datasets, optimization folders, and figures stay on the workstation and are not pushed to GitHub.

## Current Live-Run Path

The order-execution template currently points to:

```text
/home/pi/quant-trading-system/deploy/raspberry_pi/run_order_execution.sh
```

This script currently:

- validates GLD, BRK-B, QQQ, and RKLB live signals,
- normalizes portfolio weights,
- runs `jobs/execute_delta_tranche_orders.py`,
- sends `jobs/send_live_daily_report.py`,
- pushes small live logs back to GitHub.

## Updating After `git pull`

After you push new code from your main machine, the Raspberry Pi refresh flow is:

```bash
cd /home/pi/quant-trading-system
bash deploy/raspberry_pi/update_pipeline.sh
```

This script:

- runs `git pull --ff-only`
- refreshes Python packages in the local `.venv`
- recopies the `systemd` unit files
- reloads `systemd`
- restarts the signal-prep and order-execution timers
- runs one pipeline test immediately using the existing latest signal

## Current Order Rule Logic

The close-time order job now follows a more refined rule:

1. read the latest signal payload,
2. check data staleness and model age,
3. convert `target_weight` into a desired position size,
4. compare desired position vs current position,
5. submit only the delta order.

Key environment variables:

```bash
ALPACA_DRY_RUN=true
ALPACA_BASE_POSITION_QTY=10
ALPACA_MIN_WEIGHT_TO_OPEN=0.15
ALPACA_MIN_REBALANCE_QTY=1
MAX_DATASET_STALENESS_DAYS=7
MAX_MODEL_AGE_DAYS=540
BLOCK_ON_STALE_MODEL=false
```

This means the bot is no longer interpreting the signal as a raw order quantity. It is interpreting it as a target portfolio intensity and then converting that into a target share count.

## Email Alerts

The daily pipeline can also send an email summary after the order step.

Key environment variables:

```bash
EMAIL_ALERT_ENABLED=false
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=replace_with_your_email_username
SMTP_PASSWORD=replace_with_your_email_app_password
ALERT_EMAIL_FROM=replace_with_sender@example.com
ALERT_EMAIL_TO=replace_with_receiver@example.com
```

Recommended practice:

- use an app password rather than your normal mailbox password,
- keep `EMAIL_ALERT_ENABLED=false` until SMTP works on the Raspberry Pi,
- test locally with the dry-run preview:

```bash
python3 /home/pi/quant-trading-system/jobs/send_live_daily_report.py --dry-run
```

## Notes

- Closing your SSH terminal or local Git Bash window will not stop the service.
- The Raspberry Pi keeps the process alive because `systemd` owns the process.
- If you change the actual bot entrypoint later, update the `ExecStart` line in the service file.
