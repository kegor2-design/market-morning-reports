from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable
import json
import re

UTC = timezone.utc
CONTRACT = "MMP_EXPERT_HISTORICAL_CORPUS_V1"
CLAIM_LEDGER_CONTRACT = "MMP_EXPERT_CLAIM_LEDGER_V1"
PRIMITIVE_CONTRACT = "MMP_EXPERT_PRIMITIVE_INDEX_V1"
DELTA_STATES = {"NEW", "REINFORCED", "MODIFIED", "CONTRADICTED", "UNCHANGED"}
VALIDATION_STATES = {"PENDING", "SUPPORTED", "PARTIAL", "CONTRADICTED", "INCONCLUSIVE", "NOT_TESTABLE"}
PRIMARY_KINDS = {"PRIMARY_EXPERT_HYPOTHESIS", "PRIMARY_EXPERT_RULE", "PRIMARY_EXPERT_OBSERVATION"}


def _norm_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _norm_key(text: Any) -> str:
    value = _norm_space(text).lower()
    value = re.sub(r"[^0-9a-z가-힣]+", "_", value).strip("_")
    return value[:160]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_vtt_timestamp(value: str) -> float | None:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    except ValueError:
        return None
    return None


def parse_vtt(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="ignore")
    lines = raw.splitlines()
    segments: list[dict[str, Any]] = []
    current_start = None
    current_end = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, current_start, current_end
        if buf and current_start is not None:
            text = _norm_space(" ".join(buf))
            text = re.sub(r"<[^>]+>", "", text).strip()
            if text:
                segments.append({"start": current_start, "end": current_end, "text": text})
        buf = []
        current_start = None
        current_end = None

    for line in lines:
        stripped = line.strip()
        if "-->" in stripped:
            flush()
            left, right = stripped.split("-->", 1)
            current_start = left.strip().split(" ", 1)[0]
            current_end = right.strip().split(" ", 1)[0]
            continue
        if not stripped:
            flush()
            continue
        if stripped == "WEBVTT" or stripped.isdigit() or stripped.startswith(("Kind:", "Language:", "NOTE")):
            continue
        if current_start is not None:
            buf.append(stripped)
    flush()

    # YouTube VTT often repeats rolling captions. De-duplicate adjacent identical text.
    deduped: list[dict[str, Any]] = []
    for seg in segments:
        if deduped and _norm_space(deduped[-1]["text"]) == _norm_space(seg["text"]):
            deduped[-1]["end"] = seg.get("end") or deduped[-1].get("end")
            continue
        deduped.append(seg)
    transcript = "\n".join(f"[{x['start']} --> {x['end']}] {x['text']}" for x in deduped)
    plain_text = _norm_space(" ".join(x["text"] for x in deduped))
    return {"segments": deduped, "transcript": transcript, "plain_text": plain_text}


def parse_text_transcript(path: str | Path) -> dict[str, Any]:
    """Read a normalized transcript without inventing source timestamps."""
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    lines = raw.splitlines()
    metadata: dict[str, str] = {}
    body_start = 0
    for index, line in enumerate(lines):
        if not line.strip():
            body_start = index + 1
            break
        match = re.match(r"^([A-Z_]+):\s*(.*)$", line.strip())
        if not match:
            break
        metadata[match.group(1).lower()] = match.group(2).strip()
        body_start = index + 1
    plain_text = _norm_space(" ".join(lines[body_start:]))
    return {
        "segments": [],
        "transcript": plain_text,
        "plain_text": plain_text,
        "embedded_metadata": metadata,
    }


def parse_transcript(path: str | Path) -> dict[str, Any]:
    return parse_vtt(path) if str(path).endswith(".vtt") else parse_text_transcript(path)


def infer_video_id(path: str | Path) -> str:
    name = Path(path).name
    patterns = [
        r"\[([A-Za-z0-9_-]{6,20})\]",
        r"_([A-Za-z0-9_-]{11})(?:\.|_)",
        r"(?:^|[._-])([A-Za-z0-9_-]{11})(?:\.|$)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, name)
        if matches:
            return matches[-1]
    stem = name
    for suffix in (".ko-orig.vtt", ".ko.vtt", ".vtt", ".txt"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return _norm_key(stem)[-80:] or sha256(str(path).encode()).hexdigest()[:16]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def sidecar_metadata(subtitle_path: Path) -> dict[str, Any]:
    name = subtitle_path.name
    bases = []
    for suffix in (".ko-orig.vtt", ".ko.vtt", ".vtt"):
        if name.endswith(suffix):
            bases.append(name[: -len(suffix)])
    bases.append(subtitle_path.stem)
    candidates: list[Path] = []
    for base in dict.fromkeys(bases):
        candidates.extend([
            subtitle_path.with_name(base + ".info.json"),
            subtitle_path.with_name(base + ".metadata.json"),
            subtitle_path.with_name(base + ".json"),
        ])
    for p in candidates:
        if p.exists():
            obj = _load_json(p)
            if obj:
                obj["_metadata_path"] = str(p)
                return obj
    return {}


@dataclass(frozen=True)
class ExpertDefinition:
    expert_id: str
    display_name: str
    channel_aliases: tuple[str, ...]
    path_keywords: tuple[str, ...]
    expected_metadata_min: int
    expected_subtitle_min: int
    known_missing_subtitles: int = 0
    known_period_start: str | None = None
    known_period_end: str | None = None
    speaker_policy: str = ""
    weight_policy: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExpertDefinition":
        return cls(
            expert_id=str(raw["expert_id"]),
            display_name=str(raw.get("display_name") or raw["expert_id"]),
            channel_aliases=tuple(str(x) for x in raw.get("channel_aliases") or []),
            path_keywords=tuple(str(x).lower() for x in raw.get("path_keywords") or []),
            expected_metadata_min=int(raw.get("expected_metadata_min") or 0),
            expected_subtitle_min=int(raw.get("expected_subtitle_min") or 0),
            known_missing_subtitles=int(raw.get("known_missing_subtitles") or 0),
            known_period_start=raw.get("known_period_start"),
            known_period_end=raw.get("known_period_end"),
            speaker_policy=str(raw.get("speaker_policy") or ""),
            weight_policy=str(raw.get("weight_policy") or ""),
        )


@dataclass
class InventoryItem:
    expert_id: str
    video_id: str
    subtitle_path: str
    metadata_path: str | None
    title: str | None
    published_at: str | None
    channel: str | None
    duration: Any = None
    transcript_sha256: str = ""
    transcript_chars: int = 0
    segment_count: int = 0
    evidence_tier: str = "TIMESTAMP_VERIFIED"
    source_format: str = "VTT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExpertClaim:
    claim_id: str
    expert_id: str
    video_id: str
    published_at: str | None
    speaker: str
    claim_text: str
    claim_kind: str
    evidence_summary: str
    causal_chain: list[str]
    premise_metrics: list[str]
    time_horizon: str
    related_assets: list[str]
    related_entities: list[str]
    topics: list[str]
    expected_direction: dict[str, str]
    invalidation_conditions: list[str]
    primitive_key: str
    stance: str
    source_timestamp_start: str
    source_timestamp_end: str
    attribution_confidence: str
    source_path: str | None = None
    validation_status: str = "PENDING"
    validation_notes: list[str] = field(default_factory=list)
    evidence_tier: str = "TIMESTAMP_VERIFIED"

    @property
    def reusable(self) -> bool:
        return self.claim_kind in PRIMARY_KINDS and self.attribution_confidence in {"HIGH", "MEDIUM"}

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["reusable"] = self.reusable
        return row


def load_config(path: str | Path) -> tuple[dict[str, Any], dict[str, ExpertDefinition]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("contract") != CONTRACT:
        raise ValueError(f"invalid contract: {raw.get('contract')}")
    experts = {x.expert_id: x for x in (ExpertDefinition.from_dict(r) for r in raw.get("experts") or [])}
    if not experts:
        raise ValueError("no expert definitions")
    return raw, experts


def _candidate_subtitles(root: Path, suffixes: Iterable[str], max_files: int) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        s = str(p.resolve())
        if s in seen:
            continue
        if suffixes and not any(p.name.endswith(x) for x in suffixes):
            continue
        seen.add(s)
        out.append(p)
        if len(out) >= max_files:
            break
    return sorted(out)


def discover_expert_subtitles(project_root: str | Path, config_path: str | Path, expert_id: str, source_root: str | Path | None = None) -> list[Path]:
    cfg, experts = load_config(config_path)
    expert = experts[expert_id]
    max_files = int((cfg.get("discovery") or {}).get("max_files_per_scan") or 25000)
    suffixes = tuple((cfg.get("discovery") or {}).get("subtitle_suffixes") or [".vtt"])
    roots: list[Path] = []
    if source_root:
        roots = [Path(source_root)]
    else:
        for rel in (cfg.get("discovery") or {}).get("candidate_roots") or []:
            p = Path(project_root) / rel
            if p.exists():
                roots.append(p)
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(_candidate_subtitles(root, suffixes, max_files=max_files))
        if len(candidates) >= max_files:
            break
    # When a source root is explicit, trust the caller. Otherwise require expert path/metadata identity.
    if source_root:
        return sorted(dict.fromkeys(candidates))[:max_files]

    matched: list[Path] = []
    aliases = tuple(a.lower().lstrip("@") for a in expert.channel_aliases)
    for p in candidates:
        path_text = str(p).lower()
        meta = sidecar_metadata(p)
        meta_text = " ".join(str(meta.get(k) or "") for k in ("channel", "channel_id", "uploader", "uploader_id", "webpage_url", "original_url")).lower()
        haystack = path_text + " " + meta_text
        if any(k and k in haystack for k in (*expert.path_keywords, *aliases)):
            matched.append(p)
    return sorted(dict.fromkeys(matched))[:max_files]


def build_inventory(expert_id: str, subtitle_files: Iterable[Path]) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    by_video: dict[str, InventoryItem] = {}
    suffix_rank = {".ko-orig.vtt": 3, ".ko.vtt": 2, ".vtt": 1}

    def rank(path: str) -> int:
        return max((v for k, v in suffix_rank.items() if path.endswith(k)), default=0)

    for p in subtitle_files:
        parsed = parse_transcript(p)
        meta = sidecar_metadata(p)
        embedded = parsed.get("embedded_metadata") or {}
        video_id = str(meta.get("id") or embedded.get("video_id") or infer_video_id(p))
        date = meta.get("upload_date") or meta.get("release_date") or meta.get("published_at") or meta.get("timestamp") or embedded.get("upload_date")
        if isinstance(date, str) and len(date) == 8 and date.isdigit():
            date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        text_hash = sha256(parsed["plain_text"].encode("utf-8")).hexdigest()
        item = InventoryItem(
            expert_id=expert_id,
            video_id=video_id,
            subtitle_path=str(p),
            metadata_path=meta.get("_metadata_path"),
            title=meta.get("title") or embedded.get("title"),
            published_at=str(date) if date not in (None, "") else None,
            channel=meta.get("channel") or meta.get("uploader"),
            duration=meta.get("duration"),
            transcript_sha256=text_hash,
            transcript_chars=len(parsed["plain_text"]),
            segment_count=len(parsed["segments"]),
            evidence_tier="TIMESTAMP_VERIFIED" if str(p).endswith(".vtt") else "TEXT_VERIFIED",
            source_format="VTT" if str(p).endswith(".vtt") else "TXT",
        )
        old = by_video.get(video_id)
        if old is None or rank(item.subtitle_path) > rank(old.subtitle_path):
            by_video[video_id] = item
    items = sorted(by_video.values(), key=lambda x: (x.published_at or "", x.video_id))
    return items


def inventory_summary(expert: ExpertDefinition, items: Iterable[InventoryItem]) -> dict[str, Any]:
    rows = list(items)
    hashes: dict[str, int] = {}
    for x in rows:
        if x.transcript_sha256:
            hashes[x.transcript_sha256] = hashes.get(x.transcript_sha256, 0) + 1
    dates = sorted(x.published_at for x in rows if x.published_at and re.match(r"^\d{4}-\d{2}-\d{2}", x.published_at))
    return {
        "expert_id": expert.expert_id,
        "display_name": expert.display_name,
        "subtitle_videos": len(rows),
        "expected_subtitle_min": expert.expected_subtitle_min,
        "coverage_pass": len(rows) >= expert.expected_subtitle_min,
        "known_missing_subtitles": expert.known_missing_subtitles,
        "zero_text": sum(1 for x in rows if x.transcript_chars == 0),
        "duplicate_transcript_groups": sum(1 for n in hashes.values() if n > 1),
        "timestamp_verified": sum(1 for x in rows if x.evidence_tier == "TIMESTAMP_VERIFIED"),
        "text_verified": sum(1 for x in rows if x.evidence_tier == "TEXT_VERIFIED"),
        "period_start": dates[0][:10] if dates else None,
        "period_end": dates[-1][:10] if dates else None,
    }


def write_inventory(output_dir: str | Path, expert: ExpertDefinition, items: Iterable[InventoryItem]) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = list(items)
    inv = output / "inventory.jsonl"
    inv.write_text("".join(json.dumps(x.to_dict(), ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    summary = inventory_summary(expert, rows)
    summary["generated_at"] = _iso_now()
    (output / "inventory_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _claim_id(expert_id: str, video_id: str, primitive_key: str, timestamp: str, claim_text: str) -> str:
    payload = f"{expert_id}|{video_id}|{primitive_key}|{timestamp}|{_norm_space(claim_text)}"
    return "ECL-" + sha256(payload.encode("utf-8")).hexdigest()[:24]


def claim_from_llm(expert_id: str, video_id: str, published_at: str | None, raw: dict[str, Any], source_path: str | None = None, evidence_tier: str = "TIMESTAMP_VERIFIED") -> ExpertClaim:
    required = ["speaker", "claim_text", "claim_kind", "evidence_summary", "causal_chain", "premise_metrics", "time_horizon", "related_assets", "related_entities", "topics", "expected_direction", "invalidation_conditions", "primitive_key", "stance", "source_timestamp_start", "source_timestamp_end", "attribution_confidence"]
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(f"claim missing required fields: {missing}")
    primitive_key = _norm_key(raw["primitive_key"])
    if not primitive_key:
        raise ValueError("empty primitive_key")
    start = _norm_space(raw["source_timestamp_start"])
    end = _norm_space(raw["source_timestamp_end"])
    if evidence_tier == "TIMESTAMP_VERIFIED" and (not start or not end):
        raise ValueError("source timestamps required")
    kind = _norm_space(raw["claim_kind"]).upper()
    stance = _norm_space(raw["stance"]).upper()
    attr = _norm_space(raw["attribution_confidence"]).upper()
    if stance not in {"SUPPORT", "OPPOSE", "NEUTRAL"}:
        raise ValueError(f"invalid stance: {stance}")
    if attr not in {"HIGH", "MEDIUM", "LOW"}:
        raise ValueError(f"invalid attribution_confidence: {attr}")
    claim_text = _norm_space(raw["claim_text"])
    if not re.search(r"[가-힣]", claim_text):
        raise ValueError("claim_text must contain Korean reader-facing prose")
    direction_raw = raw.get("expected_direction") or {}
    if isinstance(direction_raw, list):
        direction_raw = {str(x.get("asset") or ""): x.get("direction") for x in direction_raw if isinstance(x, dict) and x.get("asset")}
    return ExpertClaim(
        claim_id=_claim_id(expert_id, video_id, primitive_key, start, claim_text),
        expert_id=expert_id,
        video_id=video_id,
        published_at=published_at,
        speaker=_norm_space(raw["speaker"]),
        claim_text=claim_text,
        claim_kind=kind,
        evidence_summary=_norm_space(raw["evidence_summary"]),
        causal_chain=[_norm_space(x) for x in raw.get("causal_chain") or [] if _norm_space(x)],
        premise_metrics=[_norm_space(x) for x in raw.get("premise_metrics") or [] if _norm_space(x)],
        time_horizon=_norm_space(raw["time_horizon"]).upper(),
        related_assets=[_norm_space(x) for x in raw.get("related_assets") or [] if _norm_space(x)],
        related_entities=[_norm_space(x) for x in raw.get("related_entities") or [] if _norm_space(x)],
        topics=[_norm_space(x) for x in raw.get("topics") or [] if _norm_space(x)],
        expected_direction={str(k): _norm_space(v).upper() for k, v in dict(direction_raw).items()},
        invalidation_conditions=[_norm_space(x) for x in raw.get("invalidation_conditions") or [] if _norm_space(x)],
        primitive_key=primitive_key,
        stance=stance,
        source_timestamp_start=start,
        source_timestamp_end=end,
        attribution_confidence=attr,
        source_path=source_path,
        evidence_tier=evidence_tier,
    )


def load_llm_result(path: str | Path, inventory: dict[str, InventoryItem]) -> list[ExpertClaim]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    expert_id = str(obj["expert_id"])
    video_id = str(obj["video_id"])
    item = inventory.get(video_id)
    published_at = item.published_at if item else None
    source_path = item.subtitle_path if item else None
    evidence_tier = item.evidence_tier if item else "TIMESTAMP_VERIFIED"
    return [claim_from_llm(expert_id, video_id, published_at, raw, source_path, evidence_tier) for raw in obj.get("claims") or []]


def write_claim_ledger(path: str | Path, claims: Iterable[ExpertClaim]) -> None:
    rows = [x.to_dict() for x in claims]
    obj = {"contract": CLAIM_LEDGER_CONTRACT, "generated_at": _iso_now(), "claims": rows}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_claim_ledger(path: str | Path) -> list[ExpertClaim]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("contract") != CLAIM_LEDGER_CONTRACT:
        raise ValueError("invalid claim ledger contract")
    out: list[ExpertClaim] = []
    allowed = {f.name for f in ExpertClaim.__dataclass_fields__.values()}
    for raw in obj.get("claims") or []:
        raw = dict(raw)
        raw.pop("reusable", None)
        out.append(ExpertClaim(**{k: raw[k] for k in raw if k in allowed}))
    return out


def build_primitive_index(claims: Iterable[ExpertClaim]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[ExpertClaim]] = {}
    for c in claims:
        if not c.reusable:
            continue
        groups.setdefault((c.expert_id, c.primitive_key), []).append(c)
    rows: list[dict[str, Any]] = []
    for (expert_id, key), items in sorted(groups.items()):
        items.sort(key=lambda x: (x.published_at or "", x.video_id, x.source_timestamp_start))
        stances = {s: sum(1 for x in items if x.stance == s) for s in ("SUPPORT", "OPPOSE", "NEUTRAL")}
        rows.append({
            "expert_id": expert_id,
            "primitive_key": key,
            "claim_count": len(items),
            "first_seen_at": items[0].published_at,
            "last_seen_at": items[-1].published_at,
            "stance_counts": stances,
            "latest_claim_id": items[-1].claim_id,
            "latest_claim_text": items[-1].claim_text,
            "topics": sorted({t for x in items for t in x.topics}),
            "premise_metrics": sorted({m for x in items for m in x.premise_metrics}),
            "related_assets": sorted({a for x in items for a in x.related_assets}),
            "invalidation_conditions": sorted({v for x in items for v in x.invalidation_conditions}),
            "validation_summary": {state: sum(1 for x in items if x.validation_status == state) for state in VALIDATION_STATES},
        })
    return {"contract": PRIMITIVE_CONTRACT, "generated_at": _iso_now(), "primitives": rows}


def compare_claim_to_history(claim: ExpertClaim, historical: Iterable[ExpertClaim]) -> str:
    matches = [x for x in historical if x.expert_id == claim.expert_id and x.primitive_key == claim.primitive_key and x.claim_id != claim.claim_id]
    if not matches:
        return "NEW"
    latest = sorted(matches, key=lambda x: (x.published_at or "", x.video_id, x.source_timestamp_start))[-1]
    if latest.stance != claim.stance and {latest.stance, claim.stance} <= {"SUPPORT", "OPPOSE"}:
        return "CONTRADICTED"
    if latest.stance == claim.stance:
        if latest.time_horizon != claim.time_horizon or latest.expected_direction != claim.expected_direction or set(latest.invalidation_conditions) != set(claim.invalidation_conditions):
            return "MODIFIED"
        if _norm_space(latest.claim_text) == _norm_space(claim.claim_text):
            return "UNCHANGED"
        return "REINFORCED"
    return "MODIFIED"


def build_validation_queue(claims: Iterable[ExpertClaim]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for c in claims:
        if not c.reusable or c.validation_status != "PENDING":
            continue
        if not c.expected_direction and not c.invalidation_conditions:
            status = "NOT_TESTABLE"
        else:
            status = "PENDING"
        queue.append({
            "claim_id": c.claim_id,
            "expert_id": c.expert_id,
            "video_id": c.video_id,
            "published_at": c.published_at,
            "primitive_key": c.primitive_key,
            "time_horizon": c.time_horizon,
            "expected_direction": c.expected_direction,
            "premise_metrics": c.premise_metrics,
            "invalidation_conditions": c.invalidation_conditions,
            "validation_status": status,
            "point_in_time_required": True,
            "notes": "Use only data available after publication according to the declared horizon; do not backfill knowledge into the original claim."
        })
    return queue


def load_inventory(path: str | Path) -> dict[str, InventoryItem]:
    out: dict[str, InventoryItem] = {}
    allowed = {f.name for f in InventoryItem.__dataclass_fields__.values()}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        values = {k: raw.get(k) for k in allowed if k in raw}
        item = InventoryItem(**values)
        out[item.video_id] = item
    return out


def prepare_batch(inventory: Iterable[InventoryItem], processed_video_ids: set[str], batch_size: int = 8) -> list[dict[str, Any]]:
    pending = [x for x in inventory if x.video_id not in processed_video_ids and x.transcript_chars > 0]
    pending.sort(key=lambda x: (x.published_at or "", x.video_id))
    out: list[dict[str, Any]] = []
    for item in pending[:max(1, int(batch_size))]:
        parsed = parse_transcript(item.subtitle_path)
        out.append({
            "expert_id": item.expert_id,
            "video_id": item.video_id,
            "published_at": item.published_at,
            "title": item.title,
            "channel": item.channel,
            "subtitle_path": item.subtitle_path,
            "transcript": parsed["transcript"],
            "evidence_tier": item.evidence_tier,
            "source_timestamp_policy": "REQUIRED" if item.evidence_tier == "TIMESTAMP_VERIFIED" else "UNAVAILABLE_DO_NOT_INVENT",
        })
    return out
