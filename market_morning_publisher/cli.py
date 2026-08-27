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
from .publication_views import (build_morning_report_view, build_premarket_mi_view,
                                freeze_mi_scenario, render_premarket_mi_markdown)
from .short_term_market_map import (build_short_term_market_map, observations_from_market_history,
                                    observations_from_us_state)


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


def historical_reports(root: Path, report_date: str, limit: int = 25) -> list[dict]:
    paths = sorted(root.glob("reports/*/*-outlook.json"))
    return [load_json(path, {}) for path in paths if path.name[:10] < report_date][-limit:]


def prediction_ids_for_as_of(path: Path, as_of: str) -> list[str]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("as_of") == as_of and row.get("prediction_id"):
            rows.append(str(row["prediction_id"]))
    return rows


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

        short_map_config = load_json(root / "config/short_term_market_map.json", {})
        short_map_observations = observations_from_market_history(
            markets, historical_reports(root, report_date)
        )
        short_map_observations.update(observations_from_us_state(
            load_json(root / "data/state/us_state/raw_metrics_latest.json", {}), as_of=collected_at
        ))
        short_term_map = build_short_term_market_map(
            short_map_config, short_map_observations, as_of=collected_at.isoformat()
        )

        event_refresh = os.getenv("MMP_EVENT_INTELLIGENCE_REFRESH", "1") == "1"
        calendar_context = build_event_calendar_context(root, as_of=collected_at, refresh=event_refresh)
        calendar_rows = calendar_context.get("upcoming_events") or []
        short_term_map["event_risks"] = [{"event_id": row.get("event_id"), "title": row.get("title"), "event_date": row.get("event_date"), "impact": row.get("dynamic_importance")} for row in calendar_context.get("critical_upcoming_events", [])][:10]
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
        analysis_input["short_term_market_map"] = short_term_map
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
            prediction_ledger = root / "data/state/mi_prediction_scoreboard/predictions.jsonl"
            prediction_capture = capture_explicit_predictions(
                analysis, as_of=collected_at.isoformat(),
                ledger=prediction_ledger,
            )
            report = render_codex_report(analysis, analysis_input)
            report += ("\n\n## 단기 시장지도 (1D~20D)\n\n"
                       f"- 현재 상태: **{short_term_map['overall_state']}**\n"
                       f"- 압력 점수: **{short_term_map['overall_score']}**\n"
                       f"- 해석: {short_term_map['interpretation']}\n\n"
                       "> 이 점수는 수익률 확률이 아니라 현재 단기 환경의 압력지표입니다.\n")
            frozen_scenario = freeze_mi_scenario(
                analysis, report_date=report_date, as_of=collected_at.isoformat(),
                prediction_ids=prediction_ids_for_as_of(prediction_ledger, collected_at.isoformat()),
            )
            premarket_mi_view = build_premarket_mi_view(frozen_scenario, short_term_map=short_term_map)
            premarket_mi_report = render_premarket_mi_markdown(premarket_mi_view)
        else:
            prediction_capture = {"created": 0, "skipped": 0}
            report = render_analysis_failure_report(report_date, events, statuses, analysis_meta["error"])
            frozen_scenario = None
            premarket_mi_view = None
            premarket_mi_report = None
        quality = quality_check(events, markets, statuses, report, macro, analysis, analysis_meta, session_expected)
        morning_public_view = build_morning_report_view({"as_of": collected_at.isoformat(), "overnight_market": markets, "major_news": events, "macro_and_policy": macro, "official_calendar": calendar_rows, "short_term_market_map_summary": {"overall_state": short_term_map["overall_state"], "overall_score": short_term_map["overall_score"], "interpretation": short_term_map["interpretation"], "event_risks": short_term_map["event_risks"]}, "brief_mi_context": [analysis.get("one_line_diagnosis")] if analysis else [], "sources": statuses})
        payload = {"report_date":report_date, "generated_at":collected_at.isoformat(), "publication_mode":"TRADING_DAY_CUMULATIVE" if session_expected else "CLOSED_DAY_DAILY", "market_session_expected":session_expected, "overnight_window":{"start":window_start.isoformat(), "end":window_end.isoformat()}, "macro":macro, "events":events, "markets":markets, "view":view, "event_intelligence":event_intelligence, "short_term_market_map":short_term_map, "morning_report_view":morning_public_view, "frozen_mi_scenario":frozen_scenario, "premarket_mi_view":premarket_mi_view, "collection_status":statuses, "analysis":analysis, "analysis_meta":analysis_meta, "prediction_capture":prediction_capture, "quality":quality}
        day = root / "data/raw" / report_date
        atomic_json(day / "articles.json", articles)
        atomic_json(day / "collection_status.json", statuses)
        atomic_json(root / "data/normalized" / f"{report_date}-events.json", events)
        atomic_json(root / "data/private" / f"{report_date}-codex-input.json", analysis_input)
        atomic_json(root / "data/state/short_term_market_map" / f"{report_date}.json", short_term_map)
        if frozen_scenario:
            frozen_path = root / "data/state/mi_scenarios" / f"{frozen_scenario['scenario_id']}.json"
            if not frozen_path.exists():
                atomic_json(frozen_path, frozen_scenario)
        report_dir = root / "reports" / report_date[:7]
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{report_date}-outlook.md"
        report_path.write_text(report, encoding="utf-8")
        mi_report_path = report_dir / f"{report_date}-premarket-mi.md"
        if premarket_mi_report:
            mi_report_path.write_text(premarket_mi_report, encoding="utf-8")
            atomic_json(report_dir / f"{report_date}-premarket-mi.json", premarket_mi_view)
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
            views = item.setdefault("views", {})
            morning_state = views.setdefault("MORNING_REPORT", {})
            post = blogger_publish(f"[Morning Market Report] {report_date} — 오늘 시장을 움직일 핵심 변수", report, morning_state.get("blogger_post_id"))
            morning_state.update({"blogger_post_id": post.get("id"), "blogger_url": post.get("url")})
            if premarket_mi_report:
                mi_state = views.setdefault("PREMARKET_MI_SCENARIO", {})
                mi_post = blogger_publish(f"[장전 MI 시나리오] {report_date} — 오늘 시장의 핵심 시나리오와 관심종목", premarket_mi_report, mi_state.get("blogger_post_id"))
                mi_state.update({"blogger_post_id": mi_post.get("id"), "blogger_url": mi_post.get("url"), "scenario_id": frozen_scenario["scenario_id"]})
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
