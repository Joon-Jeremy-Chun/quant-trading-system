"""
fetch_price_data.py  --  Stage A: Price Data Fetcher

Stage A role: fetch historical OHLCV price data for any asset and save to CSV.
Stage B (production): update_daily_price_data.py runs incremental updates daily on Pi.

Usage:
    python jobs/fetch_price_data.py --symbol GLD
    python jobs/fetch_price_data.py --symbol RKLB --start 2020-01-01
    python jobs/fetch_price_data.py --symbol BRK-B --out data/brkb_us_d.csv

Supported symbols: GLD, BRK-B, QQQ, RKLB, ITA, VRT
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]

SYMBOL_DEFAULTS = {
    "GLD":   {"ticker": "GLD",   "out": "data/gld_us_d.csv"},
    "BRK-B": {"ticker": "BRK-B", "out": "data/brkb_us_d.csv"},
    "QQQ":   {"ticker": "QQQ",   "out": "data/qqq_us_d.csv"},
    "RKLB":  {"ticker": "RKLB",  "out": "data/rklb_us_d.csv"},
    "ITA":   {"ticker": "ITA",   "out": "data/ita_us_d.csv"},
    "VRT":   {"ticker": "VRT",   "out": "data/vrt_us_d.csv"},
}


def fetch(ticker: str, start: str, end: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")

    df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"No data returned for {ticker}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    if "Date" not in df.columns:
        df.rename(columns={df.columns[0]: "Date"}, inplace=True)

    df["Date"] = pd.to_datetime(df["Date"])
    keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[keep].dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)
    return df


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch full historical price data for any asset.")
    p.add_argument("--symbol", default="GLD", help="Asset symbol (GLD, BRK-B, QQQ, RKLB, ITA, VRT)")
    p.add_argument("--ticker", default=None, help="Override yfinance ticker (default: same as symbol)")
    p.add_argument("--start", default="2015-01-01", help="Start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    p.add_argument("--out", default=None, help="Output CSV path (default: data/<symbol>_us_d.csv)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    symbol   = args.symbol.upper()
    defaults = SYMBOL_DEFAULTS.get(symbol, {})
    ticker   = args.ticker or defaults.get("ticker", symbol)
    out_rel  = args.out    or defaults.get("out", f"data/{symbol.lower().replace('-','')}_us_d.csv")
    out_path = REPO_ROOT / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    end      = args.end or date.today().isoformat()

    print(f"Fetching {symbol} ({ticker})  {args.start} -> {end}")

    try:
        df = fetch(ticker, args.start, end)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    df.to_csv(out_path, index=False)
    print(f"[OK] {len(df):,} rows -> {out_path.relative_to(REPO_ROOT)}")
    print(df.tail(3).to_string(index=False))
    print()
    print("Stage B: update_daily_price_data.py fills gaps daily (incremental, no full re-download)")


if __name__ == "__main__":
    main()
