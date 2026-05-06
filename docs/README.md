# Documentation

This folder stores ongoing project writing and dated records.

## Structure

- `notes/`: working notes, ideas, decisions, and discussion logs
- `reports/`: more polished summaries, result writeups, and report drafts

## Naming convention

Use date-stamped Markdown files so the history stays easy to track.

- Notes: `topic_YYYY-MM-DD.md`
- Reports: `topic_YYYY-MM-DD.md`

## Recommended workflow

1. Put rough thinking and decision logs in `notes/`
2. Move polished conclusions and result summaries into `reports/`
3. Keep Markdown as the source of truth, and export PDF only when needed

## 세션 시작 시 필독 문서 (Claude용)

새 세션을 시작할 때 아래 두 문서를 먼저 읽으세요. 전체 시스템 흐름과 매수/매도 로직이 담겨 있습니다.

| 문서 | 내용 |
|------|------|
| `notes/pi_execution_architecture_2026-05-05.md` | Pi 실행 구성도 (서비스, 파일 역할, 자산별 신호 담당, 주의사항) |
| `notes/delta_tranche_buy_sell_logic_2026-05-05.md` | Delta tranche 매수/매도 로직 (정규화, tranche_log, 자산 추가/제거, 부트스트랩) |
| `notes/layer0_asset_selection_framework_2026-05-05.md` | Layer 0 자산 선택 알고리즘 (앵커/섹터ETF/히든카드 구성 규칙 + 비율 가이드) |
| `reports/project_overview_2026-05-01.md` | 프로젝트 전체 개요 (3-Layer 철학, 백테스트 결과, 앵커 현황) |

## Recent deployment notes

- `notes/pi_execution_architecture_2026-05-05.md`: Pi systemd 2-service 구조, delta tranche 파일 맵, 자산 유니버스 변경 절차 (최신)
- `notes/delta_tranche_buy_sell_logic_2026-05-05.md`: delta 공식, tranche_log, 부트스트랩 매수/제거 시 전량 매도 로직 (최신)
- `notes/pi_model_artifact_handoff_2026-04-28.md`: workstation research and Raspberry Pi live-execution split, with GitHub used only for lightweight live model handoff artifacts.
