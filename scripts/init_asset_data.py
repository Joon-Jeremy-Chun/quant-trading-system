"""
First-time historical data download for a new asset.
Uses yfinance to fetch full history and saves to the asset's data_csv path.

Usage:
  python scripts/init_asset_data.py --asset brkb
  python scripts/init_asset_data.py --asset rklb --start 2019-01-01
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO_ROOT / "assets"


def load_config(asset: str) -> dict:
    config_path = ASSETS_DIR / asset / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download full historical data for a new asset.")
    parser.add_argument("--asset", required=True, help="Asset name (e.g. brkb, rklb)")
    parser.add_argument("--start", type=str, default="2005-01-01", help="Start date (YYYY-MM-DD)")
    args = parser.parse_args()

    cfg = load_config(args.asset)
    symbol = cfg["symbol"]
    out_path = REPO_ROOT / cfg["data_csv"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        print(f"[SKIP] {out_path} already exists. Use update_gld_daily_data.py for incremental updates.")
        return

    print(f"Downloading {symbol} from {args.start} via yfinance...")
    df = yf.download(symbol, start=args.start, auto_adjust=True, progress=False)

    if df.empty:
        raise ValueError(f"No data returned for {symbol}. Check the ticker symbol.")

    df = df.reset_index()
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.rename(columns={"Date": "Date", "Open": "Open", "High": "High",
                             "Low": "Low", "Close": "Close", "Volume": "Volume"})
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df.to_csv(out_path, index=False)

    print(f"[OK] Saved {len(df)} rows → {out_path}")
    print(f"     Date range: {df['Date'].iloc[0]} ~ {df['Date'].iloc[-1]}")
    print(f"     Latest close: ${float(df['Close'].iloc[-1]):.2f}")


if __name__ == "__main__":
    main()
