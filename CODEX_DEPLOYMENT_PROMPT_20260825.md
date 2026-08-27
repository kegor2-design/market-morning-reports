# MarketMorningPublisher 1.6.5 Codex 배포 원칙

외부 제공 파일 `MarketMorningPublisher_1.6.5_EventIntelligence_CODEX_APPLY_PROMPT_20260825.md`를 우선 사용하세요.
이 파일은 릴리즈 내부의 요약본입니다.

절대 원칙:

1. `/home/kegor2/MarketMorningPublisher` 현재 운영본을 먼저 timestamp backup한다.
2. `.env`, runtime `data`, `logs`, `reports`, OAuth/token 파일을 삭제하거나 릴리즈 파일로 대체하지 않는다.
3. overlay 전에 `rsync --dry-run`으로 변경 파일을 확인한다.
4. 권한 설정 후 `ops/check_closing_db_schema.sh ... --required`와 `ops/check_event_intelligence_preflight.sh`를 먼저 통과시킨다.
5. 전체 unittest가 PASS하지 않으면 적용 중단/rollback한다.
6. Event Intelligence를 foreground로 1회 실행해 official calendar 및 OpenDART 상태를 확인한다.
7. Blogger Theme는 백업 후 수동 적용하며, 1.6.4.1 share/full-post suppression이 남아 있어야 한다.
8. cron은 모든 검증이 끝난 마지막 단계에서만 갱신한다.
9. 공시 source-of-truth는 OpenDART이며 MyDream2000 DB를 공시 1차 원천으로 바꾸지 않는다.
10. DART 접수 시간이 별도 근거로 확인되지 않으면 after-close라고 만들지 않는다.
