from __future__ import annotations

import argparse
import json
from pathlib import Path

from .schedule_discovery import extract_schedule_candidates


def _rows(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract date-bearing schedule candidates from normalized news/YouTube/Telegram documents")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--default-year", type=int)
    args = ap.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", encoding="utf-8") as f:
        for doc in _rows(Path(args.input)):
            for row in extract_schedule_candidates(doc, default_year=args.default_year):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
    print(f"schedule_candidates={count} output={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
