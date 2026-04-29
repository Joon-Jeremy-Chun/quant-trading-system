# TLT 매크로 피처 설계 노트

Date: 2026-04-29

## 배경

TLT (iShares 20+ Year Treasury Bond ETF)를 단순 가격 패턴 모델로 분석한 결과:
- Sharpe: -0.36, CAGR: -2.1%, 마이너스 3년 (2021, 2022, 2024)
- 2022년 방어(전략 -5.5% vs B&H -29.4%)는 잘 됐지만 전반적으로 알파 없음

**근본 원인**: TLT 방향성 = f(인플레이션, 국가 성장률)인데,
현재 모델은 가격 패턴만 학습 → 핵심 드라이버 누락.
CPI는 월 1회, GDP는 분기 1회 발표 → 일별 가격 데이터와 주파수 불일치 (Mixed-Frequency 문제).

---

## 채택 방향: Option B — 시장 내재 일별 프록시 (Market-Implied Daily Proxies)

CPI/GDP 대신 시장이 이미 반영한 **일별 지표**를 피처로 사용.
이유: 주파수 불일치 없음, FRED에서 무료, 현재 Signal Matrix 구조에 바로 추가 가능.

### 핵심 피처 3종

| 피처 | 의미 | 소스 | 티커 |
|------|------|------|------|
| **TIPS 손익분기 인플레이션** (10Y) | 시장의 인플레이션 기대치 (일별) | FRED | T10YIE |
| **장단기 금리 스프레드** (10Y-2Y) | 경기 사이클, 경기침체 선행 지표 | FRED | T10Y2Y |
| **Fed Funds Futures** | 시장의 금리 경로 기대치 | FRED / CME | FEDL01 |

### 보조 피처 (Option A 요소 결합)

CPI, GDP는 LOCF(마지막 발표값 유지) + 서프라이즈(실제-예상) 피처로 보조 추가.
ElasticNet/Lasso가 자동 선택.

---

## 구현 계획

### 1단계: 데이터 수집
```python
import pandas_datareader as pdr
# FRED에서 일별 데이터 다운로드
tips_breakeven = pdr.get_data_fred('T10YIE', start='2005-01-01')  # TIPS 손익분기
yield_spread   = pdr.get_data_fred('T10Y2Y', start='2005-01-01')  # 장단기 스프레드
fed_funds      = pdr.get_data_fred('FEDL01', start='2005-01-01')  # FF 실효금리
```

### 2단계: Signal Matrix 확장
```
기존: A = [전략1수익, 전략2수익, ..., 전략N수익]  (N×T 행렬)
확장: A = [전략1수익, ..., 전략N수익,
           tips_breakeven_lag1,          # 전일 TIPS 스프레드
           yield_spread_lag1,            # 전일 장단기 스프레드
           tips_breakeven_30d_change,    # 30일 변화율 (추세)
           yield_spread_30d_change,      # 30일 변화율
           cpi_yoy_locf,                 # 최신 CPI YoY (LOCF)
           gdp_qoq_locf]                 # 최신 GDP QoQ (LOCF)
```

### 3단계: 학습 구조
- 현재와 동일: OLS/Ridge/Lasso/ElasticNet으로 회귀
- selection_window_years=1~2로 매크로 사이클 커버
- TLT 전용 앵커 스냅샷 + 매크로 피처 포함 버전 별도 운영

---

## 기대 효과

- **인플레이션 상승기**: TIPS 스프레드 ↑ → 모델이 TLT 매도 신호 학습
- **경기침체 우려기**: 장단기 역전 → TLT 매수 신호
- **금리 인하 사이클**: FF 하락 추세 → TLT 상승 포지션

---

## 참고: 현재 TLT 백테스트 결과

| 연도 | 전략 (top-20) | B&H | 노출도 |
|------|-------------|-----|--------|
| 2020 | +1.8% | +16.8% | 54% |
| 2021 | -8.4% | -4.5% | 40% |
| 2022 | -5.5% | -29.4% | 14% |
| 2023 | +1.7% | +0.8% | 15% |
| 2024 | -3.6% | -7.5% | 11% |
| 2025 | +0.7% | +4.0% | 27% |
| **전체** | **Sharpe -0.36** | | |

→ 매크로 피처 추가 전까지 TLT는 라이브 포트폴리오에서 제외.
