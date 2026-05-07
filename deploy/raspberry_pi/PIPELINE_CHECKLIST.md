# Quant Daily Pipeline Raspberry Pi Checklist

This checklist assumes the repository is cloned at:

```bash
/home/pi/quant-trading-system
```

## 1. Pull Latest Code

```bash
cd /home/pi/quant-trading-system
git pull --ff-only
```

For normal operation, this pull should include the latest committed live model manifest/artifact bundle from the modeling machine:

```bash
models/live/latest_model_manifest.json
models/live/
```

The Raspberry Pi uses those files as inputs, refreshes its own daily market data, and builds the live signal locally.

## 1A. Modeling Machine Model Handoff

Run this on the main modeling computer before the Raspberry Pi daily run:

```bash
python strategies/automation/run_objective2_latest_live_signal.py --help
git add models/live/latest_model_manifest.json models/live/
git commit -m "Update live model artifacts"
git push
```

Keep research datasets, optimization outputs, figures, and workstation-only analysis folders local. Then the Raspberry Pi can receive the latest model handoff with `git pull --ff-only`.

## 2. First-Time Install

Run this only the first time, or when rebuilding the Raspberry Pi environment.

```bash
cd /home/pi/quant-trading-system
bash deploy/raspberry_pi/install_pipeline.sh
```

This creates:

- `/home/pi/quant-trading-system/.venv`
- `/home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env`
- `quant-pipeline.service`
- `quant-pipeline.timer`
- `quant-order-execution.service`
- `quant-order-execution.timer`

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
LIVE_MODEL_MANIFEST=models/live/latest_model_manifest.json
REQUIRE_LIVE_MODEL_MANIFEST=false
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

Make sure the modeling machine has already generated and synced, or intentionally omitted for fallback testing:

```bash
models/live/latest_model_manifest.json
```

Then run the Raspberry Pi operating pipeline manually:

```bash
cd /home/pi/quant-trading-system
/home/pi/quant-trading-system/.venv/bin/python jobs/live_daily_pipeline.py --build-signal --skip-orders --symbols GLD,BRK-B
```

Expected result:

- latest model artifacts are pulled
- missing GLD/BRK-B daily rows are refreshed
- fresh GLD/BRK-B live signals are rebuilt
- signal preparation runs without placing orders

Check outputs:

```bash
ls -lt outputs/live | head
cat outputs/live/latest_gld_signal.json
cat outputs/live/latest_brkb_signal.json
```

## 5. Optional Email Dry Run

After the manual pipeline creates signal/order payloads:

```bash
cd /home/pi/quant-trading-system
/home/pi/quant-trading-system/.venv/bin/python jobs/send_live_daily_report.py --dry-run
```

If the preview looks good, configure SMTP in `quant-trading.env`.

Then set:

```bash
EMAIL_ALERT_ENABLED=true
```

## 6. Start Systemd Timer

```bash
sudo systemctl daemon-reload
sudo systemctl enable quant-pipeline.timer
sudo systemctl enable quant-order-execution.timer
sudo systemctl start quant-pipeline.timer
sudo systemctl start quant-order-execution.timer
```

Check timer:

```bash
sudo systemctl status quant-pipeline.timer
systemctl list-timers --all | grep quant-pipeline
```

The signal-prep timer is configured for weekdays at `12:45:00` Pacific Time. The order-execution timer is configured for `13:00:05`.

## 7. Run Service Immediately Through Systemd

Use this to test the exact systemd service environment:

```bash
sudo systemctl start quant-pipeline.service
sudo systemctl status quant-pipeline.service
```

Follow logs:

```bash
journalctl -u quant-pipeline.service -n 100 --no-pager
journalctl -u quant-pipeline.service -f
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
ls -lt outputs/live/delta_tranche_*.json | head
```

## 9. Update After New GitHub Push

When new code is pushed from the main computer:

```bash
cd /home/pi/quant-trading-system
bash deploy/raspberry_pi/update_pipeline.sh
```

This will:

- pull latest code
- update Python packages
- refresh systemd unit files
- restart the timers
- run one pipeline test using the existing latest signal

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
sudo systemctl restart quant-pipeline.timer
sudo systemctl restart quant-order-execution.timer
sudo systemctl start quant-order-execution.service
```

## Emergency Stop

Stop scheduled runs:

```bash
sudo systemctl stop quant-pipeline.timer
sudo systemctl stop quant-order-execution.timer
sudo systemctl disable quant-pipeline.timer
sudo systemctl disable quant-order-execution.timer
```

If a service is currently running:

```bash
sudo systemctl stop quant-pipeline.service
sudo systemctl stop quant-order-execution.service
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
