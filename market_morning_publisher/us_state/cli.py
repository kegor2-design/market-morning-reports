from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from market_morning_publisher.core import load_json
from market_morning_publisher.us_state.collectors import collect_us_state_metrics
from market_morning_publisher.us_state.event_engine import analyze_event, upcoming_events
from market_morning_publisher.us_state.state_engine import build_state


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Collect and build the shadow-only US State Baseline")
    p.add_argument("--root", default=".")
    p.add_argument("--metrics-config", default="config/us_state_metrics.json")
    p.add_argument("--calendar-config", default="config/us_event_calendar.json")
    p.add_argument("--no-network", action="store_true", help="Build state from existing raw_metrics_latest.json only")
    p.add_argument("--event-file", help="Optional JSON event to analyze against current state/playbooks")
    p.add_argument("--playbooks-config", default="config/us_issue_playbooks.json")
    args = p.parse_args(argv)
    root = Path(args.root).resolve()
    if args.no_network:
        raw = load_json(root / "data/state/us_state/raw_metrics_latest.json", {})
        if not raw:
            raise SystemExit("missing existing raw_metrics_latest.json")
    else:
        cfg = load_json(root / args.metrics_config, {})
        raw = collect_us_state_metrics(root, cfg)
    state = build_state(raw, root)
    calendar = load_json(root / args.calendar_config, {})
    events = upcoming_events(calendar, as_of=datetime.now(timezone.utc).date(), horizon_days=90)
    payload = {"state": state["states"], "quality": state["quality"], "upcoming_events": events[:20]}
    if args.event_file:
        event = load_json(Path(args.event_file), {})
        playbooks = load_json(root / args.playbooks_config, {})
        payload["event_analysis"] = analyze_event(event, state, playbooks, root=root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
