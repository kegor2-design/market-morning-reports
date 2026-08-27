from __future__ import annotations

import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .core import atomic_json, insight_evidence, load_json, transmission_path

KST = ZoneInfo("Asia/Seoul")

CATEGORY_RULES = [
    ("DISTRESS", "S+", ("횡령", "배임", "회생절차", "파산", "상장폐지", "영업정지", "생산중단", "거래정지")),
    ("CAPITAL", "S", ("유상증자", "감자", "전환사채", "신주인수권부사채", "교환사채")),
    ("M_AND_A", "S", ("합병", "분할", "영업양수", "영업양도", "최대주주", "경영권")),
    ("CONTRACT", "S", ("단일판매", "공급계약", "계약해지")),
    ("EARNINGS", "S", ("잠정실적", "매출액또는손익구조", "영업실적")),
    ("CAPITAL_RETURN", "A", ("자기주식", "현금배당", "주식배당", "무상증자")),
    ("INVESTMENT", "A", ("타법인주식", "시설투자", "신규시설")),
    ("LEGAL", "A", ("소송", "제재", "과징금")),
]



class _DisclosureTextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return " ".join(self.parts)


def _fetch_bytes(url: str, params: dict, *, timeout: int = 40) -> bytes:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "MarketMorningPublisher/1.6.5 (+DART document)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _safe_error(exc: Exception) -> str:
    text = str(exc)[:600]
    text = re.sub(r"(?i)(crtfc_key=)[^&\s]+", r"\1***", text)
    text = re.sub(r"(?i)(api[_-]?key[=:]\s*)[^&\s]+", r"\1***", text)
    return text[:300]


def _decode_document(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_dart_document_evidence(payload: bytes, *, keywords: list[str], max_chars: int = 2200) -> str:
    if not payload:
        return ""
    candidates: list[bytes] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                lower = info.filename.lower()
                if info.is_dir() or not lower.endswith((".xml", ".html", ".htm", ".txt")):
                    continue
                try:
                    candidates.append(archive.read(info))
                except Exception:
                    continue
    except zipfile.BadZipFile:
        candidates = [payload]
    if not candidates:
        return ""
    # Prefer the largest body because DART packages can contain small metadata XML files alongside the filing body.
    raw = max(candidates, key=len)
    text = _decode_document(raw)
    parser = _DisclosureTextCollector()
    try:
        parser.feed(text)
        plain = parser.text()
    except Exception:
        plain = re.sub(r"<[^>]+>", " ", text)
    plain = re.sub(r"\s+", " ", plain).strip()
    excerpts: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        start = 0
        while True:
            pos = plain.find(keyword, start)
            if pos < 0:
                break
            excerpt = plain[max(0, pos - 45): min(len(plain), pos + len(keyword) + 180)].strip(" |:-")
            compact = re.sub(r"\s+", " ", excerpt)
            if compact and compact not in seen:
                seen.add(compact)
                excerpts.append(compact)
            if sum(len(x) for x in excerpts) >= max_chars or len(excerpts) >= 12:
                break
            start = pos + len(keyword)
        if sum(len(x) for x in excerpts) >= max_chars or len(excerpts) >= 12:
            break
    if not excerpts:
        return plain[:max_chars]
    return " / ".join(excerpts)[:max_chars]

def _fetch_json(url: str, params: dict, *, timeout: int = 40) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "MarketMorningPublisher/1.6.5 (+DART disclosure)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_company_name(name: str) -> str:
    text = re.sub(r"\s+", "", name or "")
    text = re.sub(r"^(주식회사|\(주\)|㈜)", "", text)
    text = re.sub(r"(주식회사|\(주\)|㈜)$", "", text)
    return text.casefold()


def build_equity_lookup(rows: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_corp, by_name = {}, {}
    for row in rows:
        corp = str(row.get("dart_corp_code") or "").strip()
        if corp:
            by_corp[corp] = row
        name = str(row.get("name") or row.get("corp_name") or "").strip()
        if name:
            by_name[_normalize_company_name(name)] = row
    return by_corp, by_name


def classify_disclosure(report_name: str) -> dict | None:
    compact = re.sub(r"\s+", "", report_name or "")
    for category, importance, keywords in CATEGORY_RULES:
        matched = [keyword for keyword in keywords if keyword in compact]
        if matched:
            return {"category": category, "importance": importance, "matched_keywords": matched}
    return None


def normalize_disclosure(row: dict, *, equity_master: list[dict]) -> dict | None:
    classification = classify_disclosure(str(row.get("report_nm", "")))
    if not classification:
        return None
    by_corp, by_name = build_equity_lookup(equity_master)
    equity = by_corp.get(str(row.get("corp_code") or "")) or by_name.get(_normalize_company_name(str(row.get("corp_name", ""))))
    rcept_no = str(row.get("rcept_no") or "")
    rcept_dt = str(row.get("rcept_dt") or "")
    date_text = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}" if len(rcept_dt) == 8 else "UNKNOWN"
    report_name = str(row.get("report_nm") or "").strip()
    correction = bool(str(row.get("rm") or "").strip()) or any(token in report_name for token in ("기재정정", "첨부정정", "정정"))
    return {
        "disclosure_id": f"DART-{rcept_no}",
        "receipt_no": rcept_no,
        "receipt_date": date_text,
        "announced_at_kst": f"{date_text} 시간 미제공" if date_text != "UNKNOWN" else "UNKNOWN",
        "session_relation": "PREVIOUS_OR_PREOPEN_DISCLOSURE_TIME_UNKNOWN",
        "corp_code": row.get("corp_code"),
        "corp_name": row.get("corp_name"),
        "corp_class": row.get("corp_cls"),
        "symbol": equity.get("symbol") if equity else None,
        "market": equity.get("market") if equity else ("KOSPI" if row.get("corp_cls") == "Y" else "KOSDAQ" if row.get("corp_cls") == "K" else None),
        "report_name": report_name,
        "category": classification["category"],
        "importance": classification["importance"],
        "matched_keywords": classification["matched_keywords"],
        "is_correction": correction,
        "source": "OpenDART",
        "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
        "verification_level": "OFFICIAL",
        "fact_scope": "공시 제목과 접수 사실만 자동 확정. 금액·조건·실적 영향은 원문 확인 후 판단.",
    }


def collect_dart_disclosures(root: Path, *, as_of: datetime,
                             fetcher: Callable[[str, dict], dict] = _fetch_json,
                             document_fetcher: Callable[[str, dict], bytes] = _fetch_bytes) -> dict:
    config = load_json(root / "config/event_intelligence.json", {})
    disclosure_cfg = config.get("disclosures", {})
    if not disclosure_cfg.get("enabled", True):
        return {"contract": "MMP_DART_DISCLOSURES_V1", "rows": [], "statuses": []}
    key = os.getenv("OPENDART_API_KEY") or os.getenv("DART_API_KEY")
    if not key:
        return {
            "contract": "MMP_DART_DISCLOSURES_V1", "rows": [],
            "statuses": [{"source_id": "opendart_disclosures", "source_mode": "event_official", "ok": False, "error": "OPENDART_API_KEY/DART_API_KEY missing"}],
        }
    as_of_kst = as_of.astimezone(KST)
    lookback = max(1, int(disclosure_cfg.get("lookback_calendar_days", 2)))
    start = (as_of_kst.date() - timedelta(days=lookback)).strftime("%Y%m%d")
    end = as_of_kst.date().strftime("%Y%m%d")
    page_count = max(10, min(100, int(disclosure_cfg.get("page_count", 100))))
    max_pages = max(1, int(disclosure_cfg.get("max_pages", 20)))
    raw_rows: list[dict] = []
    status: dict = {"source_id": "opendart_disclosures", "source_mode": "event_official", "ok": True, "items": 0}
    try:
        for page in range(1, max_pages + 1):
            payload = fetcher(disclosure_cfg.get("url", "https://opendart.fss.or.kr/api/list.json"), {
                "crtfc_key": key, "bgn_de": start, "end_de": end, "page_no": page,
                "page_count": page_count, "sort": "date", "sort_mth": "desc", "last_reprt_at": "N",
            })
            code = str(payload.get("status", ""))
            if code == "013":  # no data
                break
            if code and code != "000":
                raise RuntimeError(f"OpenDART list.json: {code} {payload.get('message','')}")
            rows = payload.get("list", []) or []
            raw_rows.extend(rows)
            total_page = int(payload.get("total_page") or 1)
            if page >= total_page or not rows:
                break
    except Exception as exc:
        status.update({"ok": False, "error": _safe_error(exc)})
    equity_master = load_json(root / "data/private/reference/korea_equity_master.json", {}).get("rows", [])
    allowed_classes = set(disclosure_cfg.get("corp_classes", ["Y", "K"]))
    normalized = []
    seen = set()
    for raw in raw_rows:
        if raw.get("corp_cls") not in allowed_classes:
            continue
        item = normalize_disclosure(raw, equity_master=equity_master)
        if not item or item["receipt_no"] in seen:
            continue
        seen.add(item["receipt_no"])
        normalized.append(item)
    importance_order = {"S+": 0, "S": 1, "A": 2, "B": 3}
    normalized.sort(
        key=lambda x: (importance_order.get(x["importance"], 9), -int((x.get("receipt_date") or "0000-00-00").replace("-", "") or 0), -int(x.get("receipt_no") or 0)),
        reverse=False,
    )
    document_status = {"source_id": "opendart_documents", "source_mode": "event_official_detail", "ok": True, "attempted": 0, "enriched": 0, "errors": 0}
    if disclosure_cfg.get("enrich_original_document", True):
        max_documents = max(0, min(20, int(disclosure_cfg.get("max_document_fetches", 8))))
        keywords = list(disclosure_cfg.get("detail_keywords", []))
        max_chars = max(500, min(5000, int(disclosure_cfg.get("detail_excerpt_chars", 2200))))
        document_url = disclosure_cfg.get("document_url", "https://opendart.fss.or.kr/api/document.xml")
        for item in normalized[:max_documents]:
            if not item.get("receipt_no"):
                continue
            document_status["attempted"] += 1
            try:
                binary = document_fetcher(document_url, {"crtfc_key": key, "rcept_no": item["receipt_no"]})
                excerpt = extract_dart_document_evidence(binary, keywords=keywords, max_chars=max_chars)
                if excerpt:
                    item["original_document_evidence"] = excerpt
                    item["document_verification"] = "OFFICIAL_ORIGINAL_DOCUMENT"
                    item["fact_scope"] = "공시 제목·접수 사실과 original_document_evidence에 포함된 원문 문구까지 자동 확인. 문구 밖의 수치·조건은 추가 원문 확인 필요."
                    document_status["enriched"] += 1
            except Exception as exc:
                document_status["errors"] += 1
                item["document_verification"] = "DOCUMENT_FETCH_FAILED"
                item["document_error"] = _safe_error(exc)
        if document_status["attempted"] and document_status["enriched"] == 0 and document_status["errors"]:
            document_status["ok"] = False
    status["items"] = len(normalized)
    state_dir = root / "data/state/event_intelligence"
    state_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1, "contract": "MMP_DART_DISCLOSURES_V1",
        "updated_at": as_of.astimezone(timezone.utc).isoformat(), "window": {"start_date": start, "end_date": end},
        "rows": normalized, "statuses": [status, document_status],
    }
    atomic_json(state_dir / "disclosures.json", result)
    return result


def disclosure_news_events(rows: list[dict], *, limit: int = 20) -> list[dict]:
    events = []
    for item in rows[:limit]:
        symbol_text = f" ({item['symbol']})" if item.get("symbol") else ""
        headline = f"{item.get('corp_name','UNKNOWN')}{symbol_text} · {item.get('report_name','공시')}"
        terms = ["공시"] + list(item.get("matched_keywords", []))
        events.append({
            "event_id": item["disclosure_id"],
            "headline": headline,
            "evidence_summary": (
                f"OpenDART 공식 접수: {item.get('report_name')}. 접수일 {item.get('receipt_date')}. "
                + (f"공시 원문 근거문구: {item.get('original_document_evidence')}" if item.get('original_document_evidence')
                   else "자동판정 범위는 공시 제목·접수 사실까지이며 세부 금액과 실적 영향은 원문 확인이 필요합니다.")
            ),
            "verified": True,
            "verification_reason": "OpenDART 공식 공시 목록",
            "countries": ["KR"],
            "strategic_topics": [],
            "market_terms": terms,
            "korea_transmission": transmission_path(terms),
            "insight_evidence": insight_evidence(terms, 1),
            "source_priority": 1,
            "has_direct_source": True,
            "importance_score": {"S+": 95, "S": 88, "A": 78}.get(item.get("importance"), 70),
            "sources": [{
                "source": "OpenDART", "title": headline, "url": item.get("source_url"),
                "source_mode": "direct", "source_tier": 1, "feed": "Korea official disclosure",
                "published_at": item.get("announced_at_kst"),
            }],
            "event_type": "OFFICIAL_DISCLOSURE",
            "disclosure": item,
        })
    return events
