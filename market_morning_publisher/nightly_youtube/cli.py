from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .synthesis import build_nightly_synthesis, render_nightly_markdown
from market_morning_publisher.chart_insight.research import build_nightly_chart_research, render_chart_research_markdown


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic cross-channel nightly YouTube synthesis from extracted claims")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--date", default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    channels = json.loads((root / "config/youtube_insight_channels.json").read_text(encoding="utf-8"))
    policy = json.loads((root / "config/nightly_youtube_intelligence.json").read_text(encoding="utf-8"))
    claims = [row for row in _read_jsonl(root / "data/normalized/youtube_insight/claims.jsonl") if str(row.get("target_date")) == args.date]
    result = build_nightly_synthesis(
        args.date, claims, channels.get("channels") or [],
        minimum_importance=str((channels.get("policy") or {}).get("nightly_include_min_importance", "MEDIUM")),
        minimum_distinct_sources=int((policy.get("consensus_policy") or {}).get("minimum_distinct_sources", 2)),
    )
    primitive_registry = json.loads((root / "config/chart_insight_primitives.json").read_text(encoding="utf-8"))
    chart_research_policy = json.loads((root / "config/nightly_chart_research.json").read_text(encoding="utf-8"))
    chart_research = build_nightly_chart_research(args.date, claims, channels.get("channels") or [], primitive_registry, chart_research_policy)
    result["chart_research"] = {key: value for key, value in chart_research.items() if key not in {"candidates", "historical_research_queue"}}
    chart_state = root / "data/state/chart_insight/nightly_research" / f"{args.date}.json"
    chart_state.parent.mkdir(parents=True, exist_ok=True)
    chart_state.write_text(json.dumps(chart_research, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    state = root / "data/state/nightly_youtube" / f"{args.date}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = root / "reports" / args.date[:7] / f"{args.date}-nightly-youtube-intelligence.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_nightly_markdown(result) + "\n" + render_chart_research_markdown(chart_research), encoding="utf-8")
    print(json.dumps({"state": str(state), "report": str(report), "chart_research_state": str(chart_state), "issues": len(result["issues"]), "chart_strategy_candidates": chart_research.get("candidate_count", 0)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
