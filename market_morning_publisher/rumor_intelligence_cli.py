from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

from .rumor_intelligence import load_jsonl, read_ledger, write_ledger, ingest_rows, build_rumor_watch, build_calendar_overlay
from .source_registry import load_source_registry
from .source_performance import build_source_performance

UTC = timezone.utc


def main() -> int:
    parser = argparse.ArgumentParser(description="MarketMorningPublisher rumor/unverified event lifecycle overlay")
    parser.add_argument("--input-jsonl", action="append", default=[], help="normalized candidate JSONL; repeatable")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--rumor-watch")
    parser.add_argument("--calendar-overlay")
    parser.add_argument("--recheck-hours", type=int, default=6)
    parser.add_argument("--source-registry", default="config/source_registry.json")
    parser.add_argument("--source-performance")
    args = parser.parse_args()

    now = datetime.now(UTC)
    ledger = read_ledger(args.ledger)
    rows = load_jsonl(args.input_jsonl)
    registry = load_source_registry(args.source_registry) if args.source_registry else None
    ledger = ingest_rows(rows, ledger=ledger, now=now, default_recheck_hours=args.recheck_hours, source_registry=registry)
    write_ledger(args.ledger, ledger.values(), generated_at=now)

    if args.rumor_watch:
        p = Path(args.rumor_watch)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"contract": "MMP_RUMOR_WATCH_V1", "rows": build_rumor_watch(ledger.values())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.calendar_overlay:
        p = Path(args.calendar_overlay)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"contract": "MMP_EVENT_CALENDAR_OVERLAY_V1", "rows": build_calendar_overlay(ledger.values())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.source_performance:
        p = Path(args.source_performance)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"contract": "MMP_SOURCE_PERFORMANCE_V1", "rows": build_source_performance(ledger.values())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"rows_in={len(rows)} ledger_events={len(ledger)} rumor_watch={len(build_rumor_watch(ledger.values()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
