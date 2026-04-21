# GLD Daily Pipeline Raspberry Pi Checklist

This checklist assumes the repository is cloned at:

```bash
/home/pi/quant-trading-system
```

## 1. Pull Latest Code

```bash
cd /home/pi/quant-trading-system
git pull --ff-only
```

## 2. First-Time Install

Run this only the first time, or when rebuilding the Raspberry Pi environment.

```bash
cd /home/pi/quant-trading-system
bash deploy/raspberry_pi/install_gld_pipeline.sh
```

This creates:

- `/home/pi/quant-trading-system/.venv`
- `/home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env`
- `gld-daily-pipeline.service`
- `gld-daily-pipeline.timer`

## 3. Fill Environment Variables

Open the local env file:

```bash
nano /home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env
```

Minimum Alpaca paper-trading settings:

```bash
APCA_API_KEY_ID=your_key_here
APCA_API_SECRET_KEY=your_secret_here
ALPACA_DRY_RUN=true
```

Recommended first-run safety settings:

```bash
ALPACA_DRY_RUN=true
ALPACA_BASE_POSITION_QTY=10
ALPACA_MIN_WEIGHT_TO_OPEN=0.15
ALPACA_MIN_REBALANCE_QTY=1
MAX_DATASET_STALENESS_DAYS=7
MAX_MODEL_AGE_DAYS=540
BLOCK_ON_STALE_MODEL=false
EMAIL_ALERT_ENABLED=false
```

Keep `ALPACA_DRY_RUN=true` until the pipeline, logs, and email alerts are verified.

## 4. Manual Pipeline Test

Run the daily pipeline manually:

```bash
cd /home/pi/quant-trading-system
/home/pi/quant-trading-system/.venv/bin/python jobs/gld_daily_pipeline.py
```

Expected result:

- data update step runs
- latest signal file is created or updated
- order job logs a dry-run payload
- email step is skipped if email is disabled

Check outputs:

```bash
ls -lt outputs/live | head
cat outputs/live/latest_gld_signal.json
```

## 5. Optional Email Dry Run

After the manual pipeline creates signal/order payloads:

```bash
cd /home/pi/quant-trading-system
/home/pi/quant-trading-system/.venv/bin/python jobs/send_gld_email_alert.py --dry-run
```

If the preview looks good, configure SMTP in `quant-trading.env`.

Then set:

```bash
EMAIL_ALERT_ENABLED=true
```

## 6. Start Systemd Timer

```bash
sudo systemctl daemon-reload
sudo systemctl enable gld-daily-pipeline.timer
sudo systemctl start gld-daily-pipeline.timer
```

Check timer:

```bash
sudo systemctl status gld-daily-pipeline.timer
systemctl list-timers --all | grep gld-daily-pipeline
```

The timer is configured for weekdays at `13:00:05` Pacific Time.

## 7. Run Service Immediately Through Systemd

Use this to test the exact systemd service environment:

```bash
sudo systemctl start gld-daily-pipeline.service
sudo systemctl status gld-daily-pipeline.service
```

Follow logs:

```bash
journalctl -u gld-daily-pipeline.service -n 100 --no-pager
journalctl -u gld-daily-pipeline.service -f
```

## 8. Daily Monitoring

Useful daily checks:

```bash
cd /home/pi/quant-trading-system
ls -lt outputs/live | head
ls -lt outputs/live/history | head
tail -n 5 outputs/live/history/gld_signal_log.csv
```

Check latest order payload:

```bash
ls -lt outputs/live/gld_close_order_job_*.json | head
```

## 9. Update After New GitHub Push

When new code is pushed from the main computer:

```bash
cd /home/pi/quant-trading-system
bash deploy/raspberry_pi/update_gld_pipeline.sh
```

This will:

- pull latest code
- update Python packages
- refresh systemd unit files
- restart the timer
- run one pipeline test

## 10. Enable Paper Orders Later

Only after several dry-run days:

```bash
nano /home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env
```

Change:

```bash
ALPACA_DRY_RUN=false
```

Then reload/restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart gld-daily-pipeline.timer
sudo systemctl start gld-daily-pipeline.service
```

## Emergency Stop

Stop scheduled runs:

```bash
sudo systemctl stop gld-daily-pipeline.timer
sudo systemctl disable gld-daily-pipeline.timer
```

If a service is currently running:

```bash
sudo systemctl stop gld-daily-pipeline.service
```

## Recommended Operating Rule

Start in this order:

1. `ALPACA_DRY_RUN=true`
2. email disabled
3. manual pipeline test
4. systemd service test
5. timer enabled
6. several dry-run trading days
7. email enabled
8. paper orders enabled

