#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="/tmp/mmp-research-portal-preview.html")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root))
    from market_morning_publisher.research_portal import build_preview, validate_theme

    theme = root / "blogger_theme" / "market_morning_research_portal.xml"
    result = validate_theme(theme)
    if not result.ok:
        print(f"[FAIL] invalid theme: {result}", file=sys.stderr)
        return 2
    output = build_preview(theme, args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
