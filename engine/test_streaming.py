# engine/test_streaming.py
from __future__ import annotations

import os
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from alpaca.data.live.stock import StockDataStream


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = ["GLD", "MSFT", "RKLB"]

# "quotes" or "trades"
# STREAM_TYPE: Literal["quotes", "trades"] = "quotes"

STREAM_TYPE: Literal["quotes", "trades"] = "trades"

# flush to disk every N events
# FLUSH_EVERY_N = 20
FLUSH_EVERY_N = 20

# root output directory for streamed market data
STREAM_ROOT = Path("../data/streaming")


# ============================================================
# CREDENTIALS
# ============================================================

@dataclass(frozen=True)
class AlpacaCreds:
    key: str
    secret: str

    @staticmethod
    def from_env() -> "AlpacaCreds":
        key = os.getenv("APCA_API_KEY_ID")
        secret = os.getenv("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise EnvironmentError(
                "Missing Alpaca credentials. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY."
            )
        return AlpacaCreds(key=key, secret=secret)


# ============================================================
# STORAGE
# ============================================================

buffer: list[dict] = []


def get_output_path(stream_type: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = STREAM_ROOT / today
    out_dir.mkdir(parents=True, exist_ok=True)

    symbol_part = "_".join(SYMBOLS)
    return out_dir / f"{stream_type}_{symbol_part}.csv"


def flush_buffer_to_csv(path: Path) -> None:
    global buffer

    if not buffer:
        return

    file_exists = path.exists()
    fieldnames = list(buffer[0].keys())

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(buffer)

    print(f"[FLUSH] Wrote {len(buffer)} rows -> {path}")
    buffer = []


def append_event(row: dict, out_path: Path) -> None:
    global buffer

    buffer.append(row)

    if len(buffer) >= FLUSH_EVERY_N:
        flush_buffer_to_csv(out_path)


# ============================================================
# CALLBACKS
# ============================================================

OUT_PATH = get_output_path(STREAM_TYPE)


async def on_quote(data):
    print(
        f"QUOTE | {data.symbol} | bid={data.bid_price} | ask={data.ask_price} | time={data.timestamp}"
    )

    row = {
        "received_at_local": datetime.now().isoformat(),
        "event_type": "quote",
        "symbol": getattr(data, "symbol", None),
        "timestamp": str(getattr(data, "timestamp", None)),
        "bid_price": getattr(data, "bid_price", None),
        "ask_price": getattr(data, "ask_price", None),
        "bid_size": getattr(data, "bid_size", None),
        "ask_size": getattr(data, "ask_size", None),
    }

    append_event(row, OUT_PATH)


async def on_trade(data):
    print(
        f"TRADE | {data.symbol} | price={data.price} | size={data.size} | time={data.timestamp}"
    )

    row = {
        "received_at_local": datetime.now().isoformat(),
        "event_type": "trade",
        "symbol": getattr(data, "symbol", None),
        "timestamp": str(getattr(data, "timestamp", None)),
        "price": getattr(data, "price", None),
        "size": getattr(data, "size", None),
    }

    append_event(row, OUT_PATH)


# ============================================================
# MAIN
# ============================================================

def main():
    creds = AlpacaCreds.from_env()
    stream = StockDataStream(creds.key, creds.secret)

    print("=" * 80)
    print("TEST STREAMING START")
    print("=" * 80)
    print("SYMBOLS      :", SYMBOLS)
    print("STREAM_TYPE  :", STREAM_TYPE)
    print("FLUSH_EVERY_N:", FLUSH_EVERY_N)
    print("OUT_PATH     :", OUT_PATH.resolve())
    print("=" * 80)

    if STREAM_TYPE == "quotes":
        stream.subscribe_quotes(on_quote, *SYMBOLS)
    elif STREAM_TYPE == "trades":
        stream.subscribe_trades(on_trade, *SYMBOLS)
    else:
        raise ValueError("STREAM_TYPE must be 'quotes' or 'trades'")

    try:
        stream.run()
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    finally:
        flush_buffer_to_csv(OUT_PATH)


if __name__ == "__main__":
    main()