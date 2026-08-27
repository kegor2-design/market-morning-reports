from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

from market_morning_publisher.youtube_chart.captions import CaptionCue, parse_vtt
from market_morning_publisher.youtube_chart.media import (
    collect_metadata_and_captions,
    list_channel_videos,
    safe_component,
)
from market_morning_publisher.youtube_chart.pipeline import normalize_video_metadata, select_caption_file

from .codex import YoutubeInsightCodexError, run_chunk_analysis
from .render import blogger_publish_digest, render_digest_markdown
from .transcript_fallback import fallback_enabled, transcribe_with_faster_whisper
from market_morning_publisher.insight_engine.reasoning import build_engine_update_candidates
from market_morning_publisher.nightly_youtube.synthesis import build_nightly_synthesis, render_nightly_markdown
from market_morning_publisher.chart_insight.research import build_nightly_chart_research, render_chart_research_markdown


KST = ZoneInfo("Asia/Seoul")
IMPORTANCE_SCORE = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
CONFIDENCE_SCORE = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
CLASS_SCORE = {"RUMOR": 0, "OPINION": 1, "ACTION_RULE": 2, "FACT_CLAIM": 3, "FORECAST": 3, "HYPOTHESIS": 4}
VALID_VERIFICATION = {"SUPPORTED", "PARTIAL", "UNVERIFIED", "CONTRADICTED", "UNKNOWN"}


@dataclass(frozen=True)
class YoutubeInsightOptions:
    target_date: date
    lookback_hours: int = 48
    inventory_limit: int = 12
    channel_ids: tuple[str, ...] = ()
    max_cards: int = 6
    collect: bool = True
    analyze: bool = True
    publish: bool = False
    dry_run: bool = False
    yt_dlp: str = "yt-dlp"
    cookie_file: Path | None = None


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def upsert_jsonl(path: Path, rows: Sequence[dict[str, Any]], *, key: str) -> None:
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if item.get(key):
                    existing[str(item[key])] = item
    for row in rows:
        if row.get(key):
            existing[str(row[key])] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        for item_key in sorted(existing):
            handle.write(json.dumps(existing[item_key], ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _iso_epoch(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), timezone.utc) if value is not None else None
    except (TypeError, ValueError, OSError):
        return None


def published_at(metadata: dict[str, Any]) -> datetime | None:
    for key in ("published_at", "release_timestamp_iso", "livestream_start_at"):
        value = metadata.get(key)
        if value:
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                pass
    return _iso_epoch(metadata.get("timestamp") or metadata.get("release_timestamp"))


def _cue_line(cue: CaptionCue) -> str:
    return f"[{cue.start_ms}-{cue.end_ms}] {cue.text}"


def chunk_cues(cues: Sequence[CaptionCue], *, max_chars: int = 36000) -> list[list[CaptionCue]]:
    if max_chars < 1000:
        raise ValueError("max_chars must be >= 1000")
    chunks: list[list[CaptionCue]] = []
    current: list[CaptionCue] = []
    size = 0
    for cue in cues:
        line_size = len(_cue_line(cue)) + 1
        if current and size + line_size > max_chars:
            chunks.append(current)
            current = []
            size = 0
        current.append(cue)
        size += line_size
    if current:
        chunks.append(current)
    return chunks


def _stable_claim_id(video_id: str, claim: dict[str, Any]) -> str:
    seed = "|".join([
        video_id,
        str(claim.get("speech_start_ms")),
        str(claim.get("speech_end_ms")),
        str(claim.get("classification")),
        str(claim.get("claim_summary_ko")),
    ])
    return "YTI-" + hashlib.sha256(seed.encode()).hexdigest()[:20].upper()


def _stable_card_id(claim_id: str) -> str:
    return "YVC-" + hashlib.sha256(claim_id.encode()).hexdigest()[:20].upper()


def _latest_normalized_events(root: Path, target_date: date) -> list[dict[str, Any]]:
    preferred = root / "data/normalized" / f"{target_date.isoformat()}-events.json"
    if preferred.exists():
        return load_json(preferred, []) or []
    candidates = sorted((root / "data/normalized").glob("????-??-??-events.json"), reverse=True) if (root / "data/normalized").exists() else []
    return load_json(candidates[0], []) if candidates else []


def _load_chart_evidence(root: Path) -> dict[str, list[dict[str, Any]]]:
    by_video: dict[str, list[dict[str, Any]]] = {}
    for relative in (
        "data/normalized/youtube_chart/claim_assessments.jsonl",
        "data/normalized/youtube_chart/validated_outcomes.jsonl",
        "data/normalized/youtube_chart/claims.jsonl",
        "data/normalized/chart_insight/historical_validations.jsonl",
    ):
        path = root / relative
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            video_id = row.get("video_id")
            if video_id:
                by_video.setdefault(str(video_id), []).append(row)
    return by_video


def _chart_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"available": False, "status": "NOT_AVAILABLE", "summary_ko": "차트 검증 결과 없음"}
    confirmed = [row for row in rows if str(row.get("review_status") or row.get("human_review_status") or "").upper() == "CONFIRMED"]
    evaluated = [row for row in rows if str(row.get("status") or "").upper() not in {"", "NOT_EVALUATED", "DATA_MISSING"}]
    status = "CONFIRMED" if confirmed and evaluated else "PARTIAL" if evaluated or confirmed else "PENDING"
    return {
        "available": True,
        "status": status,
        "summary_ko": f"관련 차트 레코드 {len(rows)}개, 사람 확인 {len(confirmed)}개, 평가 가능 결과 {len(evaluated)}개",
        "records": rows[:12],
    }


def _event_context(events: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    rows = []
    for event in events[:limit]:
        rows.append({
            "event_id": event.get("event_id"),
            "headline": event.get("headline"),
            "evidence_summary": event.get("evidence_summary"),
            "countries": event.get("countries") or [],
            "topics": event.get("topics") or [],
            "published_at": event.get("published_at"),
        })
    return rows


def _verification_status(claim: dict[str, Any]) -> str:
    explicit = str(claim.get("verification_status") or "").upper()
    if explicit in VALID_VERIFICATION:
        status = explicit
    else:
        support = bool(claim.get("source_event_ids")) or bool(claim.get("supported_by_state"))
        contradiction = bool(claim.get("counterevidence_ko"))
        status = "PARTIAL" if support else "UNKNOWN"
        if contradiction and not support:
            status = "CONTRADICTED"
    if claim.get("classification") == "RUMOR" and status != "CONTRADICTED":
        return "UNVERIFIED"
    return status


def _publish_gate(claim: dict[str, Any], channel: dict[str, Any], policy: dict[str, Any]) -> tuple[bool, str]:
    if channel.get("research_only"):
        return False, "RESEARCH_ONLY_SOURCE"
    if IMPORTANCE_SCORE.get(str(claim.get("importance")), 0) < IMPORTANCE_SCORE.get(str(policy.get("minimum_importance", "HIGH")), 3):
        return False, "IMPORTANCE_BELOW_THRESHOLD"
    if claim.get("classification") == "RUMOR":
        if not policy.get("allow_rumor_auto_publish", False):
            return False, "RUMOR_AUTO_PUBLISH_DISABLED"
        if _verification_status(claim) != "SUPPORTED":
            return False, "RUMOR_NOT_INDEPENDENTLY_SUPPORTED"
    if claim.get("classification") == "FACT_CLAIM" and not claim.get("source_event_ids") and not claim.get("supported_by_state"):
        return False, "FACT_CLAIM_LACKS_INDEPENDENT_SUPPORT"
    if claim.get("classification") in {"OPINION", "ACTION_RULE"} and str(channel.get("source_weight")) not in {"HIGH", "HIGH_PROVISIONAL"}:
        return False, "LOW_WEIGHT_OPINION"
    if claim.get("chart_analysis_requested") and policy.get("require_chart_when_central", True):
        chart = claim.get("chart_evidence") or {}
        if chart.get("status") not in {"CONFIRMED", "PARTIAL"}:
            return False, "CHART_EVIDENCE_PENDING"
    return True, "PASS"


def _claim_to_card(claim: dict[str, Any], video: dict[str, Any], channel: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    publish_eligible, block_reason = _publish_gate(claim, channel, policy)
    card = {
        "schema_version": "1.0",
        "card_id": _stable_card_id(claim["claim_id"]),
        "claim_id": claim["claim_id"],
        "channel_id": channel["id"],
        "channel_name": channel["name"],
        "source_weight": channel.get("source_weight", "NORMAL"),
        "video_id": video["id"],
        "video_title": video.get("title"),
        "video_url": video.get("webpage_url") or f"https://www.youtube.com/watch?v={video['id']}",
        "published_at": video.get("published_at") or video.get("livestream_start_at"),
        "classification": claim.get("classification"),
        "importance": claim.get("importance"),
        "confidence": claim.get("confidence"),
        "title_ko": claim.get("card_title_ko") or claim.get("claim_summary_ko"),
        "source_view_ko": claim.get("claim_summary_ko"),
        "verification_status": _verification_status(claim),
        "verification_summary_ko": claim.get("verification_summary_ko") or "독립 검증 근거 부족",
        "our_interpretation_ko": claim.get("our_interpretation_ko") or "추가 검증 필요",
        "causal_chain": claim.get("causal_chain") or [],
        "data_to_watch": claim.get("data_needed") or [],
        "events_to_watch": claim.get("events_to_watch") or [],
        "korea_transmission_ko": claim.get("korea_transmission_ko") or "확인 불가",
        "invalidation_conditions": claim.get("invalidation_conditions") or [],
        "metric_ids": claim.get("metric_ids") or [],
        "playbook_ids": claim.get("playbook_ids") or [],
        "calendar_event_ids": claim.get("calendar_event_ids") or [],
        "source_event_ids": claim.get("source_event_ids") or [],
        "chart_analysis_requested": bool(claim.get("chart_analysis_requested")),
        "chart_evidence": claim.get("chart_evidence") or {"available": False, "status": "NOT_AVAILABLE"},
        "publish_eligible": publish_eligible,
        "publish_block_reason": block_reason,
        "speech_start_ms": claim.get("speech_start_ms"),
        "speech_end_ms": claim.get("speech_end_ms"),
    }
    return card


def rank_cards(cards: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    def score(card: dict[str, Any]) -> tuple[int, int, int, str]:
        return (
            IMPORTANCE_SCORE.get(str(card.get("importance")), 0),
            CLASS_SCORE.get(str(card.get("classification")), 0),
            CONFIDENCE_SCORE.get(str(card.get("confidence")), 0),
            str(card.get("card_id")),
        )
    eligible = [card for card in cards if card.get("publish_eligible")]
    return sorted(eligible, key=score, reverse=True)[:max(0, limit)]




def _verification_due_at(published: str | None, days: int = 0, minutes: int = 0) -> str | None:
    if not published:
        return None
    try:
        base = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
    except ValueError:
        return None
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base.astimezone(timezone.utc) + timedelta(days=days, minutes=minutes)).isoformat()


def _metric_snapshot(us_state: dict[str, Any], metric_ids: Sequence[str]) -> dict[str, Any]:
    metrics = us_state.get("metrics") or {}
    return {
        metric_id: {
            "value": (metrics.get(metric_id) or {}).get("value"),
            "state": (metrics.get(metric_id) or {}).get("state", "UNKNOWN"),
            "as_of": (metrics.get(metric_id) or {}).get("as_of"),
        }
        for metric_id in metric_ids
    }


def build_verification_rows(claims: Sequence[dict[str, Any]], us_state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for claim in claims:
        published = claim.get("video_published_at")
        if not published:
            continue
        rows.append({
            "schema_version": "1.0",
            "claim_id": claim["claim_id"],
            "video_id": claim.get("video_id"),
            "channel_id": claim.get("channel_id"),
            "classification": claim.get("classification"),
            "published_at": published,
            "metric_ids": claim.get("metric_ids") or [],
            "baseline_metrics": _metric_snapshot(us_state, claim.get("metric_ids") or []),
            "invalidation_conditions": claim.get("invalidation_conditions") or [],
            "windows": {
                "T30M": {"due_at": _verification_due_at(published, minutes=30), "status": "PENDING"},
                "T1D": {"due_at": _verification_due_at(published, days=1), "status": "PENDING"},
                "T5D": {"due_at": _verification_due_at(published, days=5), "status": "PENDING"},
                "T20D": {"due_at": _verification_due_at(published, days=20), "status": "PENDING"},
            },
            "review_status": "PENDING",
        })
    return rows


def refresh_verification_queue(path: Path, new_rows: Sequence[dict[str, Any]], us_state: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("claim_id"):
                    existing[str(row["claim_id"])] = row
    for row in new_rows:
        existing.setdefault(str(row["claim_id"]), row)
    for row in existing.values():
        changed = False
        for label, window in (row.get("windows") or {}).items():
            if window.get("status") != "PENDING" or not window.get("due_at"):
                continue
            try:
                due = datetime.fromisoformat(str(window["due_at"]).replace("Z", "+00:00"))
            except ValueError:
                continue
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if now >= due:
                window["status"] = "DUE_FOR_REVIEW"
                window["observed_at"] = now.isoformat()
                window["observed_metrics"] = _metric_snapshot(us_state, row.get("metric_ids") or [])
                changed = True
        if changed:
            row["review_status"] = "DUE_FOR_REVIEW"
    upsert_jsonl(path, list(existing.values()), key="claim_id")
    return list(existing.values())


def _entry_datetime(entry: dict[str, Any]) -> datetime | None:
    when = _iso_epoch(entry.get("timestamp") or entry.get("release_timestamp"))
    if when is not None:
        return when
    upload = str(entry.get("upload_date") or "")
    try:
        return datetime.strptime(upload, "%Y%m%d").replace(tzinfo=KST).astimezone(timezone.utc)
    except ValueError:
        return None


def _collection_endpoints(channel: dict[str, Any]) -> list[dict[str, str]]:
    configured = channel.get("collection_urls") or []
    endpoints = []
    for row in configured:
        if isinstance(row, str):
            endpoints.append({"type": "unknown", "url": row})
        elif isinstance(row, dict) and row.get("url"):
            endpoints.append({"type": str(row.get("type") or "unknown"), "url": str(row["url"])})
    if not endpoints and channel.get("collection_url"):
        endpoints.append({"type": "primary", "url": str(channel["collection_url"])})
    return endpoints


def _checkpoint_path(root: Path, channel_id: str) -> Path:
    return root / "data/state/youtube_insight/checkpoints" / f"{safe_component(channel_id)}.json"


def _load_checkpoint(root: Path, channel_id: str) -> dict[str, Any]:
    return load_json(_checkpoint_path(root, channel_id), {}) or {}


def _checkpoint_processed(checkpoint: dict[str, Any]) -> set[str]:
    return {str(value) for value in checkpoint.get("processed_video_ids") or [] if value}


def _update_checkpoint(root: Path, channel: dict[str, Any], videos: Sequence[dict[str, Any]], *, target_date: date) -> dict[str, Any]:
    path = _checkpoint_path(root, str(channel["id"]))
    checkpoint = _load_checkpoint(root, str(channel["id"]))
    processed = list(checkpoint.get("processed_video_ids") or [])
    seen = {str(value) for value in processed}
    latest: datetime | None = None
    for video in videos:
        video_id = str(video.get("id") or "")
        if video_id and video_id not in seen:
            processed.append(video_id)
            seen.add(video_id)
        when = published_at(video)
        if when and (latest is None or when > latest):
            latest = when
    maximum = max(50, int(channel.get("max_checkpoint_ids", 500)))
    if len(processed) > maximum:
        processed = processed[-maximum:]
    checkpoint.update({
        "schema_version": "1.0",
        "channel_id": channel["id"],
        "processed_video_ids": processed,
        "last_successful_target_date": target_date.isoformat(),
        "last_success_at": datetime.now(timezone.utc).isoformat(),
    })
    if latest:
        checkpoint["last_published_at"] = latest.isoformat()
    atomic_json(path, checkpoint)
    return checkpoint


class YoutubeInsightPipeline:
    def __init__(self, root: Path, options: YoutubeInsightOptions, *, analyzer: Callable[..., tuple[dict[str, Any], dict[str, Any]]] = run_chunk_analysis) -> None:
        self.root = root.resolve()
        self.options = options
        self.analyzer = analyzer
        config = load_json(self.root / "config/youtube_insight_channels.json", {}) or {}
        self.policy = config.get("policy") or {}
        requested = set(options.channel_ids)
        self.channel_registry = list(config.get("channels", []))
        self.channels = [
            channel for channel in self.channel_registry
            if channel.get("enabled") and (channel.get("id") in requested if requested else True)
        ]
        unknown = requested - {str(channel.get("id")) for channel in self.channel_registry}
        if unknown:
            raise ValueError("unknown YouTube insight channel IDs: " + ", ".join(sorted(unknown)))
        self.metrics = load_json(self.root / "config/us_state_metrics.json", {}) or {}
        self.playbooks = load_json(self.root / "config/us_issue_playbooks.json", {}) or {}
        self.background = load_json(self.root / "config/us_background_knowledge.json", {}) or {}
        self.calendar = load_json(self.root / "config/us_event_calendar.json", {}) or {}
        self.chart_by_video = _load_chart_evidence(self.root)
        self.engine_metric_registry = load_json(self.root / "config/insight_metric_registry.json", {}) or {}
        self.engine_playbooks = load_json(self.root / "config/insight_reasoning_playbooks.json", {}) or {}
        self.engine_background = load_json(self.root / "config/insight_background_knowledge.json", {}) or {}
        self.source_lenses = load_json(self.root / "config/source_lenses.json", {}) or {}
        self.chart_primitive_registry = load_json(self.root / "config/chart_insight_primitives.json", {}) or {}
        self.chart_expert_lenses = load_json(self.root / "config/chart_insight_expert_lenses.json", {}) or {}
        self.chart_research_policy = load_json(self.root / "config/nightly_chart_research.json", {}) or {}

    def _entry_maybe_in_window(self, entry: dict[str, Any], *, hours: int | None = None) -> bool:
        when = _entry_datetime(entry)
        if when is None:
            return True
        horizon = self.options.lookback_hours if hours is None else hours
        cutoff = datetime.combine(self.options.target_date, datetime.min.time(), KST).astimezone(timezone.utc) - timedelta(hours=max(0, horizon - 24))
        day_end = datetime.combine(self.options.target_date + timedelta(days=1), datetime.min.time(), KST).astimezone(timezone.utc)
        return cutoff <= when < day_end

    def _discover(self, channel: dict[str, Any]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        endpoint_errors: list[Exception] = []
        endpoints = _collection_endpoints(channel)
        for endpoint in endpoints:
            try:
                entries = list_channel_videos(
                    endpoint["url"],
                    limit=self.options.inventory_limit,
                    yt_dlp=self.options.yt_dlp,
                    cookie_file=self.options.cookie_file,
                )
            except Exception as exc:
                endpoint_errors.append(exc)
                continue
            for entry in entries:
                video_id = str(entry.get("id") or "")
                if not video_id:
                    continue
                value = dict(entry)
                value["content_type"] = endpoint["type"]
                # A video can appear in both videos/streams. Keep the first record with the richer timestamp.
                current = merged.get(video_id)
                if current is None or (_entry_datetime(current) is None and _entry_datetime(value) is not None):
                    merged[video_id] = value
        if not merged and endpoint_errors and len(endpoint_errors) == len(endpoints):
            raise endpoint_errors[0]
        checkpoint = _load_checkpoint(self.root, str(channel["id"]))
        processed = _checkpoint_processed(checkpoint)
        recovery = int(self.policy.get("recovery_lookback_hours", 168))
        if checkpoint.get("last_success_at"):
            try:
                last_success = datetime.fromisoformat(str(checkpoint["last_success_at"]).replace("Z", "+00:00"))
                elapsed = int((datetime.combine(self.options.target_date + timedelta(days=1), datetime.min.time(), KST).astimezone(timezone.utc) - last_success.astimezone(timezone.utc)).total_seconds() / 3600)
                recovery = max(recovery, elapsed + 24)
            except (ValueError, TypeError):
                pass
        recovery = min(recovery, int(self.policy.get("max_recovery_lookback_hours", 720)))
        bootstrap = int(self.policy.get("bootstrap_lookback_hours", self.options.lookback_hours))
        candidates = []
        for entry in merged.values():
            if str(entry.get("id")) in processed:
                continue
            window = recovery if checkpoint else bootstrap
            if self._entry_maybe_in_window(entry, hours=window):
                candidates.append(entry)
        candidates.sort(key=lambda row: _entry_datetime(row) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        maximum = max(1, int(channel.get("max_videos_per_run", 3)))
        return candidates[:maximum]

    def _collect_video(self, channel: dict[str, Any], entry: dict[str, Any]) -> tuple[dict[str, Any], Path] | None:
        video_id = safe_component(str(entry["id"]))
        raw_dir = self.root / "data/private/youtube_insight/raw" / safe_component(channel["id"]) / video_id
        metadata_path = raw_dir / "metadata.normalized.json"
        normalized = load_json(metadata_path, None)
        if normalized is None:
            url = entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
            metadata = collect_metadata_and_captions(
                url,
                raw_dir,
                subtitle_languages=channel.get("subtitle_languages") or ["ko-orig", "ko", "en-orig", "en"],
                yt_dlp=self.options.yt_dlp,
                cookie_file=self.options.cookie_file,
            )
            normalized = normalize_video_metadata(metadata, channel)
            normalized["content_type"] = entry.get("content_type") or "unknown"
            atomic_json(metadata_path, normalized)
        when = published_at(normalized)
        if when is None:
            upload = str(normalized.get("upload_date") or "")
            try:
                when = datetime.strptime(upload, "%Y%m%d").replace(tzinfo=KST).astimezone(timezone.utc)
            except ValueError:
                return None
        checkpoint = _load_checkpoint(self.root, str(channel["id"]))
        horizon = int(self.policy.get("recovery_lookback_hours", 168)) if checkpoint else int(self.policy.get("bootstrap_lookback_hours", self.options.lookback_hours))
        cutoff = datetime.combine(self.options.target_date, datetime.min.time(), KST).astimezone(timezone.utc) - timedelta(hours=max(0, horizon - 24))
        day_end = datetime.combine(self.options.target_date + timedelta(days=1), datetime.min.time(), KST).astimezone(timezone.utc)
        if not (cutoff <= when < day_end):
            return None
        caption = select_caption_file(raw_dir, video_id, channel.get("subtitle_languages") or [])
        asr_enabled = fallback_enabled() or bool(self.policy.get("asr_fallback_default"))
        if not caption and channel.get("asr_fallback_allowed") and asr_enabled:
            url = entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
            caption = transcribe_with_faster_whisper(
                url, raw_dir, language=channel.get("language"), yt_dlp=self.options.yt_dlp,
                cookie_file=self.options.cookie_file, force=bool(self.policy.get("asr_fallback_default")),
                model_name=str(self.policy.get("asr_model_default") or "tiny"),
            )
            normalized["transcript_source"] = "FASTER_WHISPER_FALLBACK"
            atomic_json(metadata_path, normalized)
        if not caption:
            incomplete = {
                "channel_id": channel["id"], "video_id": video_id, "status": "COLLECTION_INCOMPLETE",
                "reason": "CAPTION_MISSING_ASR_DISABLED_OR_UNAVAILABLE", "asr_enabled": asr_enabled,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            atomic_json(raw_dir / "collection_incomplete.json", incomplete)
            return None
        return normalized, caption

    def _context(self, video: dict[str, Any], transcript_chunk: list[CaptionCue], chunk_index: int, chunk_count: int) -> dict[str, Any]:
        events = _latest_normalized_events(self.root, self.options.target_date)
        us_state = load_json(self.root / "data/state/us_state/latest.json", {}) or {}
        metric_rows = self.metrics.get("metrics") or self.metrics.get("observations") or []
        metric_ids = [str(row.get("id") or row.get("metric_id")) for row in metric_rows if row.get("id") or row.get("metric_id")]
        playbook_rows = self.playbooks.get("playbooks") or []
        playbook_ids = [str(row.get("id")) for row in playbook_rows if row.get("id")]
        calendar_rows = self.calendar.get("events") or []
        calendar_ids = [str(row.get("event_id") or row.get("id")) for row in calendar_rows if row.get("event_id") or row.get("id")]
        chart = _chart_summary(self.chart_by_video.get(str(video["id"]), []))
        chart_primitive_rows = self.chart_primitive_registry.get("primitives") or []
        chart_primitive_ids = [str(row.get("id")) for row in chart_primitive_rows if row.get("id")]
        return {
            "input_contract": "MMP_YOUTUBE_INSIGHT_CHUNK_V1",
            "video": video,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "transcript": [_cue_line(cue) for cue in transcript_chunk],
            "source_policy": {
                "source_weight": video.get("source_weight"),
                "source_role": video.get("source_role"),
                "weight_rule": "High weight prioritizes verification; it never converts a claim into fact.",
            },
            "verified_news": _event_context(events),
            "allowed_source_event_ids": [str(row.get("event_id")) for row in events if row.get("event_id")],
            "us_state": us_state,
            "metric_registry": metric_rows,
            "allowed_metric_ids": metric_ids,
            "issue_playbooks": playbook_rows,
            "allowed_playbook_ids": playbook_ids,
            "background_knowledge": self.background.get("modules") or [],
            "event_calendar": calendar_rows,
            "allowed_calendar_event_ids": calendar_ids,
            "chart_evidence": chart,
            "chart_research": {
                "primitive_registry": chart_primitive_rows,
                "expert_lenses": self.chart_expert_lenses.get("lenses") or [],
                "lifecycle_rule": "DISCOVERED -> RESEARCH_CANDIDATE -> HISTORICALLY_SUPPORTED -> OUT_OF_SAMPLE_SUPPORTED -> OUR_CHART_PRINCIPLE. Content cannot skip stages.",
                "numeric_rule": "Do not invent thresholds not explicitly stated by the speaker; later source-example distributions may estimate research candidates.",
            },
            "allowed_chart_primitive_ids": chart_primitive_ids,
            "reasoning_engine": {
                "standard_steps": self.engine_playbooks.get("standard_reasoning_steps") or [],
                "metric_decisions": [
                    {
                        "metric_id": row.get("metric_id"), "decision": row.get("decision"),
                        "why_collect": row.get("why_collect"), "point_in_time_required": row.get("point_in_time_required", False),
                    }
                    for row in (self.engine_metric_registry.get("metrics") or [])
                ],
                "background_knowledge": self.engine_background.get("modules") or [],
                "source_lenses": self.source_lenses.get("lenses") or [],
                "engine_update_rule": "If the speaker uses a new data series, causal link, historical analogy, policy tool, invalidation rule or reasoning question that is not represented here, place it in data_needed/playbook_ids/metric_ids so it can become a REVIEW_REQUIRED engine-update candidate. Do not auto-accept it.",
            },
            "constraints": {
                "no_web_browsing": True,
                "unknown_when_missing": True,
                "no_individual_security_recommendation": True,
                "rumor_is_never_fact_without_independent_support": True,
            },
        }

    def _analyze_video(self, channel: dict[str, Any], video: dict[str, Any], caption_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        cues = parse_vtt(caption_path.read_text(encoding="utf-8", errors="ignore"))
        chunks = chunk_cues(cues, max_chars=int(os.getenv("MMP_YOUTUBE_INSIGHT_CHUNK_CHARS", "36000")))
        claims: list[dict[str, Any]] = []
        meta: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks, 1):
            analysis_input = self._context(video, chunk, index, len(chunks))
            result, run_meta = self.analyzer(self.root, analysis_input)
            meta.append({"chunk": index, **run_meta})
            for raw_claim in result.get("claims", []):
                claim = dict(raw_claim)
                claim.setdefault("stance", "UNKNOWN")
                claim.setdefault("issue_tags", [])
                claim["claim_id"] = _stable_claim_id(str(video["id"]), claim)
                claim["channel_id"] = channel["id"]
                claim["channel_name"] = channel.get("name")
                claim["source_weight"] = channel.get("source_weight", "NORMAL")
                claim["video_id"] = video["id"]
                claim["video_title"] = video.get("title")
                claim["video_url"] = video.get("webpage_url") or f"https://www.youtube.com/watch?v={video['id']}"
                claim["video_published_at"] = video.get("published_at") or video.get("livestream_start_at")
                claim["target_date"] = self.options.target_date.isoformat()
                claim["chart_evidence"] = _chart_summary(self.chart_by_video.get(str(video["id"]), []))
                claims.append(claim)
        deduped: dict[str, dict[str, Any]] = {}
        for claim in claims:
            normalized = re.sub(r"\W+", "", str(claim.get("claim_summary_ko") or "")).casefold()
            key = normalized[:120] or claim["claim_id"]
            current = deduped.get(key)
            if current is None or IMPORTANCE_SCORE.get(str(claim.get("importance")), 0) > IMPORTANCE_SCORE.get(str(current.get("importance")), 0):
                deduped[key] = claim
        return list(deduped.values()), meta

    def run(self) -> dict[str, Any]:
        lock_path = self.root / "data/state/youtube_insight/pipeline.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("YouTube insight pipeline is already running") from exc
            errors: list[dict[str, Any]] = []
            all_claims: list[dict[str, Any]] = []
            all_cards: list[dict[str, Any]] = []
            videos_seen = 0
            videos_analyzed = 0
            codex_runs: list[dict[str, Any]] = []
            successfully_analyzed: dict[str, list[dict[str, Any]]] = {}
            for channel in self.channels:
                try:
                    entries = self._discover(channel) if self.options.collect else []
                except Exception as exc:
                    errors.append({"channel_id": channel["id"], "stage": "DISCOVERY", "error": str(exc)[:500]})
                    continue
                for entry in entries:
                    try:
                        collected = self._collect_video(channel, entry)
                    except Exception as exc:
                        errors.append({"channel_id": channel["id"], "video_id": entry.get("id"), "stage": "COLLECTION", "error": str(exc)[:500]})
                        continue
                    if not collected:
                        continue
                    video, caption = collected
                    videos_seen += 1
                    video = {**video, "source_weight": channel.get("source_weight", "NORMAL"), "source_role": channel.get("role"), "source_lens_hint": channel.get("source_lens_hint")}
                    if not self.options.analyze:
                        continue
                    try:
                        claims, run_meta = self._analyze_video(channel, video, caption)
                    except YoutubeInsightCodexError as exc:
                        errors.append({"channel_id": channel["id"], "video_id": video.get("id"), "stage": "ANALYSIS", "error": str(exc)[:500]})
                        continue
                    videos_analyzed += 1
                    codex_runs.extend({"video_id": video.get("id"), **item} for item in run_meta)
                    all_claims.extend(claims)
                    all_cards.extend(_claim_to_card(claim, video, channel, self.policy) for claim in claims)
                    successfully_analyzed.setdefault(str(channel["id"]), []).append(video)
                if successfully_analyzed.get(str(channel["id"])):
                    _update_checkpoint(self.root, channel, successfully_analyzed[str(channel["id"])], target_date=self.options.target_date)
            claims_extracted_this_run = len(all_claims)
            claims_path = self.root / "data/normalized/youtube_insight/claims.jsonl"
            upsert_jsonl(claims_path, all_claims, key="claim_id")
            # Checkpointed collection must not erase same-day analysis on a rerun. Reload the day's
            # persisted claims, refresh chart evidence, and rebuild cards deterministically.
            day_claims: list[dict[str, Any]] = []
            if claims_path.exists():
                for line in claims_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if str(row.get("target_date")) != self.options.target_date.isoformat():
                        continue
                    row["chart_evidence"] = _chart_summary(self.chart_by_video.get(str(row.get("video_id")), []))
                    day_claims.append(row)
            channel_by_id = {str(channel["id"]): channel for channel in self.channel_registry}
            all_cards = []
            for claim in day_claims:
                channel = channel_by_id.get(str(claim.get("channel_id")))
                if channel is None:
                    continue
                video = {
                    "id": claim.get("video_id"), "title": claim.get("video_title"),
                    "webpage_url": claim.get("video_url"), "published_at": claim.get("video_published_at"),
                }
                all_cards.append(_claim_to_card(claim, video, channel, self.policy))
            upsert_jsonl(self.root / "data/normalized/youtube_insight/cards.jsonl", all_cards, key="card_id")
            all_claims = day_claims
            combined_playbooks = {
                "playbooks": list(self.engine_playbooks.get("playbooks") or []) + list(self.playbooks.get("playbooks") or [])
            }
            engine_candidates = build_engine_update_candidates(all_claims, self.engine_metric_registry, combined_playbooks)
            atomic_json(
                self.root / "data/state/insight_engine/engine_update_candidates" / f"{self.options.target_date.isoformat()}.json",
                {"generated_at": datetime.now(timezone.utc).isoformat(), "source": "YOUTUBE_INSIGHT", "candidates": engine_candidates},
            )
            current_us_state = load_json(self.root / "data/state/us_state/latest.json", {}) or {}
            verification_rows = build_verification_rows(all_claims, current_us_state)
            verification_queue = refresh_verification_queue(
                self.root / "data/state/youtube_insight/verification_queue.jsonl", verification_rows, current_us_state
            )
            chart_requests = []
            seen_chart_requests = set()
            for card in all_cards:
                if not card.get("chart_analysis_requested"):
                    continue
                chart = card.get("chart_evidence") or {}
                if chart.get("status") in {"CONFIRMED", "PARTIAL"}:
                    continue
                key = (card.get("channel_id"), card.get("video_id"))
                if key in seen_chart_requests:
                    continue
                seen_chart_requests.add(key)
                chart_requests.append({
                    "channel_id": card.get("channel_id"), "video_id": card.get("video_id"),
                    "video_url": card.get("video_url"), "target_date": self.options.target_date.isoformat(),
                    "reason": "CARD_DEPENDS_ON_CHART_EVIDENCE", "status": "REQUESTED",
                })
            nightly_config = load_json(self.root / "config/nightly_youtube_intelligence.json", {}) or {}
            nightly = build_nightly_synthesis(
                self.options.target_date.isoformat(), all_claims, self.channel_registry,
                minimum_importance=str(self.policy.get("nightly_include_min_importance", "MEDIUM")),
                minimum_distinct_sources=int((nightly_config.get("consensus_policy") or {}).get("minimum_distinct_sources", 2)),
            )
            chart_research = build_nightly_chart_research(
                self.options.target_date.isoformat(), all_claims, self.channel_registry,
                self.chart_primitive_registry, self.chart_research_policy,
            )
            nightly["chart_research"] = {key: value for key, value in chart_research.items() if key not in {"candidates", "historical_research_queue"}}
            upsert_jsonl(self.root / "data/normalized/chart_insight/strategy_candidates.jsonl", chart_research.get("candidates") or [], key="strategy_id")
            upsert_jsonl(self.root / "data/state/chart_insight/historical_research_queue.jsonl", chart_research.get("historical_research_queue") or [], key="task_id")
            chart_research_state = self.root / "data/state/chart_insight/nightly_research" / f"{self.options.target_date.isoformat()}.json"
            atomic_json(chart_research_state, chart_research)
            atomic_json(
                self.root / "data/state/chart_insight/engine_update_candidates" / f"{self.options.target_date.isoformat()}.json",
                {"schema_version": "1.0", "target_date": self.options.target_date.isoformat(), "candidates": chart_research.get("candidates") or [], "generated_at": datetime.now(timezone.utc).isoformat()},
            )
            nightly_state = self.root / "data/state/nightly_youtube" / f"{self.options.target_date.isoformat()}.json"
            atomic_json(nightly_state, nightly)
            nightly_report = self.root / "reports" / self.options.target_date.strftime("%Y-%m") / f"{self.options.target_date.isoformat()}-nightly-youtube-intelligence.md"
            nightly_report.parent.mkdir(parents=True, exist_ok=True)
            nightly_report.write_text(render_nightly_markdown(nightly) + "\n" + render_chart_research_markdown(chart_research), encoding="utf-8")
            selected = rank_cards(all_cards, min(self.options.max_cards, int(self.policy.get("max_cards_per_digest", self.options.max_cards))))
            manifest = {
                "schema_version": "1.0",
                "target_date": self.options.target_date.isoformat(),
                "mode": self.policy.get("mode", "SHADOW_ONLY"),
                "channels": [channel["id"] for channel in self.channels],
                "videos_seen": videos_seen,
                "videos_analyzed": videos_analyzed,
                "claims_extracted": len(all_claims),
                "claims_extracted_this_run": claims_extracted_this_run,
                "cards_total": len(all_cards),
                "cards_selected": len(selected),
                "chart_requests": len(chart_requests),
                "verification_queue_size": len(verification_queue),
                "engine_update_candidates": len(engine_candidates),
                "nightly_issues": len(nightly.get("issues") or []),
                "nightly_agreement_issues": nightly.get("agreement_issue_count", 0),
                "nightly_disagreement_issues": nightly.get("disagreement_issue_count", 0),
                "chart_strategy_candidates": chart_research.get("candidate_count", 0),
                "chart_research_candidates": chart_research.get("research_candidate_count", 0),
                "chart_historical_queue": len(chart_research.get("historical_research_queue") or []),
                "errors": errors,
                "codex_runs": codex_runs,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            state_dir = self.root / "data/state/youtube_insight"
            atomic_json(state_dir / "manifests" / f"{self.options.target_date.isoformat()}.json", manifest)
            atomic_json(state_dir / "cards" / f"{self.options.target_date.isoformat()}.json", selected)
            atomic_json(state_dir / "chart_requests" / f"{self.options.target_date.isoformat()}.json", chart_requests)
            report_dir = self.root / "reports" / self.options.target_date.strftime("%Y-%m")
            report_dir.mkdir(parents=True, exist_ok=True)
            markdown = render_digest_markdown(self.options.target_date.isoformat(), selected, manifest)
            report_path = report_dir / f"{self.options.target_date.isoformat()}-youtube-view-cards.md"
            report_path.write_text(markdown, encoding="utf-8")
            publication_path = state_dir / "publication_state.json"
            publication_state = load_json(publication_path, {}) or {}
            day_state = publication_state.get(self.options.target_date.isoformat(), {})
            digest_hash = hashlib.sha256(markdown.encode()).hexdigest()
            day_state.update({
                "content_hash": digest_hash,
                "cards": [card["card_id"] for card in selected],
                "last_generated_at": manifest["generated_at"],
                "status": "SHADOW_READY" if selected else "NO_ELIGIBLE_CARDS",
            })
            publish_requested = self.options.publish and not self.options.dry_run
            if publish_requested:
                if os.getenv("MMP_YOUTUBE_INSIGHT_PUBLISH", "0") != "1":
                    day_state["status"] = "PUBLISH_DISABLED"
                elif not selected:
                    day_state["status"] = "NO_ELIGIBLE_CARDS"
                else:
                    post = blogger_publish_digest(
                        f"시장 관점 카드 | {self.options.target_date.isoformat()}", markdown, day_state.get("blogger_post_id")
                    )
                    day_state.update({"blogger_post_id": post.get("id"), "blogger_url": post.get("url"), "status": "PUBLISHED"})
            publication_state[self.options.target_date.isoformat()] = day_state
            atomic_json(publication_path, publication_state)
            manifest["publication"] = day_state
            return {**manifest, "report": str(report_path), "nightly_report": str(nightly_report), "nightly_state": str(nightly_state), "chart_research_state": str(chart_research_state), "cards": selected}
