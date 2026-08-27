from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="Inspect nightly chart historical-research queue and data-contract readiness")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--require-adapter-ready", action="store_true")
    args=parser.parse_args(argv)
    root=args.root.resolve()
    contract=json.loads((root/"config/chart_research_data_contract.json").read_text(encoding="utf-8"))
    policy=json.loads((root/"config/nightly_chart_research.json").read_text(encoding="utf-8"))
    queue=_read_jsonl(root/"data/state/chart_insight/historical_research_queue.jsonl")
    ready=str((policy.get("historical_scan") or {}).get("provider_status")) == "READY"
    payload={"queue_size":len(queue),"provider_status":(policy.get("historical_scan") or {}).get("provider_status"),"live_adapter_status":contract.get("live_adapter_status"),"ready":ready,"note":"This command performs no DB writes and no historical scan."}
    print(json.dumps(payload,ensure_ascii=False,indent=2))
    return 0 if ready or not args.require_adapter_ready else 2

if __name__ == "__main__": raise SystemExit(main())
