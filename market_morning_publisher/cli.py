from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import (atomic_json, blogger_publish, cluster_articles, collect_macro_indicators, collect_markets,
                   collect_sources, filter_articles, git_publish, load_json, market_view,
                   is_trading_day, overnight_window, quality_check, resolve_article_urls)
from .codex_analysis import (CodexAnalysisError, build_codex_input, render_analysis_failure_report,
                             render_codex_report, run_codex_analysis)
from .event_intelligence import build_event_calendar_context
from .disclosure_intelligence import collect_dart_disclosures, disclosure_news_events
from .mi_prediction_bridge import capture_explicit_predictions


def root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def archived_articles(root: Path, start: datetime, end: datetime) -> list[dict]:
    """Load daily snapshots covering a cumulative weekend/holiday window."""
    rows, day = [], start.date()
    while day <= end.date():
        rows.extend(load_json(root / "data/raw" / day.isoformat() / "articles.json", []))
        day += timedelta(days=1)
    return rows


def merge_articles(*groups: list[dict]) -> list[dict]:
    unique = {}
    for article in (item for group in groups for item in group):
        key = article.get("article_id") or article.get("url")
        if key:
            unique[key] = article
    return list(unique.values())


def run(report_date: str | None = None, dry_run: bool = False, through_now: bool = False,
        skip_codex: bool = False, include_closed_day_domestic: bool = False) -> int:
    root = root_dir()
    tz = ZoneInfo(os.getenv("MMP_TIMEZONE", "Asia/Seoul"))
    report_date = report_date or datetime.now(tz).date().isoformat()
    lock_path = root / "data/state/pipeline.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sources = load_json(root / "config/sources.json", [])
        markets_cfg = load_json(root / "config/markets.json", [])
        macro_cfg = load_json(root / "config/macro_indicators.json", {})
        holiday_cfg = load_json(root / "config/market_holidays.json", {})
        holidays = set(holiday_cfg.get("krx", []))
        articles, statuses = collect_sources(root, sources)
        collected_at = datetime.now(tz).astimezone(ZoneInfo("UTC"))
        markets = collect_markets(markets_cfg, collected_at)
        macro = collect_macro_indicators(macro_cfg)
        session_expected = is_trading_day(collected_at.astimezone(tz).date(), holidays)
        window_start, window_end = overnight_window(
            collected_at, tz, cap_at_morning=not through_now, market_holidays=holidays
        )
        articles = merge_articles(archived_articles(root, window_start, window_end), articles)
        window_hours = (window_end - window_start).total_seconds() / 3600
        max_age_hours = max(int(os.getenv("MMP_NEWS_MAX_AGE_HOURS", "72")), int(window_hours) + 2)
        relevant_articles = filter_articles(
            articles, collected_at, max_age_hours, window_start
        )
        relevant_articles, unresolved_google_news = resolve_article_urls(relevant_articles)
        statuses.append({
            "source_id": "google_news_url_resolution", "source_mode": "internal",
            "ok": unresolved_google_news == 0, "unresolved_items": unresolved_google_news,
        })
        events = cluster_articles(relevant_articles)
        view = market_view(markets)

        event_refresh = os.getenv("MMP_EVENT_INTELLIGENCE_REFRESH", "1") == "1"
        calendar_context = build_event_calendar_context(root, as_of=collected_at, refresh=event_refresh)
        disclosures = collect_dart_disclosures(root, as_of=collected_at)
        statuses.extend(calendar_context.get("statuses", []))
        statuses.extend(disclosures.get("statuses", []))
        disclosure_events = disclosure_news_events(disclosures.get("rows", []))
        if disclosure_events:
            disclosure_ids = {event.get("event_id") for event in disclosure_events}
            events = disclosure_events + [
                event for event in events if event.get("event_id") not in disclosure_ids
            ]

        event_intelligence = {
            "contract": "MMP_EVENT_INTELLIGENCE_CONTEXT_V1",
            "calendar": calendar_context,
            "disclosures": {
                "contract": disclosures.get("contract"),
                "window": disclosures.get("window"),
                "rows": disclosures.get("rows", []),
            },
        }
        analysis_input = build_codex_input(
            report_date, collected_at, window_start, window_end, events, markets, macro, statuses, view,
            market_session_expected=session_expected,
            equity_master=load_json(root / "data/private/reference/korea_equity_master.json", {}).get("rows", []),
            equity_exposures=load_json(root / "config/korea_equity_exposures.json", {}).get("rows", []),
            include_closed_day_domestic=include_closed_day_domestic,
            event_intelligence=event_intelligence,
        )
        analysis = None
        analysis_meta = {"status": "SKIPPED", "error": "--skip-codex diagnostics mode"}
        if not skip_codex and os.getenv("MMP_CODEX_ENABLED", "1") == "1":
            try:
                analysis, analysis_meta = run_codex_analysis(root, analysis_input)
            except CodexAnalysisError as exc:
                analysis_meta = {"status": "FAILED", "error": str(exc)[:500]}
        elif not skip_codex:
            analysis_meta = {"status": "DISABLED", "error": "MMP_CODEX_ENABLED is not 1"}
        if analysis:
            prediction_capture = capture_explicit_predictions(
                analysis, as_of=collected_at.isoformat(),
                ledger=root / "data/state/mi_prediction_scoreboard/predictions.jsonl",
            )
            report = render_codex_report(analysis, analysis_input)
        else:
            prediction_capture = {"created": 0, "skipped": 0}
            report = render_analysis_failure_report(report_date, events, statuses, analysis_meta["error"])
        quality = quality_check(events, markets, statuses, report, macro, analysis, analysis_meta, session_expected)
        payload = {"report_date":report_date, "generated_at":collected_at.isoformat(), "publication_mode":"TRADING_DAY_CUMULATIVE" if session_expected else "CLOSED_DAY_DAILY", "market_session_expected":session_expected, "overnight_window":{"start":window_start.isoformat(), "end":window_end.isoformat()}, "macro":macro, "events":events, "markets":markets, "view":view, "event_intelligence":event_intelligence, "collection_status":statuses, "analysis":analysis, "analysis_meta":analysis_meta, "prediction_capture":prediction_capture, "quality":quality}
        day = root / "data/raw" / report_date
        atomic_json(day / "articles.json", articles)
        atomic_json(day / "collection_status.json", statuses)
        atomic_json(root / "data/normalized" / f"{report_date}-events.json", events)
        atomic_json(root / "data/private" / f"{report_date}-codex-input.json", analysis_input)
        report_dir = root / "reports" / report_date[:7]
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{report_date}-outlook.md"
        report_path.write_text(report, encoding="utf-8")
        atomic_json(report_dir / f"{report_date}-outlook.json", payload)
        state_path = root / "data/state/publication_state.json"
        state = load_json(state_path, {})
        item = state.get(report_date, {})
        item.update({"content_hash":hashlib.sha256(report.encode()).hexdigest(), "quality_passed":quality["passed"], "last_generated_at":collected_at.isoformat()})
        item["status"] = (
            "DRY_RUN_READY" if dry_run and quality["passed"] else
            "DRY_RUN_BLOCKED_QUALITY" if dry_run else
            "GENERATED" if quality["passed"] else "BLOCKED_QUALITY"
        )
        state[report_date] = item
        atomic_json(state_path, state)
        if quality["passed"] and not dry_run and os.getenv("MMP_GITHUB_PUSH") == "1":
            item["github_commit"] = git_publish(Path(os.environ["MMP_PUBLIC_REPO_DIR"]), report_date, report, payload)
            item["status"] = "GITHUB_PUSHED"
            state[report_date] = item
            atomic_json(state_path, state)
        if quality["passed"] and not dry_run and os.getenv("MMP_BLOGGER_PUBLISH") == "1":
            title_prefix = "우리의 모닝브리핑" if session_expected else "휴장일 뉴스 브리핑"
            post = blogger_publish(f"{title_prefix} | {report_date}", report, item.get("blogger_post_id"))
            item.update({"blogger_post_id":post.get("id"), "blogger_url":post.get("url"), "status":"PUBLISHED"})
            state[report_date] = item
            atomic_json(state_path, state)
        state[report_date] = item
        atomic_json(state_path, state)
        print(json.dumps({"report":str(report_path), "articles":len(articles), "events":len(events), "quality":quality, "publication":item}, ensure_ascii=False, indent=2))
        return 0 if quality["passed"] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--through-now", action="store_true", help="test/report mode: include news through the execution time")
    parser.add_argument("--skip-codex", action="store_true", help="diagnostics only: collect data but block analysis and publication")
    parser.add_argument("--include-closed-day-domestic", action="store_true",
                        help="include collected Korean news in a closed-day briefing")
    args = parser.parse_args()
    return run(args.date, args.dry_run, args.through_now, args.skip_codex, args.include_closed_day_domestic)


if __name__ == "__main__":
    raise SystemExit(main())
