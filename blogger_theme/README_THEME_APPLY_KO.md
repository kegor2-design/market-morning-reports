# Market Morning Research Portal Theme 1.6.5 적용 안내

1.6.5 Theme는 1.6.4.1의 Blogger 기본 공유 UI/구형 게시물 본문 노출 방지 HOTFIX를 그대로 포함하고,
최신 Morning Brief의 `주요 일정 캘린더`를 홈 Research Portal의 실제 Calendar UI로 표시합니다.

- PC/태블릿: 최대 2개 월의 달력 grid
- 모바일: agenda card
- S/S+ 일정: 고위험/핵심 이벤트 강조
- A 일정: watch 이벤트 강조
- 시간 기준: KST

## 적용 전 백업

Blogger → 테마 → 맞춤설정 메뉴 → 백업에서 현재 XML을 반드시 저장하세요.

## 적용 파일

`blogger_theme/market_morning_research_portal.xml`

## 파일 정적 검증

```bash
cd /home/kegor2/MarketMorningPublisher
chmod +x ops/check_research_portal_theme.sh ops/verify_live_research_portal.sh
./ops/check_research_portal_theme.sh /home/kegor2/MarketMorningPublisher
```

PASS 후 Blogger의 HTML 편집에서 XML 전체를 교체/저장합니다.

## 저장 후 확인

브라우저에서 홈과 게시글을 직접 확인한 뒤:

```bash
cd /home/kegor2/MarketMorningPublisher
./ops/verify_live_research_portal.sh
```

정상 marker:

```text
data-rp-theme='1.6.5'
rp-home-calendar
rp-calendar-months
rp-calendar-agenda
```

## 주의

Blogger post API는 Theme XML 쓰기를 담당하지 않습니다. 테마 적용은 수동 백업/교체가 필요합니다.
홈에 Calendar가 비어 있으면 먼저 최신 Morning 게시물에 `주요 일정 캘린더`가 실제 렌더링되어 있는지 확인하세요.
