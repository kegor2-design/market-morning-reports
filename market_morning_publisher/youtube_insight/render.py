from __future__ import annotations

import html
import json
import os
import urllib.parse
import urllib.request
from datetime import date
from typing import Any


LABELS = {
    "FACT_CLAIM": "사실 주장",
    "HYPOTHESIS": "가설",
    "OPINION": "관점",
    "FORECAST": "전망",
    "RUMOR": "미확인 소문",
    "ACTION_RULE": "조건부 규칙",
}
STATUS_LABELS = {
    "SUPPORTED": "근거 있음",
    "PARTIAL": "일부 확인",
    "UNVERIFIED": "미확인",
    "CONTRADICTED": "반대 근거 있음",
    "UNKNOWN": "판단 보류",
}


def _text(value: Any) -> str:
    return str(value or "확인 불가").strip()


def _bullet(values: list[Any]) -> str:
    cleaned = [_text(value) for value in values if _text(value) not in {"", "확인 불가"}]
    return " / ".join(cleaned) if cleaned else "확인 불가"


def render_digest_markdown(report_date: str, cards: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    lines = [
        f"# 시장 관점 카드 | {report_date}",
        "",
        "> 주요 유튜브 콘텐츠에서 시장에 영향을 줄 수 있는 주장·가설·전망을 추려, 뉴스·시장 데이터·차트 검증 결과와 분리해 정리합니다. 출처의 주장을 확인된 사실로 자동 간주하지 않습니다.",
        "",
        f"- 분석 영상: **{manifest.get('videos_analyzed', 0)}개**",
        f"- 게시 후보: **{len(cards)}개**",
        "- `미확인 소문`은 기본 자동 게시 대상이 아닙니다.",
        "",
    ]
    if not cards:
        lines.extend(["## 오늘의 게시 대상", "", "게시 기준을 통과한 시장 관점 카드가 없습니다."])
        return "\n".join(lines) + "\n"
    for index, card in enumerate(cards, 1):
        cls = LABELS.get(card.get("classification"), card.get("classification", "확인 불가"))
        status = STATUS_LABELS.get(card.get("verification_status"), card.get("verification_status", "판단 보류"))
        lines.extend([
            f"## {index}. {_text(card.get('title_ko'))}",
            "",
            f"- 출처: **{_text(card.get('channel_name'))}** · [{_text(card.get('video_title'))}]({_text(card.get('video_url'))})",
            f"- 분류: **{cls}** · 검증 상태: **{status}** · 출처 가중치: **{_text(card.get('source_weight'))}**",
            f"- 출처 관점: {_text(card.get('source_view_ko'))}",
            f"- 확인된 근거: {_text(card.get('verification_summary_ko'))}",
            f"- 우리 해석: {_text(card.get('our_interpretation_ko'))}",
            f"- 인과경로: {_bullet(card.get('causal_chain') or [])}",
            f"- 추가로 볼 데이터: {_bullet(card.get('data_to_watch') or [])}",
            f"- 확인할 일정: {_bullet(card.get('events_to_watch') or [])}",
            f"- 한국 전달경로: {_text(card.get('korea_transmission_ko'))}",
            f"- 반증조건: {_bullet(card.get('invalidation_conditions') or [])}",
        ])
        chart = card.get("chart_evidence") or {}
        if chart.get("available"):
            lines.append(
                f"- 차트 검증: **{_text(chart.get('status'))}** · {_text(chart.get('summary_ko'))}"
            )
        elif card.get("chart_analysis_requested"):
            lines.append("- 차트 검증: **대기** · 영상의 차트 근거가 중요하지만 검증 결과가 아직 없습니다.")
        lines.append("")
    lines.extend([
        "## 이용 원칙",
        "",
        "이 글은 외부 콘텐츠의 주장을 그대로 전달하는 뉴스가 아니라, 검증할 가치가 있는 시장 관점을 출처와 검증 상태를 분리해 기록하는 연구용 카드입니다. 개별 종목의 매수·매도 권유가 아닙니다.",
    ])
    return "\n".join(lines) + "\n"


def render_digest_html(markdown: str) -> str:
    from market_morning_publisher.responsive_publish import render_youtube_digest_html
    return render_youtube_digest_html(markdown)

def blogger_publish_digest(title: str, markdown: str, prior_post_id: str | None = None) -> dict[str, Any]:
    required = ["BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("missing Blogger environment: " + ", ".join(missing))
    token_body = urllib.parse.urlencode({
        "client_id": os.environ["BLOGGER_CLIENT_ID"],
        "client_secret": os.environ["BLOGGER_CLIENT_SECRET"],
        "refresh_token": os.environ["BLOGGER_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    token = json.loads(urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=token_body, method="POST"), timeout=30
    ).read())["access_token"]
    base = f"https://www.googleapis.com/blogger/v3/blogs/{os.environ['BLOGGER_BLOG_ID']}/posts/"
    url, method = ((base + prior_post_id, "PUT") if prior_post_id else (base, "POST"))
    body = json.dumps({
        "kind": "blogger#post",
        "title": title,
        "content": render_digest_html(markdown),
        "labels": ["시장 관점 카드", "유튜브 인사이트"],
    }, ensure_ascii=False).encode()
    request = urllib.request.Request(
        url, data=body, method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(request, timeout=30).read())
