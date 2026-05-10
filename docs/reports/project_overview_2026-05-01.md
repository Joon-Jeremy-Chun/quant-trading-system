# Quant Trading System — Project Overview
*Last updated: 2026-05-01*

이 문서는 프로젝트 전체 구조, 목표, 결과, 그리고 향후 계획을 한 곳에 정리한 것입니다.
다음 세션의 Claude나 새로운 기여자가 읽으면 전체 흐름을 파악할 수 있도록 작성했습니다.

---

## 1. 핵심 철학 — 3-Layer 프레임워크

```
Layer 0 (Human):  매크로 인사이트 → 어떤 자산에 투자할지 결정
                  (인간 판단: 섹터 선택, 연 1회 또는 시장 환경 변화 시)
                       ↓
Layer 1 (Algo):   전략 알고리즘 → 가격 데이터를 비선형 피처로 변환
                  (4개 전략 패밀리 × top-N 파라미터 = 설계 행렬 A)
                       ↓
Layer 2 (Model):  Ridge/Lasso/ElasticNet → 언제, 얼마나 투자할지 결정
                  (매달 앵커 업데이트, CV-MSE 기준 모델 선택)
                       ↓
Layer 3 (SINDy):  비선형 항 확장 — 미래 연구 과제
                  Θ(A) = [A, A², AᵢAⱼ, ...] → sparse 비선형 식별
```

**핵심 철학:** 인간이 *무엇에* 투자할지 결정하고, 기계가 *언제, 얼마나* 결정하는 분업.
프레임워크는 asset-agnostic이므로 config 변경만으로 어떤 자산에도 적용 가능.

---

## 2. 시스템 아키텍처 — Windows ↔ Raspberry Pi

| 역할 | 장치 | 작업 |
|------|------|------|
| **연구** | Windows (20코어) | 앵커 계산, 백테스트, 모델 분석, 코드 개발 |
| **실행** | Raspberry Pi (`joonc@joon-pi`) | 매일 13:00 PT 자율 실행 — 가격 수집 → 신호 계산 → Alpaca 주문 → 이메일 |

Pi는 Windows 없이 독립 실행. 코드/manifest/신호 JSON만 git으로 공유.
대용량 앵커 데이터(~43MB/앵커)는 rsync로 전송.

---

## 3. 현재 자산 유니버스

### 기존 4자산 (라이브 파이프라인)

| 자산 | 데이터 | 앵커 루트 | Pi 실행 | 비고 |
|------|--------|-----------|---------|------|
| **GLD** | `data/gld_us_d.csv` | `outputs/objective1_anchor_date_multi_horizon_evaluation/` | ✅ | 금 ETF, 핵심 자산 |
| **BRK-B** | `data/brkb_us_d.csv` | `outputs/brkb/anchor_snapshots/` | ✅ | 가치주 대표 |
| **QQQ** | `data/qqq_us_d.csv` | `outputs/qqq/anchor_snapshots/` | ❌ | 신호 Windows→push |
| **RKLB** | `data/rklb_us_d.csv` | `outputs/rklb/anchor_snapshots/` | ❌ | 성장주, 고변동성 |

### Layer 0 신규 추가 자산 (2026-05-01 결정)

Layer 0 선택 기준: **섹터 독립성** (기존 4자산과 낮은 상관관계) + **10년+ 데이터** + **거시 테마 직접 수혜**

| 자산 | 데이터 | 앵커 루트 | 테마 | 데이터 기간 |
|------|--------|-----------|------|------------|
| **ITA** | `data/ita_us_d.csv` | `outputs/ita/anchor_snapshots/` | 방산 ETF (트럼프 방위비 + 유럽 재무장 + 분쟁) | 2006~ (20년) |
| **VRT** | `data/vrt_us_d.csv` | `outputs/vrt/anchor_snapshots/` | AI 데이터센터 전력/냉각 인프라 (Vertiv) | 2018~ (8년) |

**ITA 선택 이유:**
- iShares U.S. Aerospace & Defense ETF
- 트럼프 방위비 확대, 유럽 재무장, 전 세계 분쟁 증가 → 정부 계약 기반으로 경기 사이클과 독립적
- GLD/QQQ와 낮은 상관관계 → 포트폴리오 분산 효과

**VRT 선택 이유:**
- Vertiv Holdings — AI 데이터센터 전력관리 및 냉각 설비 1위
- IEA 2026년 보고서: 데이터센터 전력 소비 2025년 17% 급등, 2030년 3배 전망
- AI 전력 수요 밸류체인에서 "이미 지어진 인프라 유지보수" 수익 모델 → 안정적

**검토 후 제외:**
- CEG, GEV: 2022/2024 상장으로 데이터 부족
- OILU (3x 레버리지 ETN): 130일 보유 전략과 구조적 불일치 (daily reset decay)
- TLT: 전략 불안정 (별도 연구 보류)
- GRID, XLE: ITA+VRT로 대체

---

## 4. 전략 패밀리 — Layer 1

4개 전략 패밀리가 가격 데이터를 비선형 피처로 변환:

| 전략 | 핵심 아이디어 |
|------|--------------|
| **Adaptive Band** | 가격을 rolling band 기준으로 정규화한 포지션 스코어 |
| **MA Crossover** | 단기/장기 이동평균 차이 (추세 강도) |
| **Adaptive Volatility Band** | 고가-저가-종가 기반 변동성 레짐 |
| **Fear-Greed Candle-Volume** | 캔들 크기 + 거래량 스파이크 이벤트 신호 |

각 앵커 날짜에서 그리드 서치 → top-N 파라미터 선택 → 설계 행렬 A ∈ ℝ^(T×4N)

**top-N 파라미터 결정:**
- 전 자산 top-N=20 통일 (2026-04 이후)
- 근거: top-20~40 범위가 대부분 자산에서 성능 최적 (실험적 확인)
- 기존 GLD 앵커 2019~2024는 top-N=10으로 계산됨 (이 시기 학술 보고서 기준)

---

## 5. 앵커 계산 현황 (2026-05-01 기준)

앵커 = 특정 날짜 기준 전략 최적화 결과. 각 앵커에 `optimization_outputs/`(전체 랭킹), `strategy_top_candidates.csv`(top-N 요약) 저장.

**중요:** `all_ranked_results.csv`에 전체 파라미터 조합이 저장되므로, 나중에 top-K 변경 시 재계산 불필요.

| 자산 | 기존 앵커 수 | 신규 계산 중 | 파라미터 | 로그 |
|------|------------|------------|---------|------|
| GLD | 66개 (2019-12~2024-12, top-10) | 14개 추가 (2025-01~2026-02, top-20) | `--n-jobs 18` | `anchor_run_gld_2025.log` |
| BRK-B | 20개 (일부) | 57개 추가 (2021-05~2026-02, top-20) | `--n-jobs 18` | `anchor_run_brkb_2021_2026.log` |
| QQQ | 79개 완료 | — | — | — |
| RKLB | 53개 완료 | — | — | — |
| **ITA** | 0 | **111개** (2016-12~2026-02, top-20) | `--n-jobs 18` | `anchor_run_ita.log` |
| **VRT** | 0 | **62개** (2021-01~2026-02, top-20) | `--n-jobs 18` | `anchor_run_vrt.log` |

실행 순서: GLD → BRK-B → ITA → VRT (자동 체인, BRK-B 완료 감지 후 ITA 자동 시작)

---

## 6. 학술 보고서 결과 — GLD Stage A/B/C (2020~2025)

**파일:** `docs/reports/final_written_report_2026-05-01.tex` (MATH 280 수업 제출)

**평가 설계:**
- 매달 앵커, 직전 1년 데이터로 훈련, 130일 forward 수익 예측
- look-ahead bias 없음 (앵커 날짜 이전 데이터만 사용)

**3단계 비교:**
- **Stage A:** 그리드서치 rank-1 단일 전략 (best 자동 선택)
- **Stage B:** Constrained ensemble — 선택 기간 수익 최대화 (x≥0, Σx=1)
- **Stage C:** Regularized linear model (Ridge/Lasso/ElasticNet) → 130일 forward 수익 예측

**연도별 결과 (수익률 / 평균 노출도):**

| 연도 | Buy-and-Hold | Stage A | Stage B | Stage C |
|------|------------|---------|---------|---------|
| 2020 | +23.9% | +4.4% / 27% | +6.4% / 32% | **+10.9%** / 57% |
| 2021 | -6.2% | +0.3% / 25% | +0.3% / 25% | **+0.8%** / 29% |
| 2022 | +0.8% | -0.9% / 46% | -2.3% / 42% | **-0.2%** / 31% |
| 2023 | +11.8% | +1.6% / 25% | +2.0% / 23% | **+4.0%** / 32% |
| 2024 | +27.0% | +5.9% / 21% | +8.0% / 29% | **+16.4%** / 65% |
| 2025 | +61.5% | +21.4% / 40% | +21.4% / 40% | **+34.7%** / 65% |

**핵심 발견:**
1. Stage C가 매년 A/B보다 강함 — 과거 수익 최적화 대신 미래 수익 예측이 핵심
2. 130일 타깃 > 45일 타깃 — feature-target alignment: 1년 선택 윈도우 ↔ 6개월 예측
3. 2025년 Stage A = Stage B (+21.4%): GLD 강한 단방향 상승장(+61.5%)에서 adaptive_band 100% 몰빵이 최적 → B의 분산 효과 소멸 → A=B
4. Stage C는 높은 노출도(65%)로 강세장 참여, 약세장에서는 노출 축소

**2025 특이사항:** GLD +61.5% (금 $245→$396) — 트럼프 관세전쟁 + 달러 약세로 역대급 금 강세

---

## 7. 포트폴리오 오라클 백테스트 — 다음 목표

**목표:** 6자산 포트폴리오(GLD, BRK-B, QQQ, RKLB, ITA, VRT) 역사적 시뮬레이션

**방식:**
- 각 월말 앵커 → 자산별 Stage C 신호 계산
- 4~6자산 신호 정규화 (합이 100% 초과 시 비례 축소, 미만 시 나머지 현금)
- 1개월 보유 → 실제 포트폴리오 수익 계산
- 누적 equity curve vs 개별 자산 buy-and-hold 비교

**현재 상태 (2026-05-01):**
- GLD: Windows에 2019~2026 앵커 준비 중 ✓
- BRK-B: 계산 중 (57개)
- QQQ: 79개 앵커 완료 ✓
- RKLB: 53개 앵커 완료 ✓
- ITA: 계산 중 (111개)
- VRT: 계산 중 (62개)

**다음 작업:** 앵커 계산 완료 후 `run_portfolio_forward_backtest.py` 작성

---

## 8. 라이브 파이프라인 — Raspberry Pi

**매일 13:00 PT 자동 실행:**
1. `git pull` — manifest/신호 JSON 확인
2. yfinance로 당일 가격 수집
3. 활성 앵커 모델로 신호 계산 (`build_signal_on_pi: true` 자산만)
4. 4자산 비중 정규화 (합>100% → 비례 축소, 합<100% → 나머지 현금)
5. Alpaca limit order (price × 1.005, DAY, extended_hours=True)
6. 이메일 리포트 전송

**현재 설정:**
- `TRANCHE_TOTAL_CAPITAL = $10,000` (페이퍼 트레이딩)
- `ALPACA_DRY_RUN = false` (2026-04-28부터 실제 페이퍼 주문)
- 수신자: joonchun1000@gmail.com, jpugh7@ucmerced.edu
- 테스트 시 반드시 `python jobs/send_live_daily_report.py --test` 사용

**모델 매니페스트:** `models/live/latest_model_manifest.json`
- `top_n_per_family: 20`
- `target_horizon_days: 130`
- `selection_criterion: selection_cv_mse`
- `update_interval_months: 1`

---

## 9. Layer 3 — SINDy (미래 연구)

현재 Layer 2는 선형: ŷ = Aβ

SINDy 확장:
```
Θ(A) = [A, A², AᵢAⱼ, ...]  →  sparse 비선형 식별
```

포지션 스코어 min_weight 임계값은 원래 SINDy 연구용 아이디어였으나, 멀티에셋 전환으로 현재 폐기 (0.0). Layer 3 연구 시 재검토.

---

## 10. Git 정책 요약

**커밋 가능:**
- `outputs/live/latest_<symbol>_signal.json`
- `models/live/latest_model_manifest.json`
- `.py`, `.sh`, `.md`, `.json` config

**절대 커밋 금지:**
- `figures/` (PNG)
- `outputs/11_*`, `outputs/21_*`, `outputs/31_*`, `outputs/41_*` (최적화 CSV)
- `outputs/rklb/`, `outputs/qqq/`, `outputs/brkb/`, `outputs/ita/`, `outputs/vrt/` (앵커 스냅샷)
- `models/research/` (pkl, joblib)
- **`git add .` 또는 `git add -A` 절대 사용 금지**

앵커 데이터 전송: rsync 사용 (Pi ↔ Windows)

---

## 11. 브랜치 전략

- Windows 작업: `work/pi-manifest-top20` → 조만간 `main` 머지 예정
- Pi: `main` 브랜치만 사용
- 작업 전 항상 `git branch -a` 확인 필수 (이전 잘못된 브랜치 작업 사고 방지)
