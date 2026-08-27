from __future__ import annotations
import json
from pathlib import Path
from .rumor_extraction import extract_all

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(extract_all(root), ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
