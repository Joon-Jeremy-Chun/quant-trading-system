from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


# ---- 1) 금 ETF 심볼(필요시 추가/삭제) ----
GOLD_ETFS = [
    "GLD",   # SPDR Gold Shares
    "IAU",   # iShares Gold Trust
    "SGOL",  # abrdn Physical Gold Shares ETF
    "BAR",   # GraniteShares Gold Trust
    "GLDM",  # SPDR Gold MiniShares
    "OUNZ",  # VanEck Merk Gold Trust
    "AAAU",  # Perth Mint Physical Gold
]


# ---- 2) 환경변수에서 Alpaca 키 불러오기 ----
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
                "Please set APCA_API_KEY_ID and APCA_API_SECRET_KEY in your environment."
            )
        return AlpacaCreds(key=key, secret=secret)


# ---- 3) trading_bot/data 폴더 보장 ----
def ensure_data_dir(repo_root: Path) -> Path:
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# ---- 4) Alpaca에서 바 데이터 가져와 표준 DF로 ----
def fetch_bars_df(
    client: StockHistoricalDataClient,
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: TimeFrame = TimeFrame.Day,
    adjustment: str = "all",
    feed: str = "iex",  # ★ 핵심: SIP 제한 회피 (IEX로 고정)
) -> pd.DataFrame:
    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=timeframe,
        start=start,
        end=end,
        adjustment=adjustment,
        feed=feed,
    )

    bars = client.get_stock_bars(req).df

    if bars.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    # MultiIndex (symbol, timestamp) -> slice symbol
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol)

    # 정리
    bars.index = pd.to_datetime(bars.index, utc=True)
    bars = bars.sort_index()

    # 표준 컬럼만 유지
    cols = ["open", "high", "low", "close", "volume"]
    bars = bars[[c for c in cols if c in bars.columns]].copy()

    return bars


# ---- 5) 저장 (CSV) ----
def save_df_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=True)


# ---- 6) 메인 ----
def main(
    symbols: Iterable[str] = GOLD_ETFS,
    timeframe: TimeFrame = TimeFrame.Day,
    start_date_utc: datetime = datetime(2005, 1, 1, tzinfo=timezone.utc),  # ★ 최대 과거로
    end_date_utc: Optional[datetime] = None,
    adjustment: str = "all",
    feed: str = "iex",  # ★ 핵심
) -> None:
    # 이 파일이 trading_bot/trading_bot/ 아래에 있다면 parents[1]이 repo_root일 가능성 큼
    # 안전하게: data 폴더가 보이는 위치까지 올라가며 탐색하는 방법도 있지만,
    # 지금은 간단히 "현재 파일 기준 2단계 위"를 repo_root로 둠.
    repo_root = Path(__file__).resolve().parents[1]  # test2.py가 trading_bot/trading_bot에 있을 때
    # 만약 data 폴더가 repo_root 바로 아래가 아니라면 아래 줄을 repo에 맞게 조정:
    # repo_root = Path(__file__).resolve().parents[2]

    data_dir = ensure_data_dir(repo_root)

    creds = AlpacaCreds.from_env()
    client = StockHistoricalDataClient(creds.key, creds.secret)

    end = end_date_utc or datetime.now(timezone.utc)
    start = start_date_utc

    print(f"Repo root : {repo_root}")
    print(f"Data dir  : {data_dir}")
    print(f"Range     : {start.isoformat()}  ->  {end.isoformat()}")
    print(f"Timeframe : {timeframe}")
    print(f"Feed      : {feed}")
    print("-" * 60)

    summary = []

    for sym in symbols:
        try:
            df = fetch_bars_df(
                client=client,
                symbol=sym,
                start=start,
                end=end,
                timeframe=timeframe,
                adjustment=adjustment,
                feed=feed,
            )

            out_path = data_dir / f"{sym}_{timeframe.value}_bars.csv"
            save_df_csv(df, out_path)

            summary.append((sym, len(df), str(out_path)))
            print(f"[OK] {sym}: {len(df)} rows -> {out_path}")

        except Exception as e:
            print(f"[FAIL] {sym}: {e}")

    print("\n--- Summary ---")
    for sym, n, p in summary:
        print(f"{sym}: {n} rows saved at {p}")


if __name__ == "__main__":
    main()