from __future__ import annotations

import argparse
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "derived_daily"
DEFAULT_TIMEZONE = "America/New_York"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert intraday OHLCV bars into the daily CSV format used by the "
            "Objective 1/2 research pipeline."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more intraday CSV files with timestamp/open/high/low/close/volume columns.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where daily CSV files will be written.",
    )
    parser.add_argument(
        "--timezone",
        type=str,
        default=DEFAULT_TIMEZONE,
        help="Timezone used to map timestamps to trading dates.",
    )
    parser.add_argument(
        "--session",
        choices=["regular", "all"],
        default="regular",
        help="Use only regular US equity hours or all bars in each local trading day.",
    )
    parser.add_argument(
        "--regular-start",
        type=str,
        default="09:30",
        help="Regular-session start time in local exchange time.",
    )
    parser.add_argument(
        "--regular-end",
        type=str,
        default="16:00",
        help="Regular-session end time in local exchange time.",
    )
    return parser.parse_args()


def infer_symbol(input_path: Path) -> str:
    stem = input_path.stem
    match = re.match(r"(?P<symbol>[A-Za-z0-9.]+?)(?:15min|_15min|1min|_1min)", stem)
    symbol = match.group("symbol") if match else stem
    return re.sub(r"[^A-Za-z0-9]+", "_", symbol).strip("_").upper()


def load_intraday(path: Path, timezone_name: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path}")

    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    out = out.sort_values("timestamp").reset_index(drop=True)
    out["local_timestamp"] = out["timestamp"].dt.tz_convert(ZoneInfo(timezone_name))
    out["Date"] = out["local_timestamp"].dt.normalize().dt.tz_localize(None)
    return out


def apply_session_filter(
    df: pd.DataFrame,
    session: str,
    regular_start: str,
    regular_end: str,
) -> pd.DataFrame:
    if session == "all":
        return df

    start_time = pd.to_datetime(regular_start).time()
    end_time = pd.to_datetime(regular_end).time()
    local_times = df["local_timestamp"].dt.time
    return df[(local_times >= start_time) & (local_times <= end_time)].copy()


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("Date", sort=True)
    daily = grouped.agg(
        Open=("open", "first"),
        High=("high", "max"),
        Low=("low", "min"),
        Close=("close", "last"),
        Volume=("volume", "sum"),
    ).reset_index()
    daily = daily.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"])
    daily["Date"] = pd.to_datetime(daily["Date"]).dt.strftime("%Y-%m-%d")
    return daily[["Date", "Open", "High", "Low", "Close", "Volume"]]


def convert_one(
    input_path: Path,
    output_dir: Path,
    timezone_name: str,
    session: str,
    regular_start: str,
    regular_end: str,
) -> Path:
    intraday = load_intraday(input_path, timezone_name)
    filtered = apply_session_filter(intraday, session, regular_start, regular_end)
    if filtered.empty:
        raise ValueError(f"No rows left after applying session={session} to {input_path}")

    daily = aggregate_daily(filtered)
    symbol = infer_symbol(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol}_1Day_from_intraday_{session}.csv"
    daily.to_csv(output_path, index=False)

    print("=" * 80)
    print("INTRADAY TO DAILY CONVERSION")
    print("=" * 80)
    print(f"INPUT:          {input_path}")
    print(f"OUTPUT:         {output_path}")
    print(f"TIMEZONE:       {timezone_name}")
    print(f"SESSION:        {session}")
    print(f"INTRADAY_ROWS:  {len(intraday)}")
    print(f"USED_ROWS:      {len(filtered)}")
    print(f"DAILY_ROWS:     {len(daily)}")
    print(f"DATE_MIN:       {daily['Date'].min()}")
    print(f"DATE_MAX:       {daily['Date'].max()}")
    return output_path


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    for raw_input in args.inputs:
        convert_one(
            input_path=Path(raw_input),
            output_dir=output_dir,
            timezone_name=args.timezone,
            session=args.session,
            regular_start=args.regular_start,
            regular_end=args.regular_end,
        )


if __name__ == "__main__":
    main()
