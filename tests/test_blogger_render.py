import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_morning_publisher.blogger_render import render_blogger_html


class BloggerRenderTest(unittest.TestCase):
    def _report(self):
        return """# 우리의 모닝브리핑 | 2026-08-14
## 주요 언론사 기사
- [Reuters: Fed decision](https://example.com/reuters)
  - 한글 요약: 연준 결정 요약
## 분석 기준과 데이터 완전성
- 기준 시각: **2026-08-14T08:10:00+09:00 KST**
- 종합 확신도: **LOW**
## 오늘의 한 줄 진단
**가격 확인은 우호적이다.**
- 시장 국면: **방향이 뚜렷하지 않은 혼조**
- 판단 근거: 상승과 하락 신호가 엇갈린다.
## 핵심 동인
### 가격
- 근거: **상승**
## 밤사이 시장 계기판
| 지역 | 시장 | 값 | 등락 | 세션 | 기준 시각 KST |
| --- | --- | ---: | ---: | --- | --- |
| 미국 증시 | S&P 500 | 7,798.99 | +0.65% | COMPLETED | 2026-08-14T05:35:03+09:00 |
## 확인할 데이터
- 미국 10년물
- 원달러
## 기간별 시나리오
| 기간 | 기본 | 강세 | 약세 | 전환 조건 |
| --- | --- | --- | --- | --- |
| NEXT | 혼조 | 상승 | 하락 | 금리 |
## 국제정세·국내 국정회의 상시 점검
| 감시축 | 상태 |
| --- | --- |
| 미국 정책 | 선거 정책 확인<br>요약: 표심 중심의 정책 기조 |
"""

    def test_single_analysis_renders_separate_desktop_and_mobile_views(self):
        result = render_blogger_html(self._report())
        self.assertIn('class="mmp-desktop"', result)
        self.assertIn('class="mmp-mobile"', result)
        self.assertIn('@media(max-width:820px)', result)
        self.assertIn('MARKET MORNING · INVESTMENT DESK', result)
        self.assertIn('MORNING BRIEF', result)
        self.assertIn('SCENARIO MATRIX', result)
        self.assertIn('오늘 확인할 것', result)
        self.assertIn('<details class="mmp-mobile-detail"', result)

    def test_market_cards_history_and_full_research_are_preserved(self):
        result = render_blogger_html(self._report())
        self.assertIn("지금 시장, 역사적으로 어디쯤일까요?", result)
        self.assertIn('class="mmp-history-arrow"', result)
        self.assertIn('class="mmp-market-tiles mmp-grid"', result)
        self.assertIn('mmp-card up mmp-market-tile', result)
        self.assertIn("mmp-news-lead", result)
        self.assertLess(result.index("주요 언론사 기사"), result.index("OVERNIGHT MARKET MONITOR"))
        self.assertIn("7,798.99", result)
        self.assertNotIn("<pre>", result)
        self.assertIn("<h3>가격</h3>", result)
        self.assertIn('</a><br>한글 요약: 연준 결정 요약</li>', result)
        self.assertNotIn("&lt;br&gt;", result)
        self.assertIn(
            '<div class="mmp-diagnosis-detail"><b>시장 국면:</b> 방향이 뚜렷하지 않은 혼조</div>',
            result,
        )
        self.assertIn(
            '<div class="mmp-diagnosis-detail"><b>판단 근거:</b> 상승과 하락 신호가 엇갈린다.</div>',
            result,
        )
        self.assertIn("선거 정책 확인<br>요약: 표심 중심의 정책 기조", result)


if __name__ == "__main__":
    unittest.main()
