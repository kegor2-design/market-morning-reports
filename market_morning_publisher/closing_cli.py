from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .closing import (blogger_publish_closing, build_closing_input, collect_korea_close,
                      render_closing_report, run_closing_analysis)
from .codex_analysis import CodexAnalysisError
from .core import (atomic_json, cluster_articles, collect_sources, filter_articles,
                   load_json, resolve_article_urls)


def root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def quality_check(payload: dict, analysis: dict | None, meta: dict, report: str) -> dict:
    indices = payload["actual_korea_close"]["indices"]
    checks = {
        "both_indices_available": len([row for row in indices if row.get("ok") and row.get("session_date") == payload["report_date"]]) == 2,
        "codex_analysis_complete": bool(analysis) and meta.get("status") == "COMPLETED",
        "has_prediction_evaluation": bool(analysis and analysis.get("prediction_evaluations")),
        "has_carry_forward": bool(analysis and analysis.get("carry_forward")),
        "has_missing_data_disclosure": bool(analysis and analysis.get("missing_data")),
        "has_invalidation": "판단 무효화 조건" in report,
        "has_disclaimer": "투자 권유가 아닙니다" in report,
        "no_secrets": not any(key in report.lower() for key in ("client_secret", "refresh_token", "api_key")),
    }
    return {"passed": all(checks.values()), "checks": checks}


def git_publish_closing(repo: Path, report_date: str, report: str, payload: dict) -> str:
    target = repo / "reports" / report_date[:7]
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{report_date}-close.md").write_text(report, encoding="utf-8")
    atomic_json(target / f"{report_date}-close.json", payload)
    subprocess.run(["git", "-C", str(repo), "add", "reports"], check=True)
    if subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"]).returncode == 0:
        return "UNCHANGED"
    subprocess.run(["git", "-C", str(repo), "commit", "-m", f"report: {report_date} closing review"], check=True)
    subprocess.run(["git", "-C", str(repo), "push"], check=True)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def run(report_date: str | None = None, dry_run: bool = False, market_data: str | None = None) -> int:
    root = root_dir()
    tz = ZoneInfo(os.getenv("MMP_TIMEZONE", "Asia/Seoul"))
    now = datetime.now(timezone.utc)
    report_date = report_date or now.astimezone(tz).date().isoformat()
    lock_path = root / "data/state/closing_pipeline.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        close = collect_korea_close(report_date, Path(market_data) if market_data else None)
        articles, statuses = collect_sources(root, load_json(root / "config/sources.json", []))
        filtered = filter_articles(articles, now, 36, now - timedelta(hours=36))
        filtered, unresolved = resolve_article_urls(filtered)
        statuses.append({"source_id": "google_news_url_resolution", "source_mode": "internal", "ok": unresolved == 0, "unresolved_items": unresolved})
        events = cluster_articles(filtered)
        payload_in = build_closing_input(root, report_date, close, events, now)
        analysis = None
        meta = {"status": "FAILED", "error": "analysis not run"}
        try:
            analysis, meta = run_closing_analysis(root, payload_in)
        except (CodexAnalysisError, OSError, ValueError, json.JSONDecodeError) as exc:
            meta = {"status": "FAILED", "error": str(exc)[:500]}
        report = render_closing_report(analysis, payload_in) if analysis else (
            f"# 우리의 장마감 리뷰 | {report_date}\n\n## 분석 실패\n\n장마감 분석을 완료하지 못해 게시를 차단했습니다: {meta['error']}\n\n## 판단 무효화 조건\n\n- 분석이 완료되기 전 모든 결론은 무효입니다.\n\n## 투자 유의사항\n\n이 글은 정보 정리와 자체 연구를 위한 자료이며 투자 권유가 아닙니다.\n")
        quality = quality_check(payload_in, analysis, meta, report)
        payload = {"report_type": "CLOSING_REVIEW", "idempotency_key": f"{report_date}:CLOSING_REVIEW",
                   "report_date": report_date, "generated_at": now.isoformat(), "market_close": close,
                   "collection_status": statuses, "events": events, "analysis_input_summary": {
                       "morning_available": payload_in["morning_available"], "morning_analysis_status": payload_in["morning_analysis_status"]},
                   "analysis": analysis, "analysis_meta": meta, "quality": quality}
        report_dir = root / "reports" / report_date[:7]
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{report_date}-close.md"
        report_path.write_text(report, encoding="utf-8")
        atomic_json(report_dir / f"{report_date}-close.json", payload)
        atomic_json(root / "data/private" / f"{report_date}-closing-codex-input.json", payload_in)
        state_path = root / "data/state/closing_publication_state.json"
        state = load_json(state_path, {})
        item = state.get(report_date, {})
        item.update({"idempotency_key": payload["idempotency_key"], "content_hash": hashlib.sha256(report.encode()).hexdigest(),
                     "quality_passed": quality["passed"], "last_generated_at": now.isoformat(),
                     "status": "DRY_RUN_READY" if dry_run and quality["passed"] else "DRY_RUN_BLOCKED_QUALITY" if dry_run else "GENERATED" if quality["passed"] else "BLOCKED_QUALITY"})
        state[report_date] = item
        atomic_json(state_path, state)
        if quality["passed"] and not dry_run and os.getenv("MMP_GITHUB_PUSH") == "1":
            item["github_commit"] = git_publish_closing(Path(os.environ["MMP_PUBLIC_REPO_DIR"]), report_date, report, payload)
        if quality["passed"] and not dry_run and os.getenv("MMP_BLOGGER_PUBLISH") == "1":
            post = blogger_publish_closing(f"우리의 장마감 리뷰 | {report_date}", report, item.get("blogger_post_id"))
            item.update({"blogger_post_id": post.get("id"), "blogger_url": post.get("url"), "status": "PUBLISHED"})
        state[report_date] = item
        atomic_json(state_path, state)
        print(json.dumps({"report": str(report_path), "quality": quality, "publication": item}, ensure_ascii=False, indent=2))
        return 0 if quality["passed"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent post-close market review pipeline")
    parser.add_argument("--date")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--market-data", help="optional MMP_KOREA_CLOSE_V1 enrichment JSON")
    args = parser.parse_args()
    return run(args.date, args.dry_run, args.market_data)


if __name__ == "__main__":
    raise SystemExit(main())
