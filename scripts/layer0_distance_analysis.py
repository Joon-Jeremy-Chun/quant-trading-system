"""
layer0_distance_analysis.py

Layer 0 가설 검증:
"자산 간 거리가 멀수록 조합 시 MDD가 낮아지는가?"

5가지 거리 행렬 계산:
  1. Correlation Distance  : d = 1 - |pearson(r_i, r_j)|
  2. Wasserstein Distance  : 수익률 분포 간 거리 (비선형)
  3. DTW Distance          : 시계열 모양 유사도 (직접 구현)
  4. Latent Space Distance : PCA 잠재 공간 거리 (비레이블 학습)
  5. Tail Dependence Dist  : 폭락 시 동시 하락 빈도 (하방 꼬리 의존도)
                             MDD는 폭락 때 발생 → 폭락 동조 = 진짜 위험
                             각 자산 = 846차원 수익률 벡터
                             → PCA로 저차원 압축
                             → 잠재 공간 유클리드 거리

6자산 → 15쌍 거리 행렬 → 51개 조합의 평균거리 vs 실제 MDD 상관 분석

Usage:
    python scripts/layer0_distance_analysis.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance, pearsonr, spearmanr
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR   = REPO_ROOT / "outputs" / "objective2_monthly_update_tranche_backtest"
RESULT_DIR= REPO_ROOT / "outputs" / "layer0_distance_analysis"

ASSETS = ["GLD", "BRK-B", "QQQ", "RKLB", "ITA", "VRT"]
SLUG   = {"GLD":"gld","BRK-B":"brkb","QQQ":"qqq","RKLB":"rklb","ITA":"ita","VRT":"vrt"}
LABEL  = {"GLD":"GLD","BRK-B":"BRKB","QQQ":"QQQ","RKLB":"RKLB","ITA":"ITA","VRT":"VRT"}


# ── 데이터 로드 ────────────────────────────────────────────────────────────────
def load_returns(asset: str) -> pd.DataFrame:
    slug = SLUG[asset]
    for pf in [f"6asset_{slug}_a", f"4asset_{slug}_b"]:
        p = OUT_DIR / f"monthly_update_tranche_backtest_equity_curve_{pf}.csv"
        if p.exists():
            df = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
            df["r"] = df["price"].pct_change().fillna(0)
            df["w"] = pd.to_numeric(df["portfolio_weight"], errors="coerce").fillna(0).clip(lower=0)
            return df[["Date", "r", "w"]]
    return None

def load_all() -> dict[str, pd.DataFrame]:
    dfs = {}
    for a in ASSETS:
        df = load_returns(a)
        if df is not None:
            dfs[a] = df
    # 공통 날짜로 정렬
    common = None
    for df in dfs.values():
        dates = set(df["Date"])
        common = dates if common is None else common & dates
    common = sorted(common)
    for a in dfs:
        dfs[a] = dfs[a][dfs[a]["Date"].isin(common)].reset_index(drop=True)
    return dfs, common


# ── 거리 함수 3종 ──────────────────────────────────────────────────────────────

def dist_correlation(r1: np.ndarray, r2: np.ndarray) -> float:
    """1 - |pearson correlation|  (0=완전동조, 1=완전독립)"""
    corr, _ = pearsonr(r1, r2)
    return 1.0 - abs(corr)


def dist_wasserstein(r1: np.ndarray, r2: np.ndarray) -> float:
    """Wasserstein distance between return distributions (분포 거리)"""
    return float(wasserstein_distance(r1, r2))


def build_latent_distance_matrix(dfs: dict, n_components: int = 10) -> pd.DataFrame:
    """
    비레이블 학습 기반 거리:
    각 자산 = 수익률 시계열 벡터 (846차원)
    → 전체 행렬 표준화
    → PCA로 n_components 차원으로 압축
    → 잠재 공간에서 유클리드 거리
    """
    assets = list(dfs.keys())
    # 각 자산의 수익률 벡터 (행: 자산, 열: 시간)
    R = np.array([dfs[a]["r"].values for a in assets])  # shape: (6, 846)

    # 표준화 — 절대 수익률 크기 무관하게 (위상적 접근)
    scaler = StandardScaler()
    R_scaled = scaler.fit_transform(R.T).T  # 각 자산별 표준화

    # PCA — 잠재 공간으로 압축
    n_comp = min(n_components, len(assets) - 1)
    pca = PCA(n_components=n_comp)
    # 시간 축을 특성으로: 각 자산을 시간 패턴의 점으로 봄
    # R_scaled.T: shape (846, 6) → PCA의 각 샘플 = 하루, 각 특성 = 자산
    pca.fit(R_scaled.T)

    # 각 자산의 잠재 벡터: 그 자산이 다른 자산들과 어떤 시간 패턴으로 공존하는지
    # 대신 자산을 직접 투영: R_scaled shape (6, 846)을 PCA 공간에서 비교
    pca2 = PCA(n_components=n_comp)
    latent = pca2.fit_transform(R_scaled)  # shape: (6, n_comp) — 각 자산의 잠재 벡터

    print(f"\n  [PCA Latent] explained variance: {pca2.explained_variance_ratio_.cumsum()[-1]*100:.1f}% ({n_comp}개 성분)")

    # 유클리드 거리 행렬
    n = len(assets)
    mat = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                mat[i, j] = float(np.linalg.norm(latent[i] - latent[j]))

    # 정규화 (0~1 범위)
    max_d = mat.max()
    if max_d > 0:
        mat = mat / max_d

    return pd.DataFrame(mat, index=assets, columns=assets)


def dist_tail_dependence(r1: np.ndarray, r2: np.ndarray, q: float = 0.15) -> float:
    """
    하방 꼬리 의존도 거리 (Lower Tail Dependence Distance)

    두 자산이 동시에 하위 q% 수익률을 기록하는 조건부 확률.
    = P(r2 < q분위 | r1 < q분위)

    높을수록 = 폭락 때 같이 빠짐 = 앵커 효과 없음 = 거리가 가까움
    d = 1 - tail_dependence (0=완전독립, 1=완전동조)
    """
    q1 = np.quantile(r1, q)
    q2 = np.quantile(r2, q)
    # r1이 하위 q분위일 때 r2도 하위 q분위인 비율
    both_tail  = np.sum((r1 <= q1) & (r2 <= q2))
    r1_in_tail = np.sum(r1 <= q1)
    if r1_in_tail == 0:
        return 1.0
    tail_dep = both_tail / r1_in_tail   # 조건부 확률
    return 1.0 - tail_dep               # 거리로 변환 (클수록 독립)


def dtw_distance(s1: np.ndarray, s2: np.ndarray) -> float:
    """
    Dynamic Time Warping (DTW) — 시계열 모양 거리
    윈도우 제약(Sakoe-Chiba band) 적용으로 속도 최적화
    """
    n, m = len(s1), len(s2)
    window = max(10, int(max(n, m) * 0.1))  # 10% band
    dtw = np.full((n + 1, m + 1), np.inf)
    dtw[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(max(1, i - window), min(m + 1, i + window + 1)):
            cost = abs(s1[i - 1] - s2[j - 1])
            dtw[i, j] = cost + min(dtw[i-1, j], dtw[i, j-1], dtw[i-1, j-1])
    return float(dtw[n, m]) / max(n, m)   # 길이 정규화


# ── 거리 행렬 계산 ─────────────────────────────────────────────────────────────
def build_distance_matrices(dfs: dict) -> dict[str, pd.DataFrame]:
    assets = list(dfs.keys())
    n = len(assets)
    mats = {
        "correlation":    np.zeros((n, n)),
        "wasserstein":    np.zeros((n, n)),
        "dtw":            np.zeros((n, n)),
        "tail_dependence":np.zeros((n, n)),
    }

    print("Computing pairwise distances...")
    for i, a1 in enumerate(assets):
        for j, a2 in enumerate(assets):
            if i >= j:
                continue
            r1 = dfs[a1]["r"].values
            r2 = dfs[a2]["r"].values
            dc = dist_correlation(r1, r2)
            dw = dist_wasserstein(r1, r2)
            dd = dtw_distance(r1, r2)
            dt = dist_tail_dependence(r1, r2)
            mats["correlation"][i, j]     = mats["correlation"][j, i]     = dc
            mats["wasserstein"][i, j]     = mats["wasserstein"][j, i]     = dw
            mats["dtw"][i, j]             = mats["dtw"][j, i]             = dd
            mats["tail_dependence"][i, j] = mats["tail_dependence"][j, i] = dt
            print(f"  {LABEL[a1]:<6} <-> {LABEL[a2]:<6}  corr={dc:.4f}  wass={dw:.4f}  dtw={dd:.6f}  tail={dt:.4f}")

    result = {}
    for name, mat in mats.items():
        df = pd.DataFrame(mat, index=assets, columns=assets)
        result[name] = df
    return result


# ── 조합별 평균거리 계산 ───────────────────────────────────────────────────────
def combo_avg_distance(combo: list[str], dist_df: pd.DataFrame) -> float:
    if len(combo) == 1:
        return 0.0
    pairs = list(itertools.combinations(combo, 2))
    return float(np.mean([dist_df.loc[a, b] for a, b in pairs]))


# ── 포트폴리오 MDD 계산 ────────────────────────────────────────────────────────
def portfolio_mdd(combo: list[str], dfs: dict, mode: str = "strategy") -> float:
    merged = None
    for a in combo:
        d = dfs[a].rename(columns={"r": f"r_{a}", "w": f"w_{a}"})
        cols = ["Date", f"r_{a}", f"w_{a}"]
        merged = d[cols] if merged is None else merged.merge(d[cols], on="Date", how="inner")

    if mode == "strategy":
        wc = [f"w_{a}" for a in combo]
        rc = [f"r_{a}" for a in combo]
        raw   = merged[wc].clip(lower=0)
        scale = raw.sum(axis=1).clip(lower=1.0)
        norm  = raw.div(scale, axis=0)
        port_r = sum(norm[f"w_{a}"] * merged[f"r_{a}"] for a in combo)
    else:  # B&H equal weight
        rc = [f"r_{a}" for a in combo]
        port_r = merged[rc].mean(axis=1)

    eq  = (1 + port_r).cumprod()
    mdd = ((eq / eq.cummax()) - 1).min() * 100
    return float(mdd)


# ── 상관 분석 ─────────────────────────────────────────────────────────────────
def analyze_correlation(combo_data: list[dict], dist_name: str, mode: str) -> None:
    avg_dists = [r["avg_dist"] for r in combo_data]
    mdds      = [r["mdd"] for r in combo_data]

    pearson_r, pearson_p = pearsonr(avg_dists, mdds)
    spearman_r, spearman_p = spearmanr(avg_dists, mdds)

    print(f"\n  [{dist_name.upper()} x {mode} MDD]  n={len(combo_data)}")
    print(f"    Pearson  r={pearson_r:+.3f}  p={pearson_p:.4f}  {'*' if pearson_p<0.05 else ''}")
    print(f"    Spearman r={spearman_r:+.3f}  p={spearman_p:.4f}  {'*' if spearman_p<0.05 else ''}")
    if pearson_r < -0.3 and pearson_p < 0.05:
        print(f"    => 거리 멀수록 MDD 낮아짐 (가설 지지)")
    elif abs(pearson_r) < 0.2:
        print(f"    => 거리와 MDD 거의 무관")
    else:
        print(f"    => 관계 있으나 방향 확인 필요")


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 70)
    print("  Layer 0 Distance Matrix Analysis")
    print("  가설: 거리 멀수록 MDD 낮아지는가?")
    print("=" * 70)

    dfs, common = load_all()
    print(f"\nAssets: {list(dfs.keys())}")
    print(f"Common dates: {len(common)}  ({common[0].date()} ~ {common[-1].date()})")

    # 거리 행렬 계산
    dist_mats = build_distance_matrices(dfs)

    # 4번째: PCA 잠재 공간 거리
    latent_mat = build_latent_distance_matrix(dfs)
    dist_mats["latent_pca"] = latent_mat

    # 15쌍 거리 행렬 출력
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    for name, mat in dist_mats.items():
        out = RESULT_DIR / f"distance_matrix_{name}.csv"
        mat.to_csv(out, float_format="%.4f")
        print(f"\n[{name.upper()}] Distance Matrix:")
        print(mat.round(4).to_string())

    # 모든 조합 (2,3,4,6자산)
    assets = list(dfs.keys())
    combos = []
    for size in [2, 3, 4, 6]:
        for combo in itertools.combinations(assets, size):
            combos.append(list(combo))

    print(f"\n\nTotal combinations: {len(combos)}")

    # 각 조합의 평균거리 + 실제 MDD 계산
    rows = []
    for combo in combos:
        lbl = "+".join(LABEL[a] for a in combo)
        mdd_s = portfolio_mdd(combo, dfs, "strategy")
        mdd_b = portfolio_mdd(combo, dfs, "bh")
        row = {"label": lbl, "size": len(combo), "mdd_strategy": mdd_s, "mdd_bh": mdd_b}
        for dname, mat in dist_mats.items():
            row[f"dist_{dname}"] = combo_avg_distance(combo, mat)
        rows.append(row)

    df_res = pd.DataFrame(rows)
    out_csv = RESULT_DIR / "combo_distance_vs_mdd.csv"
    df_res.to_csv(out_csv, index=False, float_format="%.4f")

    # 상관 분석 — 가설 검증
    print("\n" + "=" * 70)
    print("  상관 분석: 평균 거리 vs 실제 MDD")
    print("  (r < 0 이면 '거리 멀수록 MDD 낮음' = 가설 지지)")
    print("=" * 70)

    for dname in ["correlation", "wasserstein", "dtw", "latent_pca", "tail_dependence"]:
        for mode, mdd_col in [("strategy", "mdd_strategy"), ("B&H", "mdd_bh")]:
            data = [{"avg_dist": row[f"dist_{dname}"], "mdd": row[mdd_col]} for _, row in df_res.iterrows()]
            analyze_correlation(data, dname, mode)

    # 요약 테이블 — 2자산 조합 (해석이 가장 명확)
    print("\n" + "=" * 70)
    print("  2자산 조합 상세 (거리 vs MDD)")
    print("=" * 70)
    two = df_res[df_res["size"] == 2].sort_values("dist_correlation", ascending=False)
    print(f"  {'조합':<14} {'Corr-d':>7} {'Wass-d':>7} {'DTW-d':>9} {'PCA-d':>7} {'Tail-d':>7} {'S.MDD':>7} {'BH.MDD':>7}")
    print("  " + "-" * 78)
    for _, r in two.iterrows():
        print(f"  {r['label']:<14} {r['dist_correlation']:>7.4f} {r['dist_wasserstein']:>7.4f} {r['dist_dtw']:>9.6f} {r['dist_latent_pca']:>7.4f} {r['dist_tail_dependence']:>7.4f} {r['mdd_strategy']:>6.1f}% {r['mdd_bh']:>6.1f}%")

    print(f"\n[OK] 결과 저장: {RESULT_DIR}/")


if __name__ == "__main__":
    main()
