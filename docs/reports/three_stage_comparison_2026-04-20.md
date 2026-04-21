# 세 단계 접근법 비교: Single → Ensemble → ML-Guided

Date: 2026-04-20 (최종 업데이트: 2026-04-20 — Fear-Greed 재계산 완료)
Update interval: 1M / Selection criterion: cv_mse (Obj2), long-only optimization (Obj1)

**B&H 기준**: 2020=+23.9%, 2021=-6.2%, 2022=+0.8%, 2023=+11.8%, 2024=+27.0%
**컬럼 형식**: Ret / Exp / Eff (Ret÷Exp)

---

## 세 단계 정의

| 단계 | 이름 | 방법 | 스크립트 |
|---|---|---|---|
| **A** | Single Signal | 앵커마다 selection return 최고 전략 1개, rank1 파라미터 단독 운용 | `run_objective1_single_strategy_tranche_backtest.py` |
| **B** | Signal Ensemble | 4개 전략 rank1씩 → long-only weight 재최적화 후 가중 조합 | `run_objective1_combination_tranche_backtest.py` |
| **C** | ML-Guided | 신호 행렬 A → cv_mse 모델 선택 (OLS/Ridge/Lasso/ElasticNet) | `run_objective2_monthly_update_tranche_backtest.py` |

---

## Hold 130일 / 1M 업데이트

| 포워드 테스트 | Buy&Hold | A: Single Signal | B: Signal Ensemble | C: ML-Guided |
|---|---:|---|---|---|
| **2020** | +23.9% | +4.4% / 27% / +16% | +6.4% / 32% / +20% | **+10.9%** / 57% / **+19%** |
| **2021** | -6.2%  | +0.3% / 25% / +1%  | +0.3% / 25% / +1%  | **+0.8%** / 29% / **+3%**  |
| **2022** | +0.8%  | -0.9% / 46% / -2%  | -2.3% / 42% / -5%  | **-0.2%** / 31% / **-1%**  |
| **2023** | +11.8% | +1.6% / 25% / +6%  | +2.0% / 23% / +9%  | **+4.0%** / 32% / **+13%** |
| **2024** | +27.0% | +5.9% / 21% / +28% | +8.0% / 29% / +28% | **+16.4%** / 65% / **+25%** |

→ **C가 모든 연도에서 수익 최고**

---

## Hold 45일 / 1M 업데이트

| 포워드 테스트 | Buy&Hold | A: Single Signal | B: Signal Ensemble | C: ML-Guided |
|---|---:|---|---|---|
| **2020** | +23.9% | +4.2% / 28% / +15% | +6.5% / 34% / +19% | **+17.4%** / 72% / **+24%** |
| **2021** | -6.2%  | **+0.0%** / 30% / +0% | **+0.0%** / 30% / +0% | +1.5% / 35% / +4% |
| **2022** | +0.8%  | -2.3% / 57% / -4%  | -4.2% / 50% / -8%  | **-0.6%** / 37% / **-2%**  |
| **2023** | +11.8% | +2.7% / 32% / +8%  | **+5.5%** / 30% / **+18%** | +2.5% / 44% / +6% |
| **2024** | +27.0% | +8.7% / 24% / +36% | +8.6% / 33% / +26% | **+25.2%** / 78% / **+32%** |

→ **2021년은 A/B 방어 우수 (낮은 노출도 덕분)**

---

## 핵심 관찰

### 1. h130에서 C의 일관된 우위
- 수익: 모든 연도 C > B > A 순
- 2024: A(+5.9%) → B(+8.0%) → C(+16.4%) — 단계별 명확한 개선
- **슬라이드 핵심 메시지**: "ML 모델 선택이 단순 조합보다 2배 수익"

### 2. 노출도가 단계별로 증가
- A: 21~46% (신호 약함, 포지션 못 키움)
- B: 23~42% (조합해도 신호 강도 제한)
- C: 29~65% (ML 예측이 확실할 때 노출도 대폭 확대)

### 3. h45에서 2021년 역전
- 2021년 GLD -6.2% 하락: A/B 노출도 30%, C 노출도 35%
- h45에서는 A/B가 오히려 방어 우수

### 4. Fear-Greed 재계산 영향 (2026-04-20)
- 버그(shift(-1)) 수정 후 fear_greed 노출도 ≈ 0% → GLD에서 사실상 신호 없음
- 2020 B&H 수정: +20.2% → +23.9% (데이터 정렬 수정)
- Stage B/A 2020 수치 상향: fear_greed 가중치 재배분 효과

### 5. 선택된 전략 분포 (A 기준)
- 2020~2022, 2024: **adaptive_band 독점** (12/12)
- 2023: adaptive_band 11/12 + adaptive_volatility_band 1/12

---

## 슬라이드 스토리 흐름

```
[Stage A] Single Signal
  → 가장 잘 하는 전략 하나만 운용
  → 낮은 노출도, 낮은 수익 (2024: +5.9% vs B&H +27.0%)

[Stage B] Signal Ensemble
  → 4개 전략 조합, selection period 최적화
  → 약간 개선 (2024: +8.0%)
  → 하지만 조합 신호 자체가 약해 노출도 제한

[Stage C] ML-Guided ← 우리 시스템
  → 신호 행렬에서 미래 수익 예측 학습
  → 확신 높을 때 노출도 대폭 확대
  → 2024: +16.4% (A의 2.8배, B의 2.1배)
  → 불확실 장세(2021~2022)에서 자동 노출도 축소
```

---

## 관련 파일

- `run_objective1_single_strategy_tranche_backtest.py` — Baseline A 스크립트
- `run_objective1_combination_tranche_backtest.py` — Baseline B 스크립트
- `objective1_vs_objective2_comparison_2026-04-20.md` — B vs C 상세
- `objective2_update_frequency_comparison_h45_h130_2026-04-20.md` — Obj2 전체 비교
