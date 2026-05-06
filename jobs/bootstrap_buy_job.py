"""
bootstrap_buy_job.py  —  ONE-TIME use only.

Reads outputs/bootstrap/bootstrap_position.json and places limit buy orders
to pre-fund the 130-day accumulated position. Run this ONCE before starting
the delta_tranche_job system.

Usage:
    python jobs/bootstrap_buy_job.py --dry-run   # preview orders
    python jobs/bootstrap_buy_job.py             # submit to Alpaca paper account
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest
    _ALPACA_OK = True
except Exception:
    _ALPACA_OK = False

REPO_ROOT      = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = REPO_ROOT / "outputs" / "bootstrap" / "bootstrap_position.json"
LIVE_DIR       = REPO_ROOT / "outputs" / "live"
DONE_FLAG      = REPO_ROOT / "outputs" / "bootstrap" / "bootstrap_buy_executed.json"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Preview only, no real orders")
    p.add_argument("--force", action="store_true", help="Re-run even if already executed")
    return p.parse_args()


def fetch_price(symbol: str) -> float:
    hist = yf.Ticker(symbol).history(period="3d")
    if hist.empty:
        raise RuntimeError(f"No price data for {symbol}")
    return float(hist["Close"].iloc[-1])


def main():
    args = parse_args()
    dry_run = args.dry_run or not _ALPACA_OK

    if DONE_FLAG.exists() and not args.force:
        with open(DONE_FLAG) as f:
            info = json.load(f)
        print(f"[SKIP] Bootstrap buy already executed on {info.get('executed_at', '?')}.")
        print(f"       Use --force to re-run.")
        return

    if not BOOTSTRAP_PATH.exists():
        print(f"[ERROR] {BOOTSTRAP_PATH} not found.")
        print("        Run: python scripts/simulate_tranche_bootstrap.py --dry-run")
        return

    with open(BOOTSTRAP_PATH) as f:
        bootstrap = json.load(f)

    positions = bootstrap.get("positions", {})
    capital   = float(bootstrap.get("total_capital", 10000.0))

    print("=" * 66)
    print(f"  Bootstrap Buy Job  {'[DRY RUN]' if dry_run else '[LIVE]'}")
    print(f"  Sim period : {bootstrap.get('simulation_start')} ~ {bootstrap.get('bootstrap_date')}")
    print(f"  Days used  : {bootstrap.get('bootstrap_days_used')}/{bootstrap.get('horizon_days')}")
    print(f"  Capital    : ${capital:,.0f}")
    print("=" * 66)

    if not _ALPACA_OK and not dry_run:
        print("[ERROR] alpaca-py not available. Install it or use --dry-run.")
        return

    if not dry_run:
        key    = os.environ["APCA_API_KEY_ID"]
        secret = os.environ["APCA_API_SECRET_KEY"]
        client = TradingClient(key, secret, paper=True)

    results = []
    total_dollars = 0.0

    for symbol, pos in positions.items():
        dollars    = float(pos["dollars"])
        sim_price  = float(pos.get("price", 0.0))

        try:
            live_price = fetch_price(symbol)
        except Exception as e:
            print(f"  [{symbol}] price error: {e}, using sim price ${sim_price:.2f}")
            live_price = sim_price

        if live_price <= 0:
            print(f"  [{symbol}] SKIP — no price")
            continue

        qty         = round(dollars / live_price, 4)
        limit_price = round(live_price * 1.005, 2)
        total_dollars += dollars

        print(f"  {symbol:<8}  ${dollars:>8.2f}  px={live_price:.2f}  qty={qty:.4f}  limit=${limit_price}")

        if dry_run:
            results.append({"symbol": symbol, "submitted": False, "reason": "dry_run",
                             "dollars": dollars, "qty": qty, "limit_price": limit_price})
            continue

        req = LimitOrderRequest(
            symbol=symbol.replace("-", "."),
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=True,
        )
        result = client.submit_order(req)
        print(f"    -> ORDER SUBMITTED  id={result.id}")
        results.append({"symbol": symbol, "submitted": True, "order_id": str(result.id),
                        "dollars": dollars, "qty": qty, "limit_price": limit_price})

    print("-" * 66)
    mode_label = "DRY RUN - no orders placed" if dry_run else "ORDERS SUBMITTED"
    print(f"  Total: ${total_dollars:.2f}  ({mode_label})")

    if not dry_run:
        done = {"executed_at": datetime.now(timezone.utc).isoformat(), "results": results}
        with open(DONE_FLAG, "w") as f:
            json.dump(done, f, indent=2)
        print(f"\n  [OK] Logged to {DONE_FLAG.name} — will not re-run unless --force")

    # Save order log
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LIVE_DIR / f"bootstrap_buy_{ts}.json"
    with open(log_path, "w") as f:
        json.dump({"dry_run": dry_run, "results": results, "total_dollars": total_dollars}, f, indent=2)
    print(f"  [OK] Saved: {log_path.name}")


if __name__ == "__main__":
    main()
