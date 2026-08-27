from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .disclosure_intelligence import collect_dart_disclosures
from .event_intelligence import build_event_calendar_context
from .rumor_intelligence import (build_calendar_overlay, build_rumor_watch, ingest_rows,
                                 load_jsonl, read_ledger, write_ledger)
from .source_performance import build_source_performance
from .source_registry import load_source_registry
from .post_event_result import PostEventResult, calendar_phase
from .event_lifecycle import merge_candidate
from .official_calendar_coverage import assess_coverage


def root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh official market calendar and important OpenDART disclosures")
    parser.add_argument("--no-network", action="store_true", help="read existing/seed calendar only; do not call remote calendars")
    parser.add_argument("--calendar-only", action="store_true", help="skip OpenDART collection")
    args = parser.parse_args()
    root = root_dir()
    now = datetime.now(timezone.utc)
    state_dir = root / "data/state/event_intelligence"
    ledger_path = state_dir / "event_lifecycle.json"
    rumor_config = json.loads((root / "config/rumor_intelligence.json").read_text(encoding="utf-8"))
    telegram_config = json.loads((root / "config/telegram_rumor_sources.json").read_text(encoding="utf-8"))
    input_paths = [root / value for value in rumor_config.get("normalized_event_inputs", [])]
    telegram_input = telegram_config.get("normalized_events_path")
    if telegram_input:
        input_paths.append(root / telegram_input)
    ledger = ingest_rows(
        load_jsonl(input_paths), read_ledger(ledger_path), now=now,
        default_recheck_hours=int(rumor_config.get("default_recheck_hours", 6)),
        source_registry=load_source_registry(root / "config/source_registry.json"),
    )
    seed_path = root / "config/official_calendar_seed_20260827.json"
    seed_stats = {"added": 0, "matched": 0, "skipped": 0}
    seed_events = json.loads(seed_path.read_text(encoding="utf-8")).get("events", []) if seed_path.exists() else []
    if seed_events:
        for candidate in seed_events:
            event_id = str(candidate.get("event_id") or "")
            if not event_id:
                seed_stats["skipped"] += 1
                continue
            existing = ledger.get(event_id)
            ledger[event_id] = merge_candidate(existing, candidate, now=now,
                                               default_recheck_hours=int(rumor_config.get("default_recheck_hours", 6)))
            seed_stats["matched" if existing else "added"] += 1
    for event in ledger.values():
        result = PostEventResult.from_dict(event.post_event_result) if event.post_event_result else None
        if calendar_phase(event.event_date, result, now=now, result_expected_at=event.result_expected_at, estimated_end_date=event.estimated_end_date) == "RESULT_PENDING" and not event.post_event_result:
            event.post_event_result = {
                "result_state": "AWAITING_RESULT", "verification_class": "UNVERIFIED",
                "mi_review_status": "PENDING", "official_source_ids": [], "market_reactions": [],
            }
    write_ledger(ledger_path, ledger.values(), generated_at=now)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "rumor_watch.json").write_text(json.dumps({"contract": "MMP_RUMOR_WATCH_V1", "rows": build_rumor_watch(ledger.values())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (state_dir / "calendar_overlay.json").write_text(json.dumps({"contract": "MMP_EVENT_CALENDAR_OVERLAY_V1", "rows": build_calendar_overlay(ledger.values())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (state_dir / "source_performance.json").write_text(json.dumps({"contract": "MMP_SOURCE_PERFORMANCE_V1", "rows": build_source_performance(ledger.values())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    calendar = build_event_calendar_context(root, as_of=now, refresh=not args.no_network)
    coverage_specs = json.loads((root / "config/official_forward_calendar_sources.json").read_text(encoding="utf-8")).get("sources", [])
    coverage_events = [
        {**row, "fetched_at": now.isoformat()}
        for row in seed_events
    ]
    coverage = assess_coverage(coverage_events, coverage_specs, now=now)
    live_status = {str(x.get("source_id") or ""): x for x in calendar.get("statuses", [])}
    live_key = {
        "FED_FOMC": "event_calendar_fed", "BOK_MPB": "event_calendar_bok",
        "BLS_RELEASES": "event_calendar_bls", "BEA_RELEASES": "event_calendar_bea",
        "UST_REFUNDING": "event_calendar_treasury", "ECB_MPOL": "event_calendar_ecb",
        "BOJ_MPM": "event_calendar_boj", "KC_JACKSON_HOLE": "event_calendar_kc_fed",
        "FEC_ELECTIONS": "event_calendar_fec",
    }
    if not args.no_network:
        for row in coverage["sources"]:
            status = live_status.get(live_key.get(row["source_id"], ""))
            if status and not status.get("ok"):
                row["status"] = "FAIL" if row["required"] else "WARN"
                row["reason"] = f"live collection failed: {status.get('error') or 'unknown error'}"
        coverage["overall"] = ("FAIL" if any(x["status"] == "FAIL" for x in coverage["sources"])
                               else "WARN" if any(x["status"] == "WARN" for x in coverage["sources"])
                               else "OK")
    disclosures = {"rows": [], "statuses": []} if args.calendar_only or args.no_network else collect_dart_disclosures(root, as_of=now)
    payload = {
        "contract": "MMP_EVENT_INTELLIGENCE_REFRESH_V1",
        "generated_at": now.isoformat(),
        "calendar": {
            "upcoming": len(calendar.get("upcoming_events", [])),
            "critical_7d": len(calendar.get("critical_upcoming_events", [])),
            "statuses": calendar.get("statuses", []),
            "bootstrap_seed": seed_stats,
            "coverage": coverage,
        },
        "lifecycle": {
            "events": len(ledger),
            "active": len(calendar.get("active_events", [])),
            "rumor_watch": len(calendar.get("rumor_watch", [])),
        },
        "disclosures": {
            "important": len(disclosures.get("rows", [])),
            "statuses": disclosures.get("statuses", []),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    required_failed = [s for s in calendar.get("statuses", []) if not s.get("ok")]
    # Calendar failures do not erase the persistent ledger. Return warning code only when every remote source failed.
    if calendar.get("statuses") and len(required_failed) == len(calendar["statuses"]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
