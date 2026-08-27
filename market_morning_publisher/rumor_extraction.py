from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .schedule_discovery import extract_schedule_candidates


EVENT_TERMS = {
    "M&A": ("인수", "합병", "매각", "m&a", "지분 매입"),
    "CONTRACT": ("수주", "계약", "공급", "납품"),
    "POLICY": ("정책", "규제", "지원", "관세", "제재", "금리", "개입"),
    "EARNINGS": ("실적", "매출", "영업이익", "가이던스"),
    "FINANCING": ("유상증자", "전환사채", "자금조달", "바이백", "자사주"),
    "SUPPLY_DEMAND": ("감산", "증산", "공급 부족", "재고", "출하"),
}
CHECKABLE_TERMS = tuple({x for values in EVENT_TERMS.values() for x in values}) + (
    "예정", "추진", "검토", "협의", "발표", "가능성", "설", "찌라시", "단독",
)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _event_type(text: str) -> str:
    lower = text.lower()
    for kind, terms in EVENT_TERMS.items():
        if any(term in lower for term in terms):
            return kind
    return "OTHER"


def _is_checkable(text: str) -> bool:
    lower = text.lower()
    return len(text) >= 20 and any(term in lower for term in CHECKABLE_TERMS)


def telegram_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        claim = _text(row.get("text"))
        if not _is_checkable(claim):
            continue
        out.append({
            "source_type": row.get("source_type") or "TELEGRAM",
            "source_id": f"{row.get('channel','telegram')}:{row.get('message_id','')}",
            "title": claim[:100], "claim": claim, "event_type": _event_type(claim),
            "published_at": row.get("published_at"), "url": row.get("url"),
            "source_name": row.get("source_name") or row.get("channel"),
            "author": row.get("author"), "attributable": bool(row.get("attributable")),
            "impact_summary": claim[:240], "resolution_condition": "공식 공시·회사 발표·주요 통신사 보도로 확인",
            "metadata": dict(row.get("metadata") or {}),
        })
    return out


def youtube_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        claim = _text(row.get("claim_summary_ko") or row.get("title_ko") or row.get("claim") or row.get("summary"))
        if not _is_checkable(claim):
            continue
        video_id = _text(row.get("video_id") or row.get("source_id"))
        claim_id = _text(row.get("claim_id") or row.get("card_id") or video_id)
        out.append({
            "source_type": "YOUTUBE_EXPERT" if row.get("channel_name") else "YOUTUBE",
            "source_id": claim_id, "title": _text(row.get("title_ko")) or claim[:100],
            "claim": claim, "event_type": _event_type(claim),
            "published_at": row.get("published_at"), "url": row.get("video_url") or row.get("timestamp_url"),
            "source_name": row.get("channel_name"), "author": row.get("channel_name"),
            "attributable": bool(row.get("channel_name")),
            "impact_summary": _text(row.get("korea_transmission_ko")) or claim[:240],
            "resolution_condition": "공식 자료와 실제 시장 반응으로 사후 확인",
            "metadata": {"video_id": video_id, "classification": row.get("classification")},
        })
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_daily_news_events(root: Path) -> list[dict[str, Any]]:
    paths = sorted((root / "data/normalized").glob("????-??-??-events.json"), reverse=True)
    if not paths:
        return []
    try:
        payload = json.loads(paths[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    unique = {(str(x.get("source_type")), str(x.get("source_id"))): x for x in rows}
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in unique.values()), encoding="utf-8")


def extract_all(root: Path) -> dict[str, int]:
    telegram_rows = read_jsonl(root / "data/private/telegram/normalized/messages.jsonl")
    telegram = telegram_candidates(telegram_rows)
    youtube_rows = read_jsonl(root / "data/normalized/youtube_insight/cards.jsonl")
    if not youtube_rows:
        youtube_rows = read_jsonl(root / "data/normalized/youtube_insight/claims.jsonl")
    youtube = youtube_candidates(youtube_rows)
    news = read_jsonl(root / "data/normalized/rumor/news_events.jsonl")
    daily_news = latest_daily_news_events(root)
    schedule_documents = []
    for row in telegram_rows:
        schedule_documents.append({**row, "source_id": row.get("source_id") or f"{row.get('channel','telegram')}:{row.get('message_id','')}", "source_type": row.get("source_type") or "TELEGRAM"})
    for row in youtube_rows:
        schedule_documents.append({
            **row,
            "source_id": row.get("claim_id") or row.get("card_id") or row.get("video_id"),
            "source_type": "YOUTUBE_EXPERT" if row.get("channel_name") else "YOUTUBE",
            "source_name": row.get("channel_name"),
            "text": row.get("text") or row.get("transcript") or row.get("claim_summary_ko") or row.get("claim") or row.get("summary"),
            "url": row.get("video_url") or row.get("timestamp_url"),
        })
    for row in [*news, *daily_news]:
        schedule_documents.append({
            **row,
            "source_id": row.get("source_id") or row.get("event_id") or row.get("id") or row.get("url"),
            "source_type": row.get("source_type") or "NEWS",
            "text": row.get("text") or row.get("claim") or row.get("evidence_summary") or row.get("headline") or row.get("title"),
        })
    schedule = []
    for document in schedule_documents:
        if document.get("source_id"):
            schedule.extend(extract_schedule_candidates(document))
    output = root / "data/normalized/rumor/events.jsonl"
    write_jsonl(output, [*telegram, *youtube, *news, *schedule])
    total = len(telegram) + len(youtube) + len(news) + len(daily_news) + len(schedule)
    return {"telegram": len(telegram), "youtube": len(youtube), "news": len(news), "daily_news": len(daily_news), "schedule": len(schedule), "total": total}
