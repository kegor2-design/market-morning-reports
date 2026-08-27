#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "youtube_sources/kpunch"
OUTPUT_JSON = ROOT / "insight/kpunch_insight_ledger.json"
OUTPUT_MD = ROOT / "insight/kpunch_insight_ledger.md"

DIRECT_COLUMNS = {
    "kospi": ("public/market-history/data/korea-market-monthly.csv", "kospi", "index"),
    "usdkrw": ("public/market-history/data/korea-market-monthly.csv", "usdkrw", "KRW/USD"),
    "kr_cpi": ("public/market-history/data/macro-cpi-rates-monthly.csv", "kr_cpi", "index"),
    "kr3y": ("public/market-history/data/macro-cpi-rates-monthly.csv", "kr3y", "%"),
    "kr10y": ("public/market-history/data/macro-cpi-rates-monthly.csv", "kr10y", "%"),
    "kr30y": ("public/market-history/data/macro-cpi-rates-monthly.csv", "kr30y", "%"),
    "us10y": ("public/market-history/data/macro-cpi-rates-monthly.csv", "us10y", "%"),
    "us30y": ("public/market-history/data/macro-cpi-rates-monthly.csv", "us30y", "%"),
    "kr_debt_gdp": ("public/market-history/data/imf-government-debt-annual.csv", "KOR", "% GDP"),
    "bok_base_rate": ("public/market-history/data/macro-cpi-rates-monthly.csv", "bok_base_rate", "%"),
    "fx_reserves": ("public/market-history/data/macro-cpi-rates-monthly.csv", "fx_reserves", "USD thousand"),
    "reer_kr": ("public/market-history/data/macro-cpi-rates-monthly.csv", "kr_reer", "index"),
    "seoul_house_price": ("public/market-history/data/macro-cpi-rates-monthly.csv", "seoul_house_price", "index"),
    "sovereign_issuance": ("public/market-history/data/macro-cpi-rates-monthly.csv", "sovereign_issuance", "KRW billion/month"),
}
DERIVED = {"kr_cpi_yoy", "kr_us_10y_gap", "kospi_usd_real", "kr_m2_yoy", "us_m2_yoy", "credit_spread"}


def load_csv(relative: str) -> list[dict[str, str]]:
    with (ROOT / relative).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def last_value(relative: str, column: str) -> tuple[str, float] | None:
    rows = load_csv(relative)
    date_key = "date" if "date" in rows[0] else "year"
    for row in reversed(rows):
        try:
            return row[date_key], float(row[column])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def derived_snapshot(indicator: str) -> dict[str, Any] | None:
    if indicator in {"kr_m2_yoy", "us_m2_yoy"}:
        column = "kr_m2" if indicator == "kr_m2_yoy" else "us_m2"
        rows = [row for row in load_csv("public/market-history/data/macro-cpi-rates-monthly.csv") if row.get(column)]
        if len(rows) >= 13:
            value = (float(rows[-1][column]) / float(rows[-13][column]) - 1) * 100
            return {"as_of": rows[-1]["date"], "value": round(value, 4), "unit": "% YoY"}
    if indicator == "credit_spread":
        rows = [row for row in load_csv("public/market-history/data/macro-cpi-rates-monthly.csv") if row.get("corp_aa_3y") and row.get("kr3y")]
        if rows:
            return {"as_of": rows[-1]["date"], "value": round(float(rows[-1]["corp_aa_3y"]) - float(rows[-1]["kr3y"]), 4), "unit": "%p"}
    if indicator == "kr_cpi_yoy":
        rows = [row for row in load_csv(DIRECT_COLUMNS["kr_cpi"][0]) if row.get("kr_cpi")]
        if len(rows) >= 13:
            value = (float(rows[-1]["kr_cpi"]) / float(rows[-13]["kr_cpi"]) - 1) * 100
            return {"as_of": rows[-1]["date"], "value": round(value, 4), "unit": "% YoY"}
    if indicator == "kr_us_10y_gap":
        rows = [row for row in load_csv(DIRECT_COLUMNS["kr10y"][0]) if row.get("kr10y") and row.get("us10y")]
        if rows:
            return {"as_of": rows[-1]["date"], "value": round(float(rows[-1]["kr10y"]) - float(rows[-1]["us10y"]), 4), "unit": "%p"}
    if indicator == "kospi_usd_real":
        markets = {row["date"]: row for row in load_csv(DIRECT_COLUMNS["kospi"][0]) if row.get("kospi") and row.get("usdkrw")}
        cpi = {row["date"]: row for row in load_csv(DIRECT_COLUMNS["kr_cpi"][0]) if row.get("kr_cpi")}
        common = sorted(set(markets) & set(cpi))
        if common:
            first, latest = common[0], common[-1]
            def level(observed: str) -> float:
                return float(markets[observed]["kospi"]) / float(markets[observed]["usdkrw"]) / float(cpi[observed]["kr_cpi"])
            return {"as_of": latest, "value": round(level(latest) / level(first) * 100, 4), "unit": f"{first[:7]}=100"}
    return None


def indicator_snapshot(indicator: str) -> dict[str, Any] | None:
    if indicator in DERIVED:
        return derived_snapshot(indicator)
    spec = DIRECT_COLUMNS.get(indicator)
    if not spec:
        return None
    if indicator == "kr_debt_gdp":
        rows = [row for row in load_csv(spec[0]) if row.get(spec[1]) and int(row["year"]) <= 2024]
        if rows:
            return {"as_of": rows[-1]["year"], "value": float(rows[-1][spec[1]]), "unit": spec[2]}
    found = last_value(spec[0], spec[1])
    if not found:
        return None
    return {"as_of": found[0], "value": found[1], "unit": spec[2]}


def timestamp_seconds(video_id: str, anchor: str) -> int | None:
    files = sorted((SOURCE_DIR / "videos" / video_id).glob("*.ko.vtt"))
    if not files:
        return None
    current = 0
    recent: list[tuple[int, str]] = []
    for line in files[0].read_text(encoding="utf-8", errors="ignore").splitlines():
        if "-->" in line:
            match = re.match(r"(?:(\d+):)?(\d+):(\d+)\.(\d+)", line)
            if match:
                hours = int(match.group(1) or 0)
                current = hours * 3600 + int(match.group(2)) * 60 + int(match.group(3))
            continue
        cleaned = html.unescape(re.sub(r"<[^>]+>", "", line))
        if cleaned.strip():
            recent.append((current, cleaned.strip()))
            recent = recent[-8:]
            joined = " ".join(item[1] for item in recent).replace(" ", "")
            if anchor.replace(" ", "") in joined:
                return recent[0][0]
    return None


def main() -> None:
    config = json.loads((ROOT / "config/kpunch_insight_claims.json").read_text(encoding="utf-8"))
    metadata = {
        row["video_id"]: row
        for row in (json.loads(line) for line in (SOURCE_DIR / "video_metadata.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    }
    claims = []
    for claim in config["claims"]:
        evidence = []
        for video in claim["videos"]:
            meta = metadata.get(video["video_id"], {})
            seconds = timestamp_seconds(video["video_id"], video["anchor"])
            url = meta.get("webpage_url") or f'https://www.youtube.com/watch?v={video["video_id"]}'
            if seconds is not None:
                url += f"&t={seconds}s"
            evidence.append({
                "video_id": video["video_id"],
                "title": meta.get("title"),
                "upload_date": meta.get("upload_date"),
                "url": url,
                "anchor": video["anchor"],
                "timestamp_seconds": seconds,
            })
        indicators = []
        for indicator in claim["indicators"]:
            snapshot = indicator_snapshot(indicator)
            indicators.append({"indicator_id": indicator, "available": snapshot is not None, "snapshot": snapshot})
        coverage = sum(item["available"] for item in indicators) / len(indicators)
        status = "TRACKABLE" if coverage >= 0.75 else "PARTIAL" if coverage else "NEEDS_DATA"
        claims.append({**claim, "evidence": evidence, "indicator_status": indicators, "coverage_pct": round(coverage * 100, 1), "validation_status": status})

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status_counts = {status: sum(claim["validation_status"] == status for claim in claims) for status in ("TRACKABLE", "PARTIAL", "NEEDS_DATA")}
    missing_counts = Counter(item["indicator_id"] for claim in claims for item in claim["indicator_status"] if not item["available"])
    ledger = {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "source_id": config["source_id"],
        "channel_url": config["channel_url"],
        "method_note": "Claims are paraphrases for internal analysis. Transcript files remain internal and are not republished.",
        "claim_count": len(claims),
        "status_counts": status_counts,
        "missing_indicator_priority": [{"indicator_id": key, "claim_count": count} for key, count in missing_counts.most_common()],
        "claims": claims,
    }
    OUTPUT_JSON.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 박종훈의 지식한방 인사이트 검증 원장",
        "",
        f"- 생성 시각(UTC): {generated_at}",
        f"- 핵심 주장: {len(claims)}개",
        "- 원칙: 아래 문장은 내부 분석용 의역이며, 자막 원문은 재게시하지 않습니다.",
        "- 상태: TRACKABLE=보유 지표 75% 이상, PARTIAL=일부 보유, NEEDS_DATA=추가 수집 필요",
        "",
        "## 검증 준비 현황",
        "",
        f'- TRACKABLE: {status_counts["TRACKABLE"]}개 · PARTIAL: {status_counts["PARTIAL"]}개 · NEEDS_DATA: {status_counts["NEEDS_DATA"]}개',
        "- 우선 추가 수집: " + ", ".join(f'`{key}`({count}개 주장)' for key, count in missing_counts.most_common(10)),
        "",
    ]
    for claim in claims:
        lines.extend([
            f'## {claim["claim_id"]} · {claim["theme"]} · {claim["validation_status"]} ({claim["coverage_pct"]:.1f}%)',
            "",
            f'**주장 의역:** {claim["claim"]}',
            "",
            "**전달경로:** " + " → ".join(claim["transmission"]),
            "",
            "**대표 근거 위치**",
            "",
        ])
        for item in claim["evidence"]:
            when = f'{item["timestamp_seconds"] // 60}:{item["timestamp_seconds"] % 60:02d}' if item["timestamp_seconds"] is not None else "시각 미확인"
            lines.append(f'- [{item["title"]}]({item["url"]}) · {when} · 검색 앵커: `{item["anchor"]}`')
        lines.extend(["", "**검증 지표**", ""])
        for item in claim["indicator_status"]:
            if item["available"]:
                snapshot = item["snapshot"]
                lines.append(f'- ✅ `{item["indicator_id"]}`: {snapshot["value"]:,.4f} {snapshot["unit"]} ({snapshot["as_of"]})')
            else:
                lines.append(f'- ⬜ `{item["indicator_id"]}`: 추가 수집 필요')
        lines.append("")
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"claims": len(claims), "json": str(OUTPUT_JSON), "markdown": str(OUTPUT_MD)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
