from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_CSV = REPO_ROOT / "data" / "gld_us_d.csv"
GLD_SYMBOL = "GLD"


def alpaca_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", ".")


@dataclass(frozen=True)
class AlpacaCreds:
    key: str
    secret: str

    @staticmethod
    def from_env() -> "AlpacaCreds":
        import os

        key = os.getenv("APCA_API_KEY_ID")
        secret = os.getenv("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise EnvironmentError(
                "Missing Alpaca credentials. "
                "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY."
            )
        return AlpacaCreds(key=key, secret=secret)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Incrementally update daily OHLCV data before live signal generation."
    )
    parser.add_argument("--data-csv", type=str, default=str(DEFAULT_DATA_CSV), help="Daily CSV path.")
    parser.add_argument("--symbol", type=str, default=GLD_SYMBOL, help="Ticker symbol, default GLD.")
    parser.add_argument(
        "--max-staleness-days",
        type=int,
        default=5,
        help="If the latest row is within this many calendar days, no refresh is needed.",
    )
    parser.add_argument(
        "--lookback-padding-days",
        type=int,
        default=10,
        help="When refreshing, fetch from latest_date - padding to safely overwrite overlapping rows.",
    )
    return parser.parse_args()


def load_existing_daily_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df = pd.read_csv(path)
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")
    df["Date"] = pd.to_datetime(df["Date"], format="ISO8601").dt.normalize()
    return df.sort_values("Date").reset_index(drop=True)


def latest_trading_date(df: pd.DataFrame) -> pd.Timestamp:
    if df.empty:
        raise ValueError("Existing GLD daily CSV is empty.")
    return pd.Timestamp(df["Date"].iloc[-1]).normalize()


def should_refresh(latest_date: pd.Timestamp, max_staleness_days: int) -> bool:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    gap_days = (today - latest_date).days
    return gap_days > max_staleness_days


def fetch_daily_bars_from_alpaca(
    *,
    symbol: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    request_symbol = alpaca_symbol(symbol)
    creds = AlpacaCreds.from_env()
    client = StockHistoricalDataClient(creds.key, creds.secret)
    req = StockBarsRequest(
        symbol_or_symbols=[request_symbol],
        timeframe=TimeFrame.Day,
        start=start_date.to_pydatetime().replace(tzinfo=timezone.utc),
        end=(end_date + pd.Timedelta(days=1)).to_pydatetime().replace(tzinfo=timezone.utc),
        adjustment="all",
        feed="iex",
    )
    bars = client.get_stock_bars(req).df
    if bars.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(request_symbol)
    bars = bars.reset_index()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True).dt.tz_convert(None)
    bars["Date"] = bars["timestamp"].dt.normalize()
    out = bars.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    keep_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
    out = out[keep_cols].copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.normalize()
    return out.sort_values("Date").reset_index(drop=True)


def fetch_daily_bars_from_yfinance(
    *,
    symbol: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("yfinance is not installed.") from e

    df = yf.download(
        symbol,
        start=start_date.strftime("%Y-%m-%d"),
        end=(end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=False,
        progress=False,
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    if "Date" not in df.columns:
        df.rename(columns={df.columns[0]: "Date"}, inplace=True)
    keep_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
    out = df[keep_cols].copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.normalize()
    return out.sort_values("Date").reset_index(drop=True)


def merge_and_save(existing_df: pd.DataFrame, new_df: pd.DataFrame, path: Path) -> pd.DataFrame:
    merged = pd.concat([existing_df, new_df], ignore_index=True)
    merged["Date"] = pd.to_datetime(merged["Date"], format="ISO8601").dt.normalize()
    merged = (
        merged.sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )
    merged.to_csv(path, index=False, date_format="%Y-%m-%d")
    return merged


def main() -> None:
    args = parse_args()
    data_csv = Path(args.data_csv)
    existing_df = load_existing_daily_csv(data_csv)

    # CSV missing entirely → full historical download from 2010-01-01
    if existing_df.empty:
        print("=" * 80)
        print("DAILY DATA UPDATE")
        print("=" * 80)
        print(f"STATUS:              CSV_NOT_FOUND_FULL_DOWNLOAD")
        print(f"DATA_CSV:            {data_csv}")
        start_date = pd.Timestamp("2010-01-01")
        end_date = pd.Timestamp(datetime.now(timezone.utc).date())
        data_source = "alpaca"
        try:
            fetched_df = fetch_daily_bars_from_alpaca(symbol=args.symbol, start_date=start_date, end_date=end_date)
        except Exception:
            data_source = "yfinance_fallback"
            fetched_df = fetch_daily_bars_from_yfinance(symbol=args.symbol, start_date=start_date, end_date=end_date)
        if fetched_df.empty:
            raise RuntimeError(
                f"Full historical download returned no data for {args.symbol} "
                f"({data_source}) — cannot create {data_csv}"
            )
        data_csv.parent.mkdir(parents=True, exist_ok=True)
        fetched_df.to_csv(data_csv, index=False, date_format="%Y-%m-%d")
        print(f"STATUS:              CREATED")
        print(f"DATA_SOURCE:         {data_source}")
        print(f"ROWS:                {len(fetched_df)}")
        return

    latest_date = latest_trading_date(existing_df)

    if not should_refresh(latest_date, args.max_staleness_days):
        print("=" * 80)
        print("GLD DAILY DATA UPDATE")
        print("=" * 80)
        print(f"STATUS:              SKIPPED_FRESH_ENOUGH")
        print(f"LATEST_LOCAL_DATE:   {latest_date.date()}")
        print(f"MAX_STALENESS_DAYS:  {args.max_staleness_days}")
        print(f"ROWS:                {len(existing_df)}")
        print(f"DATA_CSV:            {data_csv}")
        return

    start_date = latest_date - pd.Timedelta(days=args.lookback_padding_days)
    end_date = pd.Timestamp(datetime.now(timezone.utc).date())
    data_source = "alpaca"
    try:
        fetched_df = fetch_daily_bars_from_alpaca(
            symbol=args.symbol,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        data_source = "yfinance_fallback"
        fetched_df = fetch_daily_bars_from_yfinance(
            symbol=args.symbol,
            start_date=start_date,
            end_date=end_date,
        )

    if fetched_df.empty:
        print("=" * 80)
        print("GLD DAILY DATA UPDATE")
        print("=" * 80)
        print("STATUS:              NO_NEW_DATA_RETURNED")
        print(f"LATEST_LOCAL_DATE:   {latest_date.date()}")
        print(f"FETCH_START_DATE:    {start_date.date()}")
        print(f"FETCH_END_DATE:      {end_date.date()}")
        return

    merged_df = merge_and_save(existing_df, fetched_df, data_csv)
    new_latest_date = latest_trading_date(merged_df)

    print("=" * 80)
    print("GLD DAILY DATA UPDATE")
    print("=" * 80)
    print("STATUS:              UPDATED")
    print(f"SYMBOL:              {args.symbol}")
    print(f"LATEST_LOCAL_BEFORE: {latest_date.date()}")
    print(f"LATEST_LOCAL_AFTER:  {new_latest_date.date()}")
    print(f"FETCH_START_DATE:    {start_date.date()}")
    print(f"FETCH_END_DATE:      {end_date.date()}")
    print(f"DATA_SOURCE:         {data_source}")
    print(f"FETCHED_ROWS:        {len(fetched_df)}")
    print(f"TOTAL_ROWS:          {len(merged_df)}")
    print(f"DATA_CSV:            {data_csv}")


if __name__ == "__main__":
    main()
