from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from market_morning_publisher.core import atomic_json, now_iso


def upcoming_events(calendar: dict, *, as_of: date | None = None, horizon_days: int = 90) -> list[dict]:
    as_of = as_of or datetime.now(timezone.utc).date()
    out = []
    for event in calendar.get("events", []):
        try:
            d = date.fromisoformat(event["date"])
        except (KeyError, ValueError):
            continue
        delta = (d - as_of).days
        if -1 <= delta <= horizon_days:
            out.append({**event, "days_until": delta})
    return sorted(out, key=lambda x: (x["date"], x.get("time", "")))


def select_playbooks(event: dict, playbook_config: dict) -> list[dict]:
    text = f"{event.get('type','')} {event.get('name','')} {event.get('headline','')}".upper()
    ids = []
    if any(k in text for k in ("TREASURY", "BUYBACK", "QRA", "AUCTION")):
        ids += ["US_TREASURY_STRESS"]
    if "BUYBACK" in text:
        ids += ["TREASURY_BUYBACK"]
    if any(k in text for k in ("REPO", "MMF", "RRP", "SRF", "LIQUIDITY")):
        ids += ["US_MONEY_MARKET_PLUMBING"]
    if any(k in text for k in ("DOLLAR", "FIMA", "TIC", "STABLECOIN")):
        ids += ["USD_HEGEMONY"]
    if any(k in text for k in ("AI", "NVIDIA", "COREWEAVE", "SEMICONDUCTOR", "HBM")):
        ids += ["AI_FINANCING"]
    if any(k in text for k in ("ELECTION", "MIDTERM", "POLITICS", "SHUTDOWN", "DEBT LIMIT")):
        ids += ["POLITICAL_LIQUIDITY_CLOCK"]
    by_id = {p["id"]: p for p in playbook_config.get("playbooks", [])}
    return [by_id[x] for x in dict.fromkeys(ids) if x in by_id]


def analyze_event(event: dict, state: dict, playbook_config: dict, *, root: Path | None = None) -> dict:
    playbooks = select_playbooks(event, playbook_config)
    required = []
    for p in playbooks:
        required.extend(p.get("required_metrics", []))
    required = list(dict.fromkeys(required))
    metrics = state.get("metrics", {})
    evidence = {mid: metrics.get(mid, {"id": mid, "state": "UNKNOWN"}) for mid in required}
    missing = sorted(mid for mid, row in evidence.items() if row.get("state") in {None, "UNKNOWN", "STALE"})
    park_hypotheses = [p.get("park_hypothesis") for p in playbooks if p.get("park_hypothesis")]
    result = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "event": event,
        "playbooks": [p["id"] for p in playbooks],
        "knowledge_modules": list(dict.fromkeys(m for p in playbooks for m in p.get("knowledge_modules", []))),
        "official_fact": event.get("official_fact"),
        "official_intent": event.get("official_intent"),
        "park_primary_hypotheses": park_hypotheses,
        "our_status": "UNKNOWN" if missing else "READY_FOR_INTERPRETATION",
        "required_evidence": evidence,
        "missing_or_stale": missing,
        "verification_windows": ["T+30M", "T+1D", "T+5D", "T+20D"],
        "analysis_rule": "Official intent is recorded, not assumed true. Initial market reaction is evidence, not final proof. Persistent balance-sheet, rate, spread and flow effects determine realized effect.",
    }
    if root is not None:
        log = root / "data" / "state" / "us_state" / "events"
        log.mkdir(parents=True, exist_ok=True)
        event_id = event.get("id") or event.get("event_id") or datetime.now(timezone.utc).strftime("event_%Y%m%dT%H%M%S")
        atomic_json(log / f"{event_id}.json", result)
    return result
