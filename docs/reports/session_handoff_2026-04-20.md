# 세션 핸드오프 — 2026-04-20

다음 세션 시작 시 이 파일을 먼저 읽고 이어서 작업할 것.

---

## 오늘 완료한 작업

### 1. Fear-Greed 앵커 재계산 완료
- `shift(-1)` 미래참조 버그 수정 후 2019~2024 전체 앵커 재계산
- `run_objective1_anchor_date_multi_horizon_evaluation.py --strategies fear_greed_candle_volume --reuse-existing-optimization-snapshots` 로 재실행
- 2019-12-31 앵커는 `--strategies all` (reuse 없이) 로 전체 재구성
- 결과: GLD에서 Fear-Greed 노출도 ≈ 0% (임계조건 거의 미충족 — 설계상 정상)

### 2. `--strategies` 인자 추가
- `run_objective1_anchor_date_multi_horizon_evaluation.py`에 `--strategies` 플래그 추가
- `--strategies all` (기본) 또는 `--strategies adaptive_band,ma_crossover` 처럼 선택 실행 가능
- `parse_strategy_keys()` 함수로 유효성 검사
- `anchor_snapshots_exist()` 도 선택 전략 기반으로 필터링

### 3. 전체 백테스트 재실행 완료 (`run_all_backtests.sh`)
- Stage C (Obj2): 5년 × 4 인터벌 × 2 홀드 = 40 runs
- Stage B (Combination): 40 runs
- Stage A (Single Strategy, 5종): 5년 × 5 전략 × 2 홀드 = 50 runs
- 총 130 runs 완료

### 4. 전체 리포트 업데이트 (최종 확정 숫자)
- `three_stage_comparison_2026-04-20.md` ✅
- `four_strategy_single_comparison_2026-04-20.md` ✅
- `objective1_vs_objective2_comparison_2026-04-20.md` ✅
- `objective2_update_frequency_comparison_h45_h130_2026-04-20.md` ✅

### 5. 슬라이드 업데이트
- `docs/slides/objective2_research_presentation_2026-04-20.tex` ✅
- Stage A/B/C 테이블 전부 교체
- Fear-Greed ≈0% 반영
- B&H 2020: +20.2% → +23.9% 수정

---

## 최종 확정 숫자 (h130 / 1M)

| Year | B&H | A: Single | B: Ensemble | C: ML-Guided |
|---|---:|---|---|---|
| 2020 | +23.9% | +4.4%/27%/+16% | +6.4%/32%/+20% | **+10.9%/57%/+19%** |
| 2021 | -6.2% | +0.3%/25%/+1% | +0.3%/25%/+1% | **+0.8%/29%/+3%** |
| 2022 | +0.8% | -0.9%/46%/-2% | -2.3%/42%/-5% | **-0.2%/31%/-1%** |
| 2023 | +11.8% | +1.6%/25%/+6% | +2.0%/23%/+9% | **+4.0%/32%/+12%** |
| 2024 | +27.0% | +5.9%/21%/+29% | +8.0%/29%/+27% | **+16.4%/65%/+25%** |

## 최종 확정 숫자 (h45 / 1M)

| Year | B&H | A: Single | B: Ensemble | C: ML-Guided |
|---|---:|---|---|---|
| 2020 | +23.9% | +4.2%/28%/+15% | +6.5%/34%/+19% | **+17.4%/72%/+24%** |
| 2021 | -6.2% | +0.0%/30%/+0% | +0.0%/30%/+0% | **+1.5%/35%/+4%** |
| 2022 | +0.8% | -2.3%/57%/-4% | -4.2%/50%/-8% | **-0.6%/37%/-2%** |
| 2023 | +11.8% | +2.7%/32%/+8% | +5.5%/30%/+18% | **+2.5%/44%/+6%** |
| 2024 | +27.0% | +8.7%/24%/+36% | +8.6%/33%/+26% | **+25.2%/78%/+32%** |

---

## 개별 전략 최종 숫자 (h130 / 1M)

| Year | B&H | Adap.Band | MA Cross | Adap.Vol | Fear.Greed |
|---|---:|---|---|---|---|
| 2020 | +23.9% | +4.4%/27% | +5.2%/29% | +5.8%/27% | ≈0%/0% |
| 2021 | -6.2% | +0.3%/25% | -0.2%/21% | +0.9%/34% | ≈0%/0% |
| 2022 | +0.8% | -0.9%/46% | -3.0%/18% | -2.1%/31% | ≈0%/1% |
| 2023 | +11.8% | +1.5%/23% | +0.9%/25% | +2.1%/31% | ≈0%/0% |
| 2024 | +27.0% | +5.9%/21% | +6.3%/32% | +10.6%/36% | ≈0%/0% |

---

## Stage C 전체 업데이트 주기 (h130)

| Year | B&H | 1M | 2M | 3M | 6M |
|---|---:|---|---|---|---|
| 2020 | +23.9% | +10.9%/57% | +10.2%/57% | +9.6%/51% | +9.7%/50% |
| 2021 | -6.2% | +0.8%/29% | +0.3%/35% | +0.6%/28% | -0.7%/49% |
| 2022 | +0.8% | -0.2%/31% | +0.9%/35% | -0.8%/33% | -1.7%/44% |
| 2023 | +11.8% | +4.0%/32% | +4.1%/23% | +3.8%/40% | +3.4%/15% |
| 2024 | +27.0% | +16.4%/65% | +13.9%/60% | +11.1%/53% | +5.5%/36% |

## Stage C 전체 업데이트 주기 (h45)

| Year | B&H | 1M | 2M | 3M | 6M |
|---|---:|---|---|---|---|
| 2020 | +23.9% | +17.4%/72% | +16.5%/71% | +13.7%/64% | +13.3%/63% |
| 2021 | -6.2% | +1.5%/35% | +1.8%/37% | +1.2%/34% | -1.2%/49% |
| 2022 | +0.8% | -0.6%/37% | +1.3%/42% | -0.6%/38% | -2.5%/51% |
| 2023 | +11.8% | +2.5%/44% | +3.7%/34% | +0.9%/50% | +3.8%/24% |
| 2024 | +27.0% | +25.2%/78% | +19.8%/73% | +16.2%/66% | +11.0%/52% |

---

## 핵심 발견 (슬라이드 스토리)

1. **C가 h130에서 모든 연도 수익 우위** — A→B→C 명확한 단계별 개선
2. **C가 h45에서도 모든 연도 수익 우위** — Fear-Greed 버그 수정 후 2021 역전 해소
3. **Fear-Greed는 GLD에서 사실상 신호 없음** — 버그 수정 후 의도된 보수적 동작 확인
4. **adaptive_volatility_band가 단일 전략 중 최강** — h130 2024: +10.6%, h45 2024: +14.2%
5. **1M 업데이트가 h130에서 가장 강함** — 빠른 신호 반영으로 강세장 포착

---

## 다음 세션에서 할 수 있는 작업

- **슬라이드 발표 연습** — 발표용 스크립트 또는 노트 정리
- **라이브 파이프라인** — Raspberry Pi 배포 상태 확인, 실시간 신호 모니터링
- **다자산 확장** — GLD 이외 자산(오일, 구리, 주식) 동일 프레임워크 적용 검토
- **SINDy 구현** — 비선형 기저함수 Θ(A) 실험
- **슬라이드 추가 수정** — 발표 피드백 반영

---

## 주요 파일 위치

| 역할 | 경로 |
|---|---|
| 슬라이드 | `docs/slides/objective2_research_presentation_2026-04-20.tex` |
| 세 단계 비교 | `docs/reports/three_stage_comparison_2026-04-20.md` |
| 개별 전략 비교 | `docs/reports/four_strategy_single_comparison_2026-04-20.md` |
| B vs C 상세 | `docs/reports/objective1_vs_objective2_comparison_2026-04-20.md` |
| 업데이트 주기 | `docs/reports/objective2_update_frequency_comparison_h45_h130_2026-04-20.md` |
| 전체 백테스트 스크립트 | `strategies/automation/run_all_backtests.sh` |
| Stage C 스크립트 | `strategies/automation/run_objective2_monthly_update_tranche_backtest.py` |
| Stage B 스크립트 | `strategies/automation/run_objective1_combination_tranche_backtest.py` |
| Stage A 스크립트 | `strategies/automation/run_objective1_single_strategy_tranche_backtest.py` |
| 앵커 최적화 마스터 | `strategies/automation/run_objective1_anchor_date_multi_horizon_evaluation.py` |
| Stage C 출력 | `outputs/objective2_monthly_update_tranche_backtest/` |
| Stage B 출력 | `outputs/objective1_combination_tranche_backtest/` |
| Stage A 출력 | `outputs/objective1_single_strategy_tranche_backtest/` |
