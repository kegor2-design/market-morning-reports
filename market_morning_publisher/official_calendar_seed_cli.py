from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Emit verified official calendar bootstrap events as JSONL")
    p.add_argument("--seed", default="config/official_calendar_seed_20260827.json")
    p.add_argument("--output", default="-")
    args = p.parse_args()
    raw = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    lines = [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in raw.get("events") or []]
    text = "\n".join(lines) + ("\n" if lines else "")
    if args.output == "-":
        print(text, end="")
    else:
        out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
