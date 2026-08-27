from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from .claim_validation import (
    assess_claim,
    classify_claim_nature,
    contextual_excerpt,
    detect_pattern_candidates,
    effective_claim,
    merge_caption_texts,
    normalize_review,
)
from .captions import CaptionCue, parse_vtt
from .ohlcv import YahooOhlcvClient, interval_for_timeframe
from .outcomes import evaluate_claim
from .time_model import parse_datetime


ASSESSMENT_PATH = Path("data/normalized/youtube_chart/claim_assessments.jsonl")
PATTERN_PATH = Path("data/normalized/youtube_chart/pattern_candidates.jsonl")
VALIDATED_OUTCOME_PATH = Path("data/normalized/youtube_chart/validated_outcomes.jsonl")
REVIEW_QUEUE_PATH = Path("data/state/youtube_chart/validation_review_queue.jsonl")
SUMMARY_PATH = Path("data/state/youtube_chart/validation_summary.json")
REPORT_PATH = Path("data/state/youtube_chart/validation_report.md")
REVIEW_PACKET_PATH = Path("data/state/youtube_chart/validation_review_packet.md")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc


def _read_jsonl(path: Path, *, required: bool = False) -> list[dict[str, Any]]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL: {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
        rows.append(value)
    return rows


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, newline="") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _atomic_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    _atomic_text(path, content)


def _upsert_jsonl(path: Path, rows: Sequence[dict[str, Any]], *, key: str, replace_all: bool) -> None:
    merged: dict[str, dict[str, Any]] = {}
    if not replace_all:
        for row in _read_jsonl(path):
            merged[str(row[key])] = row
    for row in rows:
        merged[str(row[key])] = row
    _atomic_jsonl(path, [merged[row_key] for row_key in sorted(merged)])


def _read_reviews(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    return _read_jsonl(path)


def _caption_path(root: Path, claim: dict[str, Any], priority: Sequence[str]) -> Path | None:
    directory = (
        root / "data/private/youtube_chart/raw"
        / str(claim.get("channel_id") or "UNKNOWN")
        / str(claim.get("video_id") or "UNKNOWN")
    )
    candidates = sorted(directory.glob("*.vtt"))
    for language in priority:
        suffixes = (f".{language}.vtt", f".{language.replace('-', '_')}.vtt")
        for candidate in candidates:
            if candidate.name.endswith(suffixes):
                return candidate
    return candidates[0] if candidates else None


def enrich_claim_contexts(
    root: Path,
    claims: Sequence[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    window = config.get("context_window") or {}
    before_ms = int(window.get("before_ms") or 15_000)
    after_ms = int(window.get("after_ms") or 25_000)
    priority = tuple(str(item) for item in window.get("caption_priority") or ("ko-orig", "ko", "en-orig", "en"))
    cue_cache: dict[Path, list[CaptionCue]] = {}
    enriched: list[dict[str, Any]] = []
    for claim in claims:
        value = dict(claim)
        caption = _caption_path(root, claim, priority)
        context = ""
        if caption:
            if caption not in cue_cache:
                cue_cache[caption] = parse_vtt(caption.read_text(encoding="utf-8", errors="replace"))
            context = contextual_excerpt(
                cue_cache[caption],
                start_ms=int(claim.get("speech_start_ms") or 0),
                end_ms=int(claim.get("speech_end_ms") or claim.get("speech_start_ms") or 0),
                before_ms=before_ms,
                after_ms=after_ms,
            )
        if context:
            value["validation_context_excerpt"] = context
            value["validation_context_source"] = "RAW_VTT_WINDOW"
            value["validation_context_caption"] = str(caption.relative_to(root)) if caption else None
        else:
            value["validation_context_excerpt"] = merge_caption_texts([str(claim.get("speech_excerpt") or "")])
            value["validation_context_source"] = "CLAIM_EXCERPT_DEDUPED"
            value["validation_context_caption"] = None
        enriched.append(value)
    return enriched


def _template_row(claim: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    automatic = classify_claim_nature(claim, config)
    assets = claim.get("asset_candidates") or []
    suggested_asset = assets[0].get("symbol") if len(assets) == 1 else ""
    patterns = detect_pattern_candidates(claim, config=config)
    return {
        "review_version": "1.0",
        "source_claim_id": claim["source_claim_id"],
        "review_status": "PENDING",
        "claim_type": automatic["primary_type"],
        "asset_symbol": suggested_asset or "",
        "timeframe": claim.get("timeframe_spoken") or "",
        "direction": claim.get("direction") or "NEUTRAL",
        "target_price": "",
        "invalidation_price": "",
        "pattern_ids": "",
        "suggested_pattern_ids": ";".join(row["pattern_id"] for row in patterns),
        "reviewer": "",
        "reviewed_at": "",
        "notes": "",
        "auto_suggested_type": automatic["primary_type"],
        "timestamp_url": claim.get("timestamp_url") or "",
        "speech_excerpt": " ".join(str(claim.get("validation_context_excerpt") or claim.get("speech_excerpt") or "").split()),
    }


def initialize_review_template(path: Path, claims: Sequence[dict[str, Any]], config: dict[str, Any]) -> int:
    existing = {str(row.get("source_claim_id")): row for row in _read_reviews(path) if row.get("source_claim_id")}
    added = 0
    for claim in claims:
        claim_id = str(claim["source_claim_id"])
        if claim_id not in existing:
            existing[claim_id] = _template_row(claim, config)
            added += 1
        elif str(existing[claim_id].get("review_status") or "PENDING").upper() == "PENDING":
            refreshed = _template_row(claim, config)
            for field in ("auto_suggested_type", "suggested_pattern_ids", "timestamp_url", "speech_excerpt"):
                existing[claim_id][field] = refreshed[field]
    rows = [existing[key] for key in sorted(existing)]
    if path.suffix.lower() == ".csv":
        fieldnames = [
            "review_version", "source_claim_id", "review_status", "claim_type", "asset_symbol",
            "timeframe", "direction", "target_price", "invalidation_price", "pattern_ids",
            "suggested_pattern_ids", "reviewer", "reviewed_at", "notes", "auto_suggested_type",
            "timestamp_url", "speech_excerpt",
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", dir=path.parent, delete=False, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                value = dict(row)
                if isinstance(value.get("pattern_ids"), list):
                    value["pattern_ids"] = ";".join(value["pattern_ids"])
                writer.writerow(value)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    else:
        normalized_rows = []
        for row in rows:
            value = dict(row)
            if isinstance(value.get("pattern_ids"), str):
                value["pattern_ids"] = [item.strip() for item in value["pattern_ids"].split(";") if item.strip()]
            normalized_rows.append(value)
        _atomic_jsonl(path, normalized_rows)
    return added


def _evaluate_assessment(
    root: Path,
    claim: dict[str, Any],
    assessment: dict[str, Any],
    review: dict[str, Any] | None,
    *,
    windows: Sequence[int],
    horizon_bars: int,
    evaluated_at: str,
    fetch_reviewed_ohlcv: bool = False,
    ohlcv_client: Any | None = None,
) -> dict[str, Any]:
    claim_id = str(claim["source_claim_id"])
    base = {
        "schema_version": "1.0",
        "source_claim_id": claim_id,
        "channel_id": claim.get("channel_id"),
        "video_id": claim.get("video_id"),
        "claim_type": assessment["effective_claim_type"],
        "evaluation_mode": assessment["evaluation_mode"],
        "validation_state": "SHADOW_ONLY",
        "evaluated_at": evaluated_at,
    }
    if assessment["evaluation_mode"] not in {"DIRECTIONAL_SHADOW", "BINARY_SHADOW"}:
        return {**base, "status": "NOT_EVALUATED", "reason": assessment["evaluation_mode"]}
    effective = effective_claim(claim, review)
    assets = effective.get("asset_candidates") or []
    expected_symbol = assets[0].get("symbol") if len(assets) == 1 else None
    expected_interval = interval_for_timeframe(effective.get("timeframe_spoken"))
    reviewed_market_path = root / "data/normalized/youtube_chart/ohlcv_reviewed" / f"{claim_id}.json"
    tentative_market_path = root / "data/normalized/youtube_chart/ohlcv" / f"{claim_id}.json"
    market_path = reviewed_market_path if reviewed_market_path.exists() else tentative_market_path
    market = _read_json(market_path) if market_path.exists() else None

    if fetch_reviewed_ohlcv:
        actionable = parse_datetime(effective.get("publicly_actionable_at"))
        if not actionable or not expected_symbol or not expected_interval:
            return {**base, "status": "DATA_MISSING", "reason": "REVIEWED_OHLCV_KEYS_MISSING"}
        lookback_days = 2_200 if expected_interval == "1mo" else 500 if expected_interval == "1wk" else 150 if expected_interval == "1d" else 5
        end = datetime.now(timezone.utc)
        client = ohlcv_client or YahooOhlcvClient()
        try:
            bars = client.fetch(
                expected_symbol,
                start=actionable - timedelta(days=lookback_days),
                end=end,
                interval=expected_interval,
            )
        except Exception as exc:
            return {
                **base,
                "status": "DATA_MISSING",
                "reason": "REVIEWED_OHLCV_FETCH_FAILED",
                "error_type": type(exc).__name__,
            }
        market = {
            "schema_version": "1.0",
            "source_claim_id": claim_id,
            "symbol": expected_symbol,
            "interval": expected_interval,
            "provider": "YAHOO_FINANCE",
            "price_basis": "RAW",
            "resolution": "HUMAN_CONFIRMED_CLAIM",
            "fetched_at": end.isoformat(),
            "publicly_actionable_at": effective.get("publicly_actionable_at"),
            "bars": bars,
        }
        _atomic_json(reviewed_market_path, market)

    if market is None:
        return {**base, "status": "DATA_MISSING", "reason": "OHLCV_FILE_MISSING"}
    if market.get("symbol") != expected_symbol:
        return {
            **base, "status": "DATA_MISSING", "reason": "OHLCV_SYMBOL_RECOLLECTION_REQUIRED",
            "expected_symbol": expected_symbol, "available_symbol": market.get("symbol"),
        }
    if market.get("interval") != expected_interval:
        return {
            **base, "status": "DATA_MISSING", "reason": "OHLCV_INTERVAL_RECOLLECTION_REQUIRED",
            "expected_interval": expected_interval, "available_interval": market.get("interval"),
        }
    result = evaluate_claim(effective, market.get("bars") or [], windows=windows, horizon_bars=horizon_bars)
    if assessment["evaluation_mode"] == "DIRECTIONAL_SHADOW" and result.get("status") == "UNSCORABLE":
        complete = any(item.get("status") == "COMPLETE" for item in result.get("forward_windows") or [])
        result = {
            **result,
            "binary_status": result["status"],
            "status": "DIRECTIONAL_COMPLETE" if complete else "DIRECTIONAL_PENDING",
            "reason": "FORWARD_WINDOWS_EVALUATED_WITHOUT_BINARY_LEVELS",
        }
    return {**base, **result}


def _counter(rows: Sequence[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "UNKNOWN") for row in rows).items()))


def _render_report(summary: dict[str, Any]) -> str:
    def table(values: dict[str, int]) -> str:
        if not values:
            return "| 없음 | 0 |"
        return "\n".join(f"| {name} | {count} |" for name, count in values.items())

    return f"""# 유튜브 차트 Claim 검증 보고서

- 생성 시각(UTC): `{summary['generated_at']}`
- 검증 모드: `SHADOW_ONLY`
- 처리 claim: {summary['claim_count']}개
- 사람 확인 완료: {summary['human_review_counts'].get('CONFIRMED', 0)}개
- 패턴 후보 연결: {summary['pattern_candidate_count']}개

## 자동 의미 분류

| 유형 | 건수 |
|---|---:|
{table(summary['automatic_classification_counts'])}

자동 분류는 검토 후보이며 적중률 계산에 직접 사용하지 않는다.

## 사람 검토 상태

| 상태 | 건수 |
|---|---:|
{table(summary['human_review_counts'])}

## 평가 가능성

| 모드 | 건수 |
|---|---:|
{table(summary['evaluation_mode_counts'])}

## 사후 결과

| 상태 | 건수 |
|---|---:|
{table(summary['outcome_status_counts'])}

## 판정 규칙

- `DESCRIPTION`은 사후 설명이므로 적중률에서 제외한다.
- `MIXED`는 설명과 전망을 원자 claim으로 분리하기 전까지 평가하지 않는다.
- 종목·시간축·방향·행동 가능 시각이 사람 확인된 경우에만 방향 성과를 계산한다.
- 목표가와 무효화 가격이 모두 확인된 경우에만 성공·실패를 계산한다.
- 결과는 MI 또는 모닝 브리핑에 자동 반영하지 않는다.
"""


def _render_review_packet(
    assessments: Sequence[dict[str, Any]],
    patterns: Sequence[dict[str, Any]],
) -> str:
    patterns_by_claim: dict[str, list[str]] = {}
    for row in patterns:
        patterns_by_claim.setdefault(str(row["source_claim_id"]), []).append(str(row["pattern_id"]))
    lines = [
        "# 유튜브 차트 Claim 사람 검토 묶음",
        "",
        "자동 분류는 제안일 뿐입니다. CSV에서 `review_status=CONFIRMED`로 바꾼 행만 검증에 사용됩니다.",
        "",
    ]
    for row in assessments:
        claim_id = str(row["source_claim_id"])
        automatic = row["automatic_classification"]
        ocr = row["ocr_summary"]
        excerpt = " ".join(str(row.get("validation_context_excerpt") or row.get("speech_excerpt") or "").split())[:1200]
        raw_excerpt = " ".join(str(row.get("speech_excerpt") or "").split())[:400]
        lines.extend([
            f"## `{claim_id}`",
            "",
            f"- 원문 시점: {row.get('timestamp_url') or 'UNKNOWN'}",
            f"- 자동 유형: `{automatic['primary_type']}` / 신뢰도 `{automatic['confidence']}`",
            f"- 문맥 출처: `{row.get('validation_context_source') or 'UNKNOWN'}`",
            f"- 사람 검토: `{row['human_review']['review_status']}`",
            f"- 평가 모드: `{row['evaluation_mode']}`",
            f"- 화면 종목 후보: `{', '.join(ocr['screen_asset_symbols']) or 'UNKNOWN'}`",
            f"- 화면 시간축 후보: `{', '.join(ocr['screen_timeframes']) or 'UNKNOWN'}`",
            f"- 가격축 적합 프레임: {ocr['price_axis_fitted_frame_count']}/{ocr['frame_count']}",
            f"- 패턴 후보: `{', '.join(patterns_by_claim.get(claim_id, [])) or 'NONE'}`",
            f"- 차단 사유: `{', '.join(row['blocking_issues']) or 'NONE'}`",
            f"- 주의: `{', '.join(row['warnings']) or 'NONE'}`",
            "",
            f"> 문맥: {excerpt}",
            "",
            f"> 기존 검출 구간: {raw_excerpt}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def run_validation(
    root: Path,
    *,
    config_path: Path,
    review_path: Path,
    claim_ids: Sequence[str] = (),
    initialize_reviews: bool = False,
    fetch_reviewed_ohlcv: bool = False,
    ohlcv_client: Any | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    config = _read_json(config_path)
    claims = _read_jsonl(root / "data/normalized/youtube_chart/claims.jsonl", required=True)
    by_id = {str(row["source_claim_id"]): row for row in claims}
    requested = set(claim_ids)
    unknown = requested - set(by_id)
    if unknown:
        raise ValueError(f"unknown claim IDs: {', '.join(sorted(unknown))}")
    selected_raw = [by_id[key] for key in sorted(requested)] if requested else [by_id[key] for key in sorted(by_id)]
    selected = enrich_claim_contexts(root, selected_raw, config)
    if initialize_reviews and not dry_run:
        initialize_review_template(review_path, selected, config)
    reviews = {str(row["source_claim_id"]): row for row in _read_reviews(review_path) if row.get("source_claim_id")}
    ocr_rows = _read_jsonl(root / "data/normalized/youtube_chart/ocr.jsonl")
    ocr_by_id = {str(row["source_claim_id"]): row for row in ocr_rows}
    evaluated_at = datetime.now(timezone.utc).isoformat()
    windows = tuple(int(value) for value in config.get("forward_windows") or (1, 5, 20, 60))
    horizon_bars = int(config.get("horizon_bars") or 60)
    assessments: list[dict[str, Any]] = []
    patterns: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []

    for claim in selected:
        claim_id = str(claim["source_claim_id"])
        review = reviews.get(claim_id)
        assessment = assess_claim(claim, config=config, review=review, ocr=ocr_by_id.get(claim_id))
        assessments.append(assessment)
        matches = detect_pattern_candidates(
            claim, config=config, review=review, evaluation_mode=assessment["evaluation_mode"]
        )
        patterns.extend(matches)
        outcome = _evaluate_assessment(
            root, claim, assessment, review,
            windows=windows, horizon_bars=horizon_bars, evaluated_at=evaluated_at,
            fetch_reviewed_ohlcv=fetch_reviewed_ohlcv and not dry_run,
            ohlcv_client=ohlcv_client,
        )
        outcomes.append(outcome)
        issues = list(assessment["blocking_issues"])
        if assessment["evaluation_mode"] in {"PENDING_HUMAN_REVIEW", "NOT_SCOREABLE"}:
            issues.extend(assessment["warnings"])
        if any(row["match_status"] == "AUTO_TEXT_CANDIDATE" for row in matches):
            issues.append("PATTERN_HUMAN_CONFIRMATION_REQUIRED")
        if outcome["status"] == "DATA_MISSING":
            issues.append(str(outcome["reason"]))
        if issues:
            queue.append({
                "source_claim_id": claim_id,
                "status": "PENDING",
                "evaluation_mode": assessment["evaluation_mode"],
                "issues": sorted(set(issues)),
                "timestamp_url": claim.get("timestamp_url"),
            })

    summary = {
        "schema_version": "1.0",
        "mode": "SHADOW_ONLY",
        "generated_at": evaluated_at,
        "claim_count": len(assessments),
        "selection": sorted(requested) if requested else "ALL",
        "automatic_classification_counts": _counter(
            [{"value": row["automatic_classification"]["primary_type"]} for row in assessments], "value"
        ),
        "human_review_counts": _counter(
            [{"value": row["human_review"]["review_status"]} for row in assessments], "value"
        ),
        "evaluation_mode_counts": _counter(assessments, "evaluation_mode"),
        "outcome_status_counts": _counter(outcomes, "status"),
        "pattern_candidate_count": len(patterns),
        "pattern_counts": _counter(patterns, "pattern_id"),
        "review_queue_count": len(queue),
        "paths": {
            "assessments": str(ASSESSMENT_PATH),
            "patterns": str(PATTERN_PATH),
            "outcomes": str(VALIDATED_OUTCOME_PATH),
            "review_queue": str(REVIEW_QUEUE_PATH),
            "report": str(REPORT_PATH),
            "review_packet": str(REVIEW_PACKET_PATH),
        },
    }
    if not dry_run:
        replace_all = not requested
        _upsert_jsonl(root / ASSESSMENT_PATH, assessments, key="source_claim_id", replace_all=replace_all)
        _upsert_jsonl(root / PATTERN_PATH, patterns, key="pattern_match_id", replace_all=replace_all)
        _upsert_jsonl(root / VALIDATED_OUTCOME_PATH, outcomes, key="source_claim_id", replace_all=replace_all)
        _upsert_jsonl(root / REVIEW_QUEUE_PATH, queue, key="source_claim_id", replace_all=replace_all)
        _atomic_json(root / SUMMARY_PATH, summary)
        _atomic_text(root / REPORT_PATH, _render_report(summary))
        _atomic_text(root / REVIEW_PACKET_PATH, _render_review_packet(assessments, patterns))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review and shadow-validate collected YouTube chart claims")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--review-file", type=Path)
    parser.add_argument("--claim-id", action="append", default=[])
    parser.add_argument("--init-review-template", action="store_true")
    parser.add_argument("--fetch-reviewed-ohlcv", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    config_path = (args.config or root / "config/youtube_chart_validation.json").resolve()
    review_path = (args.review_file or root / "data/state/youtube_chart/human_reviews.csv").resolve()
    summary = run_validation(
        root,
        config_path=config_path,
        review_path=review_path,
        claim_ids=args.claim_id,
        initialize_reviews=args.init_review_template,
        fetch_reviewed_ohlcv=args.fetch_reviewed_ohlcv,
        dry_run=args.dry_run,
    )
    print(json.dumps({
        "status": "COMPLETED",
        "mode": summary["mode"],
        "claims": summary["claim_count"],
        "human_confirmed": summary["human_review_counts"].get("CONFIRMED", 0),
        "review_queue": summary["review_queue_count"],
        "dry_run": args.dry_run,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
