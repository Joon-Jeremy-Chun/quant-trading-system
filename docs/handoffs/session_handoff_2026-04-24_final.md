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
- `.venv` 생성 + `requirements-live.txt` 설치 (alpaca-py, scikit-learn 등)
- `deploy/raspberry_pi/quant-trading.env` 생성 (Alpaca paper API 키, ALPACA_DRY_RUN=true)
- Alpaca API 키는 Pi `~/.bashrc`에 있던 것 사용

### 4. systemd 타이머 설정
- `/etc/systemd/system/gld-daily-pipeline.service` 생성
- `/etc/systemd/system/gld-daily-pipeline.timer` 생성
- 실행 시간: **매주 월~금 13:00:05 PDT**
- 타이머 상태: `active (waiting)`, 다음 실행: Mon 2026-04-27 13:00:05 PDT
- ExecStart: `run_daily_pipeline.sh` (래퍼 스크립트)

### 5. 자동 git push 래퍼 스크립트
`deploy/raspberry_pi/run_daily_pipeline.sh` 생성:
1. `gld_daily_pipeline.py --build-signal` 실행
   - Alpaca에서 오늘 GLD 가격 받기
   - 저장된 모델로 신호 계산 (Pi가 직접, 가벼운 작업)
   - 주문 실행 (dry-run)
2. `data/gld_us_d.csv` + `latest_gld_signal.json` + `gld_signal_log.csv` 자동 git commit + push
   - 커밋 메시지: `Auto: daily GLD data + signal YYYY-MM-DD`

### 6. .gitignore 생성
- `deploy/raspberry_pi/quant-trading.env` (API 키 보호)
- `__pycache__/`, `.venv/`
- LaTeX 중간파일 (`.aux`, `.log`, `.fdb_latexmk` 등)
- `.claude/settings.local.json` 추가 후 `git rm --cached`로 추적 해제

### 7. 데이터 및 시그널 갱신
- `data/gld_us_d.csv`: 2026-03-20 → 2026-04-24 업데이트 (33거래일 추가)
- `latest_gld_signal.json`: selection_cv_mse 기준, asof=2026-04-24, BUY, weight=1.0, model=lasso
- Pi 자동 push 테스트 완료: `[OK] Pushed to GitHub`

### 8. 앵커 학습 시작 (진행 중)
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

[Raspberry Pi — 매일 자동 (13:00 PDT)]
  run_daily_pipeline.sh
    ↓
  1. update_gld_daily_data.py (Alpaca에서 오늘 GLD 가격)
  2. run_objective2_latest_live_signal.py (저장된 모델로 신호 계산)
  3. gld_close_order_job.py (주문 실행, 현재 dry-run)
  4. send_gld_email_alert.py (이메일)
  5. git commit + push (data/gld_us_d.csv, latest_gld_signal.json, gld_signal_log.csv)
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
| ALPACA_DRY_RUN | true (아직 실제 주문 비활성) |
| Alpaca 계정 | Paper trading, $100,000 |
| GLD fractionable | True (소수점 매매 가능) |
| 마지막 앵커 (학습 전) | 2024-12-31 |

---

## 다음 세션에서 할 작업

### 즉시 (앵커 학습 완료 후)
1. **새 앵커로 라이브 시그널 재생성**
   ```
   cd strategies/automation && python run_objective2_latest_live_signal.py
   git add outputs/live/latest_gld_signal.json outputs/live/history/gld_signal_log.csv
   git commit -m "Update live signal with new anchors" && git push
   ```

2. **ALPACA_DRY_RUN=false 활성화** (몇 번 dry-run 확인 후)
   - Pi에서: `nano ~/my_github/quant-trading-system/deploy/raspberry_pi/quant-trading.env`
   - `ALPACA_DRY_RUN=true` → `ALPACA_DRY_RUN=false`
   - `sudo systemctl restart gld-daily-pipeline.timer`

### 중기
3. **Stage C live backtest 검증** — 새 앵커로 2025년 성과 확인
4. **다자산 확장** — BRK.B, oil, copper 동일 프레임워크 적용
5. **SINDy 실험** — 비선형 기저함수 Θ(A) = [s_i, s_i², s_i·s_j]

---

## 주요 파일 위치

| 역할 | 경로 |
|---|---|
| 래퍼 스크립트 | `deploy/raspberry_pi/run_daily_pipeline.sh` |
| Pi env 파일 | `deploy/raspberry_pi/quant-trading.env` (gitignored) |
| 체크리스트 | `deploy/raspberry_pi/GLD_PIPELINE_CHECKLIST.md` |
| 최신 시그널 | `outputs/live/latest_gld_signal.json` |
| 시그널 히스토리 | `outputs/live/history/gld_signal_log.csv` |
| 앵커 snapshots | `outputs/objective1_anchor_date_multi_horizon_evaluation/` |
| 슬라이드 (최신) | `docs/slides/objective2_research_presentation_2026-04-21.tex` |
| 리포트 | `docs/reports/research_report_2026-04-21.tex` |
