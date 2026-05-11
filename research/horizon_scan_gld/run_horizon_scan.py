"""
run_horizon_scan.py  --  GLD ML Prediction Horizon Scan (v4)

Feature 구성:
  - Strategy 1 (Adaptive Band): 새로운 dense window 결과 사용
      → 101 windows(20~520d) × topN params → daily position signal
  - Strategy 2,3,4: 기존 앵커 계산 결과 사용
      → 각 horizon별 topN params → daily position signal

전체 features = (101 + S2_horizons + S3_horizons + S4_horizons) × topN
→ LASSO/Ridge/ElasticNet으로 선택
→ h=5~500일 스캔해서 최적 prediction horizon 찾기

Usage:
    python run_horizon_scan.py --top-n 10
    python run_horizon_scan.py --top-n 20
"""
from __future__ import annotations

import argparse, sys, time, warnings
from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LinearRegression, LassoCV, RidgeCV, ElasticNetCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.base import clone
from sklearn.metrics import mean_squared_error

warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=UserWarning)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT  = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from strategy1_dense_windows import (
    add_features, add_position_column,
    ParamSet, NORMALIZE_MODE, DATE_COL,
)

# ============================================================
# CONFIG
# ============================================================
DATA_CSV   = REPO_ROOT / "data" / "gld_us_d.csv"
DENSE_ROOT = SCRIPT_DIR / "outputs" / "strategy1_dense"
OUT_DIR    = SCRIPT_DIR / "outputs"

ANCHOR_DATES = [
    "2021-05-28", "2021-11-30",
    "2022-05-31", "2022-11-30",
    "2023-05-31", "2023-11-30",
    "2024-05-31", "2024-11-29",
    "2025-05-30", "2025-11-28",
]

DENSE_WINDOWS     = list(range(20, 521, 5))   # 101개 (Strategy 1 전용)
SELECTION_DAYS    = 252
SCAN_HORIZONS     = list(range(5, 505, 5))    # 100개
N_CV_SPLITS       = 5
ALPHA_GRID        = np.logspace(-4, 1, 30)
FORWARD_EVAL_DAYS = 30

# 기존 앵커 루트 (전략 2,3,4 결과)
ORIG_ANCHOR_ROOT = REPO_ROOT / "outputs" / "objective1_anchor_date_multi_horizon_evaluation"
# 기존 앵커에서 사용할 horizon 이름 목록
ORIG_HORIZONS = ["1m", "3m", "6m", "1y", "3y", "5y", "10y"]
# ============================================================


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--top-n", type=int, default=10,
                   help="몇 개 파라미터 후보를 feature로 사용 (10 or 20)")
    return p.parse_args()


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_price(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    for col in ["Adj Close", "Adj_Close", "Close", "Price"]:
        if col in df.columns:
            df = df.rename(columns={col: "Price"})
            break
    return df[["Date", "Price"]].dropna().sort_values("Date").reset_index(drop=True)


def get_selection_df(prices: pd.DataFrame, anchor_date: str) -> pd.DataFrame:
    end   = pd.to_datetime(anchor_date)
    start = end - pd.DateOffset(days=SELECTION_DAYS)
    return prices[(prices["Date"] >= start) & (prices["Date"] <= end)].copy().reset_index(drop=True)


def load_topn_params(anchor_date: str, window_days: int, top_n: int) -> list[ParamSet]:
    path = DENSE_ROOT / f"anchor_{anchor_date}" / f"{window_days}d" / f"{window_days}d_top10_results.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path).head(top_n)
        params = []
        for _, row in df.iterrows():
            params.append(ParamSet(
                ma_window=int(row["ma_window"]),
                upper_k=float(row["upper_k"]),
                lower_k=float(row["lower_k"]),
            ))
        return params
    except Exception:
        return []


def compute_daily_signal(sel_df: pd.DataFrame, params: ParamSet) -> np.ndarray:
    try:
        df_feat = add_features(sel_df, params, NORMALIZE_MODE)
        if df_feat.empty:
            return np.zeros(len(sel_df))
        df_pos = add_position_column(df_feat)
        signal = pd.Series(0.0, index=sel_df.index)
        signal.loc[df_pos.index] = df_pos["Position"].values
        return signal.values
    except Exception:
        return np.zeros(len(sel_df))


# ------------------------------------------------------------------
# Strategy 2 (MA Crossover) 신호 계산
# ------------------------------------------------------------------
@dataclass(frozen=True)
class MACrossParams:
    short_ma: int
    long_ma: int

def compute_ma_crossover_signal(sel_df: pd.DataFrame, params: MACrossParams) -> np.ndarray:
    try:
        df = sel_df.copy()
        if params.long_ma > len(df):
            return np.zeros(len(df))
        df["ShortMA"] = df["Price"].rolling(params.short_ma, min_periods=params.short_ma).mean()
        df["LongMA"]  = df["Price"].rolling(params.long_ma,  min_periods=params.long_ma).mean()
        df = df.dropna(subset=["ShortMA","LongMA"]).reset_index(drop=True)
        prev_s = df["ShortMA"].shift(1)
        prev_l = df["LongMA"].shift(1)
        buy  = ((prev_s <= prev_l) & (df["ShortMA"] > df["LongMA"])).astype(int)
        sell = ((prev_s >= prev_l) & (df["ShortMA"] < df["LongMA"])).astype(int)
        pos = np.zeros(len(df))
        state = 0
        for i in range(len(df)):
            if state == 1 and sell.iloc[i]: state = 0
            elif state == 0 and buy.iloc[i]: state = 1
            pos[i] = state
        signal = pd.Series(0.0, index=sel_df.index)
        signal.iloc[df.index] = pos
        return signal.values
    except Exception:
        return np.zeros(len(sel_df))

# ------------------------------------------------------------------
# Strategy 3 (Adaptive Volatility Band) 신호 계산
# ------------------------------------------------------------------
@dataclass(frozen=True)
class VolBandParams:
    vol_window: int
    upper_k: float
    lower_k: float

def compute_vol_band_signal(sel_df: pd.DataFrame, params: VolBandParams, ohlcv_df: pd.DataFrame) -> np.ndarray:
    try:
        df = ohlcv_df[ohlcv_df["Date"].isin(sel_df["Date"])].copy().reset_index(drop=True)
        if len(df) < params.vol_window + 5:
            return np.zeros(len(sel_df))
        df["VolProxy"] = (df["High"] - df["Low"]) / df["Close"].replace(0, np.nan)
        df["VolMean"]  = df["VolProxy"].rolling(params.vol_window, min_periods=params.vol_window).mean()
        df["VolStd"]   = df["VolProxy"].rolling(params.vol_window, min_periods=params.vol_window).std(ddof=0)
        df["UpperBand"] = df["VolMean"] + params.upper_k * df["VolStd"]
        df["LowerBand"] = df["VolMean"] + params.lower_k * df["VolStd"]
        df = df.dropna(subset=["VolMean","UpperBand","LowerBand"]).reset_index(drop=True)
        buy_raw  = (df["VolProxy"] < df["LowerBand"]).astype(int)
        sell_raw = (df["VolProxy"] > df["UpperBand"]).astype(int)
        pos = np.zeros(len(df))
        state = 0
        for i in range(len(df)):
            if state == 1 and sell_raw.iloc[i]: state = 0
            elif state == 0 and buy_raw.iloc[i]: state = 1
            pos[i] = state
        date_to_pos = dict(zip(df["Date"], pos))
        return np.array([date_to_pos.get(d, 0.0) for d in sel_df["Date"]])
    except Exception:
        return np.zeros(len(sel_df))

# ------------------------------------------------------------------
# 기존 앵커에서 전략 2,3,4 topN 파라미터 로드 + 신호 계산
# ------------------------------------------------------------------
def load_orig_topn_signals(sel_df: pd.DataFrame, anchor_date: str, top_n: int, ohlcv_df: pd.DataFrame) -> tuple[list, list]:
    signals, cols = [], []
    anchor_dir = ORIG_ANCHOR_ROOT / f"anchor_{anchor_date}" / "optimization_outputs"
    if not anchor_dir.exists():
        return signals, cols

    # Strategy 2: MA Crossover
    s2_dir = anchor_dir / "21_ma_crossover_optimization"
    for h in ORIG_HORIZONS:
        f = s2_dir / h / f"{h}_top10_results.csv"
        if not f.exists(): continue
        try:
            df = pd.read_csv(f).head(top_n)
            for rank, row in enumerate(df.itertuples(), 1):
                p = MACrossParams(short_ma=int(row.short_ma), long_ma=int(row.long_ma))
                sig = compute_ma_crossover_signal(sel_df, p)
                signals.append(sig)
                cols.append(f"s2_{h}_r{rank}")
        except Exception:
            pass

    # Strategy 3: Adaptive Volatility Band
    s3_dir = anchor_dir / "31_adaptive_volatility_band_optimization"
    for h in ORIG_HORIZONS:
        f = s3_dir / h / f"{h}_top10_results.csv"
        if not f.exists(): continue
        try:
            df = pd.read_csv(f).head(top_n)
            for rank, row in enumerate(df.itertuples(), 1):
                p = VolBandParams(vol_window=int(row.vol_window),
                                  upper_k=float(row.upper_k), lower_k=float(row.lower_k))
                sig = compute_vol_band_signal(sel_df, p, ohlcv_df)
                signals.append(sig)
                cols.append(f"s3_{h}_r{rank}")
        except Exception:
            pass

    return signals, cols


def build_feature_matrix(sel_df: pd.DataFrame, anchor_date: str, top_n: int, ohlcv_df: pd.DataFrame):
    signals, cols = [], []

    # Strategy 1: dense windows (새로운 결과)
    for w in DENSE_WINDOWS:
        params_list = load_topn_params(anchor_date, w, top_n)
        for rank, params in enumerate(params_list, 1):
            signals.append(compute_daily_signal(sel_df, params))
            cols.append(f"s1_{w}d_r{rank}")
        for rank in range(len(params_list) + 1, top_n + 1):
            signals.append(np.zeros(len(sel_df)))
            cols.append(f"s1_{w}d_r{rank}")

    # Strategy 2,3 (기존 앵커 결과)
    s23_signals, s23_cols = load_orig_topn_signals(sel_df, anchor_date, top_n, ohlcv_df)
    signals.extend(s23_signals)
    cols.extend(s23_cols)

    X = np.column_stack(signals) if signals else np.zeros((len(sel_df), 1))
    return X, cols


def build_models(n_splits: int) -> dict:
    cv = TimeSeriesSplit(n_splits=n_splits)
    return {
        "ols":         LinearRegression(),
        "ridge":       Pipeline([("sc", StandardScaler()), ("m", RidgeCV(alphas=ALPHA_GRID, cv=cv))]),
        "lasso":       Pipeline([("sc", StandardScaler()), ("m", LassoCV(alphas=ALPHA_GRID, cv=cv,
                                  max_iter=10000, n_jobs=-1))]),
        "elastic_net": Pipeline([("sc", StandardScaler()), ("m", ElasticNetCV(
                                  alphas=ALPHA_GRID, l1_ratio=[0.1,0.3,0.5,0.7,0.9],
                                  cv=cv, max_iter=10000, n_jobs=-1))]),
    }


def compute_cv_mse(model, X, y, n_splits):
    splitter = TimeSeriesSplit(n_splits=n_splits)
    errs = []
    for tr, val in splitter.split(X):
        if len(tr) < 5 or len(val) < 2:
            continue
        m = clone(model)
        m.fit(X[tr], y[tr])
        errs.append(mean_squared_error(y[val], m.predict(X[val])))
    return float(np.mean(errs)) if errs else np.inf


def run_one_horizon(prices, anchor_date, h, X, sel_df):
    n = len(sel_df)
    if n < h + 20:
        return None

    prices_arr = sel_df["Price"].values
    y = np.full(n, np.nan)
    for i in range(n - h):
        if prices_arr[i] > 0:
            y[i] = (prices_arr[i + h] - prices_arr[i]) / prices_arr[i]

    valid = ~np.isnan(y)
    X_v, y_v = X[valid], y[valid]
    if len(y_v) < 20 or X_v.std(axis=0).max() < 1e-8:
        return None

    n_splits = max(3, min(N_CV_SPLITS, len(y_v) // 20))
    models   = build_models(n_splits)

    best_name, best_mse, best_model = None, np.inf, None
    for name, model in models.items():
        try:
            mse = compute_cv_mse(model, X_v, y_v, n_splits)
            if mse < best_mse:
                best_mse, best_name = mse, name
                best_model = clone(model)
        except Exception:
            continue

    if best_model is None:
        return None
    try:
        best_model.fit(X_v, y_v)
        pred = float(best_model.predict(X[-1:])[0])
    except Exception:
        return None

    pos_y = y_v[y_v > 0]
    scale  = float(np.quantile(pos_y, 0.95)) if len(pos_y) > 5 else 1.0
    weight = float(np.clip(pred / scale, 0.0, 1.0)) if scale > 0 else 0.0

    anchor_end = pd.to_datetime(anchor_date)
    fwd = prices[prices["Date"] > anchor_end].head(min(h, FORWARD_EVAL_DAYS))
    if len(fwd) < 2:
        return None

    bh_return      = float(fwd["Price"].iloc[-1] / fwd["Price"].iloc[0] - 1)
    forward_return = weight * bh_return
    dir_correct    = int(np.sign(pred) == np.sign(bh_return))

    return {
        "anchor_date":    anchor_date,
        "horizon_days":   h,
        "best_model":     best_name,
        "cv_mse":         round(best_mse, 8),
        "predicted_ret":  round(pred, 6),
        "weight":         round(weight, 4),
        "forward_return": forward_return,
        "bh_return":      bh_return,
        "dir_correct":    dir_correct,
        "n_train":        int(len(y_v)),
    }


def main():
    args    = parse_args()
    top_n   = args.top_n
    ensure_dir(OUT_DIR)
    t0 = time.perf_counter()

    print("=" * 65)
    print(f"GLD ML Horizon Scan  [top_n={top_n}]")
    print(f"features: {len(DENSE_WINDOWS)} windows x top{top_n} = {len(DENSE_WINDOWS)*top_n} features")
    print(f"horizons: {SCAN_HORIZONS[0]}~{SCAN_HORIZONS[-1]}d ({len(SCAN_HORIZONS)}개)")
    print("=" * 65)

    prices = load_price(DATA_CSV)

    # OHLCV 로드 (전략 3 Vol Band용)
    ohlcv_df = pd.read_csv(DATA_CSV, parse_dates=["Date"])
    for c in ["High","Low","Close","Open"]:
        candidates = [c, c.lower(), c.upper()]
        for cand in candidates:
            if cand in ohlcv_df.columns:
                ohlcv_df = ohlcv_df.rename(columns={cand: c})
                break
    ohlcv_df = ohlcv_df.sort_values("Date").reset_index(drop=True)

    s23_horizons = len(ORIG_HORIZONS) * top_n * 2  # S2 + S3
    total_features = len(DENSE_WINDOWS) * top_n + s23_horizons
    print(f"  S1 features: {len(DENSE_WINDOWS)}x{top_n}={len(DENSE_WINDOWS)*top_n}")
    print(f"  S2+S3 features: ~{s23_horizons}")
    print(f"  총 예상 features: ~{total_features}")

    all_results = []

    for anchor_date in ANCHOR_DATES:
        anchor_dir = DENSE_ROOT / f"anchor_{anchor_date}"
        if not anchor_dir.exists():
            print(f"[SKIP] {anchor_date}")
            continue

        print(f"\n앵커: {anchor_date}")
        sel_df = get_selection_df(prices, anchor_date)
        if len(sel_df) < 50:
            continue

        print(f"  feature matrix 구성 중...")
        X, cols = build_feature_matrix(sel_df, anchor_date, top_n, ohlcv_df)
        active  = int((X.std(axis=0) > 1e-8).sum())
        print(f"  총 features: {len(cols)}, 유효: {active}")

        anchor_t0 = time.perf_counter()
        for i, h in enumerate(SCAN_HORIZONS):
            res = run_one_horizon(prices, anchor_date, h, X, sel_df)
            if res:
                all_results.append(res)
            if (i + 1) % 25 == 0:
                el = time.perf_counter() - anchor_t0
                rem = el / (i+1) * (len(SCAN_HORIZONS)-i-1)
                print(f"  [{i+1}/{len(SCAN_HORIZONS)}] h={h}d  ({el:.0f}s / est.{rem:.0f}s)")

        print(f"  완료 ({time.perf_counter()-anchor_t0:.0f}s)")

    if not all_results:
        print("결과 없음")
        return

    results_df = pd.DataFrame(all_results)
    out_path   = OUT_DIR / f"horizon_scan_top{top_n}_results.csv"
    results_df.to_csv(out_path, index=False)
    print(f"\n[OK] raw 결과: {out_path}")

    summary = (
        results_df.dropna(subset=["forward_return"])
        .groupby("horizon_days")
        .agg(
            avg_forward_return=("forward_return", "mean"),
            avg_cv_mse=("cv_mse", "mean"),
            avg_bh_return=("bh_return", "mean"),
            avg_weight=("weight", "mean"),
            dir_accuracy=("dir_correct", "mean"),
            best_model_mode=("best_model", lambda x: x.mode()[0] if len(x) else ""),
            count=("anchor_date", "count"),
        )
        .reset_index()
    )
    summary["excess_vs_bh"] = summary["avg_forward_return"] - summary["avg_bh_return"]

    sum_path = OUT_DIR / f"horizon_scan_top{top_n}_summary.csv"
    summary.to_csv(sum_path, index=False)
    print(f"[OK] 요약: {sum_path}")

    print(f"\n=== Top 10 Horizon [top_n={top_n}] ===")
    top = summary.nlargest(10, "avg_forward_return")
    print(top[["horizon_days","avg_forward_return","avg_cv_mse","dir_accuracy","excess_vs_bh","best_model_mode"]].to_string(index=False))

    print(f"\n=== 최저 CV-MSE (예측 정확도) ===")
    top_mse = summary.nsmallest(10, "avg_cv_mse")
    print(top_mse[["horizon_days","avg_cv_mse","avg_forward_return","dir_accuracy","best_model_mode"]].to_string(index=False))

    print(f"\n전체 완료: {(time.perf_counter()-t0)/60:.1f}분")


if __name__ == "__main__":
    main()
