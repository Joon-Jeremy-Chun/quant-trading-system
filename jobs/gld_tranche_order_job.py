from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest
except Exception:
    TradingClient = None
    OrderSide = None
    TimeInForce = None
    MarketOrderRequest = None


REPO_ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "GLD"


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

    def add(self, tranche: Tranche) -> None:
        self.tranches.append(tranche)

    def total_qty(self) -> float:
        return sum(t.qty for t in self.tranches)


def fetch_latest_price(creds: AlpacaCreds, symbol: str) -> float:
    client = StockHistoricalDataClient(creds.key, creds.secret)
    req = StockLatestQuoteRequest(symbol_or_symbols=[symbol], feed="iex")
    quote = client.get_stock_latest_quote(req)[symbol]
    ask = float(getattr(quote, "ask_price", 0.0) or 0.0)
    bid = float(getattr(quote, "bid_price", 0.0) or 0.0)
    if ask > 0 and bid > 0:
        return (ask + bid) / 2.0
    return ask or bid


def maybe_submit_order(
    creds: AlpacaCreds, symbol: str, side: str, qty: float, dry_run: bool
) -> dict:
    if dry_run:
        return {"submitted": False, "reason": "dry_run", "side": side, "qty": qty}
    if qty <= 0:
        return {"submitted": False, "reason": "zero_qty", "side": side, "qty": qty}

    trading_client = TradingClient(creds.key, creds.secret, paper=True)
    order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
    order = MarketOrderRequest(symbol=symbol, qty=qty, side=order_side, time_in_force=TimeInForce.DAY)
    result = trading_client.submit_order(order)
    return {"submitted": True, "order_id": str(result.id), "side": side, "qty": qty}


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    root = REPO_ROOT
    creds = AlpacaCreds.from_env()

    horizon_days = int(_env_float("TRANCHE_HORIZON_DAYS", 130))
    total_capital = _env_float("TRANCHE_TOTAL_CAPITAL", 100000.0)
    min_weight = _env_float("ALPACA_MIN_WEIGHT_TO_OPEN", 0.15)
    min_order_qty = _env_float("ALPACA_MIN_REBALANCE_QTY", 0.01)
    dry_run = _env_bool("ALPACA_DRY_RUN", True)

    # Load today's signal
    signal_path = root / "outputs" / "live" / "latest_gld_signal.json"
    with open(signal_path, "r", encoding="utf-8") as f:
        signal_payload = json.load(f)

    today = date.fromisoformat(signal_payload["asof_date"])
    target_weight = float(signal_payload.get("target_weight", 0.0) or 0.0)
    signal_name = str(signal_payload.get("signal", "HOLD")).upper()
    active_model = signal_payload.get("active_model_name", "unknown")

    # Fetch current market price
    current_price = fetch_latest_price(creds, SYMBOL)

    # Load tranche book
    book_path = root / "outputs" / "live" / "tranche_book.json"
    book = TranchBook(book_path)

    # Step 1: close expired tranches
    expired = book.pop_expired(today)
    sell_qty = sum(t.qty for t in expired)

    # Step 2: open new tranche if BUY signal is strong enough
    new_tranche: Tranche | None = None
    buy_qty = 0.0

    if signal_name == "BUY" and target_weight >= min_weight and current_price > 0:
        allocated_capital = (total_capital / horizon_days) * target_weight
        buy_qty = allocated_capital / current_price
        close_date = (today + timedelta(days=horizon_days)).isoformat()
        new_tranche = Tranche(
            tranche_id=today.isoformat(),
            open_date=today.isoformat(),
            close_date=close_date,
            target_weight=target_weight,
            allocated_capital=allocated_capital,
            qty=buy_qty,
            open_price=current_price,
        )
        book.add(new_tranche)

    # Step 3: compute net order
    net_delta = buy_qty - sell_qty
    order_result: dict
    if abs(net_delta) >= min_order_qty:
        side = "BUY" if net_delta > 0 else "SELL"
        order_result = maybe_submit_order(creds, SYMBOL, side, abs(net_delta), dry_run)
    else:
        order_result = {
            "submitted": False,
            "reason": "net_delta_too_small",
            "net_delta": net_delta,
        }

    # Step 4: save tranche book
    book.save(SYMBOL, horizon_days, total_capital)

    # Step 5: save order log
    out_dir = root / "outputs" / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "today": today.isoformat(),
        "symbol": SYMBOL,
        "signal": signal_name,
        "target_weight": target_weight,
        "active_model": active_model,
        "current_price": current_price,
        "horizon_days": horizon_days,
        "total_capital": total_capital,
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
    out_path = out_dir / f"gld_tranche_order_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("=" * 80)
    print("GLD TRANCHE ORDER JOB")
    print("=" * 80)
    print(f"TODAY:               {today}")
    print(f"SIGNAL:              {signal_name}  weight={target_weight:.4f}  model={active_model}")
    print(f"PRICE:               ${current_price:.2f}")
    print(f"HORIZON:             {horizon_days} days")
    print(f"CAPITAL/TRANCHE:     ${total_capital / horizon_days:.2f}  x  {target_weight:.4f}  =  ${(total_capital / horizon_days) * target_weight:.2f}")
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
