from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from market_morning_publisher.youtube_chart.ohlcv import YahooOhlcvClient, interval_for_timeframe
from market_morning_publisher.youtube_chart.time_model import parse_datetime

from .historical import build_edge_summary, validate_historical_claim


DEFAULT_ASSESSMENTS = Path("data/normalized/youtube_chart/claim_assessments.jsonl")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush(); os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(content, encoding="utf-8")


def _load_market(root: Path, claim_id: str) -> dict[str, Any] | None:
    for relative in (
        f"data/normalized/youtube_chart/ohlcv_reviewed/{claim_id}.json",
        f"data/normalized/youtube_chart/ohlcv/{claim_id}.json",
    ):
        path = root / relative
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _fetch_market(claim: dict[str, Any], *, client: YahooOhlcvClient) -> dict[str, Any] | None:
    symbol = claim.get("resolved_asset_symbol") or claim.get("asset_symbol")
    timeframe = claim.get("resolved_timeframe") or claim.get("timeframe")
    actionable = parse_datetime(claim.get("publicly_actionable_at"))
    interval = interval_for_timeframe(timeframe)
    if not symbol or not actionable or not interval:
        return None
    lookback_days = 2200 if interval == "1mo" else 700 if interval == "1wk" else 500 if interval == "1d" else 7
    end = datetime.now(timezone.utc)
    bars = client.fetch(str(symbol), start=actionable - timedelta(days=lookback_days), end=end, interval=interval)
    return {"symbol": symbol, "interval": interval, "bars": bars, "provider": "YAHOO_FINANCE"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate human-confirmed expert chart claims against point-in-time historical OHLCV")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--assessments", type=Path, default=DEFAULT_ASSESSMENTS)
    parser.add_argument("--fetch-yahoo", action="store_true", help="Fetch missing OHLCV from Yahoo; otherwise use existing reviewed/local OHLCV only")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    assessments_path = args.assessments if args.assessments.is_absolute() else root / args.assessments
    primitive_registry = json.loads((root / "config/chart_insight_primitives.json").read_text(encoding="utf-8"))
    policy = json.loads((root / "config/chart_insight_policy.json").read_text(encoding="utf-8"))
    assessments = [
        row for row in _read_jsonl(assessments_path)
        if str((row.get("human_review") or {}).get("review_status") or "").upper() == "CONFIRMED"
        and str(row.get("evaluation_mode") or "") in {"DIRECTIONAL_SHADOW", "BINARY_SHADOW"}
    ]
    if args.limit > 0:
        assessments = assessments[:args.limit]
    client = YahooOhlcvClient() if args.fetch_yahoo else None
    validations = []
    missing = []
    for claim in assessments:
        claim_id = str(claim.get("source_claim_id"))
        market = _load_market(root, claim_id)
        if market is None and client is not None:
            try:
                market = _fetch_market(claim, client=client)
            except Exception as exc:
                missing.append({"source_claim_id": claim_id, "reason": "OHLCV_FETCH_FAILED", "error_type": type(exc).__name__})
                continue
        bars = (market or {}).get("bars") or []
        if not bars:
            missing.append({"source_claim_id": claim_id, "reason": "OHLCV_MISSING"})
            continue
        validations.append(validate_historical_claim(
            claim, bars, primitive_registry,
            windows=policy.get("forward_windows") or [1, 5, 20, 60],
            context_bars=int(policy.get("context_bars", 60)),
            horizon_bars=max(policy.get("forward_windows") or [60]),
        ))
    validation_path = root / "data/normalized/chart_insight/historical_validations.jsonl"
    _atomic_jsonl(validation_path, validations)
    edges = build_edge_summary(validations)
    edge_path = root / "data/state/chart_insight/edge_summary.json"
    _atomic_json(edge_path, edges)
    latest = {
        "schema_version": "1.0", "mode": "SHADOW_ONLY", "assessments_considered": len(assessments),
        "validated": len(validations), "missing": missing, "validation_path": str(validation_path),
        "edge_summary_path": str(edge_path), "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    latest_path = root / "data/state/chart_insight/latest.json"
    _atomic_json(latest_path, latest)
    print(json.dumps(latest, ensure_ascii=False, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
