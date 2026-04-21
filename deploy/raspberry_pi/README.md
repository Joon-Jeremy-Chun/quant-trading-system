# Raspberry Pi Deployment

This folder contains a minimal `systemd` setup for running the trading bot on a Raspberry Pi.

## Files

- `quant-trading.service.example`
  - template for the Linux `systemd` service
- `quant-trading.env.example`
  - template for local environment variables
- `requirements-live.txt`
  - minimal Python packages needed for the GLD live pipeline
- `install_gld_pipeline.sh`
  - first-time Raspberry Pi setup helper
- `update_gld_pipeline.sh`
  - pull latest code and refresh the pipeline install
- `gld-close-order.service.example`
  - one-shot service for a GLD close-time order run
- `gld-close-order.timer.example`
  - timer template for running the GLD order job near `1:00 p.m. PT`
- `gld-daily-pipeline.service.example`
  - one-shot service for the full daily pipeline
- `gld-daily-pipeline.timer.example`
  - timer template for running the full pipeline near `1:00 p.m. PT`

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
bash deploy/raspberry_pi/install_gld_pipeline.sh
```

This script:

- installs `python3-venv` and `python3-pip`,
- creates `/home/pi/quant-trading-system/.venv`,
- installs the live pipeline dependencies,
- creates `quant-trading.env` if it does not exist,
- installs the `systemd` unit files,
- enables the pipeline timer.

After that, edit:

```bash
/home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env
```

and fill in:

- Alpaca paper keys
- email alert settings, if desired

## Install the Service

Copy the service template into `systemd`:

```bash
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.service.example \
        /etc/systemd/system/quant-trading.service
```

Reload `systemd`, enable startup, and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable quant-trading.service
sudo systemctl start quant-trading.service
```

## Useful Commands

Check service status:

```bash
sudo systemctl status quant-trading.service
```

Follow logs:

```bash
journalctl -u quant-trading.service -f
```

Stop the service:

```bash
sudo systemctl stop quant-trading.service
```

Restart after code changes:

```bash
sudo systemctl restart quant-trading.service
```

## Close-Time GLD Order Job

If you want a weekday close-time run for GLD, use the one-shot service and timer instead of the always-on service.

Copy the templates:

```bash
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/gld-close-order.service.example \
        /etc/systemd/system/gld-close-order.service
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/gld-close-order.timer.example \
        /etc/systemd/system/gld-close-order.timer
```

Reload `systemd`, enable the timer, and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gld-close-order.timer
sudo systemctl start gld-close-order.timer
```

Check timer status:

```bash
sudo systemctl status gld-close-order.timer
systemctl list-timers --all | grep gld-close-order
```

This timer is set for `13:00:05` Pacific Time on weekdays. That is intentionally just after the close rather than exactly `13:00:00`.

## Full Daily Pipeline

If you want the entire daily flow to run automatically in one step:

1. refresh local GLD daily data if stale,
2. build the latest Objective 2 signal,
3. submit or log the order payload,

use the pipeline service and timer instead.

Copy the templates:

```bash
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/gld-daily-pipeline.service.example \
        /etc/systemd/system/gld-daily-pipeline.service
sudo cp /home/pi/quant-trading-system/deploy/raspberry_pi/gld-daily-pipeline.timer.example \
        /etc/systemd/system/gld-daily-pipeline.timer
```

Reload and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gld-daily-pipeline.timer
sudo systemctl start gld-daily-pipeline.timer
```

Manual test:

```bash
sudo systemctl start gld-daily-pipeline.service
sudo systemctl status gld-daily-pipeline.service
```

The pipeline entrypoint currently points to:

```text
/home/pi/quant-trading-system/.venv/bin/python /home/pi/quant-trading-system/jobs/gld_daily_pipeline.py
```

## Current Live-Run Skeleton

The close-time template currently points to:

```text
/home/pi/quant-trading-system/.venv/bin/python /home/pi/quant-trading-system/jobs/gld_close_order_job.py
```

This script currently:

- reads Alpaca credentials from environment,
- fetches the latest GLD quote,
- reads a placeholder signal file from `outputs/live/latest_gld_signal.json`,
- and logs a dry-run or paper-order payload.

It is a safe skeleton first, not a final production order engine yet.

## Updating After `git pull`

After you push new code from your main machine, the Raspberry Pi refresh flow is:

```bash
cd /home/pi/quant-trading-system
bash deploy/raspberry_pi/update_gld_pipeline.sh
```

This script:

- runs `git pull --ff-only`
- refreshes Python packages in the local `.venv`
- recopies the `systemd` unit files
- reloads `systemd`
- restarts the daily timer
- runs one pipeline test immediately

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
python3 /home/pi/quant-trading-system/jobs/send_gld_email_alert.py --dry-run
```

## Notes

- Closing your SSH terminal or local Git Bash window will not stop the service.
- The Raspberry Pi keeps the process alive because `systemd` owns the process.
- If you change the actual bot entrypoint later, update the `ExecStart` line in the service file.
