"""
Multi-asset signal-ratio tranche simulator.

Core logic:
- hold_days slots, each worth ~1/hold_days of total capital
- Each day one slot matures (slot = i % hold_days)
- If any signal > 0:
    ratio_A = w_A / (w_A + w_B)
    ratio_B = w_B / (w_A + w_B)
    invest 100% of matured slot, split by ratio -> A shares + B shares
- If both signals == 0 (HOLD):
    matured slot stays as cash, existing positions unchanged
"""
from __future__ import annotations

import numpy as np
import pandas as pd


DATE_COL = "Date"


def simulate_n_asset_tranches(
    df: pd.DataFrame,
    weight_cols: list[str],
    price_cols: list[str],
    hold_days: int,
    initial_capital: float,
    labels: list[str],
) -> tuple[pd.DataFrame, list[dict]]:
    """
    N-asset generalisation of simulate_multi_asset_tranches.
    Same logic: ratio-weighted investment, 100% of slot when any signal > 0.
    """
    n_assets = len(labels)
    slot_cash   = np.full(hold_days, initial_capital / hold_days, dtype=float)
    slot_shares = np.zeros((hold_days, n_assets), dtype=float)

    equity_rows:     list[dict] = []
    tranche_history: list[dict] = []

    for i, row in enumerate(df.to_dict(orient="records")):
        date   = row[DATE_COL]
        prices = np.array([float(row[pc]) for pc in price_cols])
        ws     = np.array([max(float(row[wc]), 0.0) for wc in weight_cols])
        slot   = i % hold_days

        # mature slot
        matured = slot_cash[slot] + float((slot_shares[slot] * prices).sum())

        tranche_history.append({"date": date, "slot": slot,
                                 "recycled_capital": matured, **{f"w_{l}": ws[j] for j, l in enumerate(labels)}})

        total_w = ws.sum()
        if total_w > 0:
            ratios = ws / total_w
            allocs = matured * ratios
            slot_cash[slot]      = 0.0
            slot_shares[slot, :] = np.where(prices > 0, allocs / prices, 0.0)
        else:
            slot_cash[slot]      = matured
            slot_shares[slot, :] = 0.0

        exposures    = slot_shares.sum(axis=0) * prices
        gross_exp    = float(exposures.sum())
        total_equity = float(slot_cash.sum() + gross_exp)

        row_out = {DATE_COL: date, "gross_exposure": gross_exp, "net_equity": total_equity}
        for j, lbl in enumerate(labels):
            row_out[f"price_{lbl}"]    = prices[j]
            row_out[f"weight_{lbl}"]   = ws[j]
            row_out[f"exposure_{lbl}"] = float(exposures[j])
        equity_rows.append(row_out)

    return pd.DataFrame(equity_rows), tranche_history


def simulate_multi_asset_tranches(
    df: pd.DataFrame,
    weight_col_a: str,
    weight_col_b: str,
    price_col_a: str,
    price_col_b: str,
    hold_days: int,
    initial_capital: float,
    label_a: str = "A",
    label_b: str = "B",
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Simulate a multi-asset long-only tranche portfolio.

    Parameters
    ----------
    df : DataFrame with columns [Date, weight_col_a, weight_col_b, price_col_a, price_col_b]
    weight_col_a / _b : daily signal weight for each asset (0 = HOLD, >0 = BUY)
    price_col_a / _b : daily close price for each asset
    hold_days : tranche holding period (e.g. 130)
    initial_capital : starting capital
    label_a / label_b : asset labels for output columns

    Returns
    -------
    equity_df : daily portfolio snapshot
    tranche_history : list of per-slot recycling events
    """
    slot_cash     = np.full(hold_days, initial_capital / hold_days, dtype=float)
    slot_shares_a = np.zeros(hold_days, dtype=float)
    slot_shares_b = np.zeros(hold_days, dtype=float)

    equity_rows:    list[dict] = []
    tranche_history: list[dict] = []

    for i, row in enumerate(df.to_dict(orient="records")):
        date    = row[DATE_COL]
        price_a = float(row[price_col_a])
        price_b = float(row[price_col_b])
        w_a     = max(float(row[weight_col_a]), 0.0)
        w_b     = max(float(row[weight_col_b]), 0.0)
        slot    = i % hold_days

        # --- mature the slot ---
        matured = (slot_cash[slot]
                   + slot_shares_a[slot] * price_a
                   + slot_shares_b[slot] * price_b)

        tranche_history.append({
            "date": date,
            "slot": slot,
            "w_a": w_a,
            "w_b": w_b,
            "recycled_capital": matured,
        })

        # --- reinvest by signal ratio ---
        total_w = w_a + w_b
        if total_w > 0:
            ratio_a = w_a / total_w
            ratio_b = w_b / total_w
            alloc_a = matured * ratio_a
            alloc_b = matured * ratio_b
            new_shares_a = alloc_a / price_a if price_a > 0 else 0.0
            new_shares_b = alloc_b / price_b if price_b > 0 else 0.0
            slot_cash[slot]     = 0.0
            slot_shares_a[slot] = new_shares_a
            slot_shares_b[slot] = new_shares_b
        else:
            # both HOLD -> keep as cash
            slot_cash[slot]     = matured
            slot_shares_a[slot] = 0.0
            slot_shares_b[slot] = 0.0

        # --- portfolio snapshot ---
        exposure_a   = float((slot_shares_a * price_a).sum())
        exposure_b   = float((slot_shares_b * price_b).sum())
        total_equity = float(slot_cash.sum() + exposure_a + exposure_b)

        equity_rows.append({
            DATE_COL:             date,
            "price_a":            price_a,
            "price_b":            price_b,
            f"weight_{label_a}":  w_a,
            f"weight_{label_b}":  w_b,
            f"exposure_{label_a}": exposure_a,
            f"exposure_{label_b}": exposure_b,
            "gross_exposure":     exposure_a + exposure_b,
            "net_equity":         total_equity,
        })

    return pd.DataFrame(equity_rows), tranche_history
