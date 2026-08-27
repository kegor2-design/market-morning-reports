#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_morning_publisher.blogger_render import render_blogger_html
from market_morning_publisher.closing import render_closing_html
from market_morning_publisher.youtube_insight.render import render_digest_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Blogger responsive HTML without publishing")
    parser.add_argument("--type", choices=("morning", "closing", "youtube"), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    markdown = Path(args.input).read_text(encoding="utf-8")
    renderers = {"morning": render_blogger_html, "closing": render_closing_html, "youtube": render_digest_html}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('<!doctype html><meta charset="utf-8">' + renderers[args.type](markdown), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
