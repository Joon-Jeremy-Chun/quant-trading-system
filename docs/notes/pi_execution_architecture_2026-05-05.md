# Pi Execution Architecture (최신)
*Last updated: 2026-05-05*

다음 세션의 Claude는 이 문서를 먼저 읽고 시스템 전체 흐름을 파악하세요.

---

## 전체 구조 한눈에

```
[ Windows (연구 머신) ]                    [ Raspberry Pi (자율 실행) ]
────────────────────────────────────       ────────────────────────────────────
앵커 계산 (--n-jobs -1, 20코어)             매일 12:45 PT  gld-daily-pipeline.service
백테스트 / 모델 분석                              ↓ git pull (최신 코드/manifest/신호)
모델 파일 생성                                    ↓ 가격 데이터 업데이트 (yfinance)
active_universe.json 수정                         ↓ 신호 빌드 (GLD, BRK-B)
bootstrap 시뮬레이션                               ↓ [완료 후 대기]
tranche_log 초기화
        ↓ git push                         매일 13:00 PT  gld-order-execution.service
                                                  ↓ 신호 유효성 검증
                                                  ↓ 포트폴리오 정규화
                                                  ↓ delta_tranche_job.py
                                                  ↓ 이메일 보고서
                                                  ↓ git commit & push (tranche_log 등)
```

---

## Pi systemd 서비스 2개

| 서비스 | 시간 (PT) | 스크립트 | 역할 |
|--------|-----------|----------|------|
| `gld-daily-pipeline.service` | 12:45 | `run_daily_pipeline.sh` | git pull + 데이터 업데이트 + 신호 빌드 |
| `gld-order-execution.service` | 13:00 | `run_order_execution.sh` | 주문 실행 + 이메일 + git push |

확인:
```bash
systemctl status gld-daily-pipeline.service
systemctl status gld-order-execution.service
journalctl -u gld-order-execution.service -n 50
```

---

## 파일 역할 맵

```
models/
  live_assets/
    active_universe.json     ← 오늘 거래할 자산 목록 (Windows에서 수정)
  pi_reference/
    GLD/
      anchor_2026-04-29/
        optimization_outputs/  ← Pi가 신호 계산에 사용하는 앵커 (git 제외, 로컬 복사)
      pi_reference_meta.json
    BRK-B/
      anchor_.../
  live/
    latest_model_manifest.json ← 각 자산의 anchor_output_root, horizon 등 설정

outputs/
  live/
    latest_gld_signal.json     ← 오늘 GLD 신호 (Pi가 빌드 or Windows push)
    latest_brkb_signal.json
    latest_qqq_signal.json     ← Windows가 빌드 후 push
    latest_rklb_signal.json
    tranche_log.csv            ← 130일 rolling 일별 정규화 비중 기록 (매일 1행 추가)
    history/
      gld_signal_log.csv       ← 신호 히스토리 (날짜별 누적)
  bootstrap/
    bootstrap_position.json    ← 1회성 부트스트랩 매수 수량 (시뮬에서 생성)
    daily_weights.csv          ← 시뮬레이션 원본 (123일, 2025-09-02~2026-04-24)

jobs/
  gld_daily_pipeline.py        ← 메인 파이프라인 오케스트레이터
  delta_tranche_job.py         ← 매일 delta 주문 실행 + tranche_log 업데이트
  bootstrap_buy_job.py         ← 1회성 부트스트랩 매수 (신규 자산 진입 시)
  send_gld_email_alert.py      ← 이메일 보고서
  update_gld_daily_data.py     ← 가격 데이터 업데이트

scripts/
  simulate_tranche_bootstrap.py ← 과거 6개월 시뮬 → bootstrap_position.json 생성
  refresh_pi_reference.py       ← 새 앵커 계산 후 pi_reference 갱신 (Windows에서 실행)
```

---

## 신호 빌드 담당 분리

| 자산 | 신호 빌드 담당 | 이유 |
|------|---------------|------|
| GLD | Pi | `models/pi_reference/GLD`에 앵커 보유 |
| BRK-B | Pi | `models/pi_reference/BRK-B`에 앵커 보유 |
| QQQ | Windows → push | Pi에 앵커 없음 |
| RKLB | Windows → push | Pi에 앵커 없음 |

**중요:** Pi의 `models/pi_reference/<symbol>/anchor_*/optimization_outputs/`는
git 제외(gitignore)이므로 Pi에 직접 복사 필요.
복사 방법:
```bash
# Pi에서 실행
python3 scripts/refresh_pi_reference.py --symbol GLD
python3 scripts/refresh_pi_reference.py --symbol BRK-B
# 위 스크립트가 SKIP하면 (폴더 존재하지만 빈 경우):
cp -r outputs/objective1_anchor_date_multi_horizon_evaluation/anchor_YYYY-MM-DD/optimization_outputs \
      models/pi_reference/GLD/anchor_YYYY-MM-DD/
```

---

## 자산 유니버스 변경 방법

### 자산 추가

1. Windows에서 앵커 계산 완료
2. `models/live_assets/active_universe.json`에 추가
3. `scripts/simulate_tranche_bootstrap.py` 실행 → 새 자산 포함한 bootstrap_position.json 갱신
4. git push
5. Pi에서 `python .venv/bin/python jobs/bootstrap_buy_job.py` 실행 (1회)
6. 이후 delta_tranche_job이 자동 처리

### 자산 제거

1. `models/live_assets/active_universe.json`에서 제거
2. git push
3. 다음 Pi 실행 시 delta_tranche_job이 자동으로 전량 매도

---

## 이메일 규칙

- `--test` 플래그: 오너(joonchun1000@gmail.com)에게만 발송, 제목 `[TEST]`
- 플래그 없음: 전체 수신자 (오너 + Jack + ssherwood2) — **Pi 자동화에서만**
- 수동 테스트 시 반드시 `--test` 사용

---

## 알려진 이슈 및 주의사항

1. **pi_reference optimization_outputs 미복사 문제 (2026-05-05 발생)**
   - `models/pi_reference/` 폴더 구조는 git에 있지만 `optimization_outputs/`는 gitignore
   - 새 앵커 추가 후 Pi에서 반드시 수동 복사 필요
   - 미복사 시: `FileNotFoundError: No anchor_<date>/optimization_outputs` 오류 발생
   - 신호가 5일 이상 묵으면 `ValueError: signal is too old` 로 파이프라인 전체 중단

2. **브랜치 현황**
   - Windows: `work/pi-manifest-top20`
   - Pi: `work/pi-manifest-top20` (Pi도 같은 브랜치 사용 중)
   - main 브랜치로 머지 미완료 — 머지 후 양쪽 다 `main`으로 통일 예정

3. **QQQ 앵커 갭**
   - 2026-01 ~ 2026-03 기간 앵커가 2025-12-31로 고정 (누락)
   - 운영상 문제없음 (fallback 동작)
