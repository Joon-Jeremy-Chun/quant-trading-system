from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest
except Exception:
    TradingClient = None
    OrderSide = None
    TimeInForce = None
    LimitOrderRequest = None


REPO_ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "GLD"
DEFAULT_MARKET_DATA_FEED = "iex"


def alpaca_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", ".")


def _parse_args():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="GLD", help="Trading symbol (GLD, BRK-B, etc.)")
    p.add_argument("--weight-override", type=float, default=None,
                   help="Override target_weight from signal (for multi-asset normalization)")
    return p.parse_args()

@dataclass(frozen=True)
class AlpacaCreds:
    key: str
    secret: str

    @staticmethod
    def from_env() -> "AlpacaCreds":
        key = os.getenv("APCA_API_KEY_ID")
        secret = os.getenv("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise EnvironmentError("Missing Alpaca credentials. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY.")
        return AlpacaCreds(key=key, secret=secret)


@dataclass
class Tranche:
    tranche_id: str
    open_date: str
    close_date: str
    target_weight: float
    allocated_capital: float
    qty: float
    open_price: float

    def is_expired(self, today: date) -> bool:
        return date.fromisoformat(self.close_date) <= today


class TranchBook:
    def __init__(self, path: Path):
        self.path = path
        self.tranches: list[Tranche] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.tranches = [Tranche(**t) for t in data.get("tranches", [])]

    def save(self, symbol: str, horizon_days: int, total_capital: float) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "symbol": symbol,
                    "horizon_days": horizon_days,
                    "total_capital": total_capital,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "active_count": len(self.tranches),
                    "tranches": [asdict(t) for t in self.tranches],
                },
                f,
                indent=2,
            )

    def pop_expired(self, today: date) -> list[Tranche]:
        expired = [t for t in self.tranches if t.is_expired(today)]
        self.tranches = [t for t in self.tranches if not t.is_expired(today)]
        return expired

    def has_open_date(self, open_date: date) -> bool:
        open_date_text = open_date.isoformat()
        return any(t.open_date == open_date_text for t in self.tranches)

    def add(self, tranche: Tranche) -> None:
        self.tranches.append(tranche)

    def total_qty(self) -> float:
        return sum(t.qty for t in self.tranches)


def fetch_yahoo_close(symbol: str) -> dict:
    try:
        hist = yf.Ticker(symbol).history(period="1d")
        if hist.empty:
            return {"available": False, "error": f"yfinance returned no data for {symbol}"}
        return {
            "available": True,
            "symbol": symbol,
            "close": float(hist["Close"].iloc[-1]),
            "timestamp": str(hist.index[-1]),
        }
    except Exception as exc:
        return {"available": False, "symbol": symbol, "error": str(exc)}


def fetch_alpaca_quote(creds: AlpacaCreds, symbol: str) -> dict:
    request_symbol = alpaca_symbol(symbol)
    feed = os.getenv("ALPACA_MARKET_DATA_FEED", DEFAULT_MARKET_DATA_FEED)
    client = StockHistoricalDataClient(creds.key, creds.secret)
    req = StockLatestQuoteRequest(symbol_or_symbols=[request_symbol], feed=feed)
    quote = client.get_stock_latest_quote(req)[request_symbol]
    ask = float(getattr(quote, "ask_price", 0.0) or 0.0)
    bid = float(getattr(quote, "bid_price", 0.0) or 0.0)
    if ask > 0 and bid > 0:
        price = (ask + bid) / 2.0
    else:
        price = ask or bid
    if price <= 0:
        raise RuntimeError(f"Alpaca quote has no positive bid/ask for {request_symbol}")
    return {
        "available": True,
        "symbol": request_symbol,
        "feed": feed,
        "bid_price": bid,
        "ask_price": ask,
        "price": float(price),
        "timestamp": str(getattr(quote, "timestamp", "")),
    }


def fetch_price_snapshot(creds: AlpacaCreds, symbol: str) -> dict:
    yahoo_payload = fetch_yahoo_close(symbol)
    try:
        alpaca_payload = fetch_alpaca_quote(creds, symbol)
        price = float(alpaca_payload["price"])
        source = "alpaca_quote"
    except Exception as exc:
        alpaca_payload = {"available": False, "symbol": alpaca_symbol(symbol), "error": str(exc)}
        if not yahoo_payload.get("available"):
            raise RuntimeError(
                f"Could not fetch a tradable price for {symbol}. "
                f"Alpaca error: {alpaca_payload.get('error')}; "
                f"Yahoo error: {yahoo_payload.get('error')}"
            ) from exc
        price = float(yahoo_payload["close"])
        source = "yahoo_fallback"
    return {
        "source": source,
        "price": price,
        "alpaca_quote": alpaca_payload,
        "yahoo_close": yahoo_payload,
    }


def maybe_submit_order(
    creds: AlpacaCreds, symbol: str, side: str, qty: float, dry_run: bool, price: float = 0.0
) -> dict:
    if dry_run:
        return {"submitted": False, "reason": "dry_run", "side": side, "qty": qty}
    if qty <= 0:
        return {"submitted": False, "reason": "zero_qty", "side": side, "qty": qty}
    if TradingClient is None or LimitOrderRequest is None:
        raise RuntimeError("alpaca.trading imports are unavailable. Install alpaca-py trading support.")

    trading_client = TradingClient(creds.key, creds.secret, paper=True)
    order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
    order_symbol = alpaca_symbol(symbol)
    limit_price = round(price * 1.005, 2) if price > 0 else None
    if limit_price is None:
        raise RuntimeError(f"Cannot submit limit order for {symbol}: price not available.")
    order = LimitOrderRequest(
        symbol=order_symbol,
        qty=qty,
        side=order_side,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price,
        extended_hours=True,
    )
    result = trading_client.submit_order(order)
    return {
        "submitted": True,
        "order_id": str(result.id),
        "symbol": order_symbol,
        "side": side,
        "qty": qty,
        "limit_price": limit_price,
        "extended_hours": True,
    }


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


def load_safety_config() -> dict:
    return {
        "max_signal_age_days": _env_int("MAX_SIGNAL_AGE_DAYS", 5),
        "max_dataset_staleness_days": _env_int("MAX_DATASET_STALENESS_DAYS", 5),
        "max_model_age_days": _env_int("MAX_MODEL_AGE_DAYS", 540),
        "block_on_stale_model": _env_bool("BLOCK_ON_STALE_MODEL", False),
        "dry_run_writes_live_book": _env_bool("ALPACA_DRY_RUN_WRITES_LIVE_BOOK", False),
    }


def signal_safety_reasons(
    signal_payload: dict,
    *,
    symbol: str,
    signal_date: date,
    today: date,
    config: dict,
) -> list[str]:
    reasons: list[str] = []
    signal_symbol = str(signal_payload.get("symbol", "")).upper()
    if signal_symbol and signal_symbol != symbol:
        reasons.append(f"symbol_mismatch:{signal_symbol}")

    signal_age_days = (today - signal_date).days
    if signal_age_days < 0:
        reasons.append("signal_date_in_future")
    elif signal_age_days > int(config["max_signal_age_days"]):
        reasons.append(f"signal_too_old:{signal_age_days}d")

    dataset_staleness_days = int(signal_payload.get("dataset_staleness_days", 0) or 0)
    if dataset_staleness_days > int(config["max_dataset_staleness_days"]):
        reasons.append(f"dataset_too_stale:{dataset_staleness_days}d")

    model_age_days = int(signal_payload.get("model_age_days", 0) or 0)
    if config["block_on_stale_model"] and model_age_days > int(config["max_model_age_days"]):
        reasons.append(f"model_too_old:{model_age_days}d")

    return reasons


def main() -> None:
    args = _parse_args()
    symbol = args.symbol.upper()
    root = REPO_ROOT
    creds = AlpacaCreds.from_env()

    horizon_days = int(_env_float("TRANCHE_HORIZON_DAYS", 130))
    total_capital = _env_float("TRANCHE_TOTAL_CAPITAL", 100000.0)
    min_weight = _env_float("ALPACA_MIN_WEIGHT_TO_OPEN", 0.0)
    min_order_qty = _env_float("ALPACA_MIN_REBALANCE_QTY", 0.01)
    dry_run = _env_bool("ALPACA_DRY_RUN", True)
    safety_config = load_safety_config()

    # Load today's signal (symbol-specific path)
    slug = symbol.lower().replace("-", "")
    signal_path = root / "outputs" / "live" / f"latest_{slug}_signal.json"
    with open(signal_path, "r", encoding="utf-8") as f:
        signal_payload = json.load(f)

    signal_date = date.fromisoformat(signal_payload["asof_date"])
    today = date.today()
    target_weight = float(signal_payload.get("target_weight", 0.0) or 0.0)
    if args.weight_override is not None:
        target_weight = args.weight_override
    signal_name = str(signal_payload.get("signal", "HOLD")).upper()
    active_model = signal_payload.get("active_model_name", "unknown")
    safety_reasons = signal_safety_reasons(
        signal_payload,
        symbol=symbol,
        signal_date=signal_date,
        today=today,
        config=safety_config,
    )

    # Dry-run gets its own book unless explicitly opted into live-book writes.
    book_suffix = "" if (not dry_run or safety_config["dry_run_writes_live_book"]) else "_dry_run"
    book_path = root / "outputs" / "live" / f"tranche_book_{slug}{book_suffix}.json"
    book = TranchBook(book_path)

    current_price = 0.0
    price_snapshot: dict = {"source": "not_fetched"}
    expired: list[Tranche] = []
    new_tranche: Tranche | None = None
    sell_qty = 0.0
    buy_qty = 0.0
    net_delta = 0.0
    duplicate_tranche = False
    book_saved = False

    if safety_reasons:
        order_result: dict = {
            "submitted": False,
            "reason": "blocked_by_signal_safety",
            "safety_reasons": safety_reasons,
        }
    else:
        price_snapshot = fetch_price_snapshot(creds, symbol)
        current_price = float(price_snapshot["price"])

        expired = book.pop_expired(today)
        sell_qty = sum(t.qty for t in expired)

        if signal_name == "BUY" and target_weight >= min_weight and current_price > 0:
            if book.has_open_date(today):
                duplicate_tranche = True
            else:
                allocated_capital = (total_capital / horizon_days) * target_weight
                buy_qty = allocated_capital / current_price
                close_date = (today + timedelta(days=horizon_days)).isoformat()
                new_tranche = Tranche(
                    tranche_id=f"{slug}-{today.isoformat()}",
                    open_date=today.isoformat(),
                    close_date=close_date,
                    target_weight=target_weight,
                    allocated_capital=allocated_capital,
                    qty=buy_qty,
                    open_price=current_price,
                )
                book.add(new_tranche)

        net_delta = buy_qty - sell_qty
        if abs(net_delta) >= min_order_qty:
            side = "BUY" if net_delta > 0 else "SELL"
            order_result = maybe_submit_order(creds, symbol, side, abs(net_delta), dry_run, price=current_price)
        else:
            reason = "duplicate_tranche_already_open_today" if duplicate_tranche else "net_delta_too_small"
            order_result = {
                "submitted": False,
                "reason": reason,
                "net_delta": net_delta,
            }

        book.save(symbol, horizon_days, total_capital)
        book_saved = True

    # Step 5: save order log
    out_dir = root / "outputs" / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "today": today.isoformat(),
        "symbol": symbol,
        "signal": signal_name,
        "target_weight": target_weight,
        "active_model": active_model,
        "current_price": current_price,
        "price_snapshot": price_snapshot,
        "horizon_days": horizon_days,
        "total_capital": total_capital,
        "signal_date": signal_date.isoformat(),
        "signal_age_days": (today - signal_date).days,
        "safety_reasons": safety_reasons,
        "book_path": str(book_path),
        "book_saved": book_saved,
        "duplicate_tranche": duplicate_tranche,
        "expired_tranches": [asdict(t) for t in expired],
        "new_tranche": asdict(new_tranche) if new_tranche else None,
        "sell_qty": sell_qty,
        "buy_qty": buy_qty,
        "net_delta": net_delta,
        "order": order_result,
        "active_tranches_after": len(book.tranches),
        "total_qty_held_after": book.total_qty(),
        "dry_run": dry_run,
    }
    out_path = out_dir / f"{slug}_tranche_order_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("=" * 80)
    print(f"{symbol} TRANCHE ORDER JOB")
    print("=" * 80)
    print(f"TODAY:               {today}")
    print(f"SIGNAL DATE:         {signal_date}")
    print(f"SIGNAL:              {signal_name}  weight={target_weight:.4f}  model={active_model}")
    print(f"PRICE:               ${current_price:.2f}  source={price_snapshot.get('source')}")
    print(f"HORIZON:             {horizon_days} days")
    print(f"CAPITAL/TRANCHE:     ${total_capital / horizon_days:.2f}  x  {target_weight:.4f}  =  ${(total_capital / horizon_days) * target_weight:.2f}")
    print(f"SAFETY:              {'blocked ' + ','.join(safety_reasons) if safety_reasons else 'ok'}")
    print(f"BOOK:                {book_path.name}  saved={book_saved}")
    print(f"EXPIRED → SELL:      {len(expired)} tranches  ({sell_qty:.4f} shares)")
    print(f"NEW    → BUY:        {'yes' if new_tranche else 'no'}  ({buy_qty:.4f} shares)")
    net_side = "BUY" if net_delta > 0 else "SELL" if net_delta < 0 else "HOLD"
    print(f"NET ORDER:           {net_side}  {abs(net_delta):.4f} shares")
    print(f"ACTIVE TRANCHES:     {len(book.tranches)}")
    print(f"TOTAL HELD:          {book.total_qty():.4f} shares")
    print(f"DRY_RUN:             {dry_run}")
    print(f"[OK] Saved:          {out_path}")


if __name__ == "__main__":
    main()
