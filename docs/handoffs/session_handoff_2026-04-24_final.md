# 세션 핸드오프 — 2026-04-24 (최종)

다음 세션 시작 시 이 파일을 먼저 읽고 이어서 작업할 것.

---

## 오늘 완료한 작업 (전체)

### 1. SSH 키 설정
- 이 PC → Pi: `~/.ssh/id_ed25519` 생성, `joonc@joon-pi` 비밀번호 없이 접속
- Pi → GitHub: `~/.ssh/github_id_ed25519` 생성, GitHub deploy key 등록

### 2. Pi git 최신화 및 환경 설정
- Pi 경로: `/home/joonc/my_github/quant-trading-system`
- MAR05 → 최신 커밋으로 pull 완료
- `.venv` 생성 + `requirements-live.txt` 설치 (alpaca-py, scikit-learn, matplotlib)
- `deploy/raspberry_pi/quant-trading.env` 생성:
  - Alpaca paper API 키, `ALPACA_DRY_RUN=true`
  - Gmail SMTP (`EMAIL_ALERT_ENABLED=true`)
  - `TRANCHE_HORIZON_DAYS=130`, `TRANCHE_TOTAL_CAPITAL=100000`

### 3. systemd 타이머 (완전 자동화)
- 실행: **매주 월~금 13:00:05 PDT** → 첫 실행 Mon 2026-04-27
- 래퍼: `deploy/raspberry_pi/run_daily_pipeline.sh`
  1. `update_daily_price_data.py` — Alpaca에서 오늘 GLD 가격
  2. `run_objective2_latest_live_signal.py` — Pi가 직접 신호 계산
  3. `gld_tranche_order_job.py` — 트랜치 주문 (dry-run)
  4. `send_live_daily_report.py` — Gmail HTML 리포트
  5. `git commit + push` — data/signal 자동 GitHub push

### 4. 트랜치 주문 시스템 (`jobs/gld_tranche_order_job.py`)
- 매일 `total_capital / horizon_days × target_weight` 만큼 신규 트랜치 매수
- 130일 후 해당 트랜치 자동 청산
- `outputs/live/tranche_book.json` 에 활성 트랜치 장부 관리
- 테스트: BUY 1.7764주 @ $433.03 (dry-run) ✅

### 5. HTML 이메일 리포트 (`jobs/send_live_daily_report.py`)
- HTML 포맷 + GLD 가격 차트 (최근 6개월) + BUY 마커 + weight 하단 차트
- CID 방식 이미지 첨부 (Gmail 호환)
- Gmail 발송 확인 ✅
- 제목 형식: `[GLD] BUY w=1.00 $433.03 - 2026-04-24`

### 6. .gitignore 생성
- API 키, `__pycache__`, `.venv`, LaTeX 중간파일, anchor 학습 outputs/figures 제외

### 7. 앵커 학습 (진행 중 — 이 PC 백그라운드)
- 마지막 앵커: `anchor_2024-12-31`
- **16개월 학습 명령어** (완료까지 수 시간):
```
cd strategies/automation && python run_objective1_anchor_date_multi_horizon_evaluation.py \
  --anchor-dates 2025-01-31,2025-02-28,2025-03-31,2025-04-30,2025-05-30,2025-06-30,\
2025-07-31,2025-08-29,2025-09-30,2025-10-31,2025-11-28,2025-12-31,\
2026-01-30,2026-02-27,2026-03-31
```

### 8. 멀티에셋 파이프라인 프레임워크 구축
- `assets/` 폴더: 자산별 config.yaml
- `scripts/run_asset.py`: generic runner (fetch/optimize/signal/backtest)
- `scripts/init_asset_data.py`: 신규 자산 첫 데이터 다운로드

**데이터 다운로드 완료:**
| 자산 | 데이터 | 기간 | 종가 |
|---|---|---|---|
| GLD | 5,323 rows | 2005 ~ 2026-04-24 | $432.97 |
| BRK-B | 5,361 rows | 2005 ~ 2026-04-24 | $469.32 |
| RKLB | 1,359 rows | 2020-11 ~ 2026-04-24 | $79.68 |

---

## 현재 파이프라인 구조

```
[이 PC — 월 1회 수동]
  git pull → 파라미터 학습 → git push

[Raspberry Pi — 매일 13:00 PDT 자동]
  run_daily_pipeline.sh
    ① GLD 데이터 업데이트
    ② 신호 계산 (Pi 직접)
    ③ 트랜치 주문 (dry-run)
    ④ Gmail 리포트
    ⑤ git push

[멀티에셋 분석 — 수동]
  python scripts/run_asset.py --asset brkb --step [fetch|optimize|signal|backtest]
```

---

## 주요 설정값

| 항목 | 값 |
|---|---|
| Pi SSH | `ssh joonc@joon-pi` |
| Pi 경로 | `/home/joonc/my_github/quant-trading-system` |
| 타이머 | 월~금 13:00:05 PDT |
| TRANCHE_HORIZON_DAYS | 130 |
| TRANCHE_TOTAL_CAPITAL | 100,000 (나중에 10,000으로 변경 예정) |
| ALPACA_DRY_RUN | true |
| EMAIL_ALERT_ENABLED | true |
| Alpaca | Paper trading $100,000, GLD fractionable |
| 마지막 앵커 (GLD) | 2024-12-31 (학습 중) |

---

## 다음 세션 할 작업 (우선순위 순)

### 즉시 (앵커 학습 완료 확인 후)
1. **GLD 앵커 학습 완료 확인**
   ```
   ls outputs/objective1_anchor_date_multi_horizon_evaluation/ | tail -5
   # anchor_2026-03-31 폴더 있으면 완료
   ```

2. **새 앵커로 GLD 라이브 시그널 재생성**
   ```
   python scripts/run_asset.py --asset gld --step signal
   git add outputs/live/latest_gld_signal.json outputs/live/history/gld_signal_log.csv
   git commit -m "Update GLD live signal with 2025-2026 anchors" && git push
   ```

3. **TRANCHE_TOTAL_CAPITAL=10000 으로 변경**
   - Pi `quant-trading.env` 수정

4. **ALPACA_DRY_RUN=false 활성화** (며칠 이메일 확인 후)

### BRK-B 분석 파이프라인
5. **BRK-B 앵커 최적화 시작**
   - 데이터: 2005~2026 (20년)
   - 월별 앵커 날짜 선정 후 실행:
   ```
   python scripts/run_asset.py --asset brkb --step optimize \
     --anchor-dates 2023-12-29,2024-03-28,2024-06-28,2024-09-30,2024-12-31,2025-03-31,2025-12-31
   ```

6. **BRK-B 백테스트 및 성과 분석**
   ```
   python scripts/run_asset.py --asset brkb --step backtest
   ```

7. **RKLB 앵커 최적화** (데이터가 2020년부터라 anchor 날짜 주의)
   - selection_window_years: 1 유지
   - 2022년 이후 앵커부터 시작 권장

### 중기
8. **Stage C live backtest 검증** — 새 앵커로 2025년 GLD 성과 재확인
9. **트랜치 horizon 최적화** — h45 vs h130 live 비교
10. **IBKR API 검토** — 다자산 live 확장 시 Alpaca 대체 고려
11. **SINDy 실험** — 비선형 기저함수 Θ(A) = [s_i, s_i², s_i·s_j]

---

## 멀티에셋 명령어 정리

```bash
# 새 자산 추가 (예: NVDA)
# 1. assets/nvda/config.yaml 생성
# 2. 데이터 fetch
python scripts/run_asset.py --asset nvda --step fetch

# 3. 파라미터 학습 (anchor 날짜는 월말 기준)
python scripts/run_asset.py --asset nvda --step optimize \
  --anchor-dates 2024-12-31,2025-03-31,2025-06-30,2025-09-30,2025-12-31

# 4. 라이브 신호
python scripts/run_asset.py --asset nvda --step signal

# 5. 백테스트
python scripts/run_asset.py --asset nvda --step backtest --tag 2025
```

---

## 주요 파일 위치

| 역할 | 경로 |
|---|---|
| Generic runner | `scripts/run_asset.py` |
| Init data | `scripts/init_asset_data.py` |
| GLD config | `assets/gld/config.yaml` |
| BRK-B config | `assets/brkb/config.yaml` |
| RKLB config | `assets/rklb/config.yaml` |
| 트랜치 주문 | `jobs/gld_tranche_order_job.py` |
| 이메일 리포트 | `jobs/send_live_daily_report.py` |
| Pi 래퍼 | `deploy/raspberry_pi/run_daily_pipeline.sh` |
| 트랜치 장부 | `outputs/live/tranche_book.json` |
| GLD 데이터 | `data/gld_us_d.csv` |
| BRK-B 데이터 | `data/brkb_us_d.csv` |
| RKLB 데이터 | `data/rklb_us_d.csv` |

---

## Mini Project Team

| 역할 | 이름 |
|---|---|
| 전체 (8명) | Alejandro, Ashmeet, Claire, Thomas, Matthew, Sophia, Jack, Stephen |
| Live Pipeline | Jack, Stephen |
