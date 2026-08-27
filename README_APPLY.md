# MarketMorningPublisher 1.6.5 적용 요약

이 묶음은 **1.6.4 + 1.6.4.1 HOTFIX**를 기준으로 만든 완성본입니다.
운영 서버에는 바로 압축을 덮어쓰지 말고, 제공된 `MarketMorningPublisher_1.6.5_EventIntelligence_CODEX_APPLY_PROMPT_20260825.md` 순서대로
백업 → dry-run diff → 권한 → DB schema read-only check → 전체 테스트 → Event Intelligence 실제 수집 확인 → overlay → 재검증 → cron 반영 순으로 적용하세요.

핵심:

- 공시 1차 원천: OpenDART 직접 수집
- 중요 공시: OpenDART 공식 원문 ZIP/XML 근거문구까지 선택적으로 확인
- MyDream2000 DB: 공시 원천이 아니라 기존 Closing 및 후속 반응 검증용 read-only 연동
- 일정: BLS/BEA/Fed/BOK/BOJ/ECB 공식 일정 지속 갱신 + 검증 seed
- Morning Insight Engine: 일정/공시를 최종 문장 작성 전에 first-class context로 사용
- Blogger: PC 월간 Calendar + 모바일 Agenda
- DB migration: 없음
- 전체 회귀 테스트: 184 PASS

상세 내용은 `RELEASE_NOTES_20260825.md`를 참고하세요.
