import unittest

from market_morning_publisher.closing import render_closing_html
from market_morning_publisher.responsive_publish import render_morning_html
from market_morning_publisher.youtube_insight.render import render_digest_html


class ResponsivePublishTests(unittest.TestCase):

    def test_morning_calendar_has_desktop_source_and_mobile_agenda(self):
        md = """# 우리의 모닝브리핑 | 2026-08-25

기준 시각: **2026-08-25T08:10:00+09:00**
종합 확신도: **MEDIUM**

## 오늘의 한 줄 진단
**이벤트 전 변동성을 확인한다.**
- 시장 국면: **CHOPPY**
- 판단 근거: 중요 이벤트 대기

## 주요 일정 캘린더
| KST | 남은 시간 | 중요도 | 일정 | 한국시장 전달경로 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-27 05:20 | D-2 | S+ | NVIDIA 실적 | HBM → 반도체 | SCHEDULED |

## 밤사이 시장 계기판
| 지역 | 시장 | 값 | 등락 | 세션 | 기준 시각 KST |
| --- | --- | ---: | ---: | --- | --- |
| 미국 | NASDAQ | 1 | +1.00% | 마감 | now |

## 확인할 데이터
- NVIDIA 가이던스

## 판단 무효화 조건
- 일정 변경
"""
        out = render_morning_html(md)
        self.assertIn('mmp-event-calendar-source', out)
        self.assertIn('MARKET EVENT CALENDAR', out)
        self.assertIn('NVIDIA 실적', out)
        self.assertIn('mmp-mobile-event-calendar', out)

    def test_closing_has_investment_desk_and_mobile_compact_view(self):
        md = """# 우리의 장마감 리뷰 | 2026-08-24

기준 시각: **2026-08-24T17:00:00+09:00**
종합 확신도: **MEDIUM**

## 오늘의 한 줄 진단

**외국인 수급 확인이 중요하다.**

## 국내 시장 종가

| 시장 | 종가 | 등락률 | 시가 | 고가 | 저가 |
| --- | ---: | ---: | ---: | ---: | ---: |
| KOSPI | 3,200 | +0.50% | 3,180 | 3,210 | 3,170 |
| KOSDAQ | 810 | -0.20% | 812 | 815 | 806 |

## 사실
- KOSPI 상승

## 해석
- 업종 차별화

## 가설
- 수급 영향

## 아침 전망 채점
- **SUPPORTED** — 혼조

## 우리 인사이트 일일 검증
- **MI-001 / PARTIAL** — 추가 확인

## 다음 거래일로 넘길 확인 과제
- 외국인 선물
"""
        out = render_closing_html(md)
        self.assertIn('MARKET CLOSE · REVIEW DESK', out)
        self.assertIn('CLOSING REVIEW', out)
        self.assertIn('MORNING SCORECARD', out)
        self.assertIn('다음 거래일 체크', out)
        self.assertIn('mmp-card up mmp-market-tile', out)
        self.assertIn('mmp-card down mmp-market-tile', out)

    def test_youtube_cards_use_desktop_grid_and_mobile_details(self):
        md = """# 시장 관점 카드 | 2026-08-24

> 출처 주장을 사실로 자동 간주하지 않습니다.

- 분석 영상: **2개**
- 게시 후보: **1개**

## 1. 장기금리 가설

- 출처: **테스트 채널**
- 분류: **가설** · 검증 상태: **일부 확인**
- 우리 해석: 데이터 확인 필요

## 이용 원칙

개별 종목의 매수·매도 권유가 아닙니다.
"""
        out = render_digest_html(md)
        self.assertIn('YOUTUBE · MARKET VIEW DESK', out)
        self.assertIn('MARKET VIEW CARDS', out)
        self.assertIn('MARKET VIEW CARD', out)
        self.assertIn('<details class="mmp-mobile-detail" open>', out)


if __name__ == '__main__':
    unittest.main()
