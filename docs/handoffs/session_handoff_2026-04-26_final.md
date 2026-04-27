# 세션 핸드오프 — 2026-04-26 (최종)

다음 세션 시작 시 이 파일을 먼저 읽고 이어서 작업할 것.

---

## 오늘 완료한 작업 (전체)

### 1. GLD 연구 완료

- **h45 전용 top-10 실행** (target=45, hold=45) → Sharpe 0.33, 실용 불가 확인
- **h130 vs h45 완전 비교표** (top-10~80, 2020~2024 per-year)
  - 핵심: 2021년 h130 -6~+3% vs h45 -18~-24% — 단기 예측이 노이즈에 취약
  - "투자가 45일이어도 모델은 130일로 학습하는 게 맞다" 확인
- **MSE vs N 곡선** → 역U자, double descent 없음. 피처 늘릴수록 MSE 증가하나 Lasso가 완충
- **Exposure cap 실험** (cap=0.6) → top-50/70 모두 비권장. Sharpe 하락, 최악해 악화
- **h130이 압도적 우수** 이유: Obj1 eval_horizons의 6m(≈130d)와 예측 타깃 정렬

### 2. BRK-B 파이프라인 완료

- **79/79 앵커 최적화** (2019-12-31 ~ 2026-03-31)
- **2020~2024 백테스트** (top-10, h130):
  - Sharpe 2.16, **전 연도 플러스** (최악 2022 +8.4%)
  - 5년 누적 +70.9% vs B&H +98.5%
- **라이브 시그널** (2026-04-24): BUY moderate, weight=0.55, 예측 +2.8%, ElasticNet, Adaptive Band 주도
- **Horizon 스캔** (2020~2024 5개 윈도우): mean 118d, median 109d → **h130 유지 결정**
  - 단기(≤45d) 한 번도 선택 안 됨. 분산 큼(std 57d)
- **버그 수정**: `run_objective2_latest_live_signal.py` 출력 경로 하드코딩 → symbol 기반으로 수정
  - `latest_gld_signal.json`, `latest_brkb_signal.json` 분리 완료

### 3. 멀티에셋 시뮬레이터 구현

**위치: `strategies/automation/`**
- `simulate_multi_asset_tranches.py` — N자산 신호비율 트랜치 시뮬레이터 (핵심 로직)
- `run_multi_asset_tranche_backtest.py` — 실제 모델 시그널 CSV 2개 받아 실행

**핵심 로직:**
```
매일 slot 만기 → w_A + w_B > 0 이면 100% 재투자, 신호 비율로 분배
                → 둘 다 0 (HOLD) 이면 현금 유지
```

### 4. 오라클 시뮬레이션

**위치: `research/oracle_simulation/`**
- `run_oracle_simulation.py` — 2자산 오라클 (full/proportional 모드)
- `run_oracle_all_combinations.py` — 6자산 57개 조합 전부 실행
- 결과: `research/oracle_simulation/outputs/oracle_all_combinations.csv`

**GLD+BRKB 오라클 결과 (2020~2024):**
| Mode | 5yr | Annual | Worst | Sharpe |
|---|---|---|---|---|
| Full | +164.7% | +21.5% | +16.6% | 3.63 |
| Proportional | +192.4% | +23.9% | +18.8% | 3.59 |

**57개 조합 핵심 발견:**
- FULL 기준: 2~3개 조합이 최고, 자산 늘릴수록 희석 (6개 = +149.9%)
- 안정성 best: GLD+BRKB+QQQ (Sharpe 3.02, worst +17.2%, 5yr +190.6%)
- 수익 best: BRKB+RKLB (+290.2%), BRKB+QQQ+RKLB (+243.3%)
- GLD+TLT 최하 (+66.9%) — 방어적 자산끼리 상호보완 없음
- **오라클 용어**: "Oracle bound" — 완벽한 예측 시 이론적 상한선 (정식 CS 용어)

### 5. 코드 개선

- `run_asset.py`: `--eval-start/end`, `--top-n-per-family` backtest 전달 추가
- `run_asset.py`: `step_signal`이 config의 `live_signal_out/signal_log_out` 전달
- 분석 스크립트: `scripts/analyze_topn_peryear.py`, `scripts/analyze_mse_vs_topn.py`

---

## 현재 진행 중 (내일 아침 확인)

### BRK-B top-N 백테스트 (자동 실행 중)
- h130 top-10~80 × h45 top-10~80 = 16개
- 결과 위치: `outputs/objective2_monthly_update_tranche_backtest/brkb_top*_h*.csv`
- 완료 후 실행: `python scripts/analyze_topn_peryear.py --horizon h130` (BRK-B용 수정 필요)

---

## 다음 세션 할 작업 (우선순위)

### 즉시
1. **발표 슬라이드 최종 점검** — 오늘 분석 결과 반영 여부 확인
2. **BRK-B top-N 결과 분석** — GLD와 비교, peak N 확인

### 연구
3. **QQQ 앵커 최적화** — GLD+BRKB+QQQ 실제 모델 멀티에셋 백테스트 준비
4. **멀티에셋 실제 백테스트** — `run_multi_asset_tranche_backtest.py` 실행
5. **ALPACA_DRY_RUN=false** — Pi에서 활성화
6. **SPY/TLT 앵커 최적화** (중기)

### 중기 연구 방향 (발표 후)
7. **Wider eval horizons** — Obj1에 18m/24m 추가 → 솔루션 벡터 확장 실험
   - 예상: top-40~50보다 더 넓은 최적 구간 찾을 수 있음
   - 우려: 노이즈 증가 가능성 (Lasso가 필터링할지 지켜봐야)
8. **GLD+BRKB+QQQ 오라클 vs 실제 모델 gap 분석**
9. 사용자 보유 이론 적용 (오라클 분석 결과와 연결)

---

## 자산별 현황

| 자산 | 앵커 | 백테스트 | 라이브 시그널 | 비고 |
|---|---|---|---|---|
| GLD | 79개 ✅ | 완료 ✅ | BUY strong w=1.0 | h130 top-10 기준 |
| BRK-B | 79개 ✅ | 완료 ✅ | BUY moderate w=0.55 | h130 top-10 기준 |
| SPY | 1개 | 미실행 | 없음 | 데이터 있음 |
| QQQ | 없음 | 미실행 | 없음 | 데이터 있음, 앵커 필요 |
| TLT | 없음 | 미실행 | 없음 | 데이터 있음 |
| RKLB | 없음 | 미실행 | 없음 | 데이터 있음 |

---

## 주요 파일 위치

| 항목 | 경로 |
|---|---|
| 멀티에셋 시뮬레이터 | `strategies/automation/simulate_multi_asset_tranches.py` |
| 멀티에셋 백테스트 | `strategies/automation/run_multi_asset_tranche_backtest.py` |
| 오라클 시뮬레이션 | `research/oracle_simulation/` |
| 57개 조합 결과 | `research/oracle_simulation/outputs/oracle_all_combinations.csv` |
| BRK-B 분석 노트 | `docs/notes/brkb_backtest_analysis_2026-04-26.md` |
| top-N 분석 노트 | `docs/notes/top_n_feature_expansion_analysis_2026-04-25.md` |
| GLD 시그널 | `outputs/live/latest_gld_signal.json` |
| BRK-B 시그널 | `outputs/live/latest_brkb_signal.json` |

---

## 커밋 이력 (오늘)

| 커밋 | 내용 |
|---|---|
| APR26-01 | h45 top-N 결과 + horizon mismatch insight |
| APR26-02 | GLD 전체 분석 + BRK-B 백테스트/시그널 파이프라인 |
| APR26-03 | BRK-B horizon 스캔 결과 |
| APR26-04 | (미완) 멀티에셋 시뮬레이터 + 오라클 시뮬레이션 |
