from __future__ import annotations

import hashlib
import html
import csv
import concurrent.futures
import io
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

UA = "MarketMorningPublisher/1.0 (+private market research collector)"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
        tmp = Path(fh.name)
    tmp.replace(path)


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(url: str, *, timeout: int = 10, attempts: int = 2, headers=None, data: bytes | None = None) -> bytes:
    request_headers = {"User-Agent": UA, "Accept": "application/xml,text/xml,application/json,*/*"}
    request_headers.update(headers or {})
    last = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=request_headers, data=data)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"fetch failed after {attempts} attempts: {url}: {last}")


def clean_text(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_time(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def stable_id(*values: str) -> str:
    return hashlib.sha256("\x1f".join(values).encode()).hexdigest()[:24]


def parse_feed(raw: bytes, source: dict) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    nodes = root.findall(".//item")
    if not nodes:
        nodes = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for node in nodes:
        def first(*names):
            for name in names:
                found = node.find(name)
                if found is not None and found.text:
                    return found.text
            return None
        title = clean_text(first("title", "{http://www.w3.org/2005/Atom}title"))
        link = first("link")
        if not link:
            atom_link = node.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.attrib.get("href") if atom_link is not None else None
        link = clean_text(link)
        if not title or not link:
            continue
        summary = clean_text(first("description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"))
        publisher = clean_text(first("source", "{http://www.w3.org/2005/Atom}source")) or source["name"]
        published = parse_time(first("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"))
        out.append({
            "article_id": stable_id(source["id"], link), "source_id": source["id"],
            "source_name": source["name"], "source_tier": source.get("tier", 2),
            "publisher": publisher, "country": source.get("country"), "title": title, "url": link,
            "published_at": published, "collected_at": now_iso(),
            "source_summary": summary[:1200], "content_stored": False,
            "lookback_hours": source.get("lookback_hours"),
            "source_mode": source.get("source_mode", "search" if "news.google.com" in source.get("url", "") else "direct"),
            "source_priority": int(source.get("priority", 50 if "news.google.com" in source.get("url", "") else 10)),
        })
    return out


def is_google_news_url(url: str | None) -> bool:
    try:
        return (urllib.parse.urlparse(url or "").hostname or "").lower() == "news.google.com"
    except ValueError:
        return False


def resolve_google_news_url(url: str) -> str | None:
    """Resolve a Google News RSS article token to the publisher's article URL."""
    if not is_google_news_url(url):
        return url
    page = fetch(url, headers={"Accept": "text/html,*/*"}).decode("utf-8", "replace")
    article_id = re.search(r'data-n-a-id="([^"]+)"', page)
    timestamp = re.search(r'data-n-a-ts="([^"]+)"', page)
    signature = re.search(r'data-n-a-sg="([^"]+)"', page)
    if not all((article_id, timestamp, signature)):
        return None
    request = [
        "garturlreq",
        [["en-US", "US", ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"], None, None, 1, 1,
          "US:en", None, None, None, None, None, None, None, False, 5],
         "en-US", "US", 1, [2, 3, 4, 8], 1, 0, "655000234", 0, 0, None, 0],
        article_id.group(1), int(timestamp.group(1)), signature.group(1),
    ]
    envelope = [[["Fbv4je", json.dumps(request, separators=(",", ":")), None, "generic"]]]
    body = urllib.parse.urlencode({"f.req": json.dumps(envelope, separators=(",", ":"))}).encode()
    raw = fetch(
        "https://news.google.com/_/DotsSplashUi/data/batchexecute",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "Accept": "*/*"},
    ).decode("utf-8", "replace")
    decoded = raw.replace(r'\"', '"').replace(r'\/', '/')
    for match in re.finditer(r'\["garturlres","(https?://[^"]+)"', decoded):
        candidate = html.unescape(match.group(1))
        if not is_google_news_url(candidate):
            return candidate
    return None


def resolve_article_urls(articles: list[dict]) -> tuple[list[dict], int]:
    """Replace Google News relay links; omit unresolved relays from public analysis."""
    resolved, failures = [], 0
    google_urls = list(dict.fromkeys(
        article.get("url") or "" for article in articles if is_google_news_url(article.get("url"))
    ))
    def resolve_safely(url: str) -> tuple[str, str | None]:
        try:
            return url, resolve_google_news_url(url)
        except Exception:
            return url, None
    workers = max(1, min(8, len(google_urls)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        cache = dict(pool.map(resolve_safely, google_urls))
    for article in articles:
        url = article.get("url") or ""
        if not is_google_news_url(url):
            resolved.append(article)
            continue
        publisher_url = cache[url]
        if not publisher_url:
            failures += 1
            continue
        item = dict(article)
        item["discovery_url"] = url
        item["url"] = publisher_url
        item["article_id"] = stable_id(item.get("source_id", ""), publisher_url)
        resolved.append(item)
    return resolved, failures


def parse_president_briefings(raw: bytes, source: dict) -> list[dict]:
    payload = json.loads(raw)
    rows = ((payload.get("data") or {}).get("list") or [])
    out = []
    kst = ZoneInfo("Asia/Seoul")
    for row in rows:
        title = clean_text(row.get("SUBJECT"))
        if not re.search(r"(국무회의|비상경제점검회의)", title):
            continue
        code = clean_text(row.get("BBS_CD"))
        if not code:
            continue
        raw_time = str(row.get("WRITE_DT") or row.get("WRITE_DATE") or "").split(".")[0]
        try:
            published = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=kst).astimezone(timezone.utc).isoformat()
        except ValueError:
            try:
                published = datetime.strptime(str(row.get("WRITE_DATE")), "%Y.%m.%d").replace(tzinfo=kst).astimezone(timezone.utc).isoformat()
            except ValueError:
                continue
        url = f"https://www.president.go.kr/briefings/{code}"
        out.append({
            "article_id": stable_id(source["id"], code), "source_id": source["id"],
            "source_name": source["name"], "source_tier": 1, "publisher": "대한민국 청와대",
            "country": "KR", "title": title, "url": url, "published_at": published,
            "collected_at": now_iso(), "source_summary": clean_text(row.get("CONTENTS"))[:1200],
            "content_stored": False, "lookback_hours": source.get("lookback_hours", 168),
            "source_mode": "direct", "source_priority": int(source.get("priority", 5)),
        })
    return out


def collect_sources(root: Path, sources: list[dict]) -> tuple[list[dict], list[dict]]:
    articles, status = [], []
    for source in sources:
        if not source.get("enabled", True):
            continue
        started = time.monotonic()
        try:
            if source.get("kind") == "president_json":
                form = urllib.parse.urlencode({
                    "pageNo":"1", "pagePerCnt":"30", "MENU_CD":"nFSy219D", "CONTENTS_CD":"vqNUjDNc",
                    "pSiteNo":"2", "pBoardSeq":"2", "SHORT_URL":"briefings", "sSearchTxt":"국무회의",
                }).encode()
                raw = fetch(source["url"], data=form, headers={"Referer":"https://www.president.go.kr/briefings"})
                parsed = parse_president_briefings(raw, source)
            else:
                raw = fetch(source["url"])
                parsed = parse_feed(raw, source)
            articles.extend(parsed)
            published = [datetime.fromisoformat(x["published_at"]) for x in parsed if x.get("published_at")]
            newest = max(published) if published else None
            lag_minutes = round(max(0, (datetime.now(timezone.utc) - newest).total_seconds() / 60), 1) if newest else None
            status.append({
                "source_id": source["id"], "source_mode": source.get("source_mode", "search" if "news.google.com" in source.get("url", "") else "direct"),
                "priority": int(source.get("priority", 50 if "news.google.com" in source.get("url", "") else 10)),
                "ok": True, "items": len(parsed), "latest_item_lag_minutes": lag_minutes,
                "elapsed_ms": round((time.monotonic()-started)*1000),
            })
        except Exception as exc:
            status.append({"source_id": source["id"], "ok": False, "error": str(exc)[:500], "elapsed_ms": round((time.monotonic()-started)*1000)})
    unique = {a["article_id"]: a for a in articles}
    return sorted(unique.values(), key=lambda x: x.get("published_at") or "", reverse=True), status


CORE_MARKETS = {"^GSPC", "^IXIC", "^SOX"}
TRUSTED_PUBLISHERS = {
    "reuters", "associated press", "ap news", "bloomberg", "bbc", "financial times",
    "wall street journal", "cnbc", "marketwatch", "nikkei asia", "the guardian",
    "al jazeera", "france 24", "npr", "abc news australia",
}

TRUSTED_KOREAN_PUBLISHERS = {
    "연합뉴스", "한국경제", "매일경제", "서울경제", "머니투데이", "이데일리", "조선비즈",
    "금융위원회", "금융감독원", "산업통상자원부", "기획재정부", "한국거래소",
}


def trusted_publisher(name: str | None) -> bool:
    normalized = (name or "").strip().lower()
    return any(trusted in normalized for trusted in TRUSTED_PUBLISHERS) or any(
        trusted.lower() in normalized for trusted in TRUSTED_KOREAN_PUBLISHERS
    )


def collect_markets(markets: list[dict], collected_at: datetime | None = None) -> list[dict]:
    collected_at = collected_at or datetime.now(timezone.utc)
    out = []
    for market in markets:
        symbol = market["symbol"]
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?range=5d&interval=1d"
        try:
            payload = json.loads(fetch(url).decode())
            result = payload["chart"]["result"][0]
            timestamps = result.get("timestamp") or []
            raw_closes = result["indicators"]["quote"][0]["close"]
            points = [(ts, close) for ts, close in zip(timestamps, raw_closes) if close is not None]
            closes = [close for _, close in points]
            current, prior = closes[-1], closes[-2] if len(closes) > 1 else None
            change = ((current / prior) - 1) * 100 if prior else None
            meta = result.get("meta") or {}
            quote_type = str(meta.get("instrumentType") or "").upper()
            market_state = str(meta.get("marketState") or "UNKNOWN").upper()
            quote_ts = meta.get("regularMarketTime") or points[-1][0]
            as_of = datetime.fromtimestamp(quote_ts, timezone.utc)
            session_date = datetime.fromtimestamp(points[-1][0], timezone.utc).date().isoformat()
            age_minutes = max(0, round((collected_at - as_of).total_seconds() / 60, 1))
            # Yahoo daily bars are stamped at session open. Completion is therefore
            # determined from marketState; a prior UTC session is also immutable.
            completed = market_state in {"CLOSED", "POST", "POSTPOST"}
            regular_end = (((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end"))
            if regular_end and collected_at >= datetime.fromtimestamp(regular_end, timezone.utc) + timedelta(minutes=10):
                completed = True
            if symbol in CORE_MARKETS and session_date < collected_at.date().isoformat():
                completed = True
            usable_for_score = symbol in CORE_MARKETS and completed and change is not None
            out.append({
                **market, "as_of_utc": as_of.isoformat(),
                "as_of_kst": as_of.astimezone(ZoneInfo("Asia/Seoul")).isoformat(),
                "session_date": session_date, "session_status": "COMPLETED" if completed else "PARTIAL",
                "market_state": market_state, "instrument_type": quote_type,
                "regular_session_end_utc": datetime.fromtimestamp(regular_end, timezone.utc).isoformat() if regular_end else None,
                "value": current, "previous_close": prior, "change_pct": change,
                "age_minutes": age_minutes, "usable_for_score": usable_for_score,
                "provider":"Yahoo Finance chart", "ok":True,
            })
        except Exception as exc:
            out.append({**market, "ok":False, "error":str(exc)[:300]})
    return out


def fetch_fred_series(series_id: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={urllib.parse.quote(series_id)}"
    rows = csv.DictReader(io.StringIO(fetch(url).decode("utf-8-sig")))
    points = []
    for row in rows:
        raw = row.get(series_id)
        if not raw or raw == ".":
            continue
        try:
            observation_date = row.get("DATE") or row.get("observation_date")
            if not observation_date:
                continue
            points.append((observation_date, float(raw)))
        except (KeyError, ValueError):
            continue
    return points


def collect_macro_indicators(config: dict) -> dict:
    """Collect the compact macro dashboard used before editorial analysis."""
    series_results = {}
    for item in config.get("fred_series", []):
        try:
            points = fetch_fred_series(item["series_id"])
            if not points:
                raise RuntimeError("no observations")
            latest_date, latest_value = points[-1]
            result = {**item, "ok": True, "as_of": latest_date, "value": latest_value, "provider": "FRED"}
            if item.get("transform") == "yoy_pct":
                lag = int(item.get("lag", 12))
                if len(points) <= lag:
                    raise RuntimeError("insufficient observations for YoY")
                prior_value = points[-1-lag][1]
                result["value"] = round((latest_value / prior_value - 1) * 100, 2)
                result["unit"] = "% YoY"
            series_results[item["id"]] = result
        except Exception as exc:
            series_results[item["id"]] = {**item, "ok": False, "error": str(exc)[:300]}
    return {
        "series": series_results,
        "sep": config.get("sep", {}),
        "collected_at": now_iso(),
    }


STOP = {"the","a","an","and","or","of","to","in","on","for","with","from","at","by","is","are","new","press","release"}

EXCLUDED_NEWS = re.compile(
    r"(?i)(operating normally|liquidity management publication|eligible marketable assets|"
    r"monetary financial institutions|reference rates|publication message|tender operation|"
    r"open air concert|application by .+ bancshares|enforcement action)"
)
MARKET_TERMS = {
    "rate", "rates", "inflation", "cpi", "ppi", "employment", "payroll", "unemployment",
    "gdp", "tariff", "trade", "sanction", "oil", "energy", "currency", "dollar", "yield",
    "monetary", "policy", "fomc", "ecb", "semiconductor", "chip", "china", "korea",
    "recession", "liquidity", "quantitative", "fiscal", "debt", "geopolitical",
    "earnings", "profit", "revenue", "guidance", "order", "orders", "inventory",
    "capex", "supply", "demand", "price", "margin", "futures", "options", "basis",
    "credit", "breadth", "valuation", "revision", "revisions",
    "국무회의", "비상경제", "경제성장전략", "정책", "관세", "제재", "전쟁", "중동",
    "이란", "우크라이나", "러시아", "호르무즈", "대만", "중국", "북한", "방위비",
    "반도체", "에너지", "유가", "환율", "금리", "물가", "재정", "국채", "수출",
    "공시", "실적", "영업이익", "매출", "수주", "공급계약", "증자", "유상증자",
    "무상증자", "인수합병", "합병", "생산중단", "설비투자", "배터리", "조선",
    "자동차", "바이오", "방산", "원전", "규제", "산업지원",
}

STRATEGIC_TOPICS = {
    "중동·이란·호르무즈": ("iran", "middle east", "hormuz", "중동", "이란", "호르무즈"),
    "러시아·우크라이나": ("russia", "ukraine", "러시아", "우크라이나"),
    "미중·대만·핵심공급망": ("china", "taiwan", "rare earth", "chip export", "중국", "대만", "희토류"),
    "유럽 방위·재정": ("nato", "europe defense", "defence spending", "방위비", "재무장"),
    "한반도·북한": ("north korea", "korean peninsula", "북한", "한반도"),
    "국내 국정회의": ("국무회의", "비상경제점검회의", "국정현안관계장관회의", "경제관계장관회의"),
}


def strategic_topics(article: dict) -> list[str]:
    text = f"{article.get('title', '')} {article.get('source_summary', '')}".lower()
    def contains(needle: str) -> bool:
        if re.fullmatch(r"[a-z ]+", needle):
            return bool(re.search(rf"\b{re.escape(needle)}\b", text))
        return needle in text
    topics = [name for name, needles in STRATEGIC_TOPICS.items() if any(contains(needle) for needle in needles)]
    election_anchor = any(contains(x) for x in ("midterm", "election", "중간선거"))
    us_policy_combo = contains("trump") and any(contains(x) for x in ("tariff", "immigration", "fiscal", "treasury", "tax", "관세"))
    if election_anchor or us_policy_combo:
        topics.append("미국 중간선거·정책")
    return topics


def overnight_window(
    reference_time: datetime,
    market_tz: ZoneInfo | None = None,
    cap_at_morning: bool = True,
    market_holidays: set[str] | None = None,
) -> tuple[datetime, datetime]:
    """Return the Korean post-close-to-morning collection window in UTC.

    On a trading-day morning, start at the previous KRX trading-day close so all
    intervening weekend/holiday news is retained. On a closed day, return the
    preceding 24-hour daily-news window.
    """
    market_tz = market_tz or ZoneInfo("Asia/Seoul")
    local_now = reference_time.astimezone(market_tz)
    scheduled_cutoff = datetime.combine(local_now.date(), dt_time(8, 10), market_tz)
    local_end = min(local_now, scheduled_cutoff) if cap_at_morning else local_now
    holidays = market_holidays or set()
    if not is_trading_day(local_end.date(), holidays):
        local_start = local_end - timedelta(days=1)
        return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)
    start_date = local_end.date() - timedelta(days=1)
    while not is_trading_day(start_date, holidays):
        start_date -= timedelta(days=1)
    local_start = datetime.combine(start_date, dt_time(15, 30), market_tz)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def is_trading_day(day, market_holidays: set[str] | None = None) -> bool:
    return day.weekday() < 5 and day.isoformat() not in (market_holidays or set())


def classify_article(
    article: dict,
    reference_time: datetime,
    max_age_hours: int = 72,
    window_start: datetime | None = None,
) -> dict | None:
    published_raw = article.get("published_at")
    if not published_raw:
        return None
    try:
        published = datetime.fromisoformat(published_raw)
    except ValueError:
        return None
    age_hours = (reference_time - published.astimezone(timezone.utc)).total_seconds() / 3600
    text = f"{article.get('title', '')} {article.get('source_summary', '')}"
    source_lookback = article.get("lookback_hours")
    effective_max_age = max(max_age_hours, int(source_lookback or 0))
    if age_hours < -1 or age_hours > effective_max_age or EXCLUDED_NEWS.search(text):
        return None
    if window_start and not source_lookback and published.astimezone(timezone.utc) < window_start.astimezone(timezone.utc):
        return None
    terms = sorted(term for term in MARKET_TERMS if re.search(rf"\b{re.escape(term)}\b", text, re.I))
    if not terms:
        return None
    result = dict(article)
    result.update({"age_hours": round(age_hours, 1), "market_terms": terms})
    result["strategic_topics"] = strategic_topics(result)
    return result


def filter_articles(
    articles: list[dict],
    reference_time: datetime | None = None,
    max_age_hours: int = 72,
    window_start: datetime | None = None,
) -> list[dict]:
    reference_time = reference_time or datetime.now(timezone.utc)
    return [item for article in articles if (item := classify_article(article, reference_time, max_age_hours, window_start))]


def title_tokens(title: str) -> set[str]:
    return {x for x in re.findall(r"[A-Za-z0-9가-힣]+", title.lower()) if len(x) > 2 and x not in STOP}


def cluster_articles(articles: list[dict]) -> list[dict]:
    clusters = []
    for article in articles:
        tokens = title_tokens(article["title"])
        match = None
        for cluster in clusters:
            union = tokens | cluster["tokens"]
            similarity = len(tokens & cluster["tokens"]) / len(union) if union else 0
            if similarity >= 0.45:
                match = cluster
                break
        if match is None:
            match = {"tokens": set(tokens), "articles": []}
            clusters.append(match)
        match["tokens"].update(tokens)
        match["articles"].append(article)
    result = []
    for cluster in clusters:
        items = cluster["articles"]
        tiers = [x.get("source_tier", 3) for x in items]
        independent = len({x.get("publisher") or x["source_id"] for x in items})
        newest = max((x.get("published_at") for x in items if x.get("published_at")), default=None)
        terms = sorted({term for x in items for term in x.get("market_terms", [])})
        impact = transmission_path(terms)
        evidence = insight_evidence(terms, independent)
        has_trusted_publisher = any(trusted_publisher(x.get("publisher")) for x in items)
        source_priority = min(int(x.get("source_priority", 50)) for x in items)
        has_direct_source = any(x.get("source_mode") == "direct" for x in items)
        verified = min(tiers) == 1 or has_trusted_publisher
        result.append({
            "event_id": stable_id(*(sorted(x["article_id"] for x in items))),
            "headline": items[0]["title"], "article_count": len(items),
            "independent_source_count": independent,
            "verified": verified,
            "verification_reason": (
                "공식 1차 출처" if min(tiers) == 1 else
                "신뢰 매체 보도" if has_trusted_publisher else
                "단일 또는 비검증 출처"
            ),
            "countries": sorted({x.get("country") for x in items if x.get("country")}),
            "strategic_topics": sorted({topic for x in items for topic in x.get("strategic_topics", [])}),
            "source_priority": source_priority, "has_direct_source": has_direct_source,
            "importance_score": min(100, 25 + 15 * independent + (15 if min(tiers) == 1 else 0) + min(20, len(terms) * 2)),
            "published_at": newest, "market_terms": terms, "korea_transmission": impact,
            "evidence_summary": [x.get("source_summary", "")[:1200] for x in items if x.get("source_summary")][:3],
            "insight_evidence": evidence,
            "sources": [{"source":x.get("publisher") or x["source_name"], "feed":x["source_name"], "source_tier":x.get("source_tier", 3), "source_mode":x.get("source_mode", "search"), "title":x["title"], "url":x["url"], "published_at":x.get("published_at")} for x in sorted(items, key=lambda item: (int(item.get("source_priority", 50)), item.get("published_at") or ""))],
        })
    return sorted(result, key=lambda x: (not x["verified"], x["source_priority"], -x["importance_score"], -x["article_count"], x.get("published_at") or ""))


def transmission_path(terms: list[str]) -> str:
    values = set(terms)
    paths = []
    if values & {"semiconductor", "chip", "반도체"}:
        paths.append("반도체 업황과 외국인 대형 기술주 수급")
    if values & {"rate", "rates", "yield", "inflation", "cpi", "ppi", "fomc", "monetary", "policy", "금리", "물가", "정책", "국채"}:
        paths.append("글로벌 금리·달러와 국내 성장주 밸류에이션")
    if values & {"oil", "energy", "유가", "에너지", "이란", "중동", "호르무즈"}:
        paths.append("수입물가·정유화학·운송 업종의 비용과 마진")
    if values & {"china", "trade", "tariff", "sanction", "중국", "대만", "관세", "제재", "수출"}:
        paths.append("중국 민감 수출주와 공급망·위험선호")
    if values & {"employment", "payroll", "unemployment", "gdp", "recession"}:
        paths.append("미국 경기 기대와 외국인 위험자산 선호")
    if values & {"국무회의", "비상경제", "경제성장전략", "재정"}:
        paths.append("정부 예산·규제·정책금융과 국내 산업별 실적 기대")
    if values & {"공시", "실적", "영업이익", "매출", "수주", "공급계약", "증자", "유상증자", "무상증자", "인수합병", "합병", "생산중단", "설비투자"}:
        paths.append("국내 기업의 주문·자금조달·생산과 다음 거래일 이익 기대")
    if values & {"배터리", "조선", "자동차", "바이오", "방산", "원전"}:
        paths.append("국내 주력 산업의 수주·가동률·공급망과 실적 기대")
    return " / ".join(paths) if paths else "달러·글로벌 위험선호를 통한 국내시장 간접 영향"


def insight_evidence(terms: list[str], independent_sources: int) -> dict:
    """Map collected terms to the user's active MI principles without scoring."""
    values = set(terms)
    candidates = ["MI-001", "MI-008", "MI-009"]
    if values & {"earnings", "profit", "revenue", "guidance", "revision", "revisions", "실적", "영업이익", "매출"}:
        candidates.append("MI-002")
    if values & {"order", "orders", "inventory", "price", "supply", "demand", "capex", "margin", "semiconductor", "chip", "수주", "공급계약", "생산중단", "설비투자", "반도체", "배터리", "조선", "자동차", "바이오", "방산", "원전"}:
        candidates.append("MI-003")
    if values & {"recession", "credit", "liquidity"}:
        candidates.append("MI-004")
    if values & {"breadth", "valuation"}:
        candidates.append("MI-005")
    if values & {
        "rate", "rates", "inflation", "cpi", "ppi", "employment", "payroll",
        "unemployment", "oil", "yield", "currency", "dollar", "futures", "options",
        "basis", "credit", "geopolitical",
    }:
        candidates.append("MI-006")
    candidates.append("MI-007")
    return {
        "principle_candidates": list(dict.fromkeys(candidates)),
        "evidence_level": "CROSS_CHECKED" if independent_sources >= 2 else "SINGLE_SOURCE",
        "required_confirmation": ["관련 자산 가격 반응", "미래 이익 또는 산업 사이클 데이터", "국내 수급·환율 전이"],
        "invalidation": ["독립 출처의 반증", "후속 지표와 가격 반응의 불일치"],
    }


def market_view(markets: list[dict]) -> dict:
    eligible = {x["symbol"]: x for x in markets if x.get("ok") and x.get("usable_for_score")}
    missing = sorted(CORE_MARKETS - set(eligible))
    complete = not missing
    changes = {symbol: x.get("change_pct") for symbol, x in eligible.items()}
    positives = sum(1 for value in changes.values() if isinstance(value, (int, float)) and value > 0)
    negatives = sum(1 for value in changes.values() if isinstance(value, (int, float)) and value < 0)
    price_state = "UNKNOWN" if not complete else "RISK_ON" if positives == len(changes) else "RISK_OFF" if negatives == len(changes) else "MIXED"
    return {
        "market_data_complete": complete, "missing_core_markets": missing,
        "completed_core_changes": changes,
        "price_confirmation_state": price_state,
        "base_scenario": "판단 유보 — 미국 핵심지수 완료 세션 미확인" if not complete else "가격 데이터만으로 방향 결론을 내리지 않고 Codex 분석에서 교차확인",
        "invalidation": ["원달러 방향 급변", "외국인 선물 수급 반전", "미국 지수선물의 야간 방향 반전"],
    }


def render_report(
    report_date: str,
    events: list[dict],
    markets: list[dict],
    view: dict,
    statuses: list[dict],
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    macro: dict | None = None,
) -> str:
    del markets, view, window_start, window_end, macro
    failed = [x["source_id"] for x in statuses if not x.get("ok")]
    return f"""# 우리의 모닝브리핑 | {report_date}

## 분석 상태

Codex 구조화 분석이 완료되지 않아 시장 판단과 외부 발행을 차단했습니다.

- 수집 사건: {len(events)}개
- 실패 출처: {', '.join(failed) if failed else '없음'}

## 판단 무효화 조건

- 분석 결과가 없거나 스키마·근거 검증을 통과하지 못한 상태에서는 모든 결론을 무효로 봅니다.

## 투자 유의사항

이 글은 정보 정리와 자체 연구를 위한 자료이며 투자 권유가 아닙니다.
"""


def quality_check(events: list[dict], markets: list[dict], statuses: list[dict], report: str,
                  macro: dict | None = None, analysis: dict | None = None,
                  analysis_meta: dict | None = None, market_session_expected: bool = True) -> dict:
    view = market_view(markets)
    macro = macro or {"series": {}}
    macro_series = macro.get("series", {})
    direct_statuses = [x for x in statuses if x.get("source_mode") == "direct"]
    checks = {
        "at_least_one_source_ok": any(x["ok"] for x in statuses),
        "at_least_one_direct_source_ok": any(x.get("ok") and x.get("items", 0) > 0 for x in direct_statuses) if direct_statuses else True,
        "market_coverage": sum(bool(x.get("ok")) for x in markets) >= 4,
        "market_data_complete": view["market_data_complete"] or not market_session_expected,
        "macro_dashboard_complete": all(macro_series.get(key, {}).get("ok") for key in ("us_cpi_yoy", "fed_target_upper", "fed_target_lower")),
        "fresh_relevant_event": bool(events),
        "verified_event": any(e.get("verified") for e in events),
        "events_have_transmission": all(bool(e.get("korea_transmission")) for e in events),
        "events_have_insight_evidence": bool(events) and all(bool(e.get("insight_evidence", {}).get("principle_candidates")) for e in events),
        "has_source_links": (not events) or all(e["sources"] for e in events),
        "has_disclaimer": "투자 권유가 아닙니다" in report,
        "has_invalidation": "판단 무효화 조건" in report,
        "codex_analysis_complete": bool(analysis) and (analysis_meta or {}).get("status") == "COMPLETED",
        "uses_our_principles": bool(analysis and analysis.get("applied_principles")),
        "required_horizons": bool(analysis) and {x.get("horizon") for x in analysis.get("scenarios", [])} == {"NEXT_SESSION", "SWING_1_4W", "MEDIUM_1_6M"},
        "no_named_external_lens": not re.search(r"(?i)(체슬리\s*관점|AP\s*관점|Chesley\s+(view|lens))", report),
        "no_secrets": not re.search(r"(?i)(client_secret|refresh_token|api_key)\s*[:=]\s*\S+", report),
    }
    return {"passed": all(checks.values()), "checks": checks}


def git_publish(repo: Path, report_date: str, report: str, payload: dict) -> str:
    month = report_date[:7]
    target = repo / "reports" / month
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{report_date}-outlook.md").write_text(report, encoding="utf-8")
    atomic_json(target / f"{report_date}-outlook.json", payload)
    subprocess.run(["git", "-C", str(repo), "add", "reports"], check=True)
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        return "UNCHANGED"
    subprocess.run(["git", "-C", str(repo), "commit", "-m", f"report: {report_date} morning outlook"], check=True)
    subprocess.run(["git", "-C", str(repo), "push"], check=True)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def blogger_publish(title: str, content: str, prior_post_id: str | None = None) -> dict:
    from .blogger_render import render_blogger_html

    required = ["BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"]
    missing = [x for x in required if not os.getenv(x)]
    if missing:
        raise RuntimeError("missing Blogger environment: " + ", ".join(missing))
    token_body = urllib.parse.urlencode({"client_id":os.environ["BLOGGER_CLIENT_ID"], "client_secret":os.environ["BLOGGER_CLIENT_SECRET"], "refresh_token":os.environ["BLOGGER_REFRESH_TOKEN"], "grant_type":"refresh_token"}).encode()
    token_req = urllib.request.Request("https://oauth2.googleapis.com/token", data=token_body, method="POST")
    token = json.loads(urllib.request.urlopen(token_req, timeout=30).read())["access_token"]
    blog_id = os.environ["BLOGGER_BLOG_ID"]
    if prior_post_id:
        url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/{prior_post_id}"
        method = "PUT"
    else:
        url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/"
        method = "POST"
    body = json.dumps({"kind":"blogger#post", "title":title, "content":render_blogger_html(content)}).encode()
    req = urllib.request.Request(url, data=body, method=method, headers={"Authorization":"Bearer " + token, "Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())
