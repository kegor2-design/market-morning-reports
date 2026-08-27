from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable


STANCE_SET = {"BULLISH", "BEARISH", "NEUTRAL", "MIXED", "UNKNOWN"}
IMPORTANCE_SCORE = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _issue_keys(claim: dict[str, Any]) -> list[str]:
    tags = [str(value).strip().upper() for value in claim.get("issue_tags") or [] if str(value).strip()]
    if tags:
        return tags
    playbooks = [str(value).strip().upper() for value in claim.get("playbook_ids") or [] if str(value).strip()]
    if playbooks:
        return [f"PLAYBOOK:{value}" for value in playbooks]
    metrics = [str(value).strip().upper() for value in claim.get("metric_ids") or [] if str(value).strip()]
    if metrics:
        return [f"METRIC:{value}" for value in metrics[:3]]
    return ["UNCLASSIFIED"]


def _stance(claim: dict[str, Any]) -> str:
    value = str(claim.get("stance") or "UNKNOWN").upper()
    return value if value in STANCE_SET else "UNKNOWN"


def _channel_meta(channels: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("id")): row for row in channels if row.get("id")}


def build_nightly_synthesis(
    target_date: str,
    claims: list[dict[str, Any]],
    channels: list[dict[str, Any]],
    *,
    minimum_importance: str = "MEDIUM",
    minimum_distinct_sources: int = 2,
) -> dict[str, Any]:
    threshold = IMPORTANCE_SCORE.get(minimum_importance, 2)
    channel_by_id = _channel_meta(channels)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    included_claims = []
    for claim in claims:
        if IMPORTANCE_SCORE.get(str(claim.get("importance") or "LOW"), 0) < threshold:
            continue
        included_claims.append(claim)
        for key in _issue_keys(claim):
            groups[key].append(claim)

    issues = []
    agreement_count = 0
    disagreement_count = 0
    for issue_key, rows in groups.items():
        source_rows: dict[str, dict[str, Any]] = {}
        for row in sorted(rows, key=lambda item: IMPORTANCE_SCORE.get(str(item.get("importance")), 0), reverse=True):
            channel_id = str(row.get("channel_id") or "UNKNOWN")
            if channel_id in source_rows:
                continue
            meta = channel_by_id.get(channel_id, {})
            source_rows[channel_id] = {
                "channel_id": channel_id,
                "channel_name": row.get("channel_name") or meta.get("name"),
                "tier": meta.get("tier", "UNKNOWN"),
                "role": meta.get("role"),
                "source_weight": row.get("source_weight") or meta.get("source_weight"),
                "claim_id": row.get("claim_id"),
                "classification": row.get("classification"),
                "importance": row.get("importance"),
                "stance": _stance(row),
                "claim_summary_ko": row.get("claim_summary_ko"),
                "verification_status": row.get("verification_status"),
                "chart_analysis_requested": bool(row.get("chart_analysis_requested")),
                "data_needed": row.get("data_needed") or [],
                "invalidation_conditions": row.get("invalidation_conditions") or [],
            }
        sources = list(source_rows.values())
        stance_counter = Counter(row["stance"] for row in sources)
        distinct = len(sources)
        bullish = stance_counter.get("BULLISH", 0)
        bearish = stance_counter.get("BEARISH", 0)
        disagreement = bullish > 0 and bearish > 0
        dominant = "UNKNOWN"
        agreement = False
        non_unknown = [(stance, count) for stance, count in stance_counter.items() if stance not in {"UNKNOWN", "MIXED"}]
        if non_unknown:
            dominant, count = max(non_unknown, key=lambda pair: (pair[1], pair[0]))
            agreement = distinct >= minimum_distinct_sources and count >= minimum_distinct_sources and not disagreement
        if disagreement:
            disagreement_count += 1
        if agreement:
            agreement_count += 1
        issues.append({
            "issue_key": issue_key,
            "distinct_sources": distinct,
            "stance_counts": dict(sorted(stance_counter.items())),
            "dominant_stance": dominant,
            "agreement": agreement,
            "disagreement": disagreement,
            "source_views": sources,
            "data_gaps": sorted({str(item) for row in sources for item in row.get("data_needed") or [] if str(item).strip()}),
            "chart_pending": [row["claim_id"] for row in sources if row.get("chart_analysis_requested")],
        })
    issues.sort(key=lambda row: (row["disagreement"], row["agreement"], row["distinct_sources"]), reverse=True)
    return {
        "schema_version": "1.0",
        "target_date": target_date,
        "mode": "SHADOW_ONLY",
        "claims_considered": len(included_claims),
        "issues": issues,
        "agreement_issue_count": agreement_count,
        "disagreement_issue_count": disagreement_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fact_policy": "Cross-channel agreement is not factual confirmation; independent official/news/market evidence remains required.",
    }


def render_nightly_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Nightly YouTube Intelligence | {payload.get('target_date')}",
        "",
        "> 여러 채널의 합의는 **출처 간 합의**일 뿐 사실 확정이 아닙니다. 공식자료·뉴스·시장데이터와 독립 검증합니다.",
        "",
        f"- 분석 claim: {payload.get('claims_considered', 0)}",
        f"- 합의 이슈: {payload.get('agreement_issue_count', 0)}",
        f"- 충돌 이슈: {payload.get('disagreement_issue_count', 0)}",
        "",
    ]
    issues = payload.get("issues") or []
    if not issues:
        lines += ["분석 가능한 주요 이슈가 없습니다.", ""]
        return "\n".join(lines)
    for index, issue in enumerate(issues, 1):
        marker = "충돌" if issue.get("disagreement") else "합의" if issue.get("agreement") else "관찰"
        lines += [
            f"## {index}. {issue.get('issue_key')} · {marker}",
            "",
            f"- 소스 수: {issue.get('distinct_sources')} / 우세 방향: {issue.get('dominant_stance')}",
            f"- 방향 분포: {issue.get('stance_counts')}",
            "",
        ]
        for view in issue.get("source_views") or []:
            lines.append(
                f"- **{view.get('channel_name') or view.get('channel_id')}** [{view.get('classification')}/{view.get('stance')}] "
                f"{view.get('claim_summary_ko') or ''} (검증: {view.get('verification_status') or 'UNKNOWN'})"
            )
        if issue.get("data_gaps"):
            lines += ["", "확인 필요 데이터: " + ", ".join(issue["data_gaps"][:12])]
        if issue.get("chart_pending"):
            lines += ["차트 검증 대기 claim: " + ", ".join(issue["chart_pending"][:12])]
        lines.append("")
    return "\n".join(lines)
