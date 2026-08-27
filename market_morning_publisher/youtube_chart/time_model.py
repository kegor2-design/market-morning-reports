from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class AvailabilityDecision:
    video_published_at: str | None
    livestream_start_at: str | None
    spoken_offset_ms: int
    content_as_of: str | None
    publicly_actionable_at: str | None
    availability_precision: str
    availability_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_actionable_time(
    *,
    video_published_at: str | None,
    livestream_start_at: str | None,
    spoken_offset_ms: int,
    content_as_of: str | None = None,
    is_live: bool = False,
) -> AvailabilityDecision:
    """Resolve when a viewer could first have acted on a spoken claim.

    A live claim becomes available at speech end.  A recorded upload becomes
    available at its exact public release time.  A date-only upload is left
    unknown; fabricating midnight would introduce look-ahead bias.
    """
    if spoken_offset_ms < 0:
        raise ValueError("spoken_offset_ms cannot be negative")
    published = parse_datetime(video_published_at)
    live_start = parse_datetime(livestream_start_at)
    actionable: datetime | None = None
    precision = "UNKNOWN"
    reason = "EXACT_PUBLICATION_TIME_MISSING"
    if is_live:
        if live_start:
            actionable = live_start + timedelta(milliseconds=spoken_offset_ms)
            precision = "MILLISECOND"
            reason = "LIVE_STREAM_START_PLUS_SPEECH_END"
        else:
            reason = "LIVE_STREAM_START_MISSING"
    elif published:
        actionable = published
        precision = "SECOND"
        reason = "RECORDED_VIDEO_PUBLICATION_TIME"
    return AvailabilityDecision(
        video_published_at=published.isoformat() if published else video_published_at,
        livestream_start_at=live_start.isoformat() if live_start else livestream_start_at,
        spoken_offset_ms=spoken_offset_ms,
        content_as_of=content_as_of,
        publicly_actionable_at=actionable.isoformat() if actionable else None,
        availability_precision=precision,
        availability_reason=reason,
    )


def first_bar_after(bars: list[dict[str, Any]], actionable_at: str | None) -> int | None:
    actionable = parse_datetime(actionable_at)
    if not actionable:
        return None
    for index, bar in enumerate(bars):
        started = parse_datetime(str(bar.get("timestamp") or ""))
        if started and started > actionable:
            return index
    return None

