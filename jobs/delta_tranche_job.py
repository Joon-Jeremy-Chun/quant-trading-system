"""
delta_tranche_job.py

Delta-based portfolio rebalancer. Called once per day (1:00 PM PT) from
gld_daily_pipeline.py, replacing the per-asset gld_tranche_order_job calls.

Each day:
  delta = (1/HORIZON) * (today_weight - weight_HORIZON_days_ago) * CAPITAL
  delta > 0  -> BUY  that dollar amount
  delta < 0  -> SELL that dollar amount
  delta = 0  -> nothing

Universe changes (detected by comparing active_universe.json vs tranche_log columns):
  Asset removed  -> immediate full exit: sell entire accumulated position
  Asset added    -> bootstrap mode: buy full accumulated position from bootstrap_position.json
                    (run simulate_tranche_bootstrap.py first to generate the file)

Key files:
  models/live_assets/active_universe.json  <- which assets to trade today
  outputs/live/tranche_log.csv             <- 130-day rolling weight history (appended daily)
  outputs/bootstrap/bootstrap_position.json <- one-time bootstrap buy quantities
  outputs/live/latest_<sym>_signal.json    <- today's signal per asset
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest
    _ALPACA_OK = True
except Exception:
    _ALPACA_OK = False

REPO_ROOT     = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = REPO_ROOT / "models" / "live_assets" / "active_universe.json"
LOG_PATH      = REPO_ROOT / "outputs" / "live" / "tranche_log.csv"
BOOTSTRAP_PATH= REPO_ROOT / "outputs" / "bootstrap" / "bootstrap_position.json"
LIVE_DIR      = REPO_ROOT / "outputs" / "live"


# ── Config from env ───────────────────────────────────────────────────────────
def _env_float(k, d): return float(os.getenv(k, d))
def _env_bool(k, d):
    v = os.getenv(k)
    return d if v is None else v.strip().lower() in {"1","true","yes","y","on"}

HORIZON_DAYS  = int(os.getenv("TRANCHE_HORIZON_DAYS", "130"))
TOTAL_CAPITAL = _env_float("TRANCHE_TOTAL_CAPITAL", 10_000.0)
DRY_RUN       = _env_bool("ALPACA_DRY_RUN", True)
MIN_ORDER_USD = _env_float("ALPACA_MIN_ORDER_USD", 1.0)


# ── Data loading ──────────────────────────────────────────────────────────────
def load_universe() -> list[str]:
    with open(UNIVERSE_PATH, encoding="utf-8") as f:
        return [s.upper() for s in json.load(f)["assets"]]


def load_signal(symbol: str) -> dict:
    slug = symbol.lower().replace("-", "")
    path = LIVE_DIR / f"latest_{slug}_signal.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_tranche_log() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=["Date"])
    df = pd.read_csv(LOG_PATH, parse_dates=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def fetch_price(symbol: str) -> float:
    hist = yf.Ticker(symbol).history(period="3d")
    if hist.empty:
        raise RuntimeError(f"No price data for {symbol}")
    return float(hist["Close"].iloc[-1])


def load_bootstrap_position() -> dict:
    if not BOOTSTRAP_PATH.exists():
        return {}
    with open(BOOTSTRAP_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Weight logic ──────────────────────────────────────────────────────────────
def normalize_weights(raw: dict[str, float]) -> dict[str, float]:
    total = sum(v for v in raw.values() if v > 0)
    if total <= 0:
        return {k: 0.0 for k in raw}
    scale = max(total, 1.0)
    return {k: max(v, 0.0) / scale for k, v in raw.items()}


def weight_n_days_ago(log: pd.DataFrame, symbol: str, n: int) -> float:
    col = f"w_{symbol}"
    if col not in log.columns or len(log) < n:
        return 0.0
    return float(log[col].iloc[-n])


# ── Alpaca order ──────────────────────────────────────────────────────────────
def submit_order(symbol: str, side: str, dollars: float, price: float) -> dict:
    qty = round(abs(dollars) / price, 4)
    limit_price = round(price * 1.005, 2) if side == "BUY" else round(price * 0.995, 2)

    if DRY_RUN or not _ALPACA_OK:
        return {"submitted": False, "reason": "dry_run", "symbol": symbol,
                "side": side, "dollars": dollars, "qty": qty, "limit_price": limit_price}

    key    = os.environ["APCA_API_KEY_ID"]
    secret = os.environ["APCA_API_SECRET_KEY"]
    client = TradingClient(key, secret, paper=True)
    order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
    req = LimitOrderRequest(
        symbol=symbol.replace("-", "."),
        qty=qty,
        side=order_side,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price,
        extended_hours=True,
    )
    result = client.submit_order(req)
    return {"submitted": True, "order_id": str(result.id), "symbol": symbol,
            "side": side, "dollars": dollars, "qty": qty, "limit_price": limit_price}


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    today = date.today()
    print("=" * 70)
    print(f"  Delta Tranche Job  {today}  (dry_run={DRY_RUN}  capital=${TOTAL_CAPITAL:,.0f})")
    print("=" * 70)

    universe   = load_universe()
    log        = load_tranche_log()
    log_assets = [c.replace("w_", "") for c in log.columns if c.startswith("w_")]

    # ── Detect universe changes ───────────────────────────────────────────────
    removed = [a for a in log_assets if a not in universe]
    added   = [a for a in universe if a not in log_assets]

    if removed:
        print(f"  [UNIVERSE] Removed assets: {removed} -> FULL EXIT")
    if added:
        print(f"  [UNIVERSE] Added assets:   {added} -> BOOTSTRAP BUY")

    # ── Load today's signals & normalize ─────────────────────────────────────
    raw_weights: dict[str, float] = {}
    for sym in universe:
        sig = load_signal(sym)
        raw_weights[sym] = float(sig.get("target_weight", 0.0) or 0.0)

    today_weights = normalize_weights(raw_weights)

    print(f"\n  Today's normalized weights:")
    for sym, w in today_weights.items():
        print(f"    {sym:<8}: {w:.4f}  ({w*100:.1f}%)")

    # ── Fetch prices ──────────────────────────────────────────────────────────
    print()
    prices: dict[str, float] = {}
    for sym in universe + removed:
        try:
            prices[sym] = fetch_price(sym)
            print(f"  [price] {sym}: ${prices[sym]:.2f}")
        except Exception as e:
            print(f"  [price] {sym}: ERROR — {e}")

    # ── Handle removed assets: full exit ─────────────────────────────────────
    exit_orders: list[dict] = []
    for sym in removed:
        col = f"w_{sym}"
        n_rows = len(log)
        # Accumulated position = sum of last HORIZON_DAYS rows * (1/HORIZON) * CAPITAL
        horizon_rows = log[col].tail(HORIZON_DAYS)
        accumulated_frac = float((horizon_rows / HORIZON_DAYS).sum())
        exit_dollars = accumulated_frac * TOTAL_CAPITAL
        if exit_dollars < MIN_ORDER_USD:
            print(f"  [EXIT]  {sym}: position too small (${exit_dollars:.2f}), skip")
            continue
        price = prices.get(sym, 0.0)
        if price <= 0:
            print(f"  [EXIT]  {sym}: no price, skip")
            continue
        print(f"  [EXIT]  {sym}: SELL ${exit_dollars:.2f} ({accumulated_frac*100:.1f}% of capital)")
        result = submit_order(sym, "SELL", exit_dollars, price)
        exit_orders.append(result)

    # ── Handle added assets: bootstrap buy ───────────────────────────────────
    bootstrap_orders: list[dict] = []
    bootstrap = load_bootstrap_position()
    for sym in added:
        pos = bootstrap.get("positions", {}).get(sym)
        if not pos:
            print(f"  [ADD]   {sym}: no bootstrap_position.json entry — run simulate_tranche_bootstrap.py first")
            continue
        buy_dollars = float(pos.get("dollars", 0.0))
        price = prices.get(sym, 0.0)
        if price <= 0 or buy_dollars < MIN_ORDER_USD:
            print(f"  [ADD]   {sym}: skip (dollars={buy_dollars:.2f}, price={price:.2f})")
            continue
        print(f"  [ADD]   {sym}: BOOTSTRAP BUY ${buy_dollars:.2f}")
        result = submit_order(sym, "BUY", buy_dollars, price)
        bootstrap_orders.append(result)

    # ── Delta orders for continuing assets ───────────────────────────────────
    delta_orders: list[dict] = []
    print(f"\n  Delta orders (horizon={HORIZON_DAYS}):")
    print(f"  {'Symbol':<8} {'TodayW':>8} {'130dW':>8} {'Delta':>8} {'$Trade':>10}  Side")
    print("  " + "-" * 60)

    new_log_row: dict = {"Date": today.isoformat()}

    for sym in universe:
        today_w = today_weights.get(sym, 0.0)
        new_log_row[f"w_{sym}"] = round(today_w, 6)

        past_w = weight_n_days_ago(log, sym, HORIZON_DAYS)
        delta_w = today_w - past_w
        trade_dollars = (delta_w / HORIZON_DAYS) * TOTAL_CAPITAL

        if abs(trade_dollars) < MIN_ORDER_USD:
            side = "HOLD"
        elif trade_dollars > 0:
            side = "BUY"
        else:
            side = "SELL"

        print(f"  {sym:<8} {today_w:>8.4f} {past_w:>8.4f} {delta_w:>+8.4f} {trade_dollars:>+10.2f}  {side}")

        if side in ("BUY", "SELL"):
            price = prices.get(sym, 0.0)
            if price <= 0:
                print(f"    -> skipped: no price")
                continue
            result = submit_order(sym, side, abs(trade_dollars), price)
            delta_orders.append(result)

    # ── Append today to tranche_log ───────────────────────────────────────────
    new_row_df = pd.DataFrame([new_log_row])
    if log.empty:
        updated_log = new_row_df
    else:
        # Ensure all columns align (new assets get 0 in historical rows)
        updated_log = pd.concat([log, new_row_df], ignore_index=True)
        updated_log = updated_log.fillna(0.0)

    # Remove duplicate dates (idempotent re-run)
    updated_log["Date"] = pd.to_datetime(updated_log["Date"])
    updated_log = updated_log.drop_duplicates(subset=["Date"], keep="last")
    updated_log = updated_log.sort_values("Date").reset_index(drop=True)
    updated_log.to_csv(LOG_PATH, index=False, float_format="%.6f")
    print(f"\n  [LOG] Appended to tranche_log.csv ({len(updated_log)} rows)")

    # ── Save job output ───────────────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "today": today.isoformat(),
        "dry_run": DRY_RUN,
        "universe": universe,
        "removed_assets": removed,
        "added_assets": added,
        "today_weights": today_weights,
        "horizon_days": HORIZON_DAYS,
        "total_capital": TOTAL_CAPITAL,
        "tranche_log_rows": len(updated_log),
        "delta_orders": delta_orders,
        "exit_orders": exit_orders,
        "bootstrap_orders": bootstrap_orders,
    }
    out_path = LIVE_DIR / f"delta_tranche_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"  [OK] Saved: {out_path.name}")
    print("=" * 70)


if __name__ == "__main__":
    main()
