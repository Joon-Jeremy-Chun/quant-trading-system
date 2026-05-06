# Delta Tranche 매수/매도 로직
*Last updated: 2026-05-05*

이 문서는 `jobs/delta_tranche_job.py`의 매수/매도 의사결정 구조를 설명합니다.
다음 세션의 Claude는 주문 로직 관련 작업 전에 이 문서를 먼저 읽으세요.

---

## 핵심 철학

> "전량 청산 후 재진입 없이, 오늘 신호와 130일 전 신호의 차이만큼만 사고 판다."

매일 1/130씩 포지션을 교체하는 구조. 130일 후 전체 포지션이 한 바퀴 순환.
급격한 청산 없이 포지션이 신호를 따라 자연스럽게 진화.

---

## 1. 정상 운영 (매일 13:00 PT)

```
delta_weight = today_weight - weight_130_trading_days_ago

trade_dollars = (delta_weight / 130) * TOTAL_CAPITAL

delta > 0  →  BUY  $trade_dollars 만큼
delta < 0  →  SELL $|trade_dollars| 만큼
delta = 0  →  HOLD (아무것도 안 함)
```

**예시 (TOTAL_CAPITAL = $10,000):**

| 날짜 | 오늘 비중 | 130일전 비중 | delta | 거래금액 |
|------|-----------|-------------|-------|---------|
| 05-06 | 0.45 | 0.30 | +0.15 | +$11.54 BUY |
| 05-07 | 0.45 | 0.50 | -0.05 | -$3.85 SELL |
| 05-08 | 0.45 | 0.45 | 0.00 | HOLD |

---

## 2. 포트폴리오 정규화

각 자산 신호는 0~1 범위의 독립 값. 합산 후 정규화:

```
raw = {GLD: 1.0, BRK-B: 1.0, QQQ: 0.01, RKLB: 0.23}
total = 2.24  (> 1.0)

normalized:
  GLD   = 1.00 / 2.24 = 0.446  (44.6%)
  BRK-B = 1.00 / 2.24 = 0.446  (44.6%)
  QQQ   = 0.01 / 2.24 = 0.004  ( 0.4%)
  RKLB  = 0.23 / 2.24 = 0.103  (10.3%)
  현금  = 0%

total < 1.0이면 → 정규화 없음, 나머지는 현금 보유
```

이 정규화된 비중이 `tranche_log.csv`에 저장되고, delta 계산의 기준이 됩니다.

---

## 3. tranche_log.csv — 핵심 기록부

위치: `outputs/live/tranche_log.csv`

| Date | w_GLD | w_BRK-B | w_QQQ | w_RKLB |
|------|-------|---------|-------|--------|
| 2025-09-02 | 0.612 | 0.208 | 0.000 | 0.180 |
| 2025-09-03 | 0.612 | 0.208 | 0.000 | 0.180 |
| ... | ... | ... | ... | ... |
| 2026-05-05 | 0.757 | 0.000 | 0.013 | 0.230 |

- 매일 Pi가 1행 추가 (delta_tranche_job.py 실행 시)
- 초기 123행: 2025-09-02 ~ 2026-04-24 시뮬레이션으로 생성
- 130행 미만이면 130일전 비중 = 0 (새 트랜치처럼 취급)
- **git에 포함** (Pi가 push, Windows가 pull로 동기화)

---

## 4. 자산 추가 시 (Bootstrap Buy)

```
예: ITA를 active_universe.json에 추가

1. Windows에서 simulate_tranche_bootstrap.py 실행
   → bootstrap_position.json에 ITA 매수 수량 기록

2. Pi에서 bootstrap_buy_job.py 실행 (1회)
   → 6개월치 누적 포지션을 오늘 한 번에 매수
   → done_flag 파일 생성 (재실행 방지)

3. delta_tranche_job.py가 다음 날부터 정상 delta 계산
   (tranche_log에 ITA 컬럼이 없으므로 130d_ago = 0 → 매일 소량씩 추가 매수)
```

**부트스트랩 포지션 = 시뮬레이션 기반 평단가:**
```
bootstrap_fraction = sum(daily_w / 130) for last 130 trading days
bootstrap_dollars  = fraction * TOTAL_CAPITAL
```

---

## 5. 자산 제거 시 (Full Exit)

```
예: GLD를 active_universe.json에서 제거

delta_tranche_job.py 실행 시:
  today_weight(GLD) = 0  (유니버스에 없으므로)
  accumulated = sum(tranche_log['w_GLD'].tail(130) / 130)
  exit_dollars = accumulated * TOTAL_CAPITAL
  → 즉시 전량 SELL
```

130일 전 기록이 점차 만료되므로 자연스럽게 포지션 소멸.
단, **즉시 전량 청산**이므로 하루에 큰 거래 발생 가능.

---

## 6. 주문 실행 방식

```python
# 매수
limit_price = current_price * 1.005   # 0.5% 슬리피지 허용
order = LimitOrderRequest(
    symbol=symbol,
    qty=dollars / current_price,
    side=BUY,
    time_in_force=DAY,
    limit_price=limit_price,
    extended_hours=True,
)

# 매도
limit_price = current_price * 0.995   # 0.5% 아래에 지정
```

- Paper account (ALPACA_DRY_RUN=false 이후 실제 페이퍼 주문)
- `extended_hours=True` — 장외 시간 대응
- `MIN_ORDER_USD` 미만 거래는 skip (기본 $1.00)

---

## 7. 부트스트랩 시점 포지션 요약 (2026-05-05 기준)

시뮬레이션: 2025-09-02 ~ 2026-04-24 (123 거래일)

| Symbol | 비중 | 매수금액 | 평단가 | 오늘가격 | 손익 |
|--------|------|---------|--------|---------|------|
| GLD | 33.1% | $3,314 | $397.32 | $418.27 | +5.3% |
| BRK-B | 23.6% | $2,364 | $489.53 | $465.52 | -4.9% |
| QQQ | 15.4% | $1,542 | $605.41 | $681.61 | +12.6% |
| RKLB | 27.8% | $2,780 | $64.49 | $78.76 | +22.1% |
| **합계** | **100%** | **$10,000** | — | — | **+8.7%** |

---

## 8. 미래 확장 계획

- **130일 이후**: 실제 데이터가 130일 쌓이면 시뮬 기록과 자연스럽게 교체됨
- **오라클 비교 백테스트**: 실제 운영 결과 vs 오라클(완벽한 사후 비중) 비교
- **자산 유니버스 확장**: ITA, VRT 편입 검토 (앵커 분석 완료, active_universe에 미편입)
- **Pi 경량화**: model.json (ML 계수만)으로 optimization_outputs 불필요하게 만들기

---

## 관련 파일

| 파일 | 용도 |
|------|------|
| `jobs/delta_tranche_job.py` | 매일 delta 주문 실행 |
| `jobs/bootstrap_buy_job.py` | 신규 자산 진입 시 1회 실행 |
| `scripts/simulate_tranche_bootstrap.py` | bootstrap_position.json 생성 |
| `outputs/live/tranche_log.csv` | 130일 rolling 비중 기록 |
| `models/live_assets/active_universe.json` | 현재 거래 자산 목록 |
| `outputs/bootstrap/bootstrap_position.json` | 부트스트랩 매수 수량 |
