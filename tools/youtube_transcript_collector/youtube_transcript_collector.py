#!/usr/bin/env python3
"""Resumable, source-preserving YouTube channel transcript collector."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^0-9a-zA-Z._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-._")
    return value or "youtube-source"


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def run(command: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def require_tools(yt_dlp: str) -> None:
    if shutil.which(yt_dlp) is None:
        raise SystemExit(
            f"ERROR: {yt_dlp!r} not found. Install with: python3 -m pip install -U yt-dlp"
        )
    probe = run([yt_dlp, "--version"], timeout=30)
    if probe.returncode != 0:
        raise SystemExit(f"ERROR: yt-dlp check failed: {probe.stderr.strip()}")


def common_auth_args(args: argparse.Namespace) -> list[str]:
    result: list[str] = []
    if args.cookies:
        result += ["--cookies", str(Path(args.cookies).expanduser().resolve())]
    if args.cookies_from_browser:
        result += ["--cookies-from-browser", args.cookies_from_browser]
    return result


def inventory(args: argparse.Namespace, source_dir: Path) -> list[dict[str, Any]]:
    inventory_path = source_dir / "inventory.json"
    if inventory_path.exists() and not args.refresh_inventory:
        value = json.loads(inventory_path.read_text(encoding="utf-8"))
        return list(value.get("videos", []))

    command = [
        args.yt_dlp,
        "--flat-playlist",
        "--dump-single-json",
        "--ignore-errors",
        "--no-warnings",
        *common_auth_args(args),
        args.channel_url,
    ]
    completed = run(command, timeout=args.inventory_timeout)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit(
            "ERROR: inventory collection failed\n" + completed.stderr[-4000:]
        )
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid inventory JSON: {exc}") from exc

    entries = raw.get("entries") or []
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "").strip()
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        deduped.append(
            {
                "video_id": video_id,
                "url": entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                "title": entry.get("title"),
                "duration": entry.get("duration"),
                "timestamp": entry.get("timestamp"),
                "upload_date": entry.get("upload_date"),
                "availability": entry.get("availability"),
                "live_status": entry.get("live_status"),
            }
        )

    document = {
        "schema_version": SCHEMA_VERSION,
        "source_id": args.source_id,
        "channel_url": args.channel_url,
        "channel_id": raw.get("channel_id") or raw.get("id"),
        "channel": raw.get("channel") or raw.get("title"),
        "collected_at_utc": utc_now(),
        "video_count": len(deduped),
        "videos": deduped,
    }
    atomic_write_json(inventory_path, document)
    return deduped


def latest_status_by_id(status_path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(status_path):
        video_id = str(row.get("video_id") or "")
        if video_id:
            latest[video_id] = row
    return latest


def discover_files(video_dir: Path) -> dict[str, Any]:
    subtitles = sorted(
        str(path.name)
        for path in video_dir.glob("*.vtt")
        if path.is_file() and path.stat().st_size > 0
    )
    info_files = sorted(video_dir.glob("*.info.json"))
    descriptions = sorted(video_dir.glob("*.description"))
    return {
        "subtitle_files": subtitles,
        "subtitle_count": len(subtitles),
        "has_info_json": bool(info_files),
        "has_description": bool(descriptions),
    }


def collect_one(
    args: argparse.Namespace,
    source_dir: Path,
    item: dict[str, Any],
    attempt: int,
) -> dict[str, Any]:
    video_id = item["video_id"]
    video_dir = source_dir / "videos" / video_id
    video_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(video_dir / "%(upload_date>%Y%m%d,unknown)s_%(id)s.%(ext)s")
    url = item.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    if not str(url).startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id}"

    command = [
        args.yt_dlp,
        "--ignore-config",
        "--skip-download",
        "--ignore-no-formats-error",
        "--write-info-json",
        "--write-description",
        "--write-subs",
        "--write-auto-subs",
        "--sub-format",
        "vtt",
        "--sub-langs",
        args.sub_langs,
        "--no-overwrites",
        "--ignore-errors",
        "--no-warnings",
        "--output",
        output_template,
        *common_auth_args(args),
        str(url),
    ]
    started = utc_now()
    completed = run(command, timeout=args.video_timeout)
    files = discover_files(video_dir)
    if completed.returncode == 0 and files["subtitle_count"] > 0:
        state = "COMPLETED_WITH_SUBTITLE"
    elif completed.returncode == 0 and files["has_info_json"]:
        state = "COMPLETED_NO_SUBTITLE"
    else:
        state = "FAILED"
    error_text = completed.stderr.strip()[-4000:] if completed.stderr.strip() else None
    return {
        "schema_version": SCHEMA_VERSION,
        "source_id": args.source_id,
        "video_id": video_id,
        "title_from_inventory": item.get("title"),
        "state": state,
        "attempt": attempt,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "return_code": completed.returncode,
        "error": error_text,
        **files,
    }


def compact_metadata(source_dir: Path) -> tuple[int, int]:
    output_path = source_dir / "video_metadata.jsonl"
    temp_path = output_path.with_suffix(".jsonl.tmp")
    written = 0
    invalid = 0
    with temp_path.open("w", encoding="utf-8") as output:
        for path in sorted((source_dir / "videos").glob("*/*.info.json")):
            try:
                info = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                invalid += 1
                continue
            row = {
                "schema_version": SCHEMA_VERSION,
                "video_id": info.get("id"),
                "title": info.get("title"),
                "channel": info.get("channel"),
                "channel_id": info.get("channel_id"),
                "uploader": info.get("uploader"),
                "upload_date": info.get("upload_date"),
                "timestamp": info.get("timestamp"),
                "duration": info.get("duration"),
                "availability": info.get("availability"),
                "live_status": info.get("live_status"),
                "webpage_url": info.get("webpage_url"),
                "description": info.get("description"),
                "tags": info.get("tags"),
                "categories": info.get("categories"),
                "_source_filename": str(path.relative_to(source_dir)),
            }
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            written += 1
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp_path, output_path)
    return written, invalid


def write_summary(source_dir: Path, total: int) -> dict[str, Any]:
    latest = latest_status_by_id(source_dir / "collection_status.jsonl")
    counts: dict[str, int] = {}
    for row in latest.values():
        state = str(row.get("state") or "UNKNOWN")
        counts[state] = counts.get(state, 0) + 1
    summary = {
        "schema_version": SCHEMA_VERSION,
        "updated_at_utc": utc_now(),
        "inventory_total": total,
        "attempted_unique": len(latest),
        "pending": max(0, total - len(latest)),
        "states": counts,
    }
    atomic_write_json(source_dir / "collection_summary.json", summary)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-url", required=True)
    parser.add_argument("--source-id", required=True, help="Stable source slug, e.g. kpunch")
    parser.add_argument("--output-root", default="youtube_sources")
    parser.add_argument("--sub-langs", default="ko-orig,ko,en-orig,en")
    parser.add_argument("--yt-dlp", default="yt-dlp")
    parser.add_argument("--cookies")
    parser.add_argument("--cookies-from-browser")
    parser.add_argument("--refresh-inventory", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--retry-no-subtitle", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="0 means no limit")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--min-free-gb", type=float, default=2.0)
    parser.add_argument("--inventory-timeout", type=int, default=1800)
    parser.add_argument("--video-timeout", type=int, default=900)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.source_id = safe_slug(args.source_id)
    if args.limit < 0 or args.sleep_seconds < 0 or args.min_free_gb < 0:
        raise SystemExit("ERROR: limit, sleep-seconds, and min-free-gb must be non-negative")
    require_tools(args.yt_dlp)

    output_root = Path(args.output_root).expanduser().resolve()
    source_dir = output_root / args.source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    config_fingerprint = hashlib.sha256(
        f"{args.channel_url}\0{args.source_id}\0{args.sub_langs}".encode()
    ).hexdigest()
    atomic_write_json(
        source_dir / "source.json",
        {
            "schema_version": SCHEMA_VERSION,
            "source_id": args.source_id,
            "channel_url": args.channel_url,
            "sub_langs": args.sub_langs,
            "config_fingerprint": config_fingerprint,
            "updated_at_utc": utc_now(),
        },
    )

    items = inventory(args, source_dir)
    status_path = source_dir / "collection_status.jsonl"
    latest = latest_status_by_id(status_path)
    selected: list[dict[str, Any]] = []
    for item in items:
        previous = latest.get(item["video_id"])
        if previous:
            state = previous.get("state")
            if state == "FAILED" and args.retry_failed:
                pass
            elif state == "COMPLETED_NO_SUBTITLE" and args.retry_no_subtitle:
                pass
            else:
                continue
        selected.append(item)
    if args.limit:
        selected = selected[: args.limit]

    print(f"SOURCE_ID={args.source_id}")
    print(f"INVENTORY_TOTAL={len(items)}")
    print(f"SELECTED={len(selected)}")
    for index, item in enumerate(selected, start=1):
        free_gb = shutil.disk_usage(source_dir).free / (1024**3)
        if free_gb < args.min_free_gb:
            print(
                f"STOP=LOW_DISK FREE_GB={free_gb:.2f} MIN_FREE_GB={args.min_free_gb:.2f}",
                file=sys.stderr,
            )
            write_summary(source_dir, len(items))
            return 3
        previous = latest.get(item["video_id"], {})
        attempt = int(previous.get("attempt") or 0) + 1
        row = collect_one(args, source_dir, item, attempt)
        append_jsonl(status_path, row)
        latest[item["video_id"]] = row
        print(
            f"PROGRESS={index}/{len(selected)} VIDEO_ID={item['video_id']} STATE={row['state']}"
        )
        if index < len(selected) and args.sleep_seconds:
            time.sleep(args.sleep_seconds)

    written, invalid = compact_metadata(source_dir)
    summary = write_summary(source_dir, len(items))
    print(f"METADATA_WRITTEN={written}")
    print(f"METADATA_INVALID={invalid}")
    print("SUMMARY=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
