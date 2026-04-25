# 세션 핸드오프 — 2026-04-21

다음 세션 시작 시 이 파일을 먼저 읽고 이어서 작업할 것.

---

## 오늘 완료한 작업

### 1. Handoff 폴더 정리
- `docs/handoffs/` 폴더 신설, README.md 작성
- `docs/notes/session_handoff_2026-04-20.md` → `docs/handoffs/session_handoff_2026-04-20_notes.md` 복사 후 원본 삭제
- `docs/reports/session_handoff_2026-04-20.md` → `docs/handoffs/session_handoff_2026-04-20_final.md` 복사 후 원본 삭제
- 앞으로 handoff 파일은 `docs/handoffs/`에서만 관리

### 2. 슬라이드 전면 개편 (Apr 20 → Apr 21 버전)
`docs/slides/objective2_research_presentation_2026-04-21.tex` 신규 생성.

#### 구조 변경 사항
| 변경 내용 | 세부 |
|---|---|
| 슬라이드 2: Outline 추가 | 7개 섹션 + 슬라이드 번호 범위 |
| 슬라이드 11 Capital Efficiency 제거 | Stage C 소개 전에 C 데이터 사용하는 게 논리적 오류였음 |
| Exposure/Efficiency 슬라이드 신설 | Stage C 설명 직후 배치 (슬라이드 20) |
| Stage B 테이블 수정 | p{2.8cm} → lrrrrr, Efficiency 열 제거로 줄바꿈 해소 |
| h45 데이터 추가 | Exposure 슬라이드에 h130 vs h45 효율성 비교표 |
| Appendix A–E 추가 | 그리드 서치 파라미터, CV 설계, 2024 제외, h45 비교, 거래비용 |
| Conclusion 업데이트 | Mini Project Team 8명 추가, Live/Next 라인 제거 |
| `\usepackage{multirow}` 추가 | Appendix A 컴파일 오류 수정 |

### 3. 슬라이드 순서 재조정 (이번 세션)
- 구 슬라이드 21 (Stage C 모델 내부 예시) 을 슬라이드 18 (Prediction→Weight) 바로 뒤로 이동
- 이유: 메커니즘 설명 직후 예시 확인 → Exposure 정의 → 3단계 비교(클라이맥스) 순서가 자연스럼
- Outline 슬라이드 번호 업데이트: Stage C 16–20, Results 21–24

### 4. 루브릭 기반 접근성 개선 (15분 발표 최적화)
발표 루브릭 5개 항목 검토 후 수정:
- **제목 subtitle**: GLD → "GLD (SPDR Gold Shares ETF)" 추가
- **슬라이드 3**: GLD 정의 bullet 추가 (gold commodity ETF, NYSE, 2019–2024)
- **슬라이드 18**: "tranches (small independent positions)" 괄호 정의 추가
- **Outline**: "Conclusion & Next Steps" → "Next Steps & Conclusion" (실제 순서 맞춤)
- **슬라이드 27 신규**: Q&A 화면 — Appendix 목록 표시, 발표 끝 지점 명확화

### 5. 결정 사항
- **슬라이드 11 Exposure 문구**: 구두로 설명할 예정 (텍스트 수정 없음)
  - Stage A/B exposure = 매수/매도 일 수 평균 (binary in/out)
  - Stage C exposure = 매일 다른 비중으로 신호에 맞춰 투자하는 연속 가중치
- **표 vs 그래프**: 표 유지 결정
  - 비교 구조가 핵심인 덱에서 숫자 병렬 비교는 표가 우위
  - 잠재적 추가: Stage C의 daily weight w_t 시계열 그래프 (2024년) — 연속 노출의 의미를 시각화
- **리포트**: `docs/reports/research_report_2026-04-21.tex` 생성 (9페이지, LaTeX)
  - 7–10장 요구사항에 맞춰 표 전부 포함, 그래프 제외
  - amssymb 패키지 추가로 컴파일 에러 수정 완료

---

## 최종 슬라이드 구조 (31장)

| 슬라이드 | 내용 | 섹션 |
|---|---|---|
| 1 | Title | — |
| 2 | Outline | — |
| 3 | Starting Point | Motivation |
| 4 | Function Space Analogy | Motivation |
| 5 | Four Strategy Families | Strategies |
| 6 | Strategy 1: Adaptive Band | Strategies |
| 7 | Strategy 2: MA Crossover | Strategies |
| 8 | Strategy 3: Adaptive Volatility Band | Strategies |
| 9 | Strategy 4: Fear-Greed | Strategies |
| 10 | Turning Parameters into Signals | Strategies |
| 11 | Stage A: Results | Stage A |
| 12 | Stage B: Matrix A | Stage B |
| 13 | Stage B: Optimizer Example | Stage B |
| 14 | Stage B: Ensemble Results | Stage B |
| 15 | What Stage B Cannot Do | Stage B |
| 16 | Stage C: Expanding the Strategy Space | Stage C |
| 17 | Stage C: Forward Validation Design | Stage C |
| 18 | Stage C: Prediction → Weight | Stage C |
| **19** | **Stage C: Model Example (OLS 계수)** | Stage C |
| **20** | **What Exposure Means in Each Stage** | Stage C |
| **21** | **Three-Stage Comparison: A vs B vs C** | Results |
| 22 | Update Frequency — Hold 130 Days | Results |
| 23 | Update Frequency — Hold 45 Days | Results |
| 24 | Hold Horizon: 45 vs 130 Days | Results |
| 25 | What's Next | Next Steps |
| 26 | Conclusion (Mini Project Team 포함) | Conclusion |
| 27 | Appendix A: Grid Search Params | Appendix |
| 28 | Appendix B: CV Hyperparameter Search | Appendix |
| 29 | Appendix C: Performance Excl. 2024 | Appendix |
| 30 | Appendix D: Three-Stage h45 | Appendix |
| 31 | Appendix E: Transaction Costs | Appendix |

---

## 최종 확정 숫자 (변경 없음 — Apr 20과 동일)

### h130 / 1M

| Year | B&H | A: Single | B: Ensemble | C: ML-Guided |
|---|---:|---|---|---|
| 2020 | +23.9% | +4.4%/27% | +6.4%/32% | **+10.9%/57%** |
| 2021 | -6.2%  | +0.3%/25% | +0.3%/25% | **+0.8%/29%** |
| 2022 | +0.8%  | -0.9%/46% | -2.3%/42% | **-0.2%/31%** |
| 2023 | +11.8% | +1.6%/25% | +2.0%/23% | **+4.0%/32%** |
| 2024 | +27.0% | +5.9%/21% | +8.0%/29% | **+16.4%/65%** |

### h45 / 1M

| Year | B&H | A: Single | B: Ensemble | C: ML-Guided |
|---|---:|---|---|---|
| 2020 | +23.9% | +4.2%/28% | +6.5%/34% | **+17.4%/72%** |
| 2021 | -6.2%  | +0.0%/30% | +0.0%/30% | **+1.5%/35%** |
| 2022 | +0.8%  | -2.3%/57% | -4.2%/50% | **-0.6%/37%** |
| 2023 | +11.8% | +2.7%/32% | +5.5%/30% | **+2.5%/44%** |
| 2024 | +27.0% | +8.7%/24% | +8.6%/33% | **+25.2%/78%** |

### Capital Efficiency (2024, h130 vs h45)

| | Return | Avg. Exposure | Efficiency |
|---|---|---|---|
| Buy-and-Hold | +27.0% | 100% | +27% |
| Stage C, h130 | +16.4% | 65% | +25% |
| Stage C, h45  | +25.2% | 78% | **+32%** |

---

## Mini Project Team

| 역할 | 이름 |
|---|---|
| 전체 멤버 (8명) | Alejandro Menacho, Ashmeet Singh, Claire Wang, Thomas Tran, Matthew Aguirre, Sophia (Suyiao) Wei, Jack, Stephen |
| Stage A–B 공동 진행 | Jack, Stephen, Sophia Wei, Claire Wang |
| Live Pipeline (Raspberry Pi) | Jack, Stephen |

---

## 주요 파일 위치

| 역할 | 경로 |
|---|---|
| **슬라이드 (최신)** | `docs/slides/objective2_research_presentation_2026-04-21.tex` |
| 슬라이드 (전버전) | `docs/slides/objective2_research_presentation_2026-04-20.tex` |
| Handoff 폴더 | `docs/handoffs/` |
| 세 단계 비교 | `docs/reports/three_stage_comparison_2026-04-20.md` |
| 업데이트 주기 | `docs/reports/objective2_update_frequency_comparison_h45_h130_2026-04-20.md` |
| Stage C 스크립트 | `strategies/automation/run_objective2_monthly_update_tranche_backtest.py` |
| Stage C 출력 | `outputs/objective2_monthly_update_tranche_backtest/` |
| Raspberry Pi | `ssh joonc@joon-pi` |

---

## 다음 세션에서 할 수 있는 작업

- **발표 연습** — 슬라이드 흐름 구두 리허설, 예상 질문 준비
- **선택적 그래프 추가** — Stage C daily weight w_t 시계열 (2024년) 시각화
- **라이브 파이프라인** — Raspberry Pi 배포 상태 확인 (Jack/Stephen)
- **다자산 확장** — BRK.B, oil, copper에 동일 프레임워크 적용 (GLD idle capital 활용)
- **SINDy 실험** — 비선형 기저함수 Θ(A) = [s_i, s_i², s_i·s_j] 구현
