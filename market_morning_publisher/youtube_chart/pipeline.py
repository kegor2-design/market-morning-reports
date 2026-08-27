from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence
from zoneinfo import ZoneInfo

from .captions import parse_vtt
from .claims import extract_chart_claims
from .media import collect_metadata_and_captions, download_video_once, extract_frame, list_channel_videos, safe_component
from .ohlcv import YahooOhlcvClient, completed_bars_as_of, interval_for_timeframe, reconcile_screen_prices
from .outcomes import evaluate_claim
from .time_model import parse_datetime
from .vision import PaddleOcrEngine, detect_line_candidates, extract_screen_fields, fit_price_axis, recognize_overlays


KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class PipelineOptions:
    target_date: date
    channel_ids: tuple[str, ...] = ()
    video_urls: tuple[str, ...] = ()
    inventory_limit: int = 20
    save_frames: bool = False
    run_ocr: bool = False
    fetch_ohlcv: bool = False
    yt_dlp: str = "yt-dlp"
    ffmpeg: str = "ffmpeg"
    cookie_file: Path | None = None
    dry_run: bool = False


def load_json(path: Path) -> Any:
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
                existing[str(item[key])] = item
    for row in rows:
        existing[str(row[key])] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        for row_key in sorted(existing):
            handle.write(json.dumps(existing[row_key], ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"YouTube chart pipeline is already running: {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _iso_epoch(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat() if value is not None else None
    except (TypeError, ValueError, OSError):
        return None


def normalize_video_metadata(metadata: dict[str, Any], channel: dict[str, Any]) -> dict[str, Any]:
    live = bool(metadata.get("is_live") or metadata.get("was_live") or metadata.get("live_status") in {"is_live", "was_live"})
    timestamp = _iso_epoch(metadata.get("timestamp"))
    release = _iso_epoch(metadata.get("release_timestamp"))
    return {
        "id": metadata.get("id"),
        "title": metadata.get("title"),
        "channel_id": channel["id"],
        "channel": channel["name"],
        "uploader_id": metadata.get("channel_id") or metadata.get("uploader_id"),
        "webpage_url": metadata.get("webpage_url") or metadata.get("original_url"),
        "duration": metadata.get("duration"),
        "upload_date": metadata.get("upload_date"),
        "published_at": timestamp or (release if not live else None),
        "release_timestamp_iso": timestamp or (release if not live else None),
        "livestream_start_at": release if live else None,
        "is_live": bool(metadata.get("is_live")),
        "was_live": bool(metadata.get("was_live")),
        "live_status": metadata.get("live_status"),
        "availability_note": "Exact epoch values only; upload_date is never converted to midnight.",
    }


def metadata_date_kst(metadata: dict[str, Any]) -> date | None:
    exact = parse_datetime(metadata.get("published_at") or metadata.get("livestream_start_at"))
    if exact:
        return exact.astimezone(KST).date()
    upload_date = str(metadata.get("upload_date") or "")
    try:
        return datetime.strptime(upload_date, "%Y%m%d").date()
    except ValueError:
        return None


def select_caption_file(directory: Path, video_id: str, languages: Sequence[str]) -> Path | None:
    candidates = list(directory.glob(f"{safe_component(video_id)}*.vtt"))
    if not candidates:
        return None
    for language in languages:
        suffixes = (f".{language}.vtt", f".{language.replace('-', '_')}.vtt")
        for candidate in candidates:
            if candidate.name.endswith(suffixes):
                return candidate
    return sorted(candidates)[0]


class YoutubeChartPipeline:
    def __init__(self, root: Path, options: PipelineOptions) -> None:
        self.root = root.resolve()
        self.options = options
        config = load_json(self.root / "config/youtube_chart_channels.json")
        requested = set(options.channel_ids)
        self.channels = [
            channel for channel in config["channels"]
            if (channel["id"] in requested if requested else channel.get("enabled"))
        ]
        unknown = requested - {channel["id"] for channel in config["channels"]}
        if unknown:
            raise ValueError(f"unknown channel IDs: {', '.join(sorted(unknown))}")
        self.terms = load_json(self.root / "config/youtube_chart_terms.json")
        self._ocr_engine: PaddleOcrEngine | None = None
        self.claims_path = self.root / "data/normalized/youtube_chart/claims.jsonl"
        self.ocr_path = self.root / "data/normalized/youtube_chart/ocr.jsonl"
        self.outcomes_path = self.root / "data/normalized/youtube_chart/outcomes.jsonl"
        self.review_path = self.root / "data/state/youtube_chart/review_queue.jsonl"

    def _video_urls(self, channel: dict[str, Any]) -> list[str]:
        if self.options.video_urls:
            # Explicit request handoff is authoritative: process exactly the requested videos rather than
            # rediscovering a channel section that may not contain a stream/short anymore.
            return list(dict.fromkeys(str(url) for url in self.options.video_urls if url))
        entries = list_channel_videos(
            channel["collection_url"], limit=self.options.inventory_limit, yt_dlp=self.options.yt_dlp,
            cookie_file=self.options.cookie_file,
        )
        urls = []
        for entry in entries:
            exact = _iso_epoch(entry.get("timestamp") or entry.get("release_timestamp"))
            if exact and parse_datetime(exact).astimezone(KST).date() != self.options.target_date:
                continue
            upload_date = str(entry.get("upload_date") or "")
            if upload_date:
                try:
                    if datetime.strptime(upload_date, "%Y%m%d").date() != self.options.target_date:
                        continue
                except ValueError:
                    pass
            video_id = str(entry["id"])
            urls.append(entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}")
        return urls

    def _capture_frames(
        self,
        claim: dict[str, Any],
        raw_dir: Path,
        source_video: Path,
    ) -> list[dict[str, Any]]:
        claim_id = claim["source_claim_id"]
        frame_dir = raw_dir / "frames" / claim_id

        absolute_times = {
            "start": claim["speech_start_ms"],
            "middle": (
                claim["speech_start_ms"]
                + claim["speech_end_ms"]
            ) // 2,
            "end": max(
                claim["speech_start_ms"],
                claim["speech_end_ms"] - 250,
            ),
        }

        records = []

        for label, absolute_ms in absolute_times.items():
            output = frame_dir / f"{label}.jpg"

            if not output.exists() or output.stat().st_size == 0:
                extract_frame(
                    source_video,
                    output,
                    timestamp_ms=absolute_ms,
                    ffmpeg=self.options.ffmpeg,
                )

            records.append({
                "label": label,
                "absolute_offset_ms": absolute_ms,
                "path": str(output.relative_to(self.root)),
                "source_video": str(
                    source_video.relative_to(self.root)
                ),
            })

        atomic_json(
            frame_dir / "frames.json",
            records,
        )

        return records

    def _ocr_frames(self, claim: dict[str, Any], frames: list[dict[str, Any]]) -> dict[str, Any]:
        if self._ocr_engine is None:
            self._ocr_engine = PaddleOcrEngine(languages=("korean", "en"))
        engine = self._ocr_engine
        frame_results = []

        def analyze_frame(frame: dict[str, Any]) -> dict[str, Any]:
            path = self.root / frame["path"]
            tokens = engine.recognize(path)
            try:
                import cv2
            except ImportError as exc:
                raise RuntimeError("OpenCV is required for OCR frame geometry") from exc
            image = cv2.imread(str(path))
            if image is None:
                raise RuntimeError(f"cannot read captured frame: {path}")
            height, width = image.shape[:2]
            fields = extract_screen_fields(tokens, width=width, height=height, assets=self.terms.get("assets", []))
            lines = detect_line_candidates(path)
            axis_fit = fit_price_axis(fields["price_axis_ticks"])
            return {
                **frame, "width": width, "height": height,
                "tokens": [token.to_dict() for token in tokens],
                "screen_fields": fields, "price_axis_fit": axis_fit,
                "overlays": recognize_overlays(tokens, lines, axis_fit=axis_fit),
            }

        middle = next((frame for frame in frames if frame.get("label") == "middle"), frames[0] if frames else None)
        if middle is None:
            return {
                "source_claim_id": claim["source_claim_id"], "channel_id": claim.get("channel_id"),
                "video_id": claim.get("video_id"), "status": "DATA_MISSING", "frames": [],
                "review_status": "PENDING", "ocr_frame_mode": "ADAPTIVE_3_FRAME",
            }
        primary = analyze_frame(middle)
        frame_results.append(primary)
        fields = primary.get("screen_fields") or {}
        axis_status = str((primary.get("price_axis_fit") or {}).get("status") or "")
        sufficient = bool(fields.get("asset_candidates")) and bool(fields.get("timeframe_candidates")) and axis_status in {"HIGH", "MEDIUM"}
        if not sufficient:
            for frame in frames:
                if frame is middle or frame.get("label") == "middle":
                    continue
                frame_results.append(analyze_frame(frame))
        return {
            "source_claim_id": claim["source_claim_id"],
            "channel_id": claim.get("channel_id"),
            "video_id": claim.get("video_id"),
            "status": "COMPLETED",
            "frames": frame_results,
            "review_status": "PENDING",
            "ocr_frame_mode": "MIDDLE_ONLY_SUFFICIENT" if sufficient else "ADAPTIVE_3_FRAME",
        }

    def _market_validation(self, claim: dict[str, Any], ocr: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        middle = None
        if ocr:
            middle = next((frame for frame in ocr["frames"] if frame["label"] == "middle"), ocr["frames"][0] if ocr["frames"] else None)
        speech_assets = {item["symbol"]: item for item in claim.get("asset_candidates") or []}
        screen_assets = {
            item["symbol"]: item for item in ((middle or {}).get("screen_fields") or {}).get("asset_candidates", [])
        }
        intersection = set(speech_assets) & set(screen_assets)
        if len(intersection) == 1:
            symbol = next(iter(intersection))
            asset_resolution = "SPEECH_SCREEN_AGREE"
        elif len(speech_assets) == 1 and not screen_assets:
            symbol = next(iter(speech_assets))
            asset_resolution = "SPEECH_ONLY_CANDIDATE"
        elif len(screen_assets) == 1 and not speech_assets:
            symbol = next(iter(screen_assets))
            asset_resolution = "SCREEN_ONLY_CANDIDATE"
        else:
            missing = {"source_claim_id": claim["source_claim_id"], "status": "DATA_MISSING", "reason": "ONE_CONFIRMED_ASSET_REQUIRED"}
            return missing, missing
        timeframe = claim.get("timeframe_spoken")
        timeframe_resolution = "SPEECH"
        if not interval_for_timeframe(timeframe) and middle:
            screen_timeframes = {
                item.get("normalized") for item in middle["screen_fields"].get("timeframe_candidates", []) if item.get("normalized")
            }
            if len(screen_timeframes) == 1:
                timeframe = next(iter(screen_timeframes))
                timeframe_resolution = "SCREEN_OCR_CANDIDATE"
        interval = interval_for_timeframe(timeframe)
        if not interval:
            missing = {"source_claim_id": claim["source_claim_id"], "status": "DATA_MISSING", "reason": "SUPPORTED_TIMEFRAME_REQUIRED"}
            return missing, missing
        actionable = parse_datetime(claim.get("publicly_actionable_at"))
        if not actionable:
            missing = {"source_claim_id": claim["source_claim_id"], "status": "DATA_MISSING", "reason": "ACTIONABLE_TIME_UNKNOWN"}
            return missing, missing
        end = datetime.now(timezone.utc)
        if actionable >= end:
            missing = {"source_claim_id": claim["source_claim_id"], "status": "DATA_MISSING", "reason": "ACTIONABLE_TIME_NOT_IN_PAST"}
            return missing, missing
        lookback_days = 2_200 if interval == "1mo" else 500 if interval == "1wk" else 150 if interval == "1d" else 5
        bars = YahooOhlcvClient().fetch(symbol, start=actionable - timedelta(days=lookback_days), end=end, interval=interval)
        market_path = self.root / "data/normalized/youtube_chart/ohlcv" / f"{claim['source_claim_id']}.json"
        screen_ticks: list[dict[str, Any]] = []
        comparison_basis = "PRICE_AXIS_TICKS"
        if middle:
            screen_ticks = middle["screen_fields"]["price_axis_ticks"]
            overlay_prices = [
                {"value": overlay["estimated_price"]} for overlay in middle.get("overlays", [])
                if overlay.get("semantic_status") == "EXPLICIT" and overlay.get("estimated_price") is not None
            ]
            if overlay_prices:
                screen_ticks = overlay_prices
                comparison_basis = "MAPPED_EXPLICIT_OVERLAY_LEVELS"
        context_bars = completed_bars_as_of(bars, claim.get("publicly_actionable_at"))[-60:]
        market_record = {
            "source_claim_id": claim["source_claim_id"], "symbol": symbol, "interval": interval,
            "asset_resolution": asset_resolution, "timeframe": timeframe,
            "timeframe_resolution": timeframe_resolution,
            "price_basis": "RAW", "provider": "YAHOO_FINANCE", "bars": bars,
            "point_in_time_context_bar_count": len(context_bars),
            "point_in_time_snapshot": context_bars[-1] if context_bars else None,
            "screen_comparison_basis": comparison_basis,
            "screen_reconciliation": reconcile_screen_prices(screen_ticks, context_bars),
        }
        atomic_json(market_path, market_record)
        horizon = int(claim.get("horizon_bars") or 60)
        outcome = {"source_claim_id": claim["source_claim_id"], **evaluate_claim(claim, bars, horizon_bars=horizon)}
        return market_record, outcome

    def _process_video(self, channel: dict[str, Any], video_url: str) -> dict[str, Any]:
        staging = self.root / "data/private/youtube_chart/raw" / safe_component(channel["id"]) / "_staging"
        metadata = collect_metadata_and_captions(
            video_url, staging, subtitle_languages=channel["subtitle_languages"], yt_dlp=self.options.yt_dlp,
            cookie_file=self.options.cookie_file,
        )
        normalized = normalize_video_metadata(metadata, channel)
        if not normalized.get("id"):
            raise RuntimeError("yt-dlp metadata is missing video id")
        video_id = safe_component(str(normalized["id"]))
        if metadata_date_kst(normalized) != self.options.target_date:
            return {"video_id": video_id, "status": "SKIPPED_OUTSIDE_TARGET_DATE", "claims": 0}
        raw_dir = self.root / "data/private/youtube_chart/raw" / safe_component(channel["id"]) / video_id
        raw_dir.mkdir(parents=True, exist_ok=True)
        for path in staging.glob(f"{video_id}*"):
            destination = raw_dir / path.name
            if destination.exists():
                destination.unlink()
            os.replace(path, destination)
        atomic_json(raw_dir / "metadata.normalized.json", normalized)
        caption = select_caption_file(raw_dir, video_id, channel["subtitle_languages"])
        if not caption:
            return {"video_id": video_id, "status": "CAPTIONS_MISSING", "claims": 0}
        cues = parse_vtt(caption.read_text(encoding="utf-8", errors="replace"))
        claims = extract_chart_claims(cues, video=normalized, terms=self.terms)
        if claims:
            upsert_jsonl(self.claims_path, claims, key="source_claim_id")
        ocr_rows, outcomes, review_rows = [], [], []

        # Durable OCR checkpoint/resume.
        # 이미 저장된 claim은 재실행 시 비싼 OCR을 다시 수행하지 않는다.
        existing_ocr_by_claim: dict[str, dict[str, Any]] = {}

        if self.options.run_ocr and self.ocr_path.exists():
            for line in self.ocr_path.read_text(
                encoding="utf-8"
            ).splitlines():
                if not line.strip():
                    continue

                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                claim_id = str(
                    row.get("source_claim_id") or ""
                )

                if claim_id and row.get("status") != "OCR_ERROR":
                    existing_ocr_by_claim[claim_id] = row

        source_video = None

        if self.options.save_frames and claims:
            source_video = download_video_once(
                claims[0]["video_url"],
                raw_dir,
                yt_dlp=self.options.yt_dlp,
                cookie_file=self.options.cookie_file,
            )

        for claim in claims:
            frames = (
                self._capture_frames(
                    claim,
                    raw_dir,
                    source_video,
                )
                if source_video
                else []
            )
            ocr = None

            if self.options.run_ocr and frames:
                claim_id = claim["source_claim_id"]

                # 이전 실행에서 완료된 claim이면 재사용
                ocr = existing_ocr_by_claim.get(claim_id)

                if ocr is None:
                    try:
                        ocr = self._ocr_frames(
                            claim,
                            frames,
                        )
                    except Exception as exc:
                        # 한 claim의 OCR/후처리 오류 때문에
                        # 영상 전체가 FAILED 되지 않도록 격리한다.
                        ocr = {
                            "source_claim_id": claim_id,
                            "channel_id": claim.get("channel_id"),
                            "video_id": claim.get("video_id"),
                            "status": "OCR_ERROR",
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                            "frames": [],
                        }

                    # claim 하나가 끝나는 즉시 저장.
                    # 이후 실행에서는 이 claim을 다시 OCR하지 않는다.
                    upsert_jsonl(
                        self.ocr_path,
                        [ocr],
                        key="source_claim_id",
                    )

                    existing_ocr_by_claim[claim_id] = ocr

            if ocr:
                ocr_rows.append(ocr)
            if self.options.fetch_ohlcv:
                try:
                    _, outcome = self._market_validation(claim, ocr)
                except Exception as exc:
                    outcome = {"source_claim_id": claim["source_claim_id"], "status": "DATA_MISSING", "reason": type(exc).__name__}
                outcomes.append(outcome)
            issues = []
            issues.append("ASSET_HUMAN_CONFIRMATION_REQUIRED")
            if len(claim.get("asset_candidates") or []) != 1:
                issues.append("ASSET_AMBIGUOUS_OR_MISSING")
            if not claim.get("timeframe_spoken"):
                issues.append("TIMEFRAME_CONFIRMATION_REQUIRED")
            if not claim.get("publicly_actionable_at"):
                issues.append("ACTIONABLE_TIME_UNKNOWN")
            if claim.get("target_price") is None or claim.get("invalidation_price") is None:
                issues.append("TARGET_AND_INVALIDATION_REVIEW_REQUIRED")
            if not frames:
                issues.append("FRAME_NOT_COLLECTED")
            elif not ocr:
                issues.append("OCR_NOT_RUN")
            review_rows.append({
                "source_claim_id": claim["source_claim_id"], "status": "PENDING", "issues": issues,
                "channel_id": claim["channel_id"], "video_id": claim["video_id"],
                "timestamp_url": claim["timestamp_url"],
            })
        if ocr_rows:
            upsert_jsonl(self.ocr_path, ocr_rows, key="source_claim_id")
        if outcomes:
            upsert_jsonl(self.outcomes_path, outcomes, key="source_claim_id")
        if review_rows:
            upsert_jsonl(self.review_path, review_rows, key="source_claim_id")
        return {"video_id": video_id, "status": "COMPLETED", "claims": len(claims), "caption": caption.name}

    def run(self) -> dict[str, Any]:
        if self.options.run_ocr and not self.options.save_frames:
            raise ValueError("--ocr requires --frames")
        started = datetime.now(timezone.utc)
        manifest: dict[str, Any] = {
            "schema_version": "1.0", "mode": "SHADOW_ONLY", "target_date": self.options.target_date.isoformat(),
            "started_at": started.isoformat(), "options": {**asdict(self.options), "target_date": self.options.target_date.isoformat(), "cookie_file": bool(self.options.cookie_file)},
            "channels": [], "errors": [],
        }
        lock_path = self.root / "data/state/youtube_chart_pipeline.lock"
        with exclusive_lock(lock_path):
            for channel in self.channels:
                channel_result = {"channel_id": channel["id"], "videos": []}
                try:
                    urls = self._video_urls(channel)
                    channel_result["discovered"] = len(urls)
                    if not self.options.dry_run:
                        for url in urls:
                            try:
                                channel_result["videos"].append(self._process_video(channel, url))
                            except Exception as exc:
                                message = str(exc).replace(str(self.options.cookie_file), "[COOKIE_FILE]") if self.options.cookie_file else str(exc)
                                error = {"channel_id": channel["id"], "video_url": url, "error_type": type(exc).__name__, "message": message[:500]}
                                manifest["errors"].append(error)
                                channel_result["videos"].append({"video_url": url, "status": "FAILED", "error_type": type(exc).__name__})
                except Exception as exc:
                    message = str(exc).replace(str(self.options.cookie_file), "[COOKIE_FILE]") if self.options.cookie_file else str(exc)
                    manifest["errors"].append({"channel_id": channel["id"], "error_type": type(exc).__name__, "message": message[:500]})
                manifest["channels"].append(channel_result)
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["status"] = "COMPLETED_WITH_ERRORS" if manifest["errors"] else "COMPLETED"
        manifest_path = self.root / "data/state/youtube_chart/manifests" / f"{self.options.target_date.isoformat()}.json"
        atomic_json(manifest_path, manifest)
        return manifest
