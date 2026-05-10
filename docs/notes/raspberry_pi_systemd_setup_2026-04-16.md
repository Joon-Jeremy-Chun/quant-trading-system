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

- [quant-trading.env.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/quant-trading.env.example)
- [README.md](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/README.md)
- [quant-order-execution.service.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/quant-order-execution.service.example)
- [quant-order-execution.timer.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/quant-order-execution.timer.example)
- [quant-pipeline.service.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/quant-pipeline.service.example)
- [quant-pipeline.timer.example](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/quant-pipeline.timer.example)
- [live_daily_pipeline.py](/C:/Users/joonc/My_github/quant-trading-system/jobs/live_daily_pipeline.py)

## Current Default Entrypoint

The active templates currently point to:

- [run_daily_pipeline.sh](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/run_daily_pipeline.sh)
- [run_order_execution.sh](/C:/Users/joonc/My_github/quant-trading-system/deploy/raspberry_pi/run_order_execution.sh)

The timer is set to run at `13:00:05` Pacific Time on weekdays. That is slightly safer than exact `13:00:00` because the final close-adjacent quote update has a moment to arrive.

The fuller deployment flow now:

1. updates local daily data if stale,
2. computes the latest Objective 2 live signal,
3. validates signals,
4. runs delta-tranche order execution and daily reporting.

That orchestration is handled by:

- [live_daily_pipeline.py](/C:/Users/joonc/My_github/quant-trading-system/jobs/live_daily_pipeline.py)

## Important Security Rule

The repository stores only the example environment file.

The real credential file should exist only on the Raspberry Pi:

```text
/home/pi/quant-trading-system/deploy/raspberry_pi/quant-trading.env
```

That file should not be committed to GitHub.
