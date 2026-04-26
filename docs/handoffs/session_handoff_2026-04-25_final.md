# 세션 핸드오프 — 2026-04-25 (최종)

다음 세션 시작 시 이 파일을 먼저 읽고 이어서 작업할 것.

---

## 오늘 완료한 작업 (전체)

### 1. GLD 라이브 시그널 재생성
- 새 앵커 `2026-03-31` 기준으로 재생성
- 결과: **BUY strong, weight=1.00, Ridge 모델, MA Crossover 주도**
- 예측 수익률 (130일): +55.6%

### 2. 슬라이드 업데이트
- **Slide 25 추가**: Stage C 라이브 시그널 예시 (2026-04-24 기준)
- **Remark 블록 추가**: "Stage C is already a 2-layer nonlinear system" (What's Next 슬라이드)
- Outline 업데이트: Next Steps → slides 26~27

### 3. Pi 설정 변경
- `TRANCHE_TOTAL_CAPITAL`: 100,000 → **10,000** 변경 완료

### 4. --anchor-output-root 버그 수정
- BRK-B 앵커가 GLD 폴더 덮어쓰는 문제 수정
- `run_objective1_anchor_date_multi_horizon_evaluation.py`에 `--anchor-output-root` 인자 추가
- `run_asset.py` TODO 해결 — config의 `anchor_output_root` 자동 전달
- GLD 7개 앵커 복구 완료 (gld_us_d.csv로 재학습)
- BRK-B 7개 앵커 올바른 경로에 저장 완료

### 5. 병렬 그리드 서치 구현
- 4개 전략 스크립트에 `--n-jobs` 플래그 추가 (joblib 병렬화)
- 속도: 직렬 29.7s → 병렬 6.8s (**4.4x 향상**, i7-12800H 20스레드)
- `run_asset.py`도 `--n-jobs` 지원: `python scripts/run_asset.py --asset gld --step optimize --n-jobs -1`

### 6. 멀티에셋 확장
- SPY, QQQ, TLT config + 데이터 수집 완료
  - SPY: 5,361행, $713.94
  - QQQ: 5,361행, $663.88
  - TLT: 5,361행, $86.71
- 현재 자산 유니버스: GLD, SPY, QQQ, TLT, BRK-B, RKLB

### 7. Top-N Feature Expansion 실험
- top-10~80 (40~320 컬럼) 백테스트 완료 (h130, 1M update, 2020~2024)
- **효율 곡선 peak: top-50** (+13.1%)
- **리스크 조정 Sharpe peak: top-70** (1.15), 단 차이 미미
- **권장: top-40~50** — 수익·리스크·노출도 균형

### 8. 아키텍처 인사이트 문서화
- `docs/notes/two_layer_architecture_insight_2026-04-25.md`
- `docs/notes/top_n_feature_expansion_analysis_2026-04-25.md`

---

## 주요 발견 (오늘)

### Top-N 솔루션 벡터 분포
새로 추가된 랭크 구간이 항상 가장 큰 계수 기여:
- top-20: rank 11~20이 56.9% 기여
- top-30: rank 21~30이 49.8% 기여
→ 기존 피처보다 새 피처가 더 orthogonal해서 Lasso/Ridge가 선호

### 효율 곡선 형태
```
효율
+13% |                    ● (top-50 PEAK)
+12% |         ●  ●  ●  ●  ●  ●
+9%  | ●(top-10)
     +--+--+--+--+--+--+--+--→ N
       10 20 30 40 50 60 70 80
```
- top-10→20: 큰 점프 (+8.8% → +11.9%)
- top-20→50: 완만한 상승
- top-50 이후: plateau (Lasso가 노이즈 필터링)
- 예상한 역U자 확인

### 2021 방어력
- top-10만 +0% 방어, top-20 이상은 전부 -6~7%
- 단, top-20~80 간 차이 없음 → 피처 늘려도 방어력 악화 없음

---

## 현재 파이프라인 구조

```
[이 PC — 수동]
  앵커 최적화 (--n-jobs -1로 병렬)
  백테스트 분석

[Raspberry Pi — 매일 13:00 PDT 자동]
  GLD 데이터 업데이트
  Objective2 신호 계산
  트랜치 주문 (ALPACA_DRY_RUN=true)
  Gmail HTML 리포트
  git push

[멀티에셋 — 수동]
  python scripts/run_asset.py --asset [gld|spy|qqq|tlt|brkb|rklb] --step [fetch|optimize|signal|backtest]
```

---

## 다음 세션 할 작업 (우선순위)

### 즉시
1. **ALPACA_DRY_RUN=false 활성화** — 며칠 이메일 확인 후 Pi에서 변경
   ```bash
   ssh joonc@joon-pi
   sed -i 's/ALPACA_DRY_RUN=true/ALPACA_DRY_RUN=false/' \
     /home/joonc/my_github/quant-trading-system/deploy/raspberry_pi/quant-trading.env
   ```

### 연구 — Top-N 후속
2. **Exposure cap 실험** — top-40~50에서 max 노출도 60% 제한 시 효율 변화
3. **h45 동일 실험** — top-10~80 h45 버전, peak N 위치 비교
4. **오차(MSE) 곡선** — 효율이 아닌 예측 오차 기준 U자/double descent 확인

### BRK-B 파이프라인
5. **BRK-B 백테스트** — 앵커 7개 완료됨, 바로 실행 가능
   ```bash
   python scripts/run_asset.py --asset brkb --step backtest
   ```
6. **BRK-B 라이브 시그널**
   ```bash
   python scripts/run_asset.py --asset brkb --step signal
   ```
7. **노출도 상관관계 분석** — corr(w_GLD, w_BRKB) 계산

### SPY/QQQ/TLT
8. **SPY 앵커 최적화** — 1개 앵커 테스트 완료됨 (내가 직접 돌렸음)
   전체 앵커 실행:
   ```bash
   python scripts/run_asset.py --asset spy --step optimize \
     --anchor-dates 2020-12-31,2021-12-31,2022-12-30,2023-12-29,2024-12-31 \
     --n-jobs -1
   ```
9. QQQ, TLT도 동일하게

### 중기
10. **SINDy 이차항 실험** — Θ(A) = [sᵢ, sᵢ²], 80컬럼
11. **멀티에셋 노출도 상호보완성** — 자산간 weight 상관 분석

---

## 자산별 앵커 경로

| 자산 | 앵커 경로 | 상태 |
|---|---|---|
| GLD | `outputs/objective1_anchor_date_multi_horizon_evaluation/` | 완료 (79개) |
| BRK-B | `outputs/brkb/anchor_snapshots/` | 완료 (7개, 2023~2025) |
| SPY | `outputs/spy/anchor_snapshots/` | 1개 테스트 완료 |
| QQQ | `outputs/qqq/anchor_snapshots/` | 미실행 |
| TLT | `outputs/tlt/anchor_snapshots/` | 미실행 |
| RKLB | `outputs/rklb/anchor_snapshots/` | 미실행 |

---

## 주요 설정값

| 항목 | 값 |
|---|---|
| Pi SSH | `ssh joonc@joon-pi` |
| 타이머 | 월~금 13:00:05 PDT |
| TRANCHE_HORIZON_DAYS | 130 |
| TRANCHE_TOTAL_CAPITAL | 10,000 (변경 완료) |
| ALPACA_DRY_RUN | true (→ false 전환 예정) |
| 권장 top-N | 40~50 |
| 병렬 실행 | --n-jobs -1 |

---

## 커밋 이력 (오늘)

| 커밋 | 내용 |
|---|---|
| APR25-01 | GLD 시그널 재생성 + 라이브 시그널 슬라이드 |
| APR25-02 | 병렬 그리드 서치 + SPY/QQQ/TLT 데이터 |
| APR25-03 | Top-N 분석 노트 |
