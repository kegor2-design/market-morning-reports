# Official Forward Calendar & Coverage — 1.6.5.6

YouTube/뉴스는 주요 일정을 처음 아는 주 소스가 아니라 **누락 탐지와 해석 보강** 역할을 한다.

Production flow:

`Official forward sources -> normalize -> event ledger -> calendar -> pre-event MI -> result -> post-event review`

Discovery flow:

`News / YouTube / Telegram -> date/event candidate -> existing official calendar match -> attach context`

공식 일정이 발견됐는데 캘린더에 없으면 `MISSING_SCHEDULE_CANDIDATE` 및 coverage 품질 문제로 기록한다.

## Required source families
- Federal Reserve / FOMC
- Bank of Korea
- BLS
- BEA
- U.S. Treasury
- ECB
- BOJ

Jackson Hole(Kansas City Fed), FEC election calendar 등은 중요 이벤트 source로 추가한다.

## Bootstrap seed
`official_calendar_seed_20260827.json`은 2026-08-27 기준 공식 출처로 확인한 핵심 일정을 최초 적재하기 위한 seed다. live collector가 연결되면 source의 최신 상태와 reconcile해야 하며 seed가 영구적인 truth cache가 되어서는 안 된다.

## Coverage health
required source에서 미래 event가 0건이면 Calendar가 비어 있더라도 정상으로 보지 않고 `FAIL` 처리한다.
