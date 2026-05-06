"""
trade_job.py  —  Stage A: Signal & Delta Viewer

Stage A role: shows HOW the system reads a live signal and computes today's order.
Stage B (production): daily_pipeline.py runs delta_tranche_job.py automatically at 1:00 PM PT.

What this does:
  1. Reads today's live signal for each asset (outputs/live/latest_<slug>_signal.json)
  2. Reads the tranche log to find the weight 130 days ago
  3. Computes delta = (today_weight - past_weight) / 130 * CAPITAL
  4. Prints what order WOULD be placed (does NOT submit to Alpaca)

This is a read-only viewer — no orders are placed.
To place real orders: daily_pipeline.py calls delta_tranche_job.py.

Usage:
    python jobs/trade_job.py
    python jobs/trade_job.py --capital 10000
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT     = Path(__file__).resolve().parents[1]
LIVE_DIR      = REPO_ROOT / "outputs" / "live"
LOG_PATH      = LIVE_DIR / "tranche_log.csv"
UNIVERSE_PATH = REPO_ROOT / "models" / "live_assets" / "active_universe.json"
HORIZON       = 130


def load_universe() -> list[str]:
    with open(UNIVERSE_PATH) as f:
        return [s.upper() for s in json.load(f)["assets"]]


def load_signal(symbol: str) -> dict:
    slug = symbol.lower().replace("-", "")
    path = LIVE_DIR / f"latest_{slug}_signal.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_tranche_log() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=["Date"])
    return pd.read_csv(LOG_PATH, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)


def fetch_price(symbol: str) -> float:
    hist = yf.Ticker(symbol).history(period="3d")
    return float(hist["Close"].iloc[-1]) if not hist.empty else 0.0


def weight_130d_ago(log: pd.DataFrame, symbol: str) -> float:
    col = f"w_{symbol}"
    if col not in log.columns or len(log) < HORIZON:
        return 0.0
    return float(log[col].iloc[-HORIZON])


def normalize(raw: dict[str, float]) -> dict[str, float]:
    total = sum(v for v in raw.values() if v > 0)
    if total <= 0:
        return {k: 0.0 for k in raw}
    scale = max(total, 1.0)
    return {k: max(v, 0.0) / scale for k, v in raw.items()}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--capital", type=float, default=10_000.0)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    capital = args.capital
    today = date.today()

    universe = load_universe()
    log      = load_tranche_log()

    print("=" * 68)
    print(f"  Trade Job (read-only viewer)  —  {today}  |  capital=${capital:,.0f}")
    print("=" * 68)

    # --- Signals ---
    raw_weights: dict[str, float] = {}
    print("\n  Live Signals:")
    for sym in universe:
        sig = load_signal(sym)
        w   = float(sig.get("target_weight", 0.0) or 0.0)
        raw_weights[sym] = w
        anchor = sig.get("active_anchor_date", "?")
        asof   = sig.get("asof_date", "?")
        signal = sig.get("signal", "?")
        print(f"    {sym:<8}  signal={signal:<5}  raw_w={w:.3f}  anchor={anchor}  asof={asof}")

    today_weights = normalize(raw_weights)

    # --- Prices ---
    print("\n  Current Prices:")
    prices: dict[str, float] = {}
    for sym in universe:
        try:
            prices[sym] = fetch_price(sym)
            print(f"    {sym:<8}  ${prices[sym]:.2f}")
        except Exception as e:
            print(f"    {sym:<8}  ERROR: {e}")

    # --- Delta Orders ---
    print(f"\n  Delta Orders (horizon={HORIZON}d):")
    print(f"  {'Symbol':<8} {'TodayW':>8} {'130dW':>8} {'Delta':>8} {'$Trade':>10}  Action")
    print("  " + "-" * 58)

    for sym in universe:
        today_w = today_weights.get(sym, 0.0)
        past_w  = weight_130d_ago(log, sym)
        delta_w = today_w - past_w
        trade_$ = (delta_w / HORIZON) * capital

        if abs(trade_$) < 1.0:
            action = "HOLD"
        elif trade_$ > 0:
            price  = prices.get(sym, 0.0)
            qty    = round(trade_$ / price, 4) if price > 0 else 0
            action = f"BUY  ${trade_$:+.2f}  qty={qty}"
        else:
            price  = prices.get(sym, 0.0)
            qty    = round(abs(trade_$) / price, 4) if price > 0 else 0
            action = f"SELL ${trade_$:+.2f}  qty={qty}"

        print(f"  {sym:<8} {today_w:>8.4f} {past_w:>8.4f} {delta_w:>+8.4f} {trade_$:>+10.2f}  {action}")

    print()
    print("  [NOTE] This is a read-only viewer. No orders submitted.")
    print("  Stage B connection:")
    print("  -> delta_tranche_job.py submits real Alpaca orders (called by daily_pipeline.py)")
    print("  -> run_order_execution.sh triggers this automatically at 1:00 PM PT")


if __name__ == "__main__":
    main()
