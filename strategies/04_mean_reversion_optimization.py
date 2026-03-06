# 04_mean_reversion_optimization.py
# Build a trade log (buy->sell) from the mean-reversion position/events table,
# then print strategy vs buy-and-hold summary and save the trade log.

from pathlib import Path
import sys
import numpy as np
import pandas as pd


# ============================================================
# PARAMETERS
# ============================================================

# This should be the output from code_03 (or the updated code_02/03 that saves features)
# Must contain at least: Date, Price, Position, BuyEvent, SellEvent
FEATURES_CSV = Path("./data/gold_prices_features.csv")

OUT_TRADES_CSV = Path("./data/mean_reversion_trades.csv")

DATE_COL = "Date"
PRICE_COL = "Price"          # use raw price for human-friendly trade log
POSITION_COL = "Position"
BUY_COL = "BuyEvent"
SELL_COL = "SellEvent"

# If the last trade is open (buy without sell), choose what to do:
# "drop"   -> ignore the open trade
# "close"  -> close it at the last available price
OPEN_TRADE_POLICY = "drop"   # "drop" | "close"

# ============================================================


def load_features(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Features CSV not found: {path}")

    df = pd.read_csv(path)

    required = {DATE_COL, PRICE_COL, POSITION_COL, BUY_COL, SELL_COL}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in features CSV: {missing}")

    df[DATE_COL] = pd.to_datetime(df[DATE_COL])
    df = df.sort_values(DATE_COL).reset_index(drop=True)

    # Ensure numeric
    df[PRICE_COL] = pd.to_numeric(df[PRICE_COL], errors="coerce")
    df[POSITION_COL] = pd.to_numeric(df[POSITION_COL], errors="coerce").fillna(0).astype(int)
    df[BUY_COL] = pd.to_numeric(df[BUY_COL], errors="coerce").fillna(0).astype(int)
    df[SELL_COL] = pd.to_numeric(df[SELL_COL], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=[PRICE_COL]).reset_index(drop=True)
    if df.empty:
        raise ValueError("No valid price data after cleaning.")

    return df


def build_trade_log(df: pd.DataFrame, open_policy: str = "drop") -> pd.DataFrame:
    """
    Convert BuyEvent/SellEvent into a trade log:
    Each trade = one buy followed by the next sell.

    Returns a DataFrame with:
    TradeID, BuyDate, BuyPrice, SellDate, SellPrice, HoldingDays, PnL, Return
    """
    buys = df.index[df[BUY_COL] == 1].to_list()
    sells = df.index[df[SELL_COL] == 1].to_list()

    # Walk through time and pair each buy with the next sell after it.
    trades = []
    sell_ptr = 0
    trade_id = 1

    for b in buys:
        # Advance sell pointer until sell index is after buy index
        while sell_ptr < len(sells) and sells[sell_ptr] <= b:
            sell_ptr += 1

        if sell_ptr >= len(sells):
            # No sell after this buy => open trade
            if open_policy == "close":
                s = len(df) - 1
            else:
                break
        else:
            s = sells[sell_ptr]
            sell_ptr += 1

        buy_date = df.loc[b, DATE_COL]
        buy_price = float(df.loc[b, PRICE_COL])
        sell_date = df.loc[s, DATE_COL]
        sell_price = float(df.loc[s, PRICE_COL])

        holding_days = int((sell_date - buy_date).days)
        pnl = sell_price - buy_price
        ret = (sell_price / buy_price) - 1.0 if buy_price != 0 else np.nan

        trades.append({
            "TradeID": trade_id,
            "BuyDate": buy_date,
            "BuyPrice": buy_price,
            "SellDate": sell_date,
            "SellPrice": sell_price,
            "HoldingDays": holding_days,
            "PnL": pnl,
            "Return": ret,
        })
        trade_id += 1

    trade_df = pd.DataFrame(trades)
    return trade_df


def summarize_strategy(trades: pd.DataFrame) -> dict:
    """
    Summary stats from the trade log.
    Total return is computed by compounding per-trade returns.
    """
    if trades.empty:
        return {
            "num_trades": 0,
            "total_pnl": 0.0,
            "total_return_compounded": 0.0,
            "win_rate": np.nan,
            "avg_trade_return": np.nan,
            "avg_holding_days": np.nan,
        }

    num_trades = len(trades)
    total_pnl = float(trades["PnL"].sum())

    # Compound returns across trades
    total_return = float((1.0 + trades["Return"]).prod() - 1.0)

    win_rate = float((trades["PnL"] > 0).mean())
    avg_trade_return = float(trades["Return"].mean())
    avg_holding_days = float(trades["HoldingDays"].mean())

    return {
        "num_trades": num_trades,
        "total_pnl": total_pnl,
        "total_return_compounded": total_return,
        "win_rate": win_rate,
        "avg_trade_return": avg_trade_return,
        "avg_holding_days": avg_holding_days,
    }


def buy_and_hold_summary(df: pd.DataFrame) -> dict:
    p0 = float(df[PRICE_COL].iloc[0])
    p1 = float(df[PRICE_COL].iloc[-1])
    r = (p1 / p0) - 1.0 if p0 != 0 else np.nan
    return {
        "start_date": df[DATE_COL].iloc[0],
        "end_date": df[DATE_COL].iloc[-1],
        "start_price": p0,
        "end_price": p1,
        "buy_hold_return": float(r),
        "buy_hold_pnl": float(p1 - p0),
    }


def main():
    try:
        df = load_features(FEATURES_CSV)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    trades = build_trade_log(df, open_policy=OPEN_TRADE_POLICY)

    # Save trade log
    OUT_TRADES_CSV.parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUT_TRADES_CSV, index=False)

    # Print samples + summary
    print("=" * 70)
    print("TRADE LOG (last 10 trades)")
    print("=" * 70)
    if trades.empty:
        print("[WARN] No trades were generated. Check BuyEvent/SellEvent logic.")
    else:
        print(trades.tail(10).to_string(index=False))

    strat = summarize_strategy(trades)
    bh = buy_and_hold_summary(df)

    print("\n" + "=" * 70)
    print("STRATEGY SUMMARY (Mean Reversion: buy on LowerBreak, sell on UpperBreak)")
    print("=" * 70)
    print(f"Trades:              {strat['num_trades']}")
    print(f"Total PnL:           {strat['total_pnl']:.4f} (in price units)")
    print(f"Total Return:        {strat['total_return_compounded']*100:.2f}% (compounded across trades)")
    print(f"Win rate:            {strat['win_rate']*100:.2f}%")
    print(f"Avg trade return:    {strat['avg_trade_return']*100:.2f}%")
    print(f"Avg holding days:    {strat['avg_holding_days']:.2f}")

    print("\n" + "=" * 70)
    print("BUY & HOLD SUMMARY")
    print("=" * 70)
    print(f"Period:              {bh['start_date'].date()}  ->  {bh['end_date'].date()}")
    print(f"Start price:          {bh['start_price']:.4f}")
    print(f"End price:            {bh['end_price']:.4f}")
    print(f"Buy&Hold PnL:         {bh['buy_hold_pnl']:.4f} (in price units)")
    print(f"Buy&Hold Return:      {bh['buy_hold_return']*100:.2f}%")

    print("\n[OK] Saved trade log CSV:", OUT_TRADES_CSV.resolve())
    print("=" * 70)


if __name__ == "__main__":
    main()