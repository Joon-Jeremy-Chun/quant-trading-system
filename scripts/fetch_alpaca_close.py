"""
fetch_alpaca_close.py

1 PM PT 실행 시 Alpaca latest bar로 오늘 종가를 가져와 가격 CSV에 append.
yfinance 대신 Alpaca를 사용해 오늘 장 마감 직후 즉시 반영.

Usage:
    python scripts/fetch_alpaca_close.py --symbols GLD,BRK-B,QQQ,RKLB
"""
from __future__ import annotations

import argparse
import os
from datetime import date, timezone, datetime
from pathlib import Path

import pandas as pd

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestBarRequest
    _ALPACA_OK = True
except ImportError:
    _ALPACA_OK = False

REPO_ROOT = Path(__file__).resolve().parents[1]

SYMBOL_CSV = {
    "GLD":   REPO_ROOT / "data" / "gld_us_d.csv",
    "BRK-B": REPO_ROOT / "data" / "brkb_us_d.csv",
    "QQQ":   REPO_ROOT / "data" / "qqq_us_d.csv",
    "RKLB":  REPO_ROOT / "data" / "rklb_us_d.csv",
    "ITA":   REPO_ROOT / "data" / "ita_us_d.csv",
    "VRT":   REPO_ROOT / "data" / "vrt_us_d.csv",
}

# IEX feed uses dot notation for class-B shares
_IEX_SYMBOL_MAP = {"BRK-B": "BRK.B"}


def fetch_latest_bar(symbol: str) -> dict | None:
    if not _ALPACA_OK:
        print(f"  [{symbol}] Alpaca SDK not available")
        return None
    key    = os.environ.get("APCA_API_KEY_ID", "")
    secret = os.environ.get("APCA_API_SECRET_KEY", "")
    if not key or not secret:
        print(f"  [{symbol}] Alpaca credentials missing")
        return None
    api_symbol = _IEX_SYMBOL_MAP.get(symbol, symbol)
    try:
        client = StockHistoricalDataClient(key, secret)
        req    = StockLatestBarRequest(symbol_or_symbols=[api_symbol], feed="iex")
        bars   = client.get_stock_latest_bar(req)
    except Exception as e:
        print(f"  [{symbol}] Alpaca fetch error: {e}")
        return None
    if not bars or api_symbol not in bars:
        print(f"  [{symbol}] No bar returned from Alpaca")
        return None
    bar = bars[api_symbol]
    bar_date = bar.timestamp.astimezone(timezone.utc).date()
    return {
        "date":   bar_date,
        "open":   float(bar.open),
        "high":   float(bar.high),
        "low":    float(bar.low),
        "close":  float(bar.close),
        "volume": float(bar.volume),
    }


def append_to_csv(symbol: str, bar: dict) -> str:
    csv_path = SYMBOL_CSV.get(symbol)
    if not csv_path or not csv_path.exists():
        return "NO_CSV"

    df = pd.read_csv(csv_path)
    last_date = pd.to_datetime(df["Date"].iloc[-1]).date()
    bar_date  = bar["date"]

    if bar_date <= last_date:
        return f"ALREADY_PRESENT ({last_date})"

    new_row = pd.DataFrame([{
        "Date":   bar_date,
        "Open":   bar["open"],
        "High":   bar["high"],
        "Low":    bar["low"],
        "Close":  bar["close"],
        "Volume": bar["volume"],
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(csv_path, index=False)
    return f"APPENDED ({bar_date}, close={bar['close']:.3f})"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="GLD,BRK-B,QQQ,RKLB",
                   help="Comma-separated symbols to update")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    today   = date.today()
    print(f"[fetch_alpaca_close] date={today}  symbols={symbols}")

    for sym in symbols:
        bar = fetch_latest_bar(sym)
        if bar is None:
            print(f"  [{sym}] SKIPPED — fetch failed")
            continue
        if bar["date"] < today:
            print(f"  [{sym}] bar_date={bar['date']} < today={today} — market may not have closed yet")
        status = append_to_csv(sym, bar)
        print(f"  [{sym}] close=${bar['close']:.3f}  csv={status}")


if __name__ == "__main__":
    main()
