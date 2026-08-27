from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .captions import CaptionCue
from .time_model import resolve_actionable_time


_NUMBER_RE = re.compile(r"(?<![\w.])([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)(?![\w.])")


@dataclass(frozen=True)
class ClaimSpan:
    start_ms: int
    end_ms: int
    text: str


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _stable_claim_id(channel_id: str, video_id: str, span: ClaimSpan) -> str:
    payload = "\x1f".join((channel_id, video_id, str(span.start_ms), str(span.end_ms), _normalized(span.text)))
    return "YTC-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20].upper()


def _match_any(text: str, values: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(value.lower() in lowered for value in values)


def _categories(text: str, terms: dict[str, Any]) -> list[str]:
    found = [name for name, words in terms.get("claim_categories", {}).items() if _match_any(text, words)]
    return found or ["OTHER"]


def _direction(text: str, terms: dict[str, Any]) -> str:
    bullish = sum(text.lower().count(word.lower()) for word in terms.get("directions", {}).get("BULLISH", []))
    bearish = sum(text.lower().count(word.lower()) for word in terms.get("directions", {}).get("BEARISH", []))
    if bullish > bearish:
        return "LONG"
    if bearish > bullish:
        return "SHORT"
    return "NEUTRAL"


def _timeframe(text: str, terms: dict[str, Any]) -> str | None:
    for name, words in terms.get("timeframes", {}).items():
        if _match_any(text, words):
            return name
    return None


def _assets(text: str, terms: dict[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    lowered = text.lower()
    for asset in terms.get("assets", []):
        aliases = [str(asset.get("name", "")), str(asset.get("symbol", "")), *asset.get("aliases", [])]
        if any(alias and alias.lower() in lowered for alias in aliases):
            found.append({"symbol": asset["symbol"], "name": asset["name"]})
    return found


def _numbers(text: str) -> list[dict[str, Any]]:
    result = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(1)
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        result.append({"raw": raw, "value": value, "start": match.start(1), "end": match.end(1)})
    return result


def find_chart_spans(cues: list[CaptionCue], terms: dict[str, Any], *, merge_gap_ms: int = 12_000) -> list[ClaimSpan]:
    keywords = [word for words in terms.get("claim_categories", {}).values() for word in words]
    matched = [cue for cue in cues if _match_any(cue.text, keywords)]
    spans: list[ClaimSpan] = []
    for cue in matched:
        if spans and cue.start_ms - spans[-1].end_ms <= merge_gap_ms:
            prior = spans[-1]
            spans[-1] = ClaimSpan(prior.start_ms, max(prior.end_ms, cue.end_ms), f"{prior.text} {cue.text}".strip())
        else:
            spans.append(ClaimSpan(cue.start_ms, cue.end_ms, cue.text))
    return spans


def extract_chart_claims(
    cues: list[CaptionCue],
    *,
    video: dict[str, Any],
    terms: dict[str, Any],
    merge_gap_ms: int = 12_000,
) -> list[dict[str, Any]]:
    channel_id = str(video.get("channel_id") or video.get("channel") or "UNKNOWN")
    video_id = str(video.get("id") or video.get("video_id") or "UNKNOWN")
    is_live = bool(video.get("is_live") or video.get("was_live") or video.get("live_status") in {"is_live", "was_live"})
    published_at = video.get("release_timestamp_iso") or video.get("published_at")
    live_start = video.get("livestream_start_at")
    claims = []
    for span in find_chart_spans(cues, terms, merge_gap_ms=merge_gap_ms):
        availability = resolve_actionable_time(
            video_published_at=published_at,
            livestream_start_at=live_start,
            spoken_offset_ms=span.end_ms,
            content_as_of=None,
            is_live=is_live,
        )
        categories = _categories(span.text, terms)
        numbers = _numbers(span.text)
        assets = _assets(span.text, terms)
        claims.append({
            "schema_version": "1.0",
            "source_claim_id": _stable_claim_id(channel_id, video_id, span),
            "source_type": "YOUTUBE_CHART_COMMENTARY",
            "channel_id": channel_id,
            "channel_name": video.get("channel") or video.get("uploader"),
            "video_id": video_id,
            "video_title": video.get("title"),
            "video_url": video.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
            "timestamp_url": f"https://www.youtube.com/watch?v={video_id}&t={max(0, span.start_ms // 1000)}s",
            "speech_start_ms": span.start_ms,
            "speech_end_ms": span.end_ms,
            "speech_excerpt": span.text,
            "claim_categories": categories,
            "direction": _direction(span.text, terms),
            "timeframe_spoken": _timeframe(span.text, terms),
            "asset_candidates": assets,
            "numeric_mentions": numbers,
            "target_price": None,
            "invalidation_price": None,
            "human_review_status": "PENDING",
            **availability.to_dict(),
        })
    return claims

