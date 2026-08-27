from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .pipeline import PipelineOptions, YoutubeChartPipeline


def default_target_date() -> str:
    return (datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=1)).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect and shadow-evaluate point-in-time YouTube chart claims")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="MarketMorningPublisher project root")
    parser.add_argument("--date", default=default_target_date(), help="KST video publication date (YYYY-MM-DD)")
    parser.add_argument("--channel", action="append", default=[], help="Configured channel ID; may be repeated")
    parser.add_argument("--video-url", action="append", default=[], help="Explicit requested YouTube video URL; may be repeated")
    parser.add_argument("--limit", type=int, default=20, help="Maximum recent playlist entries inspected per channel")
    parser.add_argument("--frames", action="store_true", help="Download short clips and save start/middle/end frames")
    parser.add_argument("--ocr", action="store_true", help="Run PaddleOCR and OpenCV; requires --frames")
    parser.add_argument("--ohlcv", action="store_true", help="Fetch supported Yahoo OHLCV and calculate shadow outcomes")
    parser.add_argument("--yt-dlp", default="yt-dlp")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--cookies", type=Path, help="Optional Netscape cookie file; its path is not written to manifests")
    parser.add_argument("--dry-run", action="store_true", help="Discover matching candidates without downloading captions")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    if args.limit < 1 or args.limit > 200:
        raise SystemExit("--limit must be between 1 and 200")
    options = PipelineOptions(
        target_date=target, channel_ids=tuple(args.channel), video_urls=tuple(args.video_url), inventory_limit=args.limit,
        save_frames=args.frames, run_ocr=args.ocr, fetch_ohlcv=args.ohlcv,
        yt_dlp=args.yt_dlp, ffmpeg=args.ffmpeg, cookie_file=args.cookies, dry_run=args.dry_run,
    )
    manifest = YoutubeChartPipeline(args.root, options).run()
    print(json.dumps({
        "status": manifest["status"], "target_date": manifest["target_date"],
        "channels": len(manifest["channels"]), "errors": len(manifest["errors"]),
    }, ensure_ascii=False))
    return 0 if manifest["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

