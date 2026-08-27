from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .core import atomic_json, load_json

KST = ZoneInfo("Asia/Seoul")
IMPORTANCE_SCORE = {"S+": 5, "S": 4, "A": 3, "B": 2, "C": 1}
SCORE_IMPORTANCE = {5: "S+", 4: "S", 3: "A", 2: "B", 1: "C"}
MONTHS = {name: idx for idx, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1
)}


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return " ".join(self.parts)


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def _fetch_text(url: str, *, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MarketMorningPublisher/1.6.5.6; +https://mmorningbriefing.blogspot.com/)",
        "Accept": "text/calendar,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def _rule_for_title(title: str, rules: list[dict]) -> dict | None:
    lowered = title.casefold()
    for rule in rules:
        if str(rule.get("contains", "")).casefold() in lowered:
            return rule
    return None


def _stable_event_id(source_id: str, title: str) -> str:
    key = re.sub(r"\s+", " ", title.strip().casefold())
    return f"{source_id}_{hashlib.sha1((source_id + '|' + key).encode()).hexdigest()[:14]}"


def _normalize_event(*, source: dict, title: str, scheduled: datetime, rule: dict,
                     source_url: str | None = None, raw_uid: str | None = None) -> dict:
    scheduled_kst = scheduled.astimezone(KST)
    source_id = str(source.get("id", "UNKNOWN"))
    event_id = _stable_event_id(source_id, title)
    return {
        "event_id": event_id,
        "external_uid": raw_uid,
        "name": title.strip(),
        "event_type": rule.get("event_type", "ECONOMIC_EVENT"),
        "country": "US" if source_id in {"BLS", "BEA", "FED"} else source.get("country", "UNKNOWN"),
        "scheduled_at_kst": scheduled_kst.isoformat(),
        "scheduled_at_source_tz": scheduled.isoformat(),
        "base_importance": rule.get("base_importance", "B"),
        "dynamic_importance": rule.get("base_importance", "B"),
        "korea_relevance": int(rule.get("korea_relevance", 2)),
        "affected_assets": list(rule.get("affected_assets", [])),
        "affected_sectors": list(rule.get("affected_sectors", [])),
        "affected_symbols": list(rule.get("affected_symbols", [])),
        "why_it_matters": rule.get("why_it_matters", "공식 발표 결과가 금리·환율·위험자산 기대를 바꿀 수 있습니다."),
        "korea_transmission": rule.get("korea_transmission", "미국 지표 → 금리/달러 → USD/KRW·외국인 수급 → 한국 증시"),
        "source_id": source_id,
        "source_url": source_url or source.get("url"),
        "source_verified_on": None,
        "status": "SCHEDULED",
    }


def _unfold_ics(text: str) -> list[str]:
    result: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and result:
            result[-1] += raw[1:]
        else:
            result.append(raw)
    return result


def _parse_ics_dt(value: str, params: str, default_tz: str) -> datetime | None:
    value = value.strip()
    tz_name = default_tz
    match = re.search(r"TZID=([^;:]+)", params)
    if match:
        tz_name = match.group(1)
    # BLS currently emits the legacy, non-IANA `US-Eastern` label. Minimal
    # container images may not ship its alias even though America/New_York exists.
    tz_name = {"US-Eastern": "America/New_York", "US/Pacific": "America/Los_Angeles"}.get(tz_name, tz_name)
    try:
        if value.endswith("Z"):
            raw = value[:-1]
            fmt = "%Y%m%dT%H%M%S" if len(raw) == 15 else "%Y%m%dT%H%M"
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        if "T" in value:
            fmt = "%Y%m%dT%H%M%S" if len(value) == 15 else "%Y%m%dT%H%M"
            return datetime.strptime(value, fmt).replace(tzinfo=ZoneInfo(tz_name))
        return datetime.combine(datetime.strptime(value, "%Y%m%d").date(), time(0, 0), ZoneInfo(tz_name))
    except (ValueError, ZoneInfoNotFoundError):
        return None


def parse_ics_events(text: str, source: dict) -> list[dict]:
    events: list[dict] = []
    current: dict[str, tuple[str, str]] | None = None
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if not current:
                current = None
                continue
            summary = current.get("SUMMARY", ("", ""))[1].replace("\\,", ",").replace("\\n", " ")
            rule = _rule_for_title(summary, source.get("title_rules", []))
            dt_params, dt_value = current.get("DTSTART", ("", ""))
            scheduled = _parse_ics_dt(dt_value, dt_params, source.get("timezone", "UTC")) if dt_value else None
            if summary and rule and scheduled:
                events.append(_normalize_event(
                    source=source, title=summary, scheduled=scheduled, rule=rule,
                    source_url=source.get("url"), raw_uid=current.get("UID", ("", ""))[1] or None,
                ))
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key_part, value = line.split(":", 1)
        key, *params = key_part.split(";")
        current[key] = (";".join(params), value)
    return events


def parse_bea_schedule_events(text: str, source: dict, *, year: int) -> list[dict]:
    parser = _TextCollector()
    parser.feed(text)
    plain = re.sub(r"\s+", " ", parser.text())
    month_pattern = "|".join(MONTHS)
    pattern = re.compile(
        rf"\b({month_pattern})\s+(\d{{1,2}})\s+(\d{{1,2}}:\d{{2}}\s+[AP]M)\s+(?:News|Data|Visual Data|Article)?\s*(.+?)(?=\b(?:{month_pattern})\s+\d{{1,2}}\s+\d{{1,2}}:\d{{2}}\s+[AP]M|\bTo Be Announced\b|$)",
        re.I,
    )
    result: list[dict] = []
    tz = ZoneInfo(source.get("timezone", "America/New_York"))
    for match in pattern.finditer(plain):
        month_name, day_text, clock_text, title = match.groups()
        title = re.sub(r"\s+", " ", title).strip(" |-–")
        rule = _rule_for_title(title, source.get("title_rules", []))
        if not rule:
            continue
        try:
            clock = datetime.strptime(clock_text.upper(), "%I:%M %p").time()
            scheduled = datetime(year, MONTHS[month_name.title()], int(day_text), clock.hour, clock.minute, tzinfo=tz)
        except ValueError:
            continue
        result.append(_normalize_event(source=source, title=title, scheduled=scheduled, rule=rule))
    return result



def _plain_text(text: str) -> str:
    parser = _TextCollector()
    parser.feed(text)
    return re.sub(r"\s+", " ", parser.text()).strip()


def _policy_event(*, event_id: str, name: str, event_type: str, country: str, scheduled: datetime,
                  base_importance: str, korea_relevance: int, source_id: str, source_url: str,
                  why_it_matters: str, korea_transmission: str, affected_assets: list[str],
                  affected_sectors: list[str], time_precision: str | None = None) -> dict:
    item = {
        "event_id": event_id,
        "name": name,
        "event_type": event_type,
        "country": country,
        "scheduled_at_kst": scheduled.astimezone(KST).isoformat(),
        "scheduled_at_source_tz": scheduled.isoformat(),
        "base_importance": base_importance,
        "dynamic_importance": base_importance,
        "korea_relevance": korea_relevance,
        "affected_assets": affected_assets,
        "affected_sectors": affected_sectors,
        "affected_symbols": [],
        "why_it_matters": why_it_matters,
        "korea_transmission": korea_transmission,
        "source_id": source_id,
        "source_url": source_url,
        "source_verified_on": None,
        "status": "SCHEDULED",
    }
    if time_precision:
        item["time_precision"] = time_precision
    return item


def parse_fomc_schedule_events(text: str, source: dict, *, years: list[int]) -> list[dict]:
    plain = _plain_text(text)
    result: list[dict] = []
    months = "|".join(MONTHS)
    tz = ZoneInfo(source.get("timezone", "America/New_York"))
    for year in years:
        start_token = f"{year} FOMC Meetings"
        start = plain.find(start_token)
        if start < 0:
            continue
        next_year_token = f"{year - 1} FOMC Meetings" if year > 2021 else ""
        # The Fed page is normally descending by year; bound the segment at the next section header.
        end_candidates = [pos for token in (next_year_token, f"{year + 1} FOMC Meetings")
                          if token and (pos := plain.find(token, start + len(start_token))) >= 0]
        end = min(end_candidates) if end_candidates else len(plain)
        segment = plain[start:end]
        pattern = re.compile(rf"\b({months})\s+(\d{{1,2}})-(\d{{1,2}})(\*)?(?=\s|$)")
        for match in pattern.finditer(segment):
            month_name, _first_day, decision_day, sep_marker = match.groups()
            try:
                local = datetime(year, MONTHS[month_name], int(decision_day), 14, 0, tzinfo=tz)
            except ValueError:
                continue
            sep = bool(sep_marker)
            month_num = MONTHS[month_name]
            result.append(_policy_event(
                event_id=f"FED_FOMC_{year}_{month_num:02d}",
                name=f"FOMC {year}년 {month_num}월 회의" + (" + SEP" if sep else ""),
                event_type="FOMC", country="US", scheduled=local,
                base_importance="S+", korea_relevance=5, source_id="FED",
                source_url=source["url"],
                why_it_matters="정책금리와 정책 커뮤니케이션이 글로벌 할인율과 달러 방향을 바꿀 수 있습니다.",
                korea_transmission="미국 금리 → 달러/원 → 외국인 수급 → KOSPI 성장주·반도체",
                affected_assets=["US2Y", "US10Y", "DXY", "USD/KRW", "NASDAQ", "KOSPI"],
                affected_sectors=["반도체", "성장주", "금융"],
            ))
    return result


def parse_bok_calendar_events(text: str, source: dict) -> list[dict]:
    plain = _plain_text(text)
    result: list[dict] = []
    # BOK monthly calendar exposes the label and an ISO date in the same rendered page.
    for match in re.finditer(r"통화정책방향\s*회의.*?(20\d{2})-(\d{2})-(\d{2})", plain):
        year, month, day = map(int, match.groups())
        local = datetime(year, month, day, 10, 0, tzinfo=KST)
        result.append(_policy_event(
            event_id=f"BOK_MPC_{year}_{month:02d}_{day:02d}",
            name="한국은행 금융통화위원회 통화정책방향 결정회의",
            event_type="BOK_MPC", country="KR", scheduled=local,
            base_importance="S+", korea_relevance=5, source_id="BOK", source_url=source["url"],
            why_it_matters="기준금리와 향후 경로가 원화·채권·부동산·가계신용·주식 할인율에 직접 영향을 줍니다.",
            korea_transmission="한국은행 정책 → 국내 금리/원화 → 외국인·가계 유동성 → KOSPI/KOSDAQ",
            affected_assets=["KTB", "USD/KRW", "KOSPI", "KOSDAQ"],
            affected_sectors=["금융", "건설", "성장주", "내수"],
            time_precision="DATE_CONFIRMED_TIME_OPERATIONAL_DEFAULT",
        ))
    return result


def parse_boj_schedule_events(text: str, source: dict, *, years: list[int]) -> list[dict]:
    plain = _plain_text(text)
    month_map = {name[:3]: idx for name, idx in MONTHS.items()}
    month_map["Sept"] = 9
    result: list[dict] = []
    for year in years:
        start = plain.find(f"## {year}")
        if start < 0:
            start = plain.find(f"{year} Table : {year}")
        if start < 0:
            start = plain.find(str(year))
        if start < 0:
            continue
        next_pos = plain.find(f"## {year + 1}", start + 1)
        if next_pos < 0:
            next_pos = plain.find(f"{year + 1} Table : {year + 1}", start + 1)
        if next_pos < 0:
            next_pos = plain.find(str(year + 1), start + 4)
        segment = plain[start: next_pos if next_pos >= 0 else len(plain)]
        pattern = re.compile(r"\b(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.?(?:\s+)(\d{1,2})\s*\([^)]*\),\s*(\d{1,2})\s*\([^)]*\)")
        for match in pattern.finditer(segment):
            month_token, _first_day, decision_day = match.groups()
            month = month_map.get(month_token.rstrip('.'))
            if not month:
                continue
            # BOJ does not promise a fixed decision release time; noon is only an operational display time.
            local = datetime(year, month, int(decision_day), 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
            result.append(_policy_event(
                event_id=f"BOJ_MPM_{year}_{month:02d}_{int(decision_day):02d}",
                name="일본은행 금융정책결정회의",
                event_type="BOJ_MPM", country="JP", scheduled=local,
                base_importance="S", korea_relevance=4, source_id="BOJ", source_url=source["url"],
                why_it_matters="엔화와 캐리 포지션 변화가 글로벌 위험자산 및 한국 외국인 수급에 영향을 줄 수 있습니다.",
                korea_transmission="BOJ 정책 → 엔화/캐리 → 글로벌 레버리지 → 한국 외국인 수급",
                affected_assets=["USD/JPY", "JGB", "KOSPI"],
                affected_sectors=["수출주", "금융", "성장주"],
                time_precision="DATE_CONFIRMED_TIME_OPERATIONAL_DEFAULT",
            ))
    return result


def parse_ecb_schedule_events(text: str, source: dict) -> list[dict]:
    plain = _plain_text(text)
    result: list[dict] = []
    tz = ZoneInfo(source.get("timezone", "Europe/Berlin"))
    pattern = re.compile(
        r"\b(\d{2})/(\d{2})/(20\d{2})\s+Governing Council of the ECB:\s+monetary policy meeting.*?\(Day 2\),\s+followed by press conference",
        re.I,
    )
    for match in pattern.finditer(plain):
        day, month, year = map(int, match.groups())
        local = datetime(year, month, day, 14, 15, tzinfo=tz)
        result.append(_policy_event(
            event_id=f"ECB_MPC_{year}_{month:02d}_{day:02d}",
            name="ECB 통화정책회의 및 기자회견",
            event_type="ECB_MPC", country="EU", scheduled=local,
            base_importance="A", korea_relevance=3, source_id="ECB", source_url=source["url"],
            why_it_matters="유럽 금리 경로가 달러와 글로벌 금리 상대가치에 영향을 줍니다.",
            korea_transmission="ECB 정책 → EUR/USD·DXY → USD/KRW → 한국 수급",
            affected_assets=["EUR/USD", "DXY", "GLOBAL_RATES"],
            affected_sectors=["수출주", "성장주"],
            time_precision="DATE_CONFIRMED_TIME_ESTIMATED",
        ))
    return result


def parse_official_forward_events(text: str, source: dict, *, year: int) -> list[dict]:
    """Conservative adapter for official forward-calendar pages.

    Only dated text matching a configured title rule is admitted. A page fetch with
    no recognized rows is surfaced by minimum_items health checks, never silently
    treated as a healthy empty calendar.
    """
    plain = _plain_text(text)
    tz = ZoneInfo(source.get("timezone", "America/New_York"))
    result: list[dict] = []
    patterns = (
        re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:,\s*|\s+)(20\d{2})\b", re.I),
        re.compile(r"\b(20\d{2})[-/]([01]?\d)[-/]([0-3]?\d)\b"),
    )
    for pattern in patterns:
        for match in pattern.finditer(plain):
            groups = match.groups()
            if groups[0].isdigit():
                yy, month, day = map(int, groups)
            else:
                month, day, yy = MONTHS.get(groups[0].title()), int(groups[1]), int(groups[2])
            if not month or yy < year - 1 or yy > year + 2:
                continue
            context = plain[max(0, match.start() - 140): min(len(plain), match.end() + 220)]
            rule = _rule_for_title(context, source.get("title_rules", []))
            if not rule:
                continue
            try:
                scheduled = datetime(yy, month, day, int(source.get("default_hour", 9)), 0, tzinfo=tz)
            except ValueError:
                continue
            title = str(rule.get("name") or rule.get("contains") or source.get("name"))
            item = _normalize_event(source=source, title=f"{title} {yy}-{month:02d}-{day:02d}", scheduled=scheduled, rule=rule)
            item["time_precision"] = "DATE_CONFIRMED_TIME_OPERATIONAL_DEFAULT"
            result.append(item)
    return list({row["event_id"]: row for row in result}.values())


def _normalize_seed_event(row: dict) -> dict:
    item = dict(row)
    item.setdefault("status", "SCHEDULED")
    item.setdefault("dynamic_importance", item.get("base_importance", "B"))
    item.setdefault("korea_relevance", 2)
    item.setdefault("affected_assets", [])
    item.setdefault("affected_sectors", [])
    item.setdefault("affected_symbols", [])
    return item


def _event_time(item: dict) -> datetime | None:
    value = item.get("scheduled_at_kst")
    try:
        return datetime.fromisoformat(str(value)).astimezone(KST) if value else None
    except ValueError:
        return None


def apply_dynamic_importance(event: dict, *, as_of_kst: datetime) -> dict:
    item = dict(event)
    scheduled = _event_time(item)
    base = IMPORTANCE_SCORE.get(str(item.get("base_importance", "B")), 2)
    relevance = max(1, min(5, int(item.get("korea_relevance", 2))))
    score = base
    if scheduled:
        hours = (scheduled - as_of_kst).total_seconds() / 3600
        if -6 <= hours <= 36 and relevance >= 4:
            score += 1
        elif 36 < hours <= 24 * 7 and relevance == 5 and base >= 3:
            score += 1
        item["hours_until"] = round(hours, 1)
        item["days_until"] = int(hours // 24) if hours >= 0 else -1
    score = max(1, min(5, score))
    item["dynamic_importance"] = SCORE_IMPORTANCE[score]
    return item


def merge_calendar(existing: list[dict], observed: list[dict], *, now: datetime) -> list[dict]:
    by_id = {str(x.get("event_id")): dict(x) for x in existing if x.get("event_id")}
    now_text = _now_iso(now)
    for row in observed:
        event_id = str(row.get("event_id"))
        old = by_id.get(event_id)
        merged = dict(old or {})
        old_schedule = merged.get("scheduled_at_kst")
        merged.update(row)
        merged["first_seen_at"] = (old or {}).get("first_seen_at", now_text)
        merged["last_verified_at"] = now_text
        if old and old_schedule and old_schedule != row.get("scheduled_at_kst"):
            merged["previous_scheduled_at_kst"] = old_schedule
            merged["changed_at"] = now_text
            merged["status"] = "SCHEDULE_CHANGED"
        else:
            merged.setdefault("changed_at", None)
        by_id[event_id] = merged
    return sorted(by_id.values(), key=lambda x: x.get("scheduled_at_kst", "9999"))


def select_upcoming(events: list[dict], *, as_of_kst: datetime, horizon_days: int, limit: int) -> list[dict]:
    cutoff = as_of_kst + timedelta(days=horizon_days)
    rows = []
    for event in events:
        scheduled = _event_time(event)
        if not scheduled or scheduled < as_of_kst - timedelta(hours=6) or scheduled > cutoff:
            continue
        rows.append(apply_dynamic_importance(event, as_of_kst=as_of_kst))
    return sorted(
        rows,
        key=lambda x: (-IMPORTANCE_SCORE.get(x.get("dynamic_importance", "B"), 2), x.get("scheduled_at_kst", "")),
    )[:limit]


def refresh_calendar(root: Path, *, as_of: datetime, fetcher: Callable[[str], str] = _fetch_text) -> dict:
    config = load_json(root / "config/event_intelligence.json", {})
    state_dir = root / "data/state/event_intelligence"
    state_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = state_dir / "calendar.json"
    existing = load_json(ledger_path, {}).get("events", [])
    observed = [_normalize_seed_event(x) for x in config.get("seed_events", [])]
    statuses: list[dict] = []
    current_year = as_of.astimezone(KST).year
    for source in config.get("calendar_sources", []):
        if not source.get("enabled", True):
            continue
        try:
            kind = source.get("kind")
            if kind == "BOK_HTML_MONTHS":
                rows = []
                cursor = as_of.astimezone(KST).date().replace(day=1)
                months_ahead = max(1, int(source.get("months_ahead", 6)))
                for offset in range(months_ahead):
                    month_index = cursor.month - 1 + offset
                    year = cursor.year + month_index // 12
                    month = month_index % 12 + 1
                    url = source["url_template"].format(year=year, month=month)
                    rows.extend(parse_bok_calendar_events(fetcher(url), {**source, "url": url}))
            else:
                try:
                    raw = fetcher(source["url"])
                    used_fallback = False
                except Exception:
                    fallback_template = source.get("fallback_url_template")
                    if not fallback_template:
                        raise
                    raw = fetcher(str(fallback_template).format(year=current_year))
                    used_fallback = True
                if kind == "ICS":
                    rows = (parse_official_forward_events(raw, source, year=current_year)
                            if used_fallback else parse_ics_events(raw, source))
                elif kind == "BEA_HTML":
                    rows = parse_bea_schedule_events(raw, source, year=current_year)
                elif kind == "FED_FOMC_HTML":
                    rows = parse_fomc_schedule_events(raw, source, years=[current_year, current_year + 1])
                elif kind == "BOJ_HTML":
                    rows = parse_boj_schedule_events(raw, source, years=[current_year, current_year + 1])
                elif kind == "ECB_HTML":
                    rows = parse_ecb_schedule_events(raw, source)
                elif kind in {"TREASURY_FORWARD_HTML", "KC_FED_FORWARD_HTML", "CONGRESS_FORWARD_HTML", "FEC_FORWARD_HTML"}:
                    rows = parse_official_forward_events(raw, source, year=current_year)
                else:
                    raise ValueError(f"unsupported calendar source kind: {kind}")
            minimum = int(source.get("minimum_items", 0))
            if len(rows) < minimum:
                raise ValueError(f"calendar health failure: {source.get('id')} returned {len(rows)} rows, minimum={minimum}")
            observed.extend(rows)
            statuses.append({"source_id": f"event_calendar_{source['id'].lower()}", "source_mode": "event_official", "ok": True, "items": len(rows), "required": bool(source.get("required", True))})
        except Exception as exc:  # network/calendar changes must not erase the prior ledger
            required = bool(source.get("required", True))
            statuses.append({"source_id": f"event_calendar_{source.get('id','unknown').lower()}", "source_mode": "event_official", "ok": False, "required": required, "severity": "FAIL" if required else "WARN", "error": str(exc)[:300]})
    merged = merge_calendar(existing, observed, now=as_of)
    payload = {"schema_version": 1, "contract": "MMP_EVENT_CALENDAR_LEDGER_V1", "updated_at": _now_iso(as_of), "events": merged}
    atomic_json(ledger_path, payload)
    return {"calendar": payload, "statuses": statuses}


def build_event_calendar_context(root: Path, *, as_of: datetime, refresh: bool = True,
                                 fetcher: Callable[[str], str] = _fetch_text) -> dict:
    config = load_json(root / "config/event_intelligence.json", {})
    state_path = root / "data/state/event_intelligence/calendar.json"
    statuses: list[dict] = []
    if refresh:
        refreshed = refresh_calendar(root, as_of=as_of, fetcher=fetcher)
        ledger = refreshed["calendar"]
        statuses.extend(refreshed["statuses"])
    else:
        ledger = load_json(state_path, {"events": config.get("seed_events", [])})
    as_of_kst = as_of.astimezone(KST)
    upcoming = select_upcoming(
        ledger.get("events", []), as_of_kst=as_of_kst,
        horizon_days=int(config.get("horizon_days", 180)), limit=int(config.get("max_calendar_items", 40)),
    )
    critical_days = int(config.get("critical_horizon_days", 7))
    critical = [x for x in upcoming if (x.get("hours_until") is not None and x["hours_until"] <= critical_days * 24)
                and IMPORTANCE_SCORE.get(x.get("dynamic_importance", "B"), 2) >= 3]
    lifecycle = load_json(root / "data/state/event_intelligence/event_lifecycle.json", {"events": []})
    rumor_watch = load_json(root / "data/state/event_intelligence/rumor_watch.json", {"rows": []})
    calendar_overlay = load_json(root / "data/state/event_intelligence/calendar_overlay.json", {"rows": []})
    source_performance = load_json(root / "data/state/event_intelligence/source_performance.json", {"rows": []})
    active_events = [
        event for event in lifecycle.get("events", [])
        if event.get("status") in {"VERIFIED", "ACTIVE", "RESOLVING"}
    ]
    return {
        "contract": "MMP_EVENT_CALENDAR_CONTEXT_V1",
        "as_of_kst": as_of_kst.isoformat(),
        "upcoming_events": upcoming,
        "critical_upcoming_events": critical,
        "active_events": active_events,
        "rumor_watch": rumor_watch.get("rows", []),
        "calendar_overlay": calendar_overlay.get("rows", []),
        "source_provenance": source_performance.get("rows", []),
        "statuses": statuses,
    }
