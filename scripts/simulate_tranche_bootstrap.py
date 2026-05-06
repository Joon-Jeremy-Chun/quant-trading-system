"""
simulate_tranche_bootstrap.py

Simulates daily portfolio weights for the 4-asset universe over the past N months
using monthly-updated anchor models (no look-ahead). Then computes the bootstrap
position: what we WOULD hold today if we had been running the 1/130 tranche system
since the simulation start date.

Steps:
  1. For each asset × each calendar month, call fit_month_model() using the anchor
     that was active at the start of that month. Collect daily portfolio_weight.
  2. Align all assets on common trading dates, normalize weights across the portfolio.
  3. Bootstrap position = sum over last HORIZON_DAYS trading days of (1/HORIZON) * norm_weight.
  4. Output:
       outputs/bootstrap/daily_weights.csv
       outputs/bootstrap/bootstrap_position.json
  5. Print dry-run orders (what to buy today to enter the bootstrap position).

Usage:
    python scripts/simulate_tranche_bootstrap.py
    python scripts/simulate_tranche_bootstrap.py --start-date 2025-09-01 --dry-run
    python scripts/simulate_tranche_bootstrap.py --dry-run  (skip Alpaca, print only)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "strategies" / "automation"))

from run_objective2_monthly_update_tranche_backtest import (  # noqa: E402
    fit_month_model,
    load_available_anchor_dates,
    previous_anchor_candidates_for_month,
)
from strategy_matrix_builder import DATE_COL, load_price_only_data  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────
HORIZON_DAYS     = 130
TOP_N            = 20
CRITERION        = "selection_cv_mse"
SCALE_QUANTILE   = 0.95
UPDATE_INTERVAL  = 1   # calendar months per model refresh
TOTAL_CAPITAL    = 10_000.0

ASSETS: dict[str, dict] = {
    "GLD":   {
        "data_csv":    REPO_ROOT / "data" / "gld_us_d.csv",
        "anchor_root": REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation",
    },
    "BRK-B": {
        "data_csv":    REPO_ROOT / "data" / "brkb_us_d.csv",
        "anchor_root": REPO_ROOT / "outputs" / "brkb" / "anchor_snapshots",
    },
    "QQQ":   {
        "data_csv":    REPO_ROOT / "data" / "qqq_us_d.csv",
        "anchor_root": REPO_ROOT / "outputs" / "qqq" / "anchor_snapshots",
    },
    "RKLB":  {
        "data_csv":    REPO_ROOT / "data" / "rklb_us_d.csv",
        "anchor_root": REPO_ROOT / "outputs" / "rklb" / "anchor_snapshots",
    },
}

OUT_DIR = REPO_ROOT / "outputs" / "bootstrap"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _period_start(dt: pd.Timestamp, interval: int = UPDATE_INTERVAL) -> pd.Timestamp:
    """First day of the model period containing dt (calendar-month aligned)."""
    month_idx = ((dt.month - 1) // interval) * interval + 1
    return pd.Timestamp(year=dt.year, month=month_idx, day=1)


def _month_periods(sim_start: pd.Timestamp, sim_end: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Return (period_start, period_end) tuples covering [sim_start, sim_end]."""
    periods = []
    cur = _period_start(sim_start)
    while cur <= sim_end:
        nxt = cur + pd.offsets.MonthBegin(UPDATE_INTERVAL)
        periods.append((cur, min(nxt - pd.Timedelta(days=1), sim_end)))
        cur = nxt
    return periods


# ── Per-asset simulation ──────────────────────────────────────────────────────

def simulate_asset(symbol: str, cfg: dict, sim_start: pd.Timestamp, sim_end: pd.Timestamp) -> pd.DataFrame:
    """
    Returns DataFrame with columns [Date, portfolio_weight] for every trading day
    in [sim_start, sim_end], using monthly-updated models.
    """
    data_csv    = cfg["data_csv"]
    anchor_root = cfg["anchor_root"]

    print(f"\n[{symbol}] Loading anchors from {anchor_root.name}/")
    available = load_available_anchor_dates(anchor_root)

    price_df = load_price_only_data(data_csv).sort_values(DATE_COL).reset_index(drop=True)
    price_df[DATE_COL] = pd.to_datetime(price_df[DATE_COL])

    periods = _month_periods(sim_start, sim_end)
    rows: list[pd.DataFrame] = []

    for period_start, period_end in periods:
        # Clip to actual trading dates within this period
        mask = (price_df[DATE_COL] >= period_start) & (price_df[DATE_COL] <= period_end)
        trading_dates = price_df.loc[mask, DATE_COL]
        if trading_dates.empty:
            continue

        actual_start = pd.Timestamp(trading_dates.iloc[0])
        actual_end   = pd.Timestamp(trading_dates.iloc[-1])

        # Pick anchor: most recent snapshot before this period start
        try:
            candidates = previous_anchor_candidates_for_month(period_start, available)
        except ValueError:
            print(f"  [{symbol}] {period_start.date()} — no anchor before period, skipping")
            continue

        month_df = None
        for anchor_date in candidates:
            try:
                month_df, meta = fit_month_model(
                    repo_root=REPO_ROOT,
                    data_csv=data_csv,
                    anchor_output_root=anchor_root,
                    anchor_date=anchor_date,
                    month_start=actual_start,
                    month_end=actual_end,
                    target_horizon_days=HORIZON_DAYS,
                    top_n_per_family=TOP_N,
                    selection_criterion=CRITERION,
                    scale_quantile=SCALE_QUANTILE,
                )
                print(
                    f"  [{symbol}] {period_start.date()} ~ {actual_end.date()} "
                    f"anchor={anchor_date.date()} model={meta['active_model_name']} "
                    f"rows={len(month_df)}"
                )
                break
            except Exception as exc:
                print(f"  [{symbol}] anchor {anchor_date.date()} failed: {exc}")
                continue

        if month_df is None:
            print(f"  [{symbol}] {period_start.date()} — all anchors failed, filling zeros")
            zero_df = pd.DataFrame({DATE_COL: trading_dates.values, "portfolio_weight": 0.0})
            rows.append(zero_df[[DATE_COL, "portfolio_weight"]])
            continue

        slice_df = month_df[[DATE_COL, "portfolio_weight"]].copy()
        slice_df[DATE_COL] = pd.to_datetime(slice_df[DATE_COL])
        rows.append(slice_df)

    if not rows:
        return pd.DataFrame(columns=[DATE_COL, "portfolio_weight"])

    result = pd.concat(rows, ignore_index=True).sort_values(DATE_COL).reset_index(drop=True)
    result["portfolio_weight"] = result["portfolio_weight"].clip(lower=0.0)
    return result


# ── Portfolio normalization ───────────────────────────────────────────────────

def build_normalized_portfolio(asset_weights: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Merge all assets on common dates, normalize weights so sum <= 1.
    Returns DataFrame with Date + raw/norm weights + cash_weight.
    """
    combined: pd.DataFrame | None = None
    for sym, df in asset_weights.items():
        renamed = df.rename(columns={"portfolio_weight": f"raw_{sym}"})
        renamed[DATE_COL] = pd.to_datetime(renamed[DATE_COL])
        if combined is None:
            combined = renamed
        else:
            combined = combined.merge(renamed, on=DATE_COL, how="inner")

    if combined is None or combined.empty:
        return pd.DataFrame()

    combined = combined.sort_values(DATE_COL).reset_index(drop=True)
    symbols = list(asset_weights.keys())
    raw_cols = [f"raw_{s}" for s in symbols]

    raw = combined[raw_cols].clip(lower=0.0)
    total = raw.sum(axis=1)
    scale = total.clip(lower=1.0)           # only scale down when > 1
    norm  = raw.div(scale, axis=0)

    for sym in symbols:
        combined[f"w_{sym}"] = norm[f"raw_{sym}"]
    combined["cash_weight"]      = (1.0 - norm.sum(axis=1)).clip(lower=0.0)
    combined["total_raw_weight"] = total
    combined.rename(columns={DATE_COL: "Date"}, inplace=True)
    return combined


# ── Bootstrap position ────────────────────────────────────────────────────────

def compute_bootstrap_position(port_df: pd.DataFrame, symbols: list[str]) -> dict[str, float]:
    """
    Bootstrap position = sum over last HORIZON_DAYS trading days of
        (1 / HORIZON_DAYS) * normalized_weight_for_symbol
    This represents the accumulated 1/130-per-day position.
    Result is a fraction of TOTAL_CAPITAL per symbol.
    """
    last_n = port_df.tail(HORIZON_DAYS)
    return {
        sym: float((last_n[f"w_{sym}"] / HORIZON_DAYS).sum())
        for sym in symbols
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Simulate tranche bootstrap for 4-asset portfolio.")
    p.add_argument("--start-date", default="2025-09-01",
                   help="Simulation start date (YYYY-MM-DD). Default: 2025-09-01")
    p.add_argument("--dry-run", action="store_true",
                   help="Print orders only, do not submit to Alpaca.")
    p.add_argument("--total-capital", type=float, default=TOTAL_CAPITAL,
                   help=f"Total capital in USD. Default: {TOTAL_CAPITAL}")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    sim_start = pd.Timestamp(args.start_date)
    sim_end   = pd.Timestamp("today").normalize()
    total_cap = args.total_capital
    symbols   = list(ASSETS.keys())

    print("=" * 70)
    print(f"  Tranche Bootstrap Simulation")
    print(f"  Period : {sim_start.date()} → {sim_end.date()}")
    print(f"  Assets : {', '.join(symbols)}")
    print(f"  Horizon: {HORIZON_DAYS} days   Capital: ${total_cap:,.0f}")
    print("=" * 70)

    # ── 1. Simulate each asset ────────────────────────────────────────────────
    asset_weights: dict[str, pd.DataFrame] = {}
    for sym, cfg in ASSETS.items():
        df = simulate_asset(sym, cfg, sim_start, sim_end)
        if df.empty:
            print(f"  [{sym}] WARNING: no data, using zeros")
            df = pd.DataFrame({DATE_COL: [], "portfolio_weight": []})
        asset_weights[sym] = df

    # ── 2. Normalize portfolio ────────────────────────────────────────────────
    print("\n[Portfolio] Merging and normalizing weights...")
    port_df = build_normalized_portfolio(asset_weights)
    if port_df.empty:
        print("[ERROR] No overlapping trading dates across assets.")
        return

    # ── 3. Save daily weights ─────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    daily_path = OUT_DIR / "daily_weights.csv"
    cols_to_save = ["Date"] + [f"raw_{s}" for s in symbols] + [f"w_{s}" for s in symbols] + ["cash_weight", "total_raw_weight"]
    port_df[cols_to_save].to_csv(daily_path, index=False, float_format="%.6f")
    print(f"[OK] Saved daily weights: {daily_path}  ({len(port_df)} rows)")

    # ── 4. Bootstrap position ─────────────────────────────────────────────────
    bootstrap = compute_bootstrap_position(port_df, symbols)
    total_allocated = sum(bootstrap.values())
    cash_fraction   = max(0.0, 1.0 - total_allocated)

    n_days_used = min(HORIZON_DAYS, len(port_df))
    boot_start  = port_df['Date'].iloc[-n_days_used].date()
    boot_end    = port_df['Date'].iloc[-1].date()
    print(f"\n{'─'*70}")
    print(f"  Bootstrap Position  (last {n_days_used}/{HORIZON_DAYS} trading days → {boot_start} ~ {boot_end})")
    if n_days_used < HORIZON_DAYS:
        print(f"  NOTE: only {n_days_used} days available — bootstrap fraction scaled accordingly")
    print(f"{'─'*70}")

    # ── 5. Fetch prices for order sizing ─────────────────────────────────────
    prices: dict[str, float] = {}
    print("\n[Prices] Fetching current prices...")
    for sym in symbols:
        try:
            import yfinance as yf
            ticker = sym  # keep as-is (BRK-B works with yfinance)
            hist = yf.Ticker(ticker).history(period="2d")
            if not hist.empty:
                prices[sym] = float(hist["Close"].iloc[-1])
                print(f"  {sym}: ${prices[sym]:.2f}")
            else:
                prices[sym] = 0.0
                print(f"  {sym}: price unavailable")
        except Exception as e:
            prices[sym] = 0.0
            print(f"  {sym}: error — {e}")

    # ── 6. Print orders ───────────────────────────────────────────────────────
    orders = []
    print(f"\n{'─'*70}")
    print(f"  {'Symbol':<8} {'Fraction':>10} {'$Value':>10} {'Price':>10} {'Qty':>10}  Side")
    print(f"{'─'*70}")
    for sym in symbols:
        frac       = bootstrap[sym]
        dollars    = frac * total_cap
        price      = prices.get(sym, 0.0)
        qty        = round(dollars / price, 4) if price > 0 else 0.0
        side       = "BUY" if qty > 0 else "HOLD"
        limit_px   = round(price * 1.005, 2) if price > 0 else 0.0
        print(f"  {sym:<8} {frac:>10.4f} {dollars:>10.2f} {price:>10.2f} {qty:>10.4f}  {side}  (limit ${limit_px})")
        orders.append({"symbol": sym, "fraction": frac, "dollars": dollars, "price": price, "qty": qty, "side": side, "limit_price": limit_px})

    total_dollars = sum(o["dollars"] for o in orders)
    print(f"{'─'*70}")
    print(f"  {'TOTAL':<8} {total_allocated:>10.4f} {total_dollars:>10.2f}")
    print(f"  {'CASH':<8} {cash_fraction:>10.4f} {cash_fraction * total_cap:>10.2f}")

    # ── 7. Save bootstrap JSON ────────────────────────────────────────────────
    sim_days = len(port_df)
    bootstrap_used = min(HORIZON_DAYS, sim_days)
    payload = {
        "bootstrap_date": str(sim_end.date()),
        "simulation_start": str(sim_start.date()),
        "simulation_end": str(sim_end.date()),
        "simulation_trading_days": sim_days,
        "horizon_days": HORIZON_DAYS,
        "bootstrap_days_used": bootstrap_used,
        "total_capital": total_cap,
        "total_allocated_fraction": round(total_allocated, 6),
        "cash_fraction": round(cash_fraction, 6),
        "positions": {
            o["symbol"]: {
                "fraction":    round(o["fraction"], 6),
                "dollars":     round(o["dollars"], 2),
                "price":       o["price"],
                "qty":         o["qty"],
                "limit_price": o["limit_price"],
                "side":        o["side"],
            }
            for o in orders
        },
    }
    bootstrap_path = OUT_DIR / "bootstrap_position.json"
    with open(bootstrap_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\n[OK] Saved bootstrap position: {bootstrap_path}")

    # ── 8. Quick stats on simulated period ───────────────────────────────────
    print(f"\n[Stats] Daily avg normalized weights over full simulation:")
    for sym in symbols:
        avg = port_df[f"w_{sym}"].mean()
        print(f"  {sym:<8}: avg {avg:.3f}  ({avg*100:.1f}%)")
    print(f"  {'Cash':<8}: avg {port_df['cash_weight'].mean():.3f}  ({port_df['cash_weight'].mean()*100:.1f}%)")

    if args.dry_run:
        print("\n[DRY RUN] No orders submitted.")
        return

    # ── 9. Submit orders to Alpaca ────────────────────────────────────────────
    print("\n[Alpaca] Submitting bootstrap orders...")
    try:
        import os
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest

        key    = os.environ["APCA_API_KEY_ID"]
        secret = os.environ["APCA_API_SECRET_KEY"]
        client = TradingClient(key, secret, paper=True)

        for o in orders:
            if o["side"] != "BUY" or o["qty"] <= 0:
                print(f"  [{o['symbol']}] SKIP (qty={o['qty']})")
                continue
            sym_alpaca = o["symbol"].replace("-", ".")
            req = LimitOrderRequest(
                symbol=sym_alpaca,
                qty=o["qty"],
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=o["limit_price"],
                extended_hours=True,
            )
            result = client.submit_order(req)
            print(f"  [{o['symbol']}] ORDER SUBMITTED  id={result.id}  qty={o['qty']}  limit=${o['limit_price']}")

    except Exception as e:
        print(f"[ERROR] Alpaca submission failed: {e}")
        print("  Run with --dry-run to skip order submission.")


if __name__ == "__main__":
    main()
