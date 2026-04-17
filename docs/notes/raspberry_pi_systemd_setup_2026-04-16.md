# Raspberry Pi Systemd Setup

Date: 2026-04-16

## Purpose

This note records the basic deployment pattern for running the trading bot continuously on a Raspberry Pi.

The intended workflow is:

1. develop and backtest on the local machine,
2. push code to GitHub,
3. pull the repo onto the Raspberry Pi,
4. keep secrets only on the Raspberry Pi,
5. let `systemd` manage the live or paper-trading process.

## Why `systemd`

Using `systemd` means:

- the process keeps running after the SSH session closes,
- the process can restart automatically if it crashes,
- the bot can start automatically when the Raspberry Pi reboots,
- logs can be checked with `journalctl`.

## Repo Files Added

- [quant-trading.service.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/quant-trading.service.example)
- [quant-trading.env.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/quant-trading.env.example)
- [README.md](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/README.md)
- [gld-close-order.service.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/gld-close-order.service.example)
- [gld-close-order.timer.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/gld-close-order.timer.example)
- [gld_close_order_job.py](/C:/Users/joonc/My_github/quant-trading-system/jobs/gld_close_order_job.py)
- [gld-daily-pipeline.service.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/gld-daily-pipeline.service.example)
- [gld-daily-pipeline.timer.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/gld-daily-pipeline.timer.example)
- [gld_daily_pipeline.py](/C:/Users/joonc/My_github/quant-trading-system/jobs/gld_daily_pipeline.py)

## Current Default Entrypoint

The template currently points to:

- [trade_job.py](/C:/Users/joonc/My_github/quant-trading-system/jobs/trade_job.py)

This is only the current default. If the real live-trading script changes later, the `ExecStart` line should be updated accordingly.

For a close-time GLD run, the new one-shot timer/service pair points to:

- [gld_close_order_job.py](/C:/Users/joonc/My_github/quant-trading-system/jobs/gld_close_order_job.py)

The timer is set to run at `13:00:05` Pacific Time on weekdays. That is slightly safer than exact `13:00:00` because the final close-adjacent quote update has a moment to arrive.

For a fuller deployment flow, the daily pipeline can now be used instead:

1. update local GLD daily data if stale,
2. compute the latest Objective 2 live signal,
3. create a dry-run or paper-order payload.

That orchestration is handled by:

- [gld_daily_pipeline.py](/C:/Users/joonc/My_github/quant-trading-system/jobs/gld_daily_pipeline.py)

## Important Security Rule

The repository stores only the example environment file.

The real credential file should exist only on the Raspberry Pi:

```text
/home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env
```

That file should not be committed to GitHub.
