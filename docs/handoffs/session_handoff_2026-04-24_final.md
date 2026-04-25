# 세션 핸드오프 — 2026-04-24

다음 세션 시작 시 이 파일을 먼저 읽고 이어서 작업할 것.

---

## 오늘 완료한 작업

### 1. SSH 키 설정
- 이 PC에서 `~/.ssh/id_ed25519` 생성
- Pi(`joonc@joon-pi`)에 공개키 등록 → 비밀번호 없이 SSH 접속 가능

### 2. Pi git 최신화
- Pi 경로: `/home/joonc/my_github/quant-trading-system`
- MAR05 → APR21 커밋으로 git pull 완료
- remote URL을 HTTPS → SSH(`git@github.com:Joon-Jeremy-Chun/quant-trading-system.git`)로 변경
- GitHub SSH 키 (`~/.ssh/github_id_ed25519`) 생성 + GitHub에 deploy key 등록

### 3. Pi 환경 설정
- `.venv` 생성 + `requirements-live.txt` 설치 (alpaca-py, scikit-learn, matplotlib 등)
- `deploy/raspberry_pi/quant-trading.env` 생성
  - Alpaca paper API 키 (ALPACA_DRY_RUN=true)
  - Gmail SMTP 설정 (EMAIL_ALERT_ENABLED=true)
  - TRANCHE_HORIZON_DAYS=130, TRANCHE_TOTAL_CAPITAL=100000

### 4. systemd 타이머 설정
- `/etc/systemd/system/gld-daily-pipeline.service` 생성
- `/etc/systemd/system/gld-daily-pipeline.timer` 생성
- 실행 시간: **매주 월~금 13:00:05 PDT**
- 타이머 상태: `active (waiting)`, 첫 실행: Mon 2026-04-27 13:00:05 PDT ✅

### 5. 자동 git push 래퍼 스크립트
`deploy/raspberry_pi/run_daily_pipeline.sh` 생성:
1. `gld_daily_pipeline.py --build-signal` 실행
2. `data/gld_us_d.csv` + `latest_gld_signal.json` + `gld_signal_log.csv` 자동 git commit + push
   - 커밋 메시지: `Auto: daily GLD data + signal YYYY-MM-DD`

### 6. .gitignore 생성
- `deploy/raspberry_pi/quant-trading.env` (API 키 보호)
- `__pycache__/`, `.venv/`
- LaTeX 중간파일 (`.aux`, `.log` 등)
- `.claude/settings.local.json` 추적 해제
- anchor 학습 outputs/figures 제외 (대용량, 재현 가능)

### 7. 데이터 및 시그널 갱신
- `data/gld_us_d.csv`: 2026-03-20 → 2026-04-24 업데이트 (33거래일 추가)
- `latest_gld_signal.json`: selection_cv_mse 기준, asof=2026-04-24, BUY, weight=1.0, model=lasso

### 8. 트랜치 주문 시스템 구현 (`jobs/gld_tranche_order_job.py`)
백테스트와 동일한 트랜치 방식으로 라이브 주문:
- 매일 `total_capital / horizon_days × target_weight` 만큼 새 트랜치 매수
- 130일 후 해당 트랜치 자동 청산
- `outputs/live/tranche_book.json`에 활성 트랜치 장부 관리
- 테스트 결과: BUY 1.7764주 @ $433.03 (dry-run)

### 9. HTML 이메일 리포트 (`jobs/send_gld_email_alert.py` 전면 개편)
- HTML 포맷 (기존 plain text → HTML)
- GLD 가격 차트 (최근 6개월) + BUY 시그널 마커 + target_weight 하단 차트
- CID 방식 이미지 첨부 (Gmail 호환)
- Gmail SMTP 발송 완료 확인 ✅
- 제목 형식: `[GLD] BUY w=1.00 $433.03 - 2026-04-24`

### 10. 앵커 학습 시작 (진행 중)
마지막 앵커: `anchor_2024-12-31`
빠진 16개월 학습 명령어 (이 PC에서 실행 중):
```
cd strategies/automation && python run_objective1_anchor_date_multi_horizon_evaluation.py --anchor-dates 2025-01-31,2025-02-28,2025-03-31,2025-04-30,2025-05-30,2025-06-30,2025-07-31,2025-08-29,2025-09-30,2025-10-31,2025-11-28,2025-12-31,2026-01-30,2026-02-27,2026-03-31
```

---

## 현재 파이프라인 전체 구조

```
[이 PC — 월 1회 수동]
  1. git pull (Pi가 push한 최신 데이터 받기)
  2. run_objective1_anchor_date_multi_horizon_evaluation.py (파라미터 학습, 수 시간)
  3. git push (새 앵커 snapshots)

[Raspberry Pi — 매일 자동 (13:00 PDT, 월~금)]
  run_daily_pipeline.sh
    ↓
  1. update_gld_daily_data.py      → Alpaca에서 오늘 GLD 가격
  2. run_objective2_latest_live_signal.py → 저장된 모델로 신호 계산
  3. gld_tranche_order_job.py      → 트랜치 매수/청산 주문 (dry-run)
  4. send_gld_email_alert.py       → Gmail HTML 리포트 (차트 포함)
  5. git commit + push             → data/signal 자동 GitHub push
```

---

## 주요 설정값

| 항목 | 값 |
|---|---|
| Pi SSH | `ssh joonc@joon-pi` |
| Pi 경로 | `/home/joonc/my_github/quant-trading-system` |
| Pi timezone | America/Los_Angeles (PDT) |
| 타이머 실행 | 월~금 13:00:05 PDT |
| TARGET_HORIZON_DAYS | 130 |
| UPDATE_INTERVAL_MONTHS | 1 |
| SELECTION_CRITERION | selection_cv_mse |
| TRANCHE_TOTAL_CAPITAL | $100,000 |
| TRANCHE_HORIZON_DAYS | 130 |
| ALPACA_DRY_RUN | true (실제 주문 비활성) |
| EMAIL_ALERT_ENABLED | true |
| Alpaca 계정 | Paper trading, $100,000 |
| GLD fractionable | True |
| 마지막 앵커 (학습 전) | 2024-12-31 |

---

## 주요 파일 위치

| 역할 | 경로 |
|---|---|
| 래퍼 스크립트 | `deploy/raspberry_pi/run_daily_pipeline.sh` |
| Pi env 파일 | `deploy/raspberry_pi/quant-trading.env` (gitignored) |
| 체크리스트 | `deploy/raspberry_pi/GLD_PIPELINE_CHECKLIST.md` |
| 트랜치 주문 | `jobs/gld_tranche_order_job.py` |
| 이메일 리포트 | `jobs/send_gld_email_alert.py` |
| 트랜치 장부 | `outputs/live/tranche_book.json` |
| 최신 시그널 | `outputs/live/latest_gld_signal.json` |
| 시그널 히스토리 | `outputs/live/history/gld_signal_log.csv` |
| 앵커 snapshots | `outputs/objective1_anchor_date_multi_horizon_evaluation/` |
| 슬라이드 (최신) | `docs/slides/objective2_research_presentation_2026-04-21.tex` |
| 리포트 | `docs/reports/research_report_2026-04-21.tex` |

---

## 다음 세션에서 할 작업

### 즉시 (앵커 학습 완료 후)
1. **새 앵커로 라이브 시그널 재생성**
   ```
   cd strategies/automation && python run_objective2_latest_live_signal.py
   git add outputs/live/latest_gld_signal.json outputs/live/history/gld_signal_log.csv
   git commit -m "Update live signal with 2025-2026 anchors" && git push
   ```

2. **ALPACA_DRY_RUN=false 활성화** (며칠 dry-run 이메일 확인 후)
   - Pi에서: `nano ~/my_github/quant-trading-system/deploy/raspberry_pi/quant-trading.env`
   - `ALPACA_DRY_RUN=true` → `ALPACA_DRY_RUN=false`
   - `sudo systemctl daemon-reload && sudo systemctl restart gld-daily-pipeline.timer`

### 중기
3. **Stage C live backtest 검증** — 새 앵커로 2025년 성과 확인
4. **다자산 확장** — BRK.B, oil, copper 동일 프레임워크 적용
5. **SINDy 실험** — 비선형 기저함수 Θ(A) = [s_i, s_i², s_i·s_j]
6. **트랜치 horizon 최적화** — 130일 vs 45일 live 성과 비교 후 자동 선택 고려

---

## Mini Project Team

| 역할 | 이름 |
|---|---|
| 전체 멤버 (8명) | Alejandro, Ashmeet, Claire, Thomas, Matthew, Sophia, Jack, Stephen |
| Live Pipeline | Jack, Stephen |
