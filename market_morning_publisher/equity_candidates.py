from __future__ import annotations

import re


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _event_text(event: dict) -> str:
    parts = [event.get("headline", ""), *event.get("evidence_summary", [])]
    parts.extend(source.get("title", "") for source in event.get("sources", []))
    return _text(" ".join(str(x) for x in parts))


def _direct_name_match(name: str, text: str) -> bool:
    if re.fullmatch(r"[a-z0-9 .&+-]+", name):
        return len(re.sub(r"[^a-z0-9]", "", name)) >= 4 and bool(
            re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text)
        )
    return len(name) >= 3 and name in text


def build_equity_candidate_pool(
    verified_events: list[dict], equity_master: list[dict], exposures: list[dict], max_items: int = 30,
) -> list[dict]:
    """Return only evidence-bound equities that Codex may use as pre-open candidates."""
    by_symbol = {str(row.get("symbol", "")).zfill(6): row for row in equity_master if row.get("symbol")}
    matches: dict[str, dict] = {}
    for event in verified_events:
        text = _event_text(event)
        for symbol, row in by_symbol.items():
            name = _text(row.get("name"))
            if not _direct_name_match(name, text):
                continue
            item = matches.setdefault(symbol, _pool_item(row, "DIRECT_MENTION"))
            item["matched_event_ids"].append(event["event_id"])
        for exposure in exposures:
            symbol = str(exposure.get("symbol", "")).zfill(6)
            row = by_symbol.get(symbol)
            if not row or exposure.get("evidence_status") != "VERIFIED" or not exposure.get("candidate_eligible"):
                continue
            keywords = [_text(x) for x in exposure.get("match_keywords", []) if _text(x)]
            if not keywords or not any(keyword in text for keyword in keywords):
                continue
            item = matches.setdefault(symbol, _pool_item(row, "VERIFIED_EXPOSURE"))
            if item["selection_basis"] != "DIRECT_MENTION":
                item["selection_basis"] = "VERIFIED_EXPOSURE"
            item["matched_event_ids"].append(event["event_id"])
            item["exposures"].append({
                key: exposure.get(key) for key in (
                    "industry", "value_chain_role", "revenue_exposure_pct", "evidence_type",
                    "evidence_url", "evidence_date", "confidence", "exposure_relation",
                )
            })
    result = []
    for item in matches.values():
        item["matched_event_ids"] = list(dict.fromkeys(item["matched_event_ids"]))
        item["exposures"] = _dedupe_exposures(item["exposures"])
        result.append(item)
    result.sort(key=lambda x: (x["selection_basis"] != "DIRECT_MENTION", -len(x["matched_event_ids"]), x["symbol"]))
    return result[:max_items]


def _pool_item(row: dict, basis: str) -> dict:
    return {
        "symbol": str(row.get("symbol", "")).zfill(6), "name": row.get("name"),
        "market": row.get("market"), "industry_larg_code": row.get("industry_larg_code"),
        "industry_medm_code": row.get("industry_medm_code"), "industry_smal_code": row.get("industry_smal_code"),
        "selection_basis": basis, "matched_event_ids": [], "exposures": [],
    }


def _dedupe_exposures(items: list[dict]) -> list[dict]:
    seen, result = set(), []
    for item in items:
        key = (item.get("industry"), item.get("value_chain_role"), item.get("evidence_url"))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
