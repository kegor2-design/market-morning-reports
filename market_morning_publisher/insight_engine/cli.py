from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from market_morning_publisher.core import atomic_json

from .history import build_case_market_snapshot, load_cases
from .hypothesis import source_performance, upsert_hypothesis
from .reasoning import build_engine_update_candidates, build_reasoning_packet, load_json
from .registry import collection_plan, load_metric_registry
from .states import build_market_states
from .global_flow_collectors import collect_global_flow_metrics


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    rows=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip(): rows.append(json.loads(line))
    return rows


def _load_observations(root: Path) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    us = load_json(root / "data/state/us_state/latest.json", {}) or {}
    observations.update(us.get("metrics") or {})
    local = load_json(root / "data/state/insight_engine/metrics_latest.json", {}) or {}
    observations.update(local.get("metrics") or local)
    return observations


def _seed_hypotheses(root: Path, seed_config: dict[str, Any]) -> list[dict[str, Any]]:
    path = root / "data/state/insight_engine/hypotheses.jsonl"
    existing = _read_jsonl(path)
    existing_keys = {(str(row.get("source_lens")), str(row.get("hypothesis")), str(row.get("event_id", ""))) for row in existing}
    for row in seed_config.get("hypotheses", []):
        key = (str(row.get("source_lens")), str(row.get("hypothesis")), str(row.get("event_id", "")))
        if key not in existing_keys:
            upsert_hypothesis(path, row)
            existing_keys.add(key)
    return _read_jsonl(path)


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Shadow market reasoning engine")
    p.add_argument("--root", default=".")
    p.add_argument("--event-file")
    p.add_argument("--build-case", action="append", default=[])
    p.add_argument("--scan-youtube-updates", action="store_true")
    p.add_argument("--scan-events-date", help="Build shadow reasoning packets for verified normalized events on YYYY-MM-DD")
    p.add_argument("--min-event-importance", type=int, default=60)
    p.add_argument("--max-events", type=int, default=12)
    p.add_argument("--collect-global-flows", action="store_true", help="Collect official/FRED cross-border flow sensors before reasoning")
    args=p.parse_args(argv)
    root=Path(args.root).resolve()
    registry=load_metric_registry(root / "config/insight_metric_registry.json")
    playbooks=load_json(root / "config/insight_reasoning_playbooks.json", {}) or {}
    causal_flows=load_json(root / "config/global_causal_flows.json", {}) or {}
    cases=load_cases(root / "config/historical_cases.json")
    lenses=load_json(root / "config/source_lenses.json", {}) or {}
    seeds=load_json(root / "config/insight_hypothesis_seeds.json", {}) or {}
    hypotheses=_seed_hypotheses(root, seeds)
    if args.collect_global_flows:
        global_cfg=load_json(root / "config/global_flow_metrics.json", {}) or {}
        collect_global_flow_metrics(root, global_cfg)
    observations=_load_observations(root)
    chart_insight=load_json(root / "data/state/chart_insight/latest.json", {}) or {}
    nightly_date=args.scan_events_date or date.today().isoformat()
    nightly_youtube=load_json(root / f"data/state/nightly_youtube/{nightly_date}.json", {}) or {}
    states=build_market_states(observations)
    plan = collection_plan(registry)
    plan_path = root / "data/state/insight_engine/collection_plan.json"
    atomic_json(plan_path, {"generated_at": datetime.now(timezone.utc).isoformat(), **plan})
    output={
        "schema_version":"1.0", "generated_at":datetime.now(timezone.utc).isoformat(), "states":states,
        "hypothesis_performance":source_performance(hypotheses),
        "collection_plan_summary": {
            key: len(value) for key, value in plan.items()
        },
        "pending_p0_metric_ids": [row["metric_id"] for row in plan.get("PENDING_P0", [])],
        "collection_plan_path": str(plan_path),
    }
    atomic_json(root / "data/state/insight_engine/latest.json", output)
    if args.event_file:
        event=load_json(Path(args.event_file), {}) or {}
        packet=build_reasoning_packet(event, metric_registry=registry, playbook_config=playbooks, historical_cases=cases, observations=observations, hypotheses=hypotheses, source_lenses=lenses, chart_insight=chart_insight, nightly_youtube=nightly_youtube, causal_flow_config=causal_flows)
        output["reasoning_packet"]=packet
        event_id=event.get("event_id") or event.get("id") or datetime.now(timezone.utc).strftime("event_%Y%m%dT%H%M%S")
        atomic_json(root / f"data/state/insight_engine/events/{event_id}.json", packet)
    if args.build_case:
        case_by_id={row["case_id"]:row for row in cases}
        output["historical_cases"]=[]
        for case_id in args.build_case:
            if case_id not in case_by_id: raise SystemExit(f"unknown case: {case_id}")
            snapshot=build_case_market_snapshot(root, case_by_id[case_id])
            output["historical_cases"].append(snapshot)
            atomic_json(root / f"data/state/insight_engine/history/{case_id}.json", snapshot)
    if args.scan_events_date:
        event_path=root / f"data/normalized/{args.scan_events_date}-events.json"
        events=load_json(event_path, []) or []
        selected=[row for row in events if row.get("verified") and int(row.get("importance_score") or 0) >= args.min_event_importance]
        selected=sorted(selected, key=lambda row: int(row.get("importance_score") or 0), reverse=True)[:max(0,args.max_events)]
        packets=[]
        for raw_event in selected:
            event=dict(raw_event)
            event["tags"]=list(dict.fromkeys([*(event.get("market_terms") or []), *(event.get("strategic_topics") or []), *(event.get("countries") or [])]))
            packet=build_reasoning_packet(event, metric_registry=registry, playbook_config=playbooks, historical_cases=cases, observations=observations, hypotheses=hypotheses, source_lenses=lenses, chart_insight=chart_insight, nightly_youtube=nightly_youtube, causal_flow_config=causal_flows)
            packets.append(packet)
            event_id=event.get("event_id") or event.get("id")
            if event_id:
                atomic_json(root / f"data/state/insight_engine/events/{event_id}.json", packet)
        output["event_packets"]={"source":str(event_path),"selected":len(packets),"packets":packets}
    if args.scan_youtube_updates:
        claims=_read_jsonl(root / "data/normalized/youtube_insight/claims.jsonl")
        us_playbooks=load_json(root / "config/us_issue_playbooks.json", {}) or {}
        combined_playbooks={"playbooks": list(playbooks.get("playbooks", [])) + list(us_playbooks.get("playbooks", []))}
        candidates=build_engine_update_candidates(claims, registry, combined_playbooks)
        today=(args.scan_events_date or date.today().isoformat())
        atomic_json(root / f"data/state/insight_engine/engine_update_candidates/{today}.json", {"generated_at":output["generated_at"],"candidates":candidates})
        output["engine_update_candidates"]=candidates
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
