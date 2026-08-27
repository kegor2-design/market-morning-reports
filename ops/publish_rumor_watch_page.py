#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_morning_publisher.rumor_page import render_rumor_page

TITLE = "Rumor Watch | 소문·찌라시 추적"
STATE = ROOT / "data/state/rumor_watch_publication.json"

def request_json(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + token}
    if data is not None: headers["Content-Type"] = "application/json"
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=30).read())

def main() -> int:
    required = ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")
    missing = [key for key in required if not os.getenv(key)]
    if missing: raise RuntimeError("missing Blogger environment: " + ", ".join(missing))
    data = urllib.parse.urlencode({"client_id":os.environ["BLOGGER_CLIENT_ID"],"client_secret":os.environ["BLOGGER_CLIENT_SECRET"],"refresh_token":os.environ["BLOGGER_REFRESH_TOKEN"],"grant_type":"refresh_token"}).encode()
    token = json.loads(urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST"), timeout=30).read())["access_token"]
    base = f'https://www.googleapis.com/blogger/v3/blogs/{os.environ["BLOGGER_BLOG_ID"]}/pages'
    matches = [x for x in request_json(base + "?fetchBodies=false&maxResults=50", token).get("items", []) if x.get("title") == TITLE]
    payload = {"kind":"blogger#page", "title":TITLE, "content":render_rumor_page(ROOT)}
    if matches:
        result = request_json(base + "/" + matches[0]["id"], token, "PUT", payload); action="updated"
    else:
        result = request_json(base + "/", token, "POST", payload); action="created"
    state={"action":action,"page_id":result.get("id"),"url":result.get("url"),"status":result.get("status")}
    STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(state,ensure_ascii=False,indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
