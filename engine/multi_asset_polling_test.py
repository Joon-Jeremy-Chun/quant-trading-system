# engine/test2_polling_quotes.py
from __future__ import annotations

import os
import time
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = ["GLD", "MSFT", "RKLB"]

# polling interval in seconds
POLL_INTERVAL_SECONDS = 10

# save path
OUT_PATH = Path("../data/polling/latest_quotes_test2.csv")

BOT_NAME = "GLD_MSFT_RKLB_POLLING_TEST"


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

def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_rows_to_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return

    ensure_parent_dir(path)
    file_exists = path.exists()
    fieldnames = list(rows[0].keys())

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


# ============================================================
# POLLING
# ============================================================

def fetch_latest_quotes(client: StockHistoricalDataClient, symbols: list[str]):
    request = StockLatestQuoteRequest(symbol_or_symbols=symbols, feed="iex")
    return client.get_stock_latest_quote(request)


def quote_to_row(symbol: str, quote_obj) -> dict:
    return {
        "received_at_local": datetime.now().isoformat(),
        "symbol": symbol,
        "quote_timestamp": str(getattr(quote_obj, "timestamp", None)),
        "bid_price": getattr(quote_obj, "bid_price", None),
        "ask_price": getattr(quote_obj, "ask_price", None),
        "bid_size": getattr(quote_obj, "bid_size", None),
        "ask_size": getattr(quote_obj, "ask_size", None),
    }


# ============================================================
# MAIN
# ============================================================

def main():
    creds = AlpacaCreds.from_env()
    client = StockHistoricalDataClient(creds.key, creds.secret)

    print("=" * 70)
    print(f"{BOT_NAME} START")
    print("=" * 70)
    print("SYMBOLS:", SYMBOLS)
    print("POLL_INTERVAL_SEC:", POLL_INTERVAL_SECONDS)
    print("FEED: IEX")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            try:
                quotes = fetch_latest_quotes(client, SYMBOLS)

                rows = []
                for symbol in SYMBOLS:
                    quote_obj = quotes.get(symbol)
                    if quote_obj is None:
                        continue

                    row = quote_to_row(symbol, quote_obj)
                    rows.append(row)

                if rows:
                    append_rows_to_csv(rows, OUT_PATH)

                # 🔹 조용한 상태 메시지
                now = datetime.now().strftime("%H:%M:%S")
                print(
                    f"[{now}] running | polling {', '.join(SYMBOLS)} every {POLL_INTERVAL_SECONDS}s"
                )

            except Exception as e:
                print(f"[ERROR] {e}")

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user.")


if __name__ == "__main__":
    main()