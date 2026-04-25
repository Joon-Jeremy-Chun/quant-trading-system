# Session Handoff Note

Date: 2026-04-20 (자기 전 저장)

---

## 이번 세션에서 한 것

### 1. 코드 버그 수정 (전부 완료)
- Fear-Greed `shift(-1)` look-ahead 제거 (41, 42, strategy_matrix_builder, objective2_signal_matrix_builder)
- Adaptive band z-score 정규화 일관성 수정 (전체 history 기준으로)
- `get_test_df` 순서 수정 → `add_targets` 이후에 필터링
- `get_history_df` import 누락 추가
- `selection_cv_mse` (TimeSeriesSplit CV) 기반 모델 선택으로 변경
- `OPEN_TRADE_POLICY = "close"` (12, 22, 32, 42 전부)
- 41, 42 경로 `SCRIPT_DIR` 기준으로 수정 (어디서 실행해도 동작)
- `month_metadata`에 `selection_cv_mse` 저장 누락 수정

### 2. 백테스트 실행 완료
- 1M 업데이트, 130일 hold, 2020~2024 전부 새 코드로 완료 → `summary_2020~2024.json`
- 2M 업데이트, 130일 hold, 2020~2024 완료 → `summary_2020~2024_2m.json`
- 3M 업데이트, 130일 hold, 2020~2024 완료 → `summary_2020~2024_3m.json`

### 3. 주요 발견
- `selection_cv_mse`로 바꾼 후 5개 연도 전부 수익 개선 (2024: +7.4% → +16.4%)
- OLS 독점 깨지고 Ridge/Lasso/ElasticNet 선택됨
- **노출도 행동 검증됨**: 2021~2022 횡보/불확실 장세에서 노출도 자동 축소 (42% / 37%)
- 1M 업데이트가 새 코드에서 전반적으로 가장 강함 (구 코드에선 3M이 best였음)
- 2M은 불확실 장세에서 자본효율 우수

### 4. 보고서/노트 저장
- `docs/reports/objective2_update_frequency_comparison_2026-04-20.md` — 전체 비교 보고서
- `docs/notes/multi_asset_pipeline_vision_2026-04-19.md` — 다자산 파이프라인 비전
- `docs/notes/dynamic_capital_allocation_vision_2026-04-19.md` — 동적 자본 배분 시스템 비전

---

## 다음 세션에서 할 것 (우선순위 순)

### 즉시 할 것
1. **6M 업데이트 백테스트 실행** (2020~2024)
   ```
   python strategies/automation/run_objective2_monthly_update_tranche_backtest.py --evaluation-start-date 2020-02-01 --evaluation-end-date 2020-12-31 --update-interval-months 6 --tag 2020_6m
   ```
   (2021~2024도 동일하게)

2. **45일 hold 버전도 새 코드로 실행** (1M/2M/3M/6M)
   - `--target-horizon-days 45 --tag 2020_1m_h45` 등

3. **비교표 완성 후 보고서 최종 업데이트**

### 중기 목표
4. **Anchor snapshot 재계산 고려**
   - 현재 anchor는 Fear-Greed 버그 있는 파라미터로 생성됨
   - `run_objective1_anchor_date_multi_horizon_evaluation.py`로 재실행 필요
   - 연도별 커맨드 준비되어 있음 (2020~2024 월별 anchor dates)
   - 약 2일 소요 예상

5. **다자산 파이프라인 설계 시작**
   - BRK.B 등 두 번째 자산으로 파이프라인 테스트
   - GLD 노출도 낮은 시기와 다른 자산 노출도 상관관계 연구

---

## 큰 그림 비전 (오늘 이야기한 것)

1. **노출도가 진짜 알파** — 수익률/노출도 비율(자본효율)이 진짜 지표
2. **불확실할 때 노출도 축소** → 그 자본을 다른 자산에 배치
3. **닫힌 계 논리** — 전체 포트폴리오 자본은 보존, GLD 노출 낮을 때 다른 곳 높아짐
4. **다차원 확장** — GLD + 주식 + 채권 + 암호화폐 각각 독립 모델 → 동적 자본 배분 시스템
5. **최종 목표** — 범용 strategy-space 파이프라인, 자산만 바꾸면 동작

---

## 다음 세션 시작할 때 Claude에게

> "session_handoff_2026-04-20.md 읽어줘, 거기서 이어서 작업하자"

라고 말하면 바로 컨텍스트 복원 가능.
