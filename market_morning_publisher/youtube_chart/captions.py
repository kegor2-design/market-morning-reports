from __future__ import annotations

import html
import re
from dataclasses import dataclass


_TIMING_RE = re.compile(
    r"^(?P<start>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s+-->\s+"
    r"(?P<end>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})(?:\s+.*)?$"
)
_INLINE_TIME_RE = re.compile(r"<\d{1,2}:\d{2}:\d{2}[.,]\d{3}>")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class CaptionCue:
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("caption cue must have a positive duration")
        if not self.text.strip():
            raise ValueError("caption cue text cannot be empty")


def timestamp_to_ms(value: str) -> int:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"invalid WebVTT timestamp: {value}")
    second, millis = seconds.split(".", 1)
    if not (str(hours).isdigit() and minutes.isdigit() and second.isdigit() and millis.isdigit()):
        raise ValueError(f"invalid WebVTT timestamp: {value}")
    return ((int(hours) * 60 + int(minutes)) * 60 + int(second)) * 1000 + int(millis[:3].ljust(3, "0"))


def clean_caption_text(lines: list[str]) -> str:
    value = " ".join(line.strip() for line in lines if line.strip())
    value = _INLINE_TIME_RE.sub("", value)
    value = _TAG_RE.sub("", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _remove_rolling_prefix(previous: str, current: str) -> str:
    """Remove only a full prior cue repeated by YouTube rolling captions."""
    if not previous or previous == current:
        return "" if previous == current else current
    if current.startswith(previous):
        return current[len(previous):].strip(" -")
    return current


def parse_vtt(raw: str, *, dedupe_rolling: bool = True) -> list[CaptionCue]:
    """Parse WebVTT without requiring a subtitle dependency.

    STYLE/NOTE/REGION blocks, cue identifiers, HTML voice tags, and YouTube's
    inline word timestamps are ignored.  Consecutive rolling captions are
    reduced only when the entire previous cue is repeated as a prefix.
    """
    lines = raw.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[CaptionCue] = []
    index = 0
    prior_visible = ""
    while index < len(lines):
        line = lines[index].strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:")):
            index += 1
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            index += 1
            while index < len(lines) and lines[index].strip():
                index += 1
            continue
        match = _TIMING_RE.match(line)
        if not match and index + 1 < len(lines):
            match = _TIMING_RE.match(lines[index + 1].strip())
            if match:
                index += 1
        if not match:
            index += 1
            continue
        index += 1
        payload: list[str] = []
        while index < len(lines) and lines[index].strip():
            payload.append(lines[index])
            index += 1
        visible = clean_caption_text(payload)
        text = _remove_rolling_prefix(prior_visible, visible) if dedupe_rolling else visible
        if visible:
            prior_visible = visible
        if text:
            cues.append(CaptionCue(timestamp_to_ms(match.group("start")), timestamp_to_ms(match.group("end")), text))
    return cues

