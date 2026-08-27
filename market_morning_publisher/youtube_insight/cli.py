from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .pipeline import YoutubeInsightOptions, YoutubeInsightPipeline


def default_target_date() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect, classify, verify, and render latest YouTube market-view cards")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--date", default=default_target_date(), help="KST digest date YYYY-MM-DD")
    parser.add_argument("--lookback-hours", type=int, default=int(os.getenv("MMP_YOUTUBE_INSIGHT_LOOKBACK_HOURS", "48")))
    parser.add_argument("--limit", type=int, default=int(os.getenv("MMP_YOUTUBE_INSIGHT_INVENTORY_LIMIT", "30")))
    parser.add_argument("--max-cards", type=int, default=int(os.getenv("MMP_YOUTUBE_INSIGHT_MAX_CARDS", "6")))
    parser.add_argument("--channel", action="append", default=[])
    parser.add_argument("--no-collect", action="store_true")
    parser.add_argument("--no-analyze", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yt-dlp", default=os.getenv("MMP_YT_DLP", "yt-dlp"))
    parser.add_argument("--cookies", type=Path, default=Path(os.environ["MMP_YOUTUBE_COOKIE_FILE"]) if os.getenv("MMP_YOUTUBE_COOKIE_FILE") else None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback_hours < 1 or args.lookback_hours > 168:
        raise SystemExit("--lookback-hours must be between 1 and 168")
    if args.limit < 1 or args.limit > 100:
        raise SystemExit("--limit must be between 1 and 100")
    options = YoutubeInsightOptions(
        target_date=datetime.strptime(args.date, "%Y-%m-%d").date(),
        lookback_hours=args.lookback_hours,
        inventory_limit=args.limit,
        channel_ids=tuple(args.channel),
        max_cards=args.max_cards,
        collect=not args.no_collect,
        analyze=not args.no_analyze,
        publish=args.publish,
        dry_run=args.dry_run,
        yt_dlp=args.yt_dlp,
        cookie_file=args.cookies,
    )
    result = YoutubeInsightPipeline(args.root, options).run()
    print(json.dumps({
        "target_date": result["target_date"],
        "videos_seen": result["videos_seen"],
        "videos_analyzed": result["videos_analyzed"],
        "claims_extracted": result["claims_extracted"],
        "cards_selected": result["cards_selected"],
        "errors": len(result["errors"]),
        "publication": result["publication"],
        "report": result["report"],
    }, ensure_ascii=False, indent=2))
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
