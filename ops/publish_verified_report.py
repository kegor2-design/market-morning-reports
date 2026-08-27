#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_morning_publisher.core import atomic_json, blogger_publish, load_json


def current_report_date() -> str:
    timezone_name = os.environ.get("MMP_TIMEZONE", "Asia/Seoul")
    return datetime.now(ZoneInfo(timezone_name)).date().isoformat()


def main() -> int:
    root = ROOT
    report_date = os.environ.get("MMP_REPORT_DATE") or current_report_date()
    public_repo = Path(os.environ["MMP_PUBLIC_REPO_DIR"])
    report_dir = public_repo / "reports" / report_date[:7]
    report = (report_dir / f"{report_date}-outlook.md").read_text(encoding="utf-8")
    payload = json.loads((report_dir / f"{report_date}-outlook.json").read_text(encoding="utf-8"))
    if payload.get("report_date") != report_date:
        raise RuntimeError(
            f"report date mismatch: requested={report_date}, payload={payload.get('report_date')}"
        )
    if not payload.get("quality", {}).get("passed"):
        raise RuntimeError("refusing to publish a report that did not pass quality checks")
    if payload.get("analysis_meta", {}).get("status") != "COMPLETED":
        raise RuntimeError("refusing to publish an incomplete Codex analysis")

    local_commit = subprocess.check_output(
        ["git", "-C", str(public_repo), "rev-parse", "HEAD"], text=True
    ).strip()
    remote_line = subprocess.check_output(
        ["git", "-C", str(public_repo), "ls-remote", "origin", "refs/heads/main"], text=True
    ).strip()
    remote_commit = remote_line.split()[0] if remote_line else ""
    if remote_commit != local_commit:
        raise RuntimeError(f"GitHub main mismatch: local={local_commit}, remote={remote_commit}")

    required = ["BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("missing Blogger environment: " + ", ".join(missing))
    token_body = urllib.parse.urlencode({
        "client_id": os.environ["BLOGGER_CLIENT_ID"],
        "client_secret": os.environ["BLOGGER_CLIENT_SECRET"],
        "refresh_token": os.environ["BLOGGER_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    token_req = urllib.request.Request("https://oauth2.googleapis.com/token", data=token_body, method="POST")
    access_token = json.loads(urllib.request.urlopen(token_req, timeout=30).read())["access_token"]

    title_prefix = "우리의 모닝브리핑" if payload.get("market_session_expected") else "휴장일 뉴스 브리핑"
    title = f"{title_prefix} | {report_date}"
    query = urllib.parse.urlencode({"q": title, "fetchBodies": "false", "maxResults": "20"})
    search_url = f"https://www.googleapis.com/blogger/v3/blogs/{os.environ['BLOGGER_BLOG_ID']}/posts/search?{query}"
    search_req = urllib.request.Request(search_url, headers={"Authorization": "Bearer " + access_token})
    search_result = json.loads(urllib.request.urlopen(search_req, timeout=30).read())
    matches = [item for item in search_result.get("items", []) if item.get("title") == title]
    prior_post_id = matches[0].get("id") if matches else None
    post = blogger_publish(title, report, prior_post_id)

    state_path = root / "data/state/publication_state.json"
    state = load_json(state_path, {})
    item = state.get(report_date, {})
    item.update({
        "github_commit": local_commit,
        "blogger_post_id": post.get("id"),
        "blogger_url": post.get("url"),
        "quality_passed": True,
        "status": "PUBLISHED",
    })
    state[report_date] = item
    atomic_json(state_path, state)
    print(json.dumps({
        "report_date": report_date,
        "github_commit": local_commit,
        "blogger_action": "updated" if prior_post_id else "created",
        "blogger_post_id": post.get("id"),
        "blogger_url": post.get("url"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
