#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "public/market-history/blogger-page.html"
STATE_PATH = ROOT / "data/state/market_history_publication.json"
TITLE = "Market History | 장기 시장 지도"


def request_json(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    return json.loads(urllib.request.urlopen(request, timeout=30).read())


def main() -> int:
    required = ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("missing Blogger environment: " + ", ".join(missing))
    if not PAGE_PATH.exists():
        raise RuntimeError("build market history before publishing the page")
    token_body = urllib.parse.urlencode({
        "client_id": os.environ["BLOGGER_CLIENT_ID"],
        "client_secret": os.environ["BLOGGER_CLIENT_SECRET"],
        "refresh_token": os.environ["BLOGGER_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    token_request = urllib.request.Request("https://oauth2.googleapis.com/token", data=token_body, method="POST")
    token = json.loads(urllib.request.urlopen(token_request, timeout=30).read())["access_token"]
    base = f'https://www.googleapis.com/blogger/v3/blogs/{os.environ["BLOGGER_BLOG_ID"]}/pages'
    listing = request_json(base + "?fetchBodies=false&maxResults=50", token)
    matches = [item for item in listing.get("items", []) if item.get("title") == TITLE]
    payload = {"kind": "blogger#page", "title": TITLE, "content": PAGE_PATH.read_text(encoding="utf-8")}
    if matches:
        page_id = matches[0]["id"]
        result = request_json(base + f"/{page_id}", token, "PUT", payload)
        action = "updated"
    else:
        result = request_json(base + "/", token, "POST", payload)
        action = "created"
    state = {"action": action, "page_id": result.get("id"), "url": result.get("url"), "status": result.get("status")}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
