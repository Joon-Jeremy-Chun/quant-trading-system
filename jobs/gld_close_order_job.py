from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from pathlib import Path

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest
except Exception:  # pragma: no cover - depends on local package version
    TradingClient = None
    OrderSide = None
    TimeInForce = None
    MarketOrderRequest = None


SYMBOL = "GLD"
DEFAULT_QTY = 1.0


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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_latest_signal_payload(root: Path) -> dict:
    """
    Placeholder for future Objective 2 live signal output.
    If the file does not exist yet, fall back to a dry-run HOLD decision.
    """
    signal_path = root / "outputs" / "live" / "latest_gld_signal.json"
    if not signal_path.exists():
        return {
            "symbol": SYMBOL,
            "signal": "HOLD",
            "target_weight": 0.0,
            "source": "fallback_no_live_signal_file",
        }

    with open(signal_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_latest_quote(creds: AlpacaCreds, symbol: str) -> dict:
    client = StockHistoricalDataClient(creds.key, creds.secret)
    req = StockLatestQuoteRequest(symbol_or_symbols=[symbol], feed="iex")
    quote_map = client.get_stock_latest_quote(req)
    quote = quote_map[symbol]
    return {
        "bid_price": float(getattr(quote, "bid_price", 0.0) or 0.0),
        "ask_price": float(getattr(quote, "ask_price", 0.0) or 0.0),
        "timestamp": str(getattr(quote, "timestamp", "")),
    }


def log_payload(root: Path, payload: dict) -> None:
    out_dir = root / "outputs" / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"gld_close_order_job_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return float(default)
    return float(raw)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return int(default)
    return int(raw)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_order_config() -> dict:
    return {
        "base_position_qty": env_float("ALPACA_BASE_POSITION_QTY", 10.0),
        "min_weight_to_open": env_float("ALPACA_MIN_WEIGHT_TO_OPEN", 0.15),
        "min_rebalance_qty": env_float("ALPACA_MIN_REBALANCE_QTY", 1.0),
        "max_dataset_staleness_days": env_int("MAX_DATASET_STALENESS_DAYS", 7),
        "max_model_age_days": env_int("MAX_MODEL_AGE_DAYS", 540),
        "block_on_stale_model": env_bool("BLOCK_ON_STALE_MODEL", False),
        "dry_run": env_bool("ALPACA_DRY_RUN", True),
    }


def fetch_current_position_qty(creds: AlpacaCreds, symbol: str) -> dict:
    if TradingClient is None:
        return {
            "available": False,
            "qty": 0.0,
            "error": "TradingClient unavailable",
        }
    try:
        trading_client = TradingClient(creds.key, creds.secret, paper=True)
        position = trading_client.get_open_position(symbol)
        qty = float(getattr(position, "qty", 0.0) or 0.0)
        side = str(getattr(position, "side", "long") or "long").lower()
        if side == "short":
            qty = -qty
        return {
            "available": True,
            "qty": qty,
            "market_value": float(getattr(position, "market_value", 0.0) or 0.0),
            "avg_entry_price": float(getattr(position, "avg_entry_price", 0.0) or 0.0),
        }
    except Exception as exc:
        return {
            "available": False,
            "qty": 0.0,
            "error": str(exc),
        }


def desired_position_qty_from_signal(signal_payload: dict, config: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    signal = str(signal_payload.get("signal", "HOLD")).upper()
    target_weight = float(signal_payload.get("target_weight", 0.0) or 0.0)
    dataset_staleness_days = int(signal_payload.get("dataset_staleness_days", 0) or 0)
    model_age_days = int(signal_payload.get("model_age_days", 0) or 0)

    if dataset_staleness_days > config["max_dataset_staleness_days"]:
        reasons.append("dataset_too_stale")
        return 0.0, reasons

    if config["block_on_stale_model"] and model_age_days > config["max_model_age_days"]:
        reasons.append("model_too_old")
        return 0.0, reasons

    if signal != "BUY":
        reasons.append("non_buy_signal")
        return 0.0, reasons

    if target_weight < config["min_weight_to_open"]:
        reasons.append("weight_below_open_threshold")
        return 0.0, reasons

    desired_qty = ceil(config["base_position_qty"] * target_weight)
    desired_qty = max(float(desired_qty), 0.0)
    reasons.append("weight_scaled_position")
    return desired_qty, reasons


def build_order_plan(signal_payload: dict, position_payload: dict, config: dict) -> dict:
    current_qty = float(position_payload.get("qty", 0.0) or 0.0)
    desired_qty, reasons = desired_position_qty_from_signal(signal_payload, config)
    delta_qty = desired_qty - current_qty

    if abs(delta_qty) < config["min_rebalance_qty"]:
        return {
            "action": "HOLD",
            "desired_position_qty": desired_qty,
            "current_position_qty": current_qty,
            "delta_qty": delta_qty,
            "order_side": None,
            "order_qty": 0.0,
            "reasons": reasons + ["rebalance_too_small"],
        }

    if delta_qty > 0:
        action = "BUY"
        order_side = "BUY"
        order_qty = float(delta_qty)
    elif delta_qty < 0:
        action = "SELL"
        order_side = "SELL"
        order_qty = float(abs(delta_qty))
    else:
        action = "HOLD"
        order_side = None
        order_qty = 0.0

    return {
        "action": action,
        "desired_position_qty": desired_qty,
        "current_position_qty": current_qty,
        "delta_qty": delta_qty,
        "order_side": order_side,
        "order_qty": order_qty,
        "reasons": reasons,
    }


def maybe_submit_market_order(
    creds: AlpacaCreds,
    symbol: str,
    side_text: str,
    qty: float,
    dry_run: bool,
) -> dict:
    if dry_run:
        return {
            "submitted": False,
            "reason": "dry_run",
            "symbol": symbol,
            "side": side_text,
            "qty": qty,
        }

    if TradingClient is None or MarketOrderRequest is None:
        raise RuntimeError(
            "alpaca.trading imports are unavailable. "
            "Install the trading package version that includes TradingClient."
        )

    trading_client = TradingClient(creds.key, creds.secret, paper=True)
    side = OrderSide.BUY if side_text.upper() == "BUY" else OrderSide.SELL
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
    )
    submitted = trading_client.submit_order(order_data=order)
    return {
        "submitted": True,
        "order_id": str(getattr(submitted, "id", "")),
        "symbol": symbol,
        "side": side_text,
        "qty": qty,
    }


def main() -> None:
    root = repo_root()
    creds = AlpacaCreds.from_env()
    config = load_order_config()
    signal_payload = load_latest_signal_payload(root)
    try:
        quote_payload = fetch_latest_quote(creds, SYMBOL)
    except Exception as exc:
        quote_payload = {
            "bid_price": None,
            "ask_price": None,
            "timestamp": None,
            "quote_fetch_error": str(exc),
        }

    position_payload = fetch_current_position_qty(creds, SYMBOL)
    order_plan = build_order_plan(signal_payload, position_payload, config)
    dry_run = bool(config["dry_run"])

    order_payload: dict
    if order_plan["order_side"] in {"BUY", "SELL"} and order_plan["order_qty"] > 0:
        order_payload = maybe_submit_market_order(
            creds=creds,
            symbol=SYMBOL,
            side_text=str(order_plan["order_side"]),
            qty=float(order_plan["order_qty"]),
            dry_run=dry_run,
        )
    else:
        order_payload = {
            "submitted": False,
            "reason": "no_order_required",
            "symbol": SYMBOL,
            "signal": signal_payload.get("signal"),
            "qty": 0.0,
        }

    payload = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": SYMBOL,
        "config": config,
        "signal_payload": signal_payload,
        "quote_payload": quote_payload,
        "position_payload": position_payload,
        "order_plan": order_plan,
        "order_payload": order_payload,
        "notes": [
            "This is the close-time GLD order skeleton.",
            "Replace outputs/live/latest_gld_signal.json with the real Objective 2 live signal writer.",
            "Set ALPACA_DRY_RUN=false only after paper-trading checks are complete.",
            "Order sizing now uses target_weight -> desired_position_qty -> delta order logic.",
        ],
    }
    log_payload(root, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
