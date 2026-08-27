from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


REQUIRED_THEME_MARKERS = (
    "rp-site-header",
    "rp-home-portal",
    "rp-market-board",
    "rp-intelligence",
    "rp-research-layout",
    "data:view.isHomepage",
    "mmp-responsive",
    "Market Morning Briefing — Research Portal Theme 1.6.5 (includes 1.6.4.1 Hotfix)",
    "rp-home-calendar",
    "buildCalendar",
    ".rp-home .post-body",
    "decorateResearchCards",
    "post-share-buttons",
)


@dataclass(frozen=True)
class ThemeValidation:
    ok: bool
    missing_markers: tuple[str, ...]
    xml_parse_ok: bool
    has_blog_widget: bool
    has_mobile_breakpoint: bool
    blogger_css_enabled: bool
    has_home_post_suppression: bool
    has_share_suppression: bool


def validate_theme(theme_path: str | Path) -> ThemeValidation:
    path = Path(theme_path)
    text = path.read_text(encoding="utf-8")
    missing = tuple(marker for marker in REQUIRED_THEME_MARKERS if marker not in text)
    xml_ok = True
    try:
        ET.fromstring(text)
    except ET.ParseError:
        xml_ok = False
    has_blog = "type='Blog'" in text or 'type="Blog"' in text
    compact = text.replace(" ", "")
    has_mobile = "@media(max-width:820px)" in compact
    css_enabled = "b:css='true'" in text or 'b:css="true"' in text
    home_suppression = ".rp-home .post-body" in text and "display:none!important" in text
    share_suppression = ".rp-home .post-share-buttons" in text and ".rp-item .post-share-buttons" in text
    return ThemeValidation(
        ok=not missing and xml_ok and has_blog and has_mobile,
        missing_markers=missing,
        xml_parse_ok=xml_ok,
        has_blog_widget=has_blog,
        has_mobile_breakpoint=has_mobile,
        blogger_css_enabled=css_enabled,
        has_home_post_suppression=home_suppression,
        has_share_suppression=share_suppression,
    )


def _extract_skin(theme_text: str) -> str:
    match = re.search(r"<b:skin><!\[CDATA\[(.*?)\]\]></b:skin>", theme_text, re.S)
    if not match:
        raise ValueError("theme b:skin CDATA not found")
    return match.group(1).strip()



def _extract_theme_script(theme_text: str) -> str:
    matches = re.findall(r"<script[^>]*>\s*//<!\[CDATA\[(.*?)//\]\]>\s*</script>", theme_text, re.S)
    return matches[-1].strip() if matches else ""

def _sample_markdown() -> str:
    return """# 2026-08-25 Market Morning Briefing

## 오늘의 한 줄 진단
**혼조 출발 가능성이 높지만 반도체 상대강도와 외국인 수급이 유지되는지 우선 확인합니다.**
- 시장 국면: **RISK_ON_SELECTIVE**
- 판단 근거: 장기금리 경계와 AI/반도체 이익 기대가 동시에 존재

## 주요 일정 캘린더
| KST | 남은 시간 | 중요도 | 일정 | 한국시장 전달경로 | 상태 |
|---|---|---|---|---|---|
| 2026-08-27 05:20 | D-2 | S+ | NVIDIA FY2027 2분기 실적 발표 | HBM·반도체 실적 기대 | SCHEDULED |
| 2026-08-27 10:00 | D-2 | S+ | 한국은행 금통위 | 금리·원화·외국인 수급 | SCHEDULED |

## 밤사이 시장 계기판
| 지역 | 시장 | 값 | 변화 | 세션 | 기준 |
|---|---|---:|---:|---|---|
| 미국 | S&P 500 | 6,502 | +0.28% | COMPLETED | 05:00 KST |
| 미국 | NASDAQ | 22,114 | +0.46% | COMPLETED | 05:00 KST |
| 미국 | PHLX Semiconductor | 6,142 | +0.91% | COMPLETED | 05:00 KST |
| 미국 | US 10Y yield | 4.18% | +0.03%p | COMPLETED | 06:00 KST |
| 한국 | USD/KRW | 1,367 | -0.22% | COMPLETED | 06:00 KST |

## 핵심 동인
- **Treasury** — 장기금리가 재차 상승하는지 확인합니다.
- **AI / Semiconductor** — 이익 추정치와 실제 가격반응이 계속 일치하는지 봅니다.
- **Korea Flow** — 외국인 현·선물 동반수급 여부가 중요합니다.
- **Dollar** — 달러 강세 재개 시 성장주 부담을 확인합니다.

## 투자위원회 관점
- 기본 시나리오: 업종 차별화와 반도체 상대강세
- 강세 시나리오: 장기금리 안정 + 외국인 선물 매수
- 약세 시나리오: 금리 재상승 + 달러 강세 + breadth 악화

## 차트 인사이트
- NASDAQ: 상승추세 유지 여부보다 breadth와 신고가 확산을 함께 확인합니다.
- 반도체: 돌파 자체보다 거래량·수급·실적 revision 결합 여부를 봅니다.

## 오늘 확인할 것
- 미 10년/30년 금리와 Treasury auction 반응
- 외국인 KOSPI200 선물 방향
- SOX 대비 KOSPI 반도체 상대강도
- 주요 지지선 이탈 시 가설 무효화 여부

## 주요 해외 언론사 기사
- 미국 재정과 장기금리 관련 정책 뉴스
- AI CAPEX 및 반도체 수요 관련 업데이트
"""


def build_preview(theme_path: str | Path, output_path: str | Path) -> Path:
    from .responsive_publish import render_morning_html

    theme_path = Path(theme_path)
    output = Path(output_path)
    theme_text = theme_path.read_text(encoding="utf-8")
    css = _extract_skin(theme_text)
    theme_js = _extract_theme_script(theme_text)
    post_html = render_morning_html(_sample_markdown())

    # A deterministic standalone rendering of the intended Blogger home surface.
    market_cards = "".join(
        [
            '<div class="rp-market up"><small>미국</small><b>S&amp;P 500</b><strong>6,502</strong><em>+0.28%</em></div>',
            '<div class="rp-market up"><small>미국</small><b>NASDAQ</b><strong>22,114</strong><em>+0.46%</em></div>',
            '<div class="rp-market up"><small>미국</small><b>PHLX Semiconductor</b><strong>6,142</strong><em>+0.91%</em></div>',
            '<div class="rp-market down"><small>미국</small><b>US 10Y yield</b><strong>4.18%</strong><em>+3bp</em></div>',
            '<div class="rp-market up"><small>한국</small><b>USD/KRW</b><strong>1,367</strong><em>-0.22%</em></div>',
        ]
    )
    content = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Research Portal Preview</title><style>{css}</style></head><body class='rp-home'><div class='rp-shell'>
<header class='rp-site-header'><div class='rp-header-inner'><a class='rp-brand'><span class='rp-mark'>M</span><span class='rp-brand-copy'><b>Market Morning Briefing</b><small>Research Portal</small></span></a><nav class='rp-nav'><a>Research Desk</a><a>Morning</a><a>Closing</a><a>Market View</a><a>Chart Research</a></nav><div class='rp-header-status'><span class='rp-status-dot'></span><span>RESEARCH SYSTEM</span></div></div></header>
<div class='rp-home-portal'><section class='rp-home-hero'><div class='rp-command'><div class='rp-kicker'>MARKET MORNING · INVESTMENT RESEARCH DESK</div><h1>오늘의 Research Desk</h1><p class='rp-diagnosis'>혼조 출발 가능성이 높지만 반도체 상대강도와 외국인 수급이 유지되는지 우선 확인합니다.</p><div class='rp-command-actions'><a class='rp-btn primary'>최신 리서치 열기</a><a class='rp-btn'>Chart Research</a></div><div class='rp-asof'>2026-08-25 · 08:10 KST</div></div><aside class='rp-risk-card'><h2>Research Framework</h2><div class='rp-risk-grid'><div class='rp-risk-cell'><small>MACRO / POLICY</small><b>WATCH</b></div><div class='rp-risk-cell'><small>EARNINGS</small><b>POSITIVE</b></div><div class='rp-risk-cell'><small>FLOW</small><b>NEUTRAL</b></div><div class='rp-risk-cell'><small>CHART</small><b>IMPROVING</b></div></div><div class='rp-note'>가설과 사실을 분리하고 실제 시장반응으로 사후 검증합니다.</div></aside></section>
<div class='rp-section-head'><h2>Market Monitor</h2><span>Overnight · Rates · FX · Risk</span></div><section class='rp-market-board'>{market_cards}</section>
<div class='rp-section-head'><h2>Market Calendar</h2><span>Official Schedule · KST</span></div><section class='rp-calendar-board' id='rp-home-calendar'><article class='rp-calendar-item hot'><small><span>2026-08-27 05:20</span><span>D-2 · S+</span></small><b>NVIDIA FY2027 2분기 실적 발표</b><p>HBM·반도체 실적 기대</p></article><article class='rp-calendar-item hot'><small><span>2026-08-27 10:00</span><span>D-2 · S+</span></small><b>한국은행 금통위</b><p>금리·원화·외국인 수급</p></article></section>
<div class='rp-section-head'><h2>Investment Intelligence</h2><span>Drivers · Chart · Watch</span></div><section class='rp-intelligence'><article class='rp-module rp-driver'><div class='rp-module-head'><b>Core Drivers</b><span>WHY NOW</span></div><ul><li>Treasury 장기금리와 발행 수요</li><li>AI/반도체 이익 추정치</li><li>외국인 현·선물 수급</li></ul></article><article class='rp-module rp-chart'><div class='rp-module-head'><b>Chart / Market Evidence</b><span>PRICE ACTION</span></div><ul><li>NASDAQ breadth 확인</li><li>반도체 돌파 + 거래량 확인</li><li>시장 regime과 패턴 결합</li></ul></article><article class='rp-module rp-watch'><div class='rp-module-head'><b>Watch &amp; Invalidation</b><span>RISK CONTROL</span></div><ul><li>US 10Y/30Y 급등 여부</li><li>외국인 선물 매도 전환</li><li>핵심 지지 이탈 시 가설 재검토</li></ul></article></section></div>
<main class='rp-research-layout'><div class='rp-feed-title'><h2>Latest Research</h2><small>MORNING · CLOSING · MARKET VIEW · CHART</small></div><div class='blog-posts'><article class='post'><h3 class='post-title'><a href='#morning'>오늘 장전 Market Morning Briefing</a></h3><div class='post-header'>2026-08-25</div><div class='post-body'>{post_html}</div><div class='post-share-buttons'><svg width='180' height='180'><circle cx='90' cy='90' r='70'/></svg><span>Facebook</span></div></article><article class='post'><h3 class='post-title'><a href='#closing'>장마감 Review Desk</a></h3><div class='post-header'>Latest closing research</div><div class='post-body'><p>아침 시나리오와 실제 시장 반응을 비교하고 다음 거래일 확인 과제를 남깁니다.</p><div class='sharing-platform-button'><svg width='180' height='180'></svg>공유 링크 만들기</div></div></article><article class='post'><h3 class='post-title'><a href='#chart'>Chart Strategy Research</a></h3><div class='post-header'>Research only</div><p class='post-snippet'>콘텐츠에서 발굴한 차트 전략을 실제 과거 차트와 Point-in-Time 방식으로 검증합니다.</p></article></div></main>
<footer class='rp-site-footer'><div class='rp-footer-inner'><b>Market Morning Briefing</b> · Independent market research framework.</div></footer></div><script>{theme_js}</script></body></html>"""
    output.write_text(content, encoding="utf-8")
    return output


def load_portal_config(root: str | Path) -> dict:
    return json.loads((Path(root) / "config" / "research_portal_ui.json").read_text(encoding="utf-8"))
