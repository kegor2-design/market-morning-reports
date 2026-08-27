#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PROJECT_DIR"
PY="${MMP_PYTHON:-python3}"
"$PY" - <<'PY'
from market_morning_publisher.responsive_publish import render_morning_html, render_closing_html, render_youtube_digest_html
m='# 우리의 모닝브리핑 | 2099-01-01\n\n## 오늘의 한 줄 진단\n\n**테스트**\n\n- 시장 국면: **혼조**\n- 판단 근거: 확인\n\n## 밤사이 시장 계기판\n\n| 지역 | 시장 | 값 | 등락 | 세션 | 기준 |\n| --- | --- | --- | --- | --- | --- |\n| 미국 | S&P 500 | 1 | +1.0% | COMPLETED | now |\n\n## 확인할 데이터\n\n- 금리\n'
c='# 우리의 장마감 리뷰 | 2099-01-01\n\n## 오늘의 한 줄 진단\n\n**마감 테스트**\n\n## 국내 시장 종가\n\n| 시장 | 종가 | 등락률 |\n| --- | --- | --- |\n| KOSPI | 1 | +1.0% |\n\n## 사실\n\n- 확인\n'
y='# 시장 관점 카드 | 2099-01-01\n\n- 분석 영상: **1개**\n\n## 1. 테스트\n\n- 분류: **가설**\n'
for name, out in [('morning',render_morning_html(m)),('closing',render_closing_html(c)),('youtube',render_youtube_digest_html(y))]:
    assert 'mmp-desktop' in out and 'mmp-mobile' in out and '@media(max-width:820px)' in out
    print('[OK]', name, 'desktop/mobile responsive contract')
PY
