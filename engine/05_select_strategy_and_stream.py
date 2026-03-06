# 05_0_select_params_and_stream.py
# Read Top10 optimization results, select ONE final parameter set,
# then connect to Alpaca stream and print incoming events.
#
# This file does NOT place orders yet.
# It only:
#   1) loads Top10 CSV
#   2) selects final parameters by your rule
#   3) connects to Alpaca streaming
#   4) prints incoming stream data for one chosen symbol

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from alpaca.data.live.stock import StockDataStream


# ============================================================
# CONFIG
# ============================================================

TOP10_CSV = Path("./data/opti_maxprofit_results_top10.csv")
OUT_SELECTED_JSON = Path("./outputs/params/latest_reversion_params.json")

SYMBOL = "GLD"

# stream type:
#   "bars"          -> minute bars
#   "updated_bars"  -> updating minute bars
#   "trades"        -> trades
#   "quotes"        -> bid/ask quotes
STREAM_TYPE: Literal["bars", "updated_bars", "trades", "quotes"] = "bars"

# if True, save selected parameter set to JSON
SAVE_SELECTED_PARAMS = True


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
                "Missing Alpaca credentials. "
                "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY."
            )
        return AlpacaCreds(key=key, secret=secret)


# ============================================================
# PARAMETER SELECTION
# ============================================================

def load_top10_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Top10 CSV not found: {path}")

    df = pd.read_csv(path)

    required = {"MA_WINDOW", "UPPER_K", "LOWER_K", "TotalReturn", "NumTrades", "WinRate"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in Top10 CSV: {missing}")

    return df


def select_final_params(df_top10: pd.DataFrame) -> pd.Series:
    """
    Rule:
      1) highest WinRate
      2) if tie, fewer NumTrades
      3) if tie, higher TotalReturn
    """
    ranked = df_top10.sort_values(
        by=["WinRate", "NumTrades", "TotalReturn"],
        ascending=[False, True, False]
    ).reset_index(drop=True)

    return ranked.iloc[0]


def save_selected_params(best: pd.Series, out_json: Path) -> None:
    payload = {
        "saved_at_utc": datetime.utcnow().isoformat() + "Z",
        "strategy_name": "reversion_bollinger_selected_from_top10",
        "selection_rule": [
            "highest WinRate",
            "if tie: fewer NumTrades",
            "if tie: higher TotalReturn"
        ],
        "params": {
            "ma_window": int(best["MA_WINDOW"]),
            "upper_k": float(best["UPPER_K"]),
            "lower_k": float(best["LOWER_K"])
        },
        "backtest_summary": {
            "win_rate": float(best["WinRate"]),
            "num_trades": int(best["NumTrades"]),
            "total_return": float(best["TotalReturn"])
        }
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)

    print(f"[OK] Saved selected params to: {out_json.resolve()}")


# ============================================================
# STREAM CALLBACKS
# ============================================================

async def on_bar(bar):
    print("-" * 80)
    print("[BAR]")
    print("symbol     :", getattr(bar, "symbol", None))
    print("timestamp  :", getattr(bar, "timestamp", None))
    print("open       :", getattr(bar, "open", None))
    print("high       :", getattr(bar, "high", None))
    print("low        :", getattr(bar, "low", None))
    print("close      :", getattr(bar, "close", None))
    print("volume     :", getattr(bar, "volume", None))


async def on_updated_bar(bar):
    print("-" * 80)
    print("[UPDATED BAR]")
    print("symbol     :", getattr(bar, "symbol", None))
    print("timestamp  :", getattr(bar, "timestamp", None))
    print("open       :", getattr(bar, "open", None))
    print("high       :", getattr(bar, "high", None))
    print("low        :", getattr(bar, "low", None))
    print("close      :", getattr(bar, "close", None))
    print("volume     :", getattr(bar, "volume", None))


async def on_trade(trade):
    print("-" * 80)
    print("[TRADE]")
    print("symbol     :", getattr(trade, "symbol", None))
    print("timestamp  :", getattr(trade, "timestamp", None))
    print("price      :", getattr(trade, "price", None))
    print("size       :", getattr(trade, "size", None))


async def on_quote(quote):
    print("-" * 80)
    print("[QUOTE]")
    print("symbol     :", getattr(quote, "symbol", None))
    print("timestamp  :", getattr(quote, "timestamp", None))
    print("bid_price  :", getattr(quote, "bid_price", None))
    print("ask_price  :", getattr(quote, "ask_price", None))
    print("bid_size   :", getattr(quote, "bid_size", None))
    print("ask_size   :", getattr(quote, "ask_size", None))


# ============================================================
# MAIN
# ============================================================

def main():
    # 1) load top10 and select final params
    df_top10 = load_top10_csv(TOP10_CSV)
    best = select_final_params(df_top10)

    ma_window = int(best["MA_WINDOW"])
    upper_k = float(best["UPPER_K"])
    lower_k = float(best["LOWER_K"])

    print("=" * 80)
    print("SELECTED PARAMETER SET")
    print("=" * 80)
    print(f"SYMBOL      : {SYMBOL}")
    print(f"MA_WINDOW   : {ma_window}")
    print(f"UPPER_K     : {upper_k}")
    print(f"LOWER_K     : {lower_k}")
    print(f"WIN_RATE    : {float(best['WinRate']):.4f}")
    print(f"NUM_TRADES  : {int(best['NumTrades'])}")
    print(f"TOTALRETURN : {float(best['TotalReturn']):.6f}")
    print(f"STREAM_TYPE : {STREAM_TYPE}")
    print("=" * 80)

    if SAVE_SELECTED_PARAMS:
        save_selected_params(best, OUT_SELECTED_JSON)

    # 2) connect to Alpaca stream
    creds = AlpacaCreds.from_env()
    stream = StockDataStream(creds.key, creds.secret)

    if STREAM_TYPE == "bars":
        stream.subscribe_bars(on_bar, SYMBOL)
    elif STREAM_TYPE == "updated_bars":
        stream.subscribe_updated_bars(on_updated_bar, SYMBOL)
    elif STREAM_TYPE == "trades":
        stream.subscribe_trades(on_trade, SYMBOL)
    elif STREAM_TYPE == "quotes":
        stream.subscribe_quotes(on_quote, SYMBOL)
    else:
        raise ValueError("STREAM_TYPE must be one of: bars, updated_bars, trades, quotes")

    print(f"[INFO] Connected. Listening to {STREAM_TYPE} stream for {SYMBOL}...")
    print("[INFO] Stop manually with Ctrl+C")
    stream.run()


if __name__ == "__main__":
    main()