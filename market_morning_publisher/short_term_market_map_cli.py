from __future__ import annotations

import argparse
import json
from pathlib import Path

from .short_term_market_map import build_short_term_market_map, load_config


def main() -> int:
    p = argparse.ArgumentParser(description="Build point-in-time Short-Term Market Map JSON")
    p.add_argument("--config", default="config/short_term_market_map.json")
    p.add_argument("--input", required=True, help="JSON mapping indicator_id -> observation")
    p.add_argument("--output", required=True)
    p.add_argument("--as-of", default=None)
    args = p.parse_args()
    cfg = load_config(args.config)
    observations = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = build_short_term_market_map(cfg, observations, as_of=args.as_of)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "overall_state": result["overall_state"], "output": args.output}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
