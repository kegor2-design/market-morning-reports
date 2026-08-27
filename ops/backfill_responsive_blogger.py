#!/usr/bin/env python3
"""Safely re-render existing Blogger posts with the current responsive renderer.

The default mode is read-only.  --execute backs up every remote API payload
before replacing its content from the corresponding local Markdown report.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from market_morning_publisher.blogger_render import render_blogger_html
from market_morning_publisher.closing import render_closing_html


def request_json(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def access_token() -> str:
    keys = ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")
    missing = [key for key in keys if not os.getenv(key)]
    if missing:
        raise RuntimeError("missing Blogger environment: " + ", ".join(missing))
    data = urllib.parse.urlencode({
        "client_id": os.environ[keys[0]], "client_secret": os.environ[keys[1]],
        "refresh_token": os.environ[keys[2]], "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]


def targets(root: Path) -> list[dict]:
    result = []
    specs = (("morning", "publication_state.json", "outlook", render_blogger_html),
             ("closing", "closing_publication_state.json", "close", render_closing_html))
    for kind, state_name, suffix, renderer in specs:
        state = json.loads((root / "data/state" / state_name).read_text())
        for date, item in sorted(state.items()):
            post_id = item.get("blogger_post_id") if isinstance(item, dict) else None
            report = root / "reports" / date[:7] / f"{date}-{suffix}.md"
            if post_id and report.exists():
                markdown = report.read_text(encoding="utf-8")
                result.append({"kind": kind, "date": date, "post_id": str(post_id),
                               "report": str(report), "title": markdown.splitlines()[0].removeprefix("# "),
                               "content": renderer(markdown)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", nargs="?", default=str(PROJECT_ROOT))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root, blog_id, token = Path(args.project).resolve(), os.environ.get("BLOGGER_BLOG_ID"), access_token()
    if not blog_id:
        raise RuntimeError("missing Blogger environment: BLOGGER_BLOG_ID")
    backup = root / "progress" / ("blogger_responsive_backfill_" + datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S"))
    if args.execute:
        backup.mkdir(parents=True, exist_ok=False)
    rows = []
    for target in targets(root):
        url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/{target['post_id']}"
        row = {key: target[key] for key in ("kind", "date", "post_id", "report")}
        try:
            current = request_json(url, token)
        except urllib.error.HTTPError as exc:
            row.update({"available": False, "http_error": exc.code}); rows.append(row); continue
        row.update({"available": True, "current_responsive": "mmp-responsive" in current.get("content", ""),
                    "rendered_desktop": "mmp-terminal-bar" in target["content"],
                    "rendered_mobile": "mmp-mobile" in target["content"]})
        if args.execute:
            (backup / f"{target['date']}-{target['kind']}-{target['post_id']}.json").write_text(
                json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
            updated = request_json(url, token, "PUT", {"kind": "blogger#post", "id": target["post_id"],
                                                        "title": target["title"], "content": target["content"]})
            row.update({"updated": updated.get("id") == target["post_id"], "url": updated.get("url")})
        rows.append(row)
    print(json.dumps({"mode": "execute" if args.execute else "dry-run", "count": len(rows),
                      "backup": str(backup) if args.execute else None, "results": rows}, ensure_ascii=False, indent=2))
    actionable = [row for row in rows if row.get("available")]
    return 0 if actionable and all(row["rendered_desktop"] and row["rendered_mobile"] and
                                    (not args.execute or row.get("updated")) for row in actionable) else 2


if __name__ == "__main__":
    raise SystemExit(main())
